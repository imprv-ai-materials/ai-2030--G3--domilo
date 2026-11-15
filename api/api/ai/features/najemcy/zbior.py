"""Zbiór do uczenia i oceny listy retencyjnej: migawki_najemcy + cechy_najemcy + score_polityki, z podziałem w czasie.

Podział według miesiąca końca umowy (`miesiac_konca`):
- trening: końce umów 2023-03 – 2025-12;
- test: końce umów 2026-04 – 2026-09 (migawki 2026-01-31 – 2026-08-01);
- końce 2026-01 – 2026-03 nie wchodzą do żadnego zbioru. Dzięki tej przerwie wynik każdej umowy treningowej
  (najpóźniej data_do 2025-12-31 + 30 dni okna przeprowadzki = 2026-01-30) jest znany przed pierwszą migawką testu.
`score_polityki` (retencja_decyzje) służy tylko jako punkt odniesienia; model nie może go używać
(churn_model/base.py, KOLUMNY_ZAKAZANE).
"""

import duckdb
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
