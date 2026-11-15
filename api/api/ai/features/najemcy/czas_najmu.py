"""Czas najmu do analizy przeżycia: tabela czas_najmu w domilo.duckdb (najem roczny, czas w miesiącach, cenzura).

Definicja jest w `czas_najmu.sql` obok tego pliku; opis i liczby w `docs/przezycie.md`.
Budowa: `pypyr baza` (po przebudowie bazy) albo `cd api && python -m api.ai.features.najemcy.czas_najmu`.
"""

from pathlib import Path

import duckdb

SCIEZKA_SQL = Path(__file__).with_name("czas_najmu.sql")
TABELA = "czas_najmu"


def sql_czas_najmu() -> str:
    """Treść zapytania z czas_najmu.sql (bez średnika, do użycia jako podzapytanie)."""
    return SCIEZKA_SQL.read_text(encoding="utf-8").strip().rstrip(";")


def zbuduj_czas_najmu(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę czas_najmu; zwraca liczbę wierszy."""
    con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS {sql_czas_najmu()}")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_czas_najmu(polaczenie_bazy):,} wierszy".replace(",", " "))
