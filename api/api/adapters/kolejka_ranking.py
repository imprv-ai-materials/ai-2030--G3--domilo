"""Pełny ranking dzienny kolejki w domilo.duckdb: tabela `kolejka_ranking` (źródło metryk panelu kierownika, dbt).

Jeden wiersz = jedno otwarte zapytanie w jednym dniu kolejki: miejsce w rankingu swojego miasta (według EV), p, EV,
a dla zapytań w kolejkach doradców także id_doradcy i pozycja. `kolejka_doradcow` to tylko pozycje wysłane do CRM;
górny decyl i adopcja wymagają całego rankingu, więc zapisujemy go osobno.

`zrodlo_kolejki`:
- `zadanie`: dzienne zadanie kolejka-doradcow (inngest_app.py), kolejka trafiła do CRM;
- `symulacja_wstecz`: ranking policzony wstecz tym samym kodem (leasing_bc/kolejka_wstecz.py) dla dni, w których
  kolejki jeszcze nie było; doradcy go nie widzieli, więc metryki z tych dni to punkt odniesienia przed wdrożeniem.
Zapis zastępuje cały dzień. Symulacja nie nadpisuje dni z `zadanie`. Tabela nie pochodzi z data/, więc przebudowa
bazy (duckdb_baza.zbuduj_baze) przenosi ją ze starego pliku.
"""

from datetime import date

import duckdb
import pandas as pd

TABELA = "kolejka_ranking"
ZRODLA = ("zadanie", "symulacja_wstecz")
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    data_kolejki DATE NOT NULL,
    id_leada VARCHAR NOT NULL,
    miasto VARCHAR NOT NULL,
    ranga INTEGER NOT NULL CHECK (ranga >= 1),
    otwarte_w_miescie INTEGER NOT NULL CHECK (otwarte_w_miescie >= ranga),
    p DOUBLE NOT NULL,
    ev_pln DOUBLE NOT NULL,
    id_doradcy VARCHAR,
    pozycja INTEGER CHECK (pozycja >= 1),
    wersja_modelu VARCHAR NOT NULL,
    zrodlo_kolejki VARCHAR NOT NULL CHECK (zrodlo_kolejki IN {ZRODLA}),
    stan_danych_na TIMESTAMPTZ NOT NULL,
    id_przebiegu VARCHAR NOT NULL,
    PRIMARY KEY (data_kolejki, id_leada)
)
"""
KOLUMNY = (
    "data_kolejki",
    "id_leada",
    "miasto",
    "ranga",
    "otwarte_w_miescie",
    "p",
    "ev_pln",
    "id_doradcy",
    "pozycja",
    "wersja_modelu",
    "zrodlo_kolejki",
    "stan_danych_na",
    "id_przebiegu",
)


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_TABELI)


def dni_zadania(con: duckdb.DuckDBPyConnection) -> set[date]:
    """Dni z rankingiem z dziennego zadania (tych symulacja nie nadpisuje)."""
    utworz(con)
    rows = con.execute(f"SELECT DISTINCT data_kolejki FROM {TABELA} WHERE zrodlo_kolejki = 'zadanie'").fetchall()
    return {r[0] for r in rows}


def zapisz(con: duckdb.DuckDBPyConnection, ranking: pd.DataFrame) -> int:
    """Zastępuje dni obecne w `ranking` (kolumny KOLUMNY); zwraca liczbę wierszy."""
    utworz(con)
    df = ranking[list(KOLUMNY)].copy()
    df["data_kolejki"] = pd.to_datetime(df["data_kolejki"]).dt.date
    df["pozycja"] = df["pozycja"].astype("Int64")
    dni = sorted(set(df["data_kolejki"]))
    con.execute("BEGIN TRANSACTION")
    try:
        con.register("_ranking_nowy", df)
        con.execute(f"DELETE FROM {TABELA} WHERE data_kolejki IN (SELECT DISTINCT data_kolejki FROM _ranking_nowy)")
        con.execute(f"INSERT INTO {TABELA} ({', '.join(KOLUMNY)}) SELECT {', '.join(KOLUMNY)} FROM _ranking_nowy")
        con.unregister("_ranking_nowy")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return len(df) if dni else 0
