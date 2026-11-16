"""Zadanie `telemetra-okna` (Inngest co 10 minut): nowe okna z Telemetry -> magazyn Parquet (adapters/telemetra.py).

Kroki (każdy przez ctx.step.run, po awarii Inngest ponawia tylko krok, który padł):
1. `zakres`: od = najpóźniejsze okno w magazynie albo w eksporcie data/ (późniejsze z nich) minus `ZAKLADKA`
   (okna spóźnione do tylu godzin też trafią do magazynu; powtórzone okna zapis pomija po kluczu), do = teraz
   zaokrąglone w dół do 10 minut. Gdy zaległość jest większa niż `MAKS_ZAKRES`, przebieg bierze tylko pierwsze
   `MAKS_ZAKRES` (kolejne przebiegi nadrabiają po tyle samo). Zdarzenie ręczne może podać `od` i `do` (ISO 8601).
2. `okna-<n>`: pobranie okien z (od; do] kawałkami po `KROK_ZAPYTANIA` i dopisanie do magazynu (idempotentnie po
   id_windy + ts_utc). Krok zwraca liczby: pobrane, nowe, powtórzenia, konflikty, odrzucone.

Stałe ZAKLADKA, MAKS_ZAKRES, KROK_ZAPYTANIA to parametry techniczne przyjęte w tej pracy (nie z danych): eksport nie
ma czasu nadejścia okna, więc nie wiemy, jak bardzo Telemetra się spóźnia (pytanie do użytkownika).
Ręcznie: `cd api && poetry run python -m api.contexts_boundaries.maintenance_bc.telemetria_biezaca [od] [do]`.
"""

import json
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from api.adapters import telemetra

ZAKLADKA = timedelta(hours=1)
MAKS_ZAKRES = timedelta(hours=24)
KROK_ZAPYTANIA = timedelta(hours=6)

Krok = Callable[..., Any]


def _czas(tekst: str) -> datetime:
    t = pd.Timestamp(tekst)
    return (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()


def krok_zakres(
    od: str | None,
    do: str | None,
    katalog_magazynu: str | None,
    teraz: str | None = None,
    katalog_eksportu: str = str(telemetra.KATALOG_EKSPORTU),
) -> dict:
    """Zakres (od; do] tego przebiegu (ISO 8601, UTC)."""
    magazyn = telemetra.MagazynTelemetrii(katalog_magazynu)
    chwila = _czas(teraz) if teraz else telemetra.teraz_utc()
    koniec = _czas(do) if do else pd.Timestamp(chwila).floor(telemetra.OKNO).to_pydatetime()
    ostatnie = [t for t in (magazyn.ostatnie_okno(), telemetra.ostatnie_okno_eksportu(Path(katalog_eksportu))) if t]
    kursor = max(ostatnie) if ostatnie else None
    if od:
        poczatek = _czas(od)
    else:
        poczatek = (pd.Timestamp(kursor) if kursor else pd.Timestamp(koniec)) - ZAKLADKA
        poczatek = poczatek.to_pydatetime()
    zaleglosc = koniec - poczatek
    if not od and not do and zaleglosc > MAKS_ZAKRES:
        koniec = poczatek + MAKS_ZAKRES
    return {
        "od": pd.Timestamp(poczatek).isoformat(),
        "do": pd.Timestamp(koniec).isoformat(),
        "ostatnie_okno": pd.Timestamp(kursor).isoformat() if kursor else None,
        "zaleglosc_h": round(zaleglosc.total_seconds() / 3600, 2),
        "kawalki": [
            [pd.Timestamp(a).isoformat(), pd.Timestamp(b).isoformat()]
            for a, b in telemetra.podziel_zakres(poczatek, koniec, KROK_ZAPYTANIA)
        ],
    }


def krok_okna(od: str, do: str, katalog_magazynu: str | None, zrodlo: telemetra.ZrodloOkien | None = None) -> dict:
    """Pobiera okna z (od; do] i dopisuje je do magazynu."""
    okna = (zrodlo or telemetra.zrodlo_okien()).pobierz_okna(_czas(od), _czas(do))
    wynik = telemetra.MagazynTelemetrii(katalog_magazynu).dopisz(okna)
    return {"od": od, "do": do, **wynik}


def wykonaj_telemetre_okna(
    krok: Krok,
    od: str | None = None,
    do: str | None = None,
    katalog_magazynu: str | None = None,
    zrodlo: telemetra.ZrodloOkien | None = None,
) -> dict:
    """Kolejność kroków; `krok(id, handler, *args)` = ctx.step.run w Inngest (w testach i CLI: wywołanie wprost)."""
    zakres = krok("zakres", krok_zakres, od, do, katalog_magazynu)
    kawalki = [
        krok(f"okna-{i}", krok_okna, a, b, katalog_magazynu, *([zrodlo] if zrodlo else []))
        for i, (a, b) in enumerate(zakres["kawalki"])
    ]
    suma = {k: sum(c[k] for c in kawalki) for k in ("pobrane", "nowe", "powtorzenia", "konflikty", "odrzucone")}
    return {"zakres": zakres, **suma}


def _krok_wprost(id_kroku: str, handler: Callable, *args):
    wynik = handler(*args)
    print(f"[{id_kroku}] {json.dumps(wynik, ensure_ascii=False, default=str)}", flush=True)
    return wynik


if __name__ == "__main__":
    argumenty = [a for a in sys.argv[1:] if a]
    print(f"start {datetime.now(timezone.utc).isoformat()}")
    wykonaj_telemetre_okna(_krok_wprost, *(argumenty + [None, None])[:2])
