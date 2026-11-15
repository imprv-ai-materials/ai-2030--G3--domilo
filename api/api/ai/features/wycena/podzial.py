"""Podział czasowy transakcji RCN (trening / walidacja / test) dla modelu wyceny.

Definicja jest w `podzial.sql` obok tego pliku; opis i liczności w `docs/b1_dane.md`.
"""

from pathlib import Path

import duckdb

SCIEZKA_PODZIALU = Path(__file__).with_name("podzial.sql")
ZBIORY = ("trening", "walidacja", "test")


def sql_podzialu() -> str:
    """Treść zapytania z podzial.sql (bez średnika, do użycia jako podzapytanie)."""
    return SCIEZKA_PODZIALU.read_text(encoding="utf-8").strip().rstrip(";")


def podzial(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Relacja: id_transakcji, data_aktu, data_publikacji_rejestru, zbior — tylko transakcje objęte podziałem."""
    return con.sql(sql_podzialu())
