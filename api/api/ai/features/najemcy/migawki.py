"""Target listy retencyjnej: tabela migawki_najemcy w domilo.duckdb (czy najemca nie przedłuży umowy rocznej).

Definicja jest w `migawki.sql` obok tego pliku; opis i liczby w `docs/target_najemcy.md`.
Budowa: `pypyr baza` (po przebudowie bazy) albo `cd api && python -m api.ai.features.najemcy.migawki`.
"""

from pathlib import Path

import duckdb

SCIEZKA_SQL = Path(__file__).with_name("migawki.sql")
TABELA = "migawki_najemcy"


def sql_migawki() -> str:
    """Treść zapytania z migawki.sql (bez średnika, do użycia jako podzapytanie)."""
    return SCIEZKA_SQL.read_text(encoding="utf-8").strip().rstrip(";")


def migawki_najemcy(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Relacja: jedna kończąca się umowa roczna (B2C/B2B) na wiersz, z dniem migawki i targetem odejdzie."""
    return con.sql(sql_migawki())


def zbuduj_migawki_najemcy(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę migawki_najemcy; zwraca liczbę wierszy."""
    con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS {sql_migawki()}")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_migawki_najemcy(polaczenie_bazy):,} wierszy".replace(",", " "))
