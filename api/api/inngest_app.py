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

`lista-retencyjna` (w każdy poniedziałek o 07:00 czasu warszawskiego albo na zdarzenie `domilo/lista.retencyjna`,
opcjonalnie z `data.data_listy` = "RRRR-MM-DD" i `data.kampania`): kroki z
contexts_boundaries/retention_bc/lista_retencyjna.py, każdy przez ctx.step.run: parametry -> umowy-w-oknie (koniec
umowy za 60–66 dni) -> ryzyko-i-czas -> uplift-i-akcja (modele z churn_model/current.yaml) -> grupy-kampanii (hash
id_umowy i nazwy kampanii) -> zapis-listy (tabela lista_retencyjna, zastępuje dzień listy). Opis:
docs/lista_retencyjna.md.

Alerty o awariach wind — trzy osobne funkcje (każda ze swoim harmonogramem, ponowieniami i zdarzeniem ręcznym;
opis: docs/b4_ryzyko_dzienne.md):
- `telemetra-okna` (co 10 minut albo `domilo/telemetra.okna` z opcjonalnymi `data.od`, `data.do` w ISO 8601):
  nowe okna z Telemetry (adapters/telemetra.py) -> magazyn Parquet, idempotentnie po (id_windy, ts_utc); kroki
  zakres -> okna-<n> (contexts_boundaries/maintenance_bc/telemetria_biezaca.py).
- `cechy-wind` (05:50 albo `domilo/windy.cechy` z opcjonalnym `data.dzien`): cechy dnia z tych samych plików SQL co
  trening (features/windy/cechy.py, tsfresh_cechy.py) na eksporcie + magazynie; kroki parametry -> kompletnosc
  (czeka na okno 05:50 do 05:58) -> cechy (maintenance_bc/cechy_dzienne.py).
- `ryzyko-wind` (06:00 albo `domilo/windy.ryzyko` z opcjonalnym `data.dzien`): ryzyko aktywną wersją z
  failure_model/current.yaml, reguła alarmu z maintenance_bc/ (poniedziałek, 3 windy, przerwa 7 dni) i zgłoszenie
  w Serwisowniku osobnym krokiem na alarm; kroki parametry -> ryzyko -> zapis-ryzyka -> alarmy ->
  serwisownik-<id_windy> (maintenance_bc/ryzyko_dzienne.py).
"""

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import inngest
from api.contexts_boundaries.leasing_bc import kolejka_dzienna
from api.contexts_boundaries.maintenance_bc import cechy_dzienne, ryzyko_dzienne, telemetria_biezaca
from api.contexts_boundaries.retention_bc import lista_retencyjna
from api.contexts_boundaries.valuation_bc import nocne

ZDARZENIE_RECZNE = "domilo/wyceny.nocne"
HARMONOGRAM = "TZ=Europe/Warsaw 0 2 * * *"
ZDARZENIE_KOLEJKI = "domilo/kolejka.doradcow"
HARMONOGRAM_KOLEJKI = "TZ=Europe/Warsaw 30 5 * * *"
ZDARZENIE_LISTY = "domilo/lista.retencyjna"
HARMONOGRAM_LISTY = "TZ=Europe/Warsaw 0 7 * * 1"  # poniedziałek 07:00, po kolejce doradców (05:30)
ZDARZENIE_OKIEN = "domilo/telemetra.okna"
HARMONOGRAM_OKIEN = "*/10 * * * *"  # co 10 minut (okno Telemetry = 10 min)
ZDARZENIE_CECH_WIND = "domilo/windy.cechy"
HARMONOGRAM_CECH_WIND = "TZ=Europe/Warsaw 50 5 * * *"  # 05:50 = odcięcie cech (features/windy/cechy.py)
ZDARZENIE_RYZYKA_WIND = "domilo/windy.ryzyko"
HARMONOGRAM_RYZYKA_WIND = "TZ=Europe/Warsaw 0 6 * * *"  # 06:00 = moment predykcji (dni_wind)

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


def parametry_listy_ze_zdarzenia(dane: dict | None) -> tuple[str | None, str | None]:
    """(`data_listy`, `kampania`) ze zdarzenia ręcznego; dla harmonogramu (None, None) = dziś, kampania z daty."""
    dane = dane or {}
    data, kampania = dane.get("data_listy"), dane.get("kampania")
    return (str(data) if data else None, str(kampania) if kampania else None)


@klient_inngest.create_function(
    fn_id="lista-retencyjna",
    name="Lista retencyjna: umowy za 60–66 dni, ryzyko, czas, uplift, akcja, grupa kampanii",
    trigger=[inngest.TriggerCron(cron=HARMONOGRAM_LISTY), inngest.TriggerEvent(event=ZDARZENIE_LISTY)],
    concurrency=[inngest.Concurrency(limit=1)],
    retries=3,
)
def lista_retencyjna_tygodniowa(ctx: inngest.ContextSync) -> dict:
    data_listy, kampania = parametry_listy_ze_zdarzenia(ctx.event.data if ctx.event is not None else None)
    return lista_retencyjna.wykonaj_liste_retencyjna(ctx.step.run, ctx.run_id, data_listy, kampania)


def _pole(dane: dict | None, nazwa: str) -> str | None:
    """Pole zdarzenia ręcznego jako tekst; dla harmonogramu (zdarzenie inngest/scheduled.timer) None."""
    wartosc = (dane or {}).get(nazwa)
    return str(wartosc) if wartosc else None


def _dane(ctx: inngest.ContextSync) -> dict | None:
    return ctx.event.data if ctx.event is not None else None


@klient_inngest.create_function(
    fn_id="telemetra-okna",
    name="Telemetra: nowe okna wind do magazynu Parquet (idempotentnie po windzie i ts_utc)",
    trigger=[inngest.TriggerCron(cron=HARMONOGRAM_OKIEN), inngest.TriggerEvent(event=ZDARZENIE_OKIEN)],
    concurrency=[inngest.Concurrency(limit=1)],
    retries=3,
)
def telemetra_okna(ctx: inngest.ContextSync) -> dict:
    dane = _dane(ctx)
    return telemetria_biezaca.wykonaj_telemetre_okna(ctx.step.run, _pole(dane, "od"), _pole(dane, "do"))


@klient_inngest.create_function(
    fn_id="cechy-wind",
    name="Cechy wind na dzień oceny (05:50, te same pliki SQL co trening)",
    trigger=[inngest.TriggerCron(cron=HARMONOGRAM_CECH_WIND), inngest.TriggerEvent(event=ZDARZENIE_CECH_WIND)],
    concurrency=[inngest.Concurrency(limit=1)],
    retries=10,  # krok kompletnosc ponawia co minutę, czekając na okno 05:50 (do 05:58)
)
def cechy_wind(ctx: inngest.ContextSync) -> dict:
    return cechy_dzienne.wykonaj_cechy_wind(ctx.step.run, _pole(_dane(ctx), "dzien"))


@klient_inngest.create_function(
    fn_id="ryzyko-wind",
    name="Ryzyko awarii wind (06:00): model z current.yaml, reguła alarmu, zgłoszenia w Serwisowniku",
    trigger=[inngest.TriggerCron(cron=HARMONOGRAM_RYZYKA_WIND), inngest.TriggerEvent(event=ZDARZENIE_RYZYKA_WIND)],
    concurrency=[inngest.Concurrency(limit=1)],
    retries=15,  # krok ryzyko ponawia co 2 minuty, czekając na cechy dnia (do 06:30)
)
def ryzyko_wind(ctx: inngest.ContextSync) -> dict:
    return ryzyko_dzienne.wykonaj_ryzyko_wind(ctx.step.run, ctx.run_id, _pole(_dane(ctx), "dzien"))


FUNKCJE = [wyceny_nocne, kolejka_doradcow, lista_retencyjna_tygodniowa, telemetra_okna, cechy_wind, ryzyko_wind]
