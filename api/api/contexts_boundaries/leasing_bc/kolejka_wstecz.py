"""Ranking kolejki policzony wstecz (symulacja) dla dni, w których kolejki jeszcze nie było: punkt odniesienia panelu
kierownika (docs/kolejka_panel.md).

Ten sam kod co dzienne zadanie (kolejka_dzienna.py): otwarte zapytania w chwili 05:30 (`otwarte_zapytania`),
aktywni doradcy (`aktywni_doradcy`), wynik modelu z current.yaml przez kontrakt ModelLeadow, EV (leasing_bc/wartosc.py)
i ranking z przydziałem (`ranking_kolejki`). Różnice wobec zadania: bez uzasadnień i bez webhooka (doradcy kolejki nie
widzieli), a p i EV liczymy raz na zapytanie, bo cechy są z chwili utworzenia zapytania i nie zależą od dnia kolejki.
Sygnały LLM tylko z cache: brak sygnału przerywa przebieg (inaczej symulacja różniłaby się od zadania).

Zapis: tabela `kolejka_ranking` z `zrodlo_kolejki = 'symulacja_wstecz'` (adapters/kolejka_ranking.py), bez dni,
które ma już dzienne zadanie.

Domyślne okno: 2026-04-15 – 2026-06-30. Model v3 uczono na zapytaniach sprzed 2025-07 i kalibrowano na 2025-07 –
2026-02, więc 45-dniowe okno otwartych zapytań od 2026-04-15 zaczyna się 2026-03-01, po kalibracji. Sygnały LLM
są w cache dla wszystkich zapytań 2026-03 – 2026-06.

Uruchomienie: `pypyr kolejka_wstecz [od=RRRR-MM-DD do=RRRR-MM-DD]` albo
`cd api && poetry run python -m api.contexts_boundaries.leasing_bc.kolejka_wstecz [od] [do]`.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters import kolejka_ranking
from api.adapters.duckdb_baza import SCIEZKA_BAZY, polaczenie
from api.ai.features.leady.cechy import zbuduj_cechy
from api.ai.features.leady.sygnaly_v1 import wczytaj_sygnaly
from api.ai.lead_model.base import KOLUMNY_WEJSCIA
from api.ai.lead_model.obecny import wczytaj_obecny
from api.contexts_boundaries.leasing_bc.kolejka_dzienna import (
    WIEK_MAKS_DNI,
    aktywni_doradcy,
    otwarte_zapytania,
    ranking_kolejki,
    stan_danych_na,
)
from api.contexts_boundaries.leasing_bc.wartosc import wartosc_oczekiwana

OD = date(2026, 4, 15)
DO = date(2026, 6, 30)

SQL_ZAPYTANIA_OKNA = f"""
SELECT {", ".join(f"l.{k}" for k in KOLUMNY_WEJSCIA)}
FROM crm_leady AS l
WHERE l.utworzono >= $od AND l.utworzono < $do
ORDER BY l.id_leada
"""


class BrakSygnalow(RuntimeError):
    pass


def ev_zapytan(con, od: date, do: date) -> tuple[pd.DataFrame, str]:
    """id_leada, miasto, p, ev dla zapytań, które mogą być otwarte w dniach od–do; wersja modelu."""
    leady = con.execute(
        SQL_ZAPYTANIA_OKNA, {"od": stan_danych_na(od) - timedelta(days=WIEK_MAKS_DNI), "do": stan_danych_na(do)}
    ).df()
    sygnaly = wczytaj_sygnaly(leady)
    brak = int(sygnaly["sygnaly"].isna().sum())
    if brak:
        raise BrakSygnalow(
            f"{brak} zapytań bez sygnałów LLM w cache (uzupełnij: python -m api.ai.features.leady.sygnaly_v1)"
        )
    cechy = zbuduj_cechy(con, sygnaly)
    X = leady[["id_leada", "utworzono"]].merge(cechy, on="id_leada", how="left", validate="1:1")
    obecny = wczytaj_obecny()
    p = np.asarray(obecny.model.predict(X), dtype=float)
    df = leady[["id_leada", "miasto", "utworzono"]].assign(p=p, ev=wartosc_oczekiwana(p, leady))
    return df, obecny.wersja


def ranking_wstecz(con, od: date, do: date, id_przebiegu: str, pomin: set[date] = frozenset()) -> pd.DataFrame:
    """Ranking (kolumny kolejka_ranking.KOLUMNY) dla każdego dnia od–do poza `pomin`."""
    ev, wersja = ev_zapytan(con, od, do)
    czesci = []
    dzien = od
    while dzien <= do:
        if dzien not in pomin:
            stan = stan_danych_na(dzien)
            otwarte = otwarte_zapytania(con, stan)[["id_leada"]]
            e = otwarte.merge(ev, on="id_leada", how="left", validate="1:1")
            if e["ev"].isna().any():
                raise RuntimeError(f"{dzien}: otwarte zapytania bez EV ({int(e['ev'].isna().sum())})")
            # Wariant `model` i ta sama część losowa (ziarno dnia) co dzienne zadanie.
            r = ranking_kolejki(e, aktywni_doradcy(con, dzien), ziarno_dnia=dzien.isoformat()).merge(
                ev[["id_leada", "p", "ev"]], on="id_leada", validate="1:1"
            )
            czesci.append(
                r.assign(
                    data_kolejki=dzien,
                    p=r["p"].round(6),
                    ev_pln=r["ev"].round(2),
                    wersja_modelu=wersja,
                    zrodlo_kolejki="symulacja_wstecz",
                    stan_danych_na=pd.Timestamp(stan),
                    id_przebiegu=id_przebiegu,
                )
            )
        dzien += timedelta(days=1)
    return pd.concat(czesci, ignore_index=True) if czesci else pd.DataFrame(columns=kolejka_ranking.KOLUMNY)


def policz_wstecz(od: date = OD, do: date = DO, sciezka: Path = SCIEZKA_BAZY) -> dict:
    przebieg = f"wstecz-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        pomin = kolejka_ranking.dni_zadania(con)
    with polaczenie(sciezka=sciezka) as con:
        ranking = ranking_wstecz(con, od, do, przebieg, pomin)
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        n = kolejka_ranking.zapisz(con, ranking)
    return {
        "od": od.isoformat(),
        "do": do.isoformat(),
        "dni": int(ranking["data_kolejki"].nunique()) if n else 0,
        "pominiete_dni_zadania": sorted(d.isoformat() for d in pomin if od <= d <= do),
        "wiersze": n,
        "w_kolejkach": int(ranking["id_doradcy"].notna().sum()) if n else 0,
        "id_przebiegu": przebieg,
    }


if __name__ == "__main__":
    argumenty = sys.argv[1:] + ["", ""]  # pypyr podaje puste napisy dla domyślnych od= i do=
    od = date.fromisoformat(argumenty[0]) if argumenty[0] else OD
    do = date.fromisoformat(argumenty[1]) if argumenty[1] else DO
    print(policz_wstecz(od, do))
