"""Funkcje Inngest Domilo: nocna wycena portfela (serwowane przez main.py pod /api/inngest).

Serwer Inngest z devcontainera (compose.yaml) szuka funkcji pod http://app:8101/api/inngest; w kontenerze zmienna
INNGEST_DEV wskazuje serwer deweloperski, więc nie trzeba klucza podpisu. Tryb produkcyjny: INNGEST_PRODUKCJA=1
(wtedy SDK wymaga INNGEST_SIGNING_KEY).

`wyceny-nocne` (codziennie o 02:00 czasu warszawskiego albo na zdarzenie `domilo/wyceny.nocne`):
1. czas-przebiegu: jeden znacznik czasu dla całego przebiegu (zapamiętany przez Inngest przy ponowieniach);
2. wycena-lokali: 7 200 lokali Domilo -> wyceny_historia;
3. wycena-nowych-ofert: oferty z ostatnich 30 dni danych, jeszcze niewycenione -> wyceny_historia;
4. raport-kwartalny: docs/bank/raport_RRRRQn.md za ostatni pełny kwartał, jeśli jeszcze go nie ma.
Każdy krok jest ponawiany osobno, a zapis do historii jest idempotentny (id przebiegu = run_id Inngest).

`kolejka-doradcow` (codziennie o 05:30 czasu warszawskiego albo na zdarzenie `domilo/kolejka.doradcow`, opcjonalnie
z `data.data_kolejki` = "RRRR-MM-DD"): kroki z contexts_boundaries/leasing_bc/kolejka_dzienna.py, każdy przez
ctx.step.run: parametry -> otwarte-zapytania -> sygnaly-llm -> cechy -> wynik-modelu -> ev -> kolejki -> uzasadnienia
-> zapis-kolejki -> webhook-crm-<id_doradcy> (osobny krok na doradcę). Webhook jest idempotentny po
(id_leada, data_kolejki) (adapters/crm_lejek.py). Opis: docs/kolejka_dzienna.md.
"""

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import inngest
from api.contexts_boundaries.leasing_bc import kolejka_dzienna
from api.contexts_boundaries.valuation_bc import nocne

ZDARZENIE_RECZNE = "domilo/wyceny.nocne"
HARMONOGRAM = "TZ=Europe/Warsaw 0 2 * * *"
ZDARZENIE_KOLEJKI = "domilo/kolejka.doradcow"
HARMONOGRAM_KOLEJKI = "TZ=Europe/Warsaw 30 5 * * *"

klient_inngest = inngest.Inngest(app_id="domilo", is_production=os.environ.get("INNGEST_PRODUKCJA") == "1")


def _teraz_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def wykonaj_wyceny_nocne(krok: Callable[..., Any], id_przebiegu: str) -> dict:
    """Kolejność kroków przebiegu; `krok(id, handler, *args)` = ctx.step.run w Inngest (w testach: wywołanie wprost)."""
    czas = krok("czas-przebiegu", _teraz_iso)
    lokale = krok("wycena-lokali", nocne.przebieg_lokali, id_przebiegu, czas)
    oferty = krok("wycena-nowych-ofert", nocne.przebieg_ofert, id_przebiegu, czas)
    raport = krok("raport-kwartalny", nocne.przebieg_raportu, czas)
    return {"id_przebiegu": id_przebiegu, "czas": czas, "lokale": lokale, "oferty": oferty, "raport": raport}


@klient_inngest.create_function(
    fn_id="wyceny-nocne",
    name="Wyceny nocne: lokale Domilo, nowe oferty, raport dla banku",
    trigger=[inngest.TriggerCron(cron=HARMONOGRAM), inngest.TriggerEvent(event=ZDARZENIE_RECZNE)],
    concurrency=[inngest.Concurrency(limit=1)],
    retries=2,
)
def wyceny_nocne(ctx: inngest.ContextSync) -> dict:
    return wykonaj_wyceny_nocne(ctx.step.run, ctx.run_id)


def data_kolejki_ze_zdarzenia(dane: dict | None) -> str | None:
    """`data_kolejki` ze zdarzenia ręcznego; dla harmonogramu (zdarzenie inngest/scheduled.timer) None = dziś."""
    data = (dane or {}).get("data_kolejki")
    return str(data) if data else None


@klient_inngest.create_function(
    fn_id="kolejka-doradcow",
    name="Kolejka doradców: wynik modelu, EV, uzasadnienia, webhook do CRM",
    trigger=[inngest.TriggerCron(cron=HARMONOGRAM_KOLEJKI), inngest.TriggerEvent(event=ZDARZENIE_KOLEJKI)],
    concurrency=[inngest.Concurrency(limit=1)],
    retries=3,
)
def kolejka_doradcow(ctx: inngest.ContextSync) -> dict:
    dane = ctx.event.data if ctx.event is not None else None
    return kolejka_dzienna.wykonaj_kolejke_doradcow(ctx.step.run, ctx.run_id, data_kolejki_ze_zdarzenia(dane))


FUNKCJE = [wyceny_nocne, kolejka_doradcow]
