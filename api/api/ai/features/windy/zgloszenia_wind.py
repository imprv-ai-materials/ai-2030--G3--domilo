"""Zgłoszenia Serwisownika dotyczące wind: tabela zgloszenia_wind w domilo.duckdb (z ustaloną windą).

Definicja w `zgloszenia_wind.sql` obok tego pliku; opis i liczby w `docs/b4_historia_awarii.md`.
To materiał do zdefiniowania targetu modelu awarii wind, a nie sam target: kategoria „awaria” w Serwisowniku
nie pokrywa się z faktyczną awarią (patrz raport).
Budowa: `pypyr baza` (po przebudowie bazy) albo `cd api && python -m api.ai.features.windy.zgloszenia_wind`.
"""

from pathlib import Path

import duckdb

SCIEZKA_SQL = Path(__file__).with_name("zgloszenia_wind.sql")
TABELA = "zgloszenia_wind"


def sql_zgloszenia_wind() -> str:
    """Treść zapytania z zgloszenia_wind.sql (bez średnika, do użycia jako podzapytanie)."""
    return SCIEZKA_SQL.read_text(encoding="utf-8").strip().rstrip(";")


def zgloszenia_wind(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Relacja: jedno zgłoszenie dotyczące windy na wiersz, z id_windy i sposobem jej ustalenia."""
    return con.sql(sql_zgloszenia_wind())


def zbuduj_zgloszenia_wind(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę zgloszenia_wind; zwraca liczbę wierszy."""
    con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS {sql_zgloszenia_wind()}")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_zgloszenia_wind(polaczenie_bazy):,} wierszy".replace(",", " "))
