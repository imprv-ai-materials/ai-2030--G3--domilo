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
"""

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import inngest
from api.contexts_boundaries.valuation_bc import nocne

ZDARZENIE_RECZNE = "domilo/wyceny.nocne"
HARMONOGRAM = "TZ=Europe/Warsaw 0 2 * * *"

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


FUNKCJE = [wyceny_nocne]
