"""Cechy v1 (features/najemcy/sql/*.sql) przeliczone na początek każdego okresu umowy (model v2_przezycie_cox).

Te same pliki SQL co dla migawek (cechy.py), ale zamiast tabeli migawki_najemcy czytają tymczasową tabelę okresów
z `okresy_umow.sql`, w której data_migawki = data_od okresu. Cechy liczone są więc tylko ze zdarzeń sprzed początku
okresu. Tabelę tymczasową tworzymy na połączeniu (także tylko do odczytu) i usuwamy po użyciu.
"""

from pathlib import Path

import duckdb
import pandas as pd
from api.ai.features.najemcy.cechy import KATEGORIE, RODZINY, sql_rodziny

SCIEZKA_SQL = Path(__file__).with_name("okresy_umow.sql")
TABELA_TYMCZASOWA = "okresy_umow_tmp"
KONIEC_DANYCH = "2026-09-30"


def sql_okresow() -> str:
    return SCIEZKA_SQL.read_text(encoding="utf-8").strip().rstrip(";")


def okresy_umow(con: duckdb.DuckDBPyConnection, koniec_obserwacji: str = KONIEC_DANYCH) -> pd.DataFrame:
    """Okresy umów (B2C / B2B) z czasem i zdarzeniem liczonymi do końca obserwacji (włącznie)."""
    okresy = con.execute(sql_okresow(), {"koniec_obserwacji": koniec_obserwacji}).df()
    for k in ("data_migawki", "data_od", "data_do", "data_wprowadzenia", "data_wyprowadzenia", "koniec_w_okresie"):
        okresy[k] = pd.to_datetime(okresy[k])
    return okresy


def cechy_okresow(con: duckdb.DuckDBPyConnection, okresy: pd.DataFrame) -> pd.DataFrame:
    """Cechy wszystkich rodzin na data_od każdego okresu (id_umowy + kolumny cech), liczby jako float64."""
    kolumny = ["id_umowy", "id_najmu", "id_najemcy", "id_lokalu", "linia", "nr_okresu", "miesiecy_umowy"]
    wejscie = okresy[kolumny].copy()
    wejscie["data_migawki"] = pd.to_datetime(okresy["data_migawki"]).dt.date
    con.register("okresy_df", wejscie)
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE {TABELA_TYMCZASOWA} AS SELECT * FROM okresy_df")
        czesci = [
            con.execute(sql_rodziny(r).replace("migawki_najemcy", TABELA_TYMCZASOWA)).df().set_index("id_umowy")
            for r in RODZINY
        ]
    finally:
        con.execute(f"DROP TABLE IF EXISTS {TABELA_TYMCZASOWA}")
        con.unregister("okresy_df")
    cechy = pd.concat(czesci, axis=1, join="outer")
    if not cechy.index.is_unique:
        raise ValueError("Cechy okresów: id_umowy nie jest unikalne")
    liczbowe = [k for k in cechy.columns if k not in KATEGORIE and k != "podobne_poziom"]
    cechy[liczbowe] = cechy[liczbowe].astype("float64")
    return cechy.reset_index()


def zbior_okresow(con: duckdb.DuckDBPyConnection, koniec_obserwacji: str = KONIEC_DANYCH) -> pd.DataFrame:
    """Okresy + cechy na ich początek; `linia` z okresu (cecha z rodziny umowa jest taka sama)."""
    okresy = okresy_umow(con, koniec_obserwacji)
    cechy = cechy_okresow(con, okresy).drop(columns=["linia", "miesiecy_umowy", "nr_okresu"])
    return okresy.merge(cechy, on="id_umowy", how="left", validate="1:1")
