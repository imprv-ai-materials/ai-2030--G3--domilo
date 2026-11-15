"""Kolejki doradców w domilo.duckdb: tabela `kolejka_doradcow` (zadanie kolejka-doradcow zapisuje, API i CRM czytają).

Jeden wiersz = jedno zapytanie w kolejce jednego doradcy w jednym dniu (`data_kolejki`). Klucz: (data_kolejki,
id_leada), czyli to samo, co klucz idempotencji webhooka do CRM (adapters/crm_lejek.py): zapytanie trafia danego
dnia najwyżej do jednego doradcy. Zapis zastępuje cały dzień, więc ponowienie kroku i drugi przebieg tego samego dnia
nie dublują wierszy. Tabela nie pochodzi z data/, więc przebudowa bazy (duckdb_baza.zbuduj_baze) przenosi ją ze
starego pliku.

`pozycje` to jedyne miejsce, które składa kolejkę doradcy z tabeli: używa go webhook do CRM i `GET /leads/next`,
więc oba widzą tę samą kolejkę.
"""

from datetime import date

import duckdb
import pandas as pd

TABELA = "kolejka_doradcow"
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    data_kolejki DATE NOT NULL,
    id_doradcy VARCHAR NOT NULL,
    miasto VARCHAR NOT NULL,
    pozycja INTEGER NOT NULL CHECK (pozycja >= 1),
    id_leada VARCHAR NOT NULL,
    utworzono TIMESTAMPTZ NOT NULL,
    status_crm VARCHAR NOT NULL,
    zrodlo VARCHAR,
    linia_pref VARCHAR,
    liczba_lokali DOUBLE NOT NULL,
    p DOUBLE NOT NULL,
    ev_pln DOUBLE NOT NULL,
    uzasadnienie VARCHAR NOT NULL,
    zrodlo_uzasadnienia VARCHAR NOT NULL,
    wersja_modelu VARCHAR NOT NULL,
    stan_danych_na TIMESTAMPTZ NOT NULL,
    id_przebiegu VARCHAR NOT NULL,
    PRIMARY KEY (data_kolejki, id_leada),
    UNIQUE (data_kolejki, id_doradcy, pozycja)
)
"""
KOLUMNY = (
    "data_kolejki",
    "id_doradcy",
    "miasto",
    "pozycja",
    "id_leada",
    "utworzono",
    "status_crm",
    "zrodlo",
    "linia_pref",
    "liczba_lokali",
    "p",
    "ev_pln",
    "uzasadnienie",
    "zrodlo_uzasadnienia",
    "wersja_modelu",
    "stan_danych_na",
    "id_przebiegu",
)
# Pola kolejki wysyłane do CRM i oddawane przez API. Bez id_przebiegu: dwa przebiegi tego samego dnia mają dać ten
# sam stan w CRM.
POLA_POZYCJI = (
    "data_kolejki",
    "id_doradcy",
    "miasto",
    "pozycja",
    "id_leada",
    "utworzono",
    "status_crm",
    "zrodlo",
    "linia_pref",
    "liczba_lokali",
    "p",
    "ev_pln",
    "uzasadnienie",
    "zrodlo_uzasadnienia",
    "wersja_modelu",
    "stan_danych_na",
)


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_TABELI)


def zapisz(con: duckdb.DuckDBPyConnection, data_kolejki: date, kolejka: pd.DataFrame) -> int:
    """Zastępuje kolejki dnia `data_kolejki` wierszami `kolejka` (kolumny KOLUMNY); zwraca liczbę wierszy."""
    utworz(con)
    df = kolejka[list(KOLUMNY)]
    if (pd.to_datetime(df["data_kolejki"]).dt.date != data_kolejki).any():
        raise ValueError(f"kolejka_doradcow.zapisz: wiersze spoza dnia {data_kolejki}")
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM {TABELA} WHERE data_kolejki = ?", [data_kolejki])
        con.register("_kolejka_nowa", df)
        con.execute(f"INSERT INTO {TABELA} ({', '.join(KOLUMNY)}) SELECT {', '.join(KOLUMNY)} FROM _kolejka_nowa")
        con.unregister("_kolejka_nowa")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return len(df)


def _istnieje(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(
        con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = ? AND schema_name = 'main'", [TABELA]
        ).fetchone()[0]
    )


def ostatnia_data(con: duckdb.DuckDBPyConnection, id_doradcy: str) -> date | None:
    """Najnowszy dzień, dla którego doradca ma kolejkę (None, gdy żadnej)."""
    if not _istnieje(con):
        return None
    return con.execute(f"SELECT max(data_kolejki) FROM {TABELA} WHERE id_doradcy = ?", [id_doradcy]).fetchone()[0]


def doradcy_dnia(con: duckdb.DuckDBPyConnection, data_kolejki: date) -> list[str]:
    if not _istnieje(con):
        return []
    rows = con.execute(
        f"SELECT DISTINCT id_doradcy FROM {TABELA} WHERE data_kolejki = ? ORDER BY id_doradcy", [data_kolejki]
    ).fetchall()
    return [r[0] for r in rows]


def pozycje(con: duckdb.DuckDBPyConnection, id_doradcy: str, data_kolejki: date) -> list[dict]:
    """Kolejka doradcy z dnia, od pozycji 1: słowniki z polami POLA_POZYCJI (daty jako ISO, liczby jako float)."""
    if not _istnieje(con):
        return []
    df = con.execute(
        f"SELECT {', '.join(POLA_POZYCJI)} FROM {TABELA} WHERE id_doradcy = ? AND data_kolejki = ? ORDER BY pozycja",
        [id_doradcy, data_kolejki],
    ).df()
    wynik = []
    for r in df.to_dict("records"):
        r["data_kolejki"] = pd.Timestamp(r["data_kolejki"]).date().isoformat()
        r["utworzono"] = pd.Timestamp(r["utworzono"]).isoformat()
        r["stan_danych_na"] = pd.Timestamp(r["stan_danych_na"]).isoformat()
        r["pozycja"] = int(r["pozycja"])
        for k in ("liczba_lokali", "p", "ev_pln"):
            r[k] = float(r[k])
        wynik.append({k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in r.items()})
    return wynik
