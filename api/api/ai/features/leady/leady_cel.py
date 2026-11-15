"""Target kolejki zapytań: tabela leady_cel w domilo.duckdb (umowa w ciągu 45 dni od zapytania).

Definicja jest w `leady_cel.sql` obok tego pliku; opis i liczby w `docs/kolejka_target.md`.
Budowa: `pypyr baza` (po przebudowie bazy) albo `cd api && python -m api.ai.features.leady.leady_cel`.
"""

from pathlib import Path

import duckdb

SCIEZKA_SQL = Path(__file__).with_name("leady_cel.sql")
TABELA = "leady_cel"


def sql_leady_cel() -> str:
    """Treść zapytania z leady_cel.sql (bez średnika, do użycia jako podzapytanie)."""
    return SCIEZKA_SQL.read_text(encoding="utf-8").strip().rstrip(";")


def leady_cel(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Relacja: jedno zapytanie z crm_leady na wiersz, z umowa_45d, cenzurowaniem i flagami obsługi."""
    return con.sql(sql_leady_cel())


def zbuduj_leady_cel(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę leady_cel; zwraca liczbę wierszy."""
    con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS {sql_leady_cel()}")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_leady_cel(polaczenie_bazy):,} wierszy".replace(",", " "))
