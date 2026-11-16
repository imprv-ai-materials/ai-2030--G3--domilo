"""Zbiór do uczenia i oceny listy retencyjnej: migawki_najemcy + cechy_najemcy + score_polityki, z podziałem w czasie.

Podział według miesiąca końca umowy (`miesiac_konca`):
- trening: końce umów 2023-03 – 2025-12;
- test: końce umów 2026-04 – 2026-09 (migawki 2026-01-31 – 2026-08-01);
- końce 2026-01 – 2026-03 nie wchodzą do żadnego zbioru. Dzięki tej przerwie wynik każdej umowy treningowej
  (najpóźniej data_do 2025-12-31 + 30 dni okna przeprowadzki = 2026-01-30) jest znany przed pierwszą migawką testu.
`score_polityki` (retencja_decyzje) służy tylko jako punkt odniesienia; model nie może go używać
(churn_model/base.py, KOLUMNY_ZAKAZANE).

Podział dla modeli uplift (`podziel_uplift`): tylko losowy test oferty `retencja_decyzje.okres = 'test_2025'`
(końce umów 2025-07 – 2026-03, oferta 50/50, docs/test_rabatu_2025.md). Część zależy wyłącznie od `id_umowy`:
md5(SOL_UPLIFT + id_umowy) jako liczba z [0, 1), poniżej 0,70 = trening, reszta = test. Ta sama umowa trafia zawsze
do tej samej części, niezależnie od kolejności wierszy i od tego, co jeszcze jest w zbiorze.
"""

import hashlib

import duckdb
import numpy as np
import pandas as pd
from api.ai.features.najemcy.cechy import zbuduj_cechy

TRENING_DO = pd.Timestamp("2025-12-01")
TEST_OD = pd.Timestamp("2026-04-01")
TEST_DO = pd.Timestamp("2026-09-01")
OPIS = {
    "trening": "umowy z końcem 2023-03 – 2025-12 (miesiac_konca)",
    "test": "umowy z końcem 2026-04 – 2026-09 (miesiac_konca)",
    "przerwa": "końce 2026-01 – 2026-03 poza zbiorami (wynik treningu znany przed pierwszą migawką testu)",
}

SQL_MIGAWKI = """
SELECT
    m.id_umowy, m.linia AS linia_umowy, m.data_do, m.data_migawki, m.miesiac_konca,
    m.wypowiedzenie_przed_migawka, m.odejdzie,
    r.score_polityki, r.okres, r.grupa
FROM migawki_najemcy AS m
LEFT JOIN retencja_decyzje AS r USING (id_umowy)
"""

OKRES_UPLIFT = "test_2025"
FRAKCJA_TRENINGU_UPLIFT = 0.70
SOL_UPLIFT = "uplift_test_2025:"


def czesc_uplift(id_umowy: pd.Series) -> pd.Series:
    """'trening' (ok. 70%) albo 'test' dla każdej umowy, deterministycznie z md5(SOL_UPLIFT + id_umowy)."""

    def u(i: str) -> float:
        return int(hashlib.md5((SOL_UPLIFT + i).encode("utf-8")).hexdigest()[:13], 16) / 16**13

    los = id_umowy.astype(str).map(u)
    return pd.Series(np.where(los < FRAKCJA_TRENINGU_UPLIFT, "trening", "test"), index=id_umowy.index)


def podziel_uplift(zbior: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Umowy z okresu test_2025 podzielone 70 / 30 według id_umowy (czesc_uplift)."""
    t = zbior[zbior["okres"] == OKRES_UPLIFT]
    czesc = czesc_uplift(t["id_umowy"])
    return {nazwa: t[czesc == nazwa].reset_index(drop=True) for nazwa in ("trening", "test")}


def wczytaj_zbior(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Jedna umowa na wiersz: kolumny migawki, target, punkt odniesienia i cechy (KOLUMNY_CECH)."""
    migawki = con.execute(SQL_MIGAWKI).df()
    cechy = zbuduj_cechy(con)
    zbior = migawki.merge(cechy, on="id_umowy", how="left", validate="1:1")
    for k in ("data_do", "data_migawki", "miesiac_konca"):
        zbior[k] = pd.to_datetime(zbior[k])
    return zbior


def podziel(zbior: pd.DataFrame) -> dict[str, pd.DataFrame]:
    mies = pd.to_datetime(zbior["miesiac_konca"])
    return {
        "trening": zbior[mies <= TRENING_DO].reset_index(drop=True),
        "test": zbior[(mies >= TEST_OD) & (mies <= TEST_DO)].reset_index(drop=True),
    }
