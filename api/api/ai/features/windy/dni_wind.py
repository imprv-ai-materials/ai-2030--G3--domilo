"""Target modelu awarii wind: tabela dni_wind w domilo.duckdb (winda × dzień, awaria_7d).

Definicja w `dni_wind.sql` obok tego pliku; okno, przypadki brzegowe i liczby w `docs/b4_target.md`.
Wymaga tabeli `awarie_odtworzone` (krok wcześniej w `pypyr baza`); bez niej krok jest pomijany.
Budowa: `pypyr baza` albo `cd api && python -m api.ai.features.windy.dni_wind`.
"""

import sys
from pathlib import Path

import duckdb

SCIEZKA_SQL = Path(__file__).with_name("dni_wind.sql")
TABELA = "dni_wind"


def sql_dni_wind() -> str:
    """Treść zapytania z dni_wind.sql (bez średnika, do użycia jako podzapytanie)."""
    return SCIEZKA_SQL.read_text(encoding="utf-8").strip().rstrip(";")


def zbuduj_dni_wind(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę dni_wind; zwraca liczbę wierszy."""
    con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS {sql_dni_wind()}")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        jest = polaczenie_bazy.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'awarie_odtworzone'"
        ).fetchone()[0]
        if not jest:
            print(f"{TABELA}: pomijam, brak tabeli awarie_odtworzone")
            sys.exit(0)
        print(f"{TABELA}: {zbuduj_dni_wind(polaczenie_bazy):,} wierszy".replace(",", " "))
