"""Historia wycen w domilo.duckdb: tabela `wyceny_historia` (zadanie nocne zapisuje, API i panel czytają).

Jeden wiersz = wycena jednego obiektu (`rodzaj` 'lokal' = lokal Domilo, 'oferta' = oferta z Radaru) w jednym przebiegu.
Zapis jest idempotentny: ponowienie kroku z tym samym `id_przebiegu` i `rodzaj` zastępuje wcześniejsze wiersze.
Tabela nie pochodzi z data/, więc przebudowa bazy (duckdb_baza.zbuduj_baze) przenosi ją ze starego pliku.
Czynniki: wszystkie wkłady cech w PLN jako JSON (valuation_bc/wycena.py); `wartosc_bazowa` = B w PLN.
"""

import json
import math
import uuid
from datetime import datetime

import duckdb
import pandas as pd

TABELA = "wyceny_historia"
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    id_przebiegu VARCHAR NOT NULL,
    czas_przebiegu TIMESTAMPTZ NOT NULL,
    wersja_modelu VARCHAR NOT NULL,
    rodzaj VARCHAR NOT NULL CHECK (rodzaj IN ('lokal', 'oferta')),
    id_obiektu VARCHAR NOT NULL,
    miasto VARCHAR,
    dzielnica VARCHAR,
    metraz DOUBLE,
    dzien_wyceny DATE,
    p10 DOUBLE,
    p50 DOUBLE,
    p90 DOUBLE,
    odmowa BOOLEAN NOT NULL,
    powod VARCHAR,
    cena_ofertowa DOUBLE,
    wartosc_bazowa DOUBLE,
    czynniki JSON,
    PRIMARY KEY (id_przebiegu, rodzaj, id_obiektu)
)
"""
KOLUMNY_WYCEN = (
    "id_obiektu",
    "miasto",
    "dzielnica",
    "metraz",
    "dzien_wyceny",
    "p10",
    "p50",
    "p90",
    "odmowa",
    "powod",
    "cena_ofertowa",
    "wartosc_bazowa",
    "czynniki",
)
_LICZBY = ("metraz", "p10", "p50", "p90", "cena_ofertowa", "wartosc_bazowa")
_OSTATNIE = f"""
SELECT * FROM {TABELA}
WHERE ($rodzaj IS NULL OR rodzaj = $rodzaj)
QUALIFY row_number() OVER (PARTITION BY rodzaj, id_obiektu ORDER BY czas_przebiegu DESC) = 1
"""


def istnieje(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [TABELA]).fetchone()[0])


def zapisz(
    con: duckdb.DuckDBPyConnection, id_przebiegu: str, czas: datetime, wersja: str, rodzaj: str, wyceny: pd.DataFrame
) -> int:
    """Zapisuje wyceny jednego rodzaju z jednego przebiegu (w transakcji: usuń stare wiersze, wstaw nowe)."""
    df = wyceny[list(KOLUMNY_WYCEN)].copy()
    df["czynniki"] = df["czynniki"].map(lambda c: json.dumps(c, ensure_ascii=False) if c else None)
    for k in _LICZBY:
        df[k] = pd.to_numeric(df[k], errors="coerce").astype(float)
    widok = f"_wyceny_{uuid.uuid4().hex}"
    con.execute(SQL_TABELI)
    con.register(widok, df)
    liczby = ", ".join(f"CASE WHEN isnan({k}) THEN NULL ELSE {k} END" for k in _LICZBY)
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(f"DELETE FROM {TABELA} WHERE id_przebiegu = ? AND rodzaj = ?", [id_przebiegu, rodzaj])
        con.execute(
            f"""
            INSERT INTO {TABELA} (id_przebiegu, czas_przebiegu, wersja_modelu, rodzaj, id_obiektu, miasto, dzielnica,
                                  dzien_wyceny, odmowa, powod, czynniki, {", ".join(_LICZBY)})
            SELECT ?, ?, ?, ?, id_obiektu, miasto, dzielnica, CAST(dzien_wyceny AS DATE), odmowa,
                   nullif(powod, ''), CAST(czynniki AS JSON), {liczby}
            FROM {widok}
            """,
            [id_przebiegu, czas, wersja, rodzaj],
        )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.unregister(widok)
    return len(df)


def _z_czynnikami(df: pd.DataFrame) -> pd.DataFrame:
    df["czynniki"] = df["czynniki"].map(lambda c: json.loads(c) if isinstance(c, str) else {})
    return df


def ostatnie(con: duckdb.DuckDBPyConnection, rodzaj: str | None = None) -> pd.DataFrame:
    """Najnowsza wycena każdego obiektu (opcjonalnie tylko jednego rodzaju)."""
    if not istnieje(con):
        return pd.DataFrame()
    df = con.execute(_OSTATNIE + " ORDER BY rodzaj, id_obiektu", {"rodzaj": rodzaj}).df()
    return _z_czynnikami(df)


def odmowy(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Kolejka „nie wiem”: obiekty, których najnowsza wycena to odmowa."""
    df = ostatnie(con)
    return df[df["odmowa"]].reset_index(drop=True) if not df.empty else df


def oferty_ponizej_p10(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Oferty z ceną ofertową poniżej P10 najnowszej wyceny (bez odmów), od największego rabatu."""
    df = ostatnie(con, "oferta")
    if df.empty:
        return df
    df = df[~df["odmowa"] & (df["cena_ofertowa"] < df["p10"])].copy()
    df["cena_do_p10"] = df["cena_ofertowa"] / df["p10"]
    return df.sort_values(["cena_do_p10", "id_obiektu"]).reset_index(drop=True)


def karta(con: duckdb.DuckDBPyConnection, rodzaj: str, id_obiektu: str) -> dict | None:
    """Najnowsza wycena obiektu + historia (czas, p10, p50, p90, odmowa) ze wszystkich przebiegów."""
    if not istnieje(con):
        return None
    df = con.execute(
        f"SELECT * FROM {TABELA} WHERE rodzaj = ? AND id_obiektu = ? ORDER BY czas_przebiegu", [rodzaj, id_obiektu]
    ).df()
    if df.empty:
        return None
    df = _z_czynnikami(df)
    wynik = {k: _bez_nan(v) for k, v in df.iloc[-1].to_dict().items()}
    wynik["historia"] = [
        {k: _bez_nan(r[k]) for k in ("czas_przebiegu", "p10", "p50", "p90", "odmowa")} for _, r in df.iterrows()
    ]
    return wynik


def wycenione(con: duckdb.DuckDBPyConnection, rodzaj: str, poza_przebiegiem: str | None = None) -> set[str]:
    """Obiekty z co najmniej jedną wyceną; `poza_przebiegiem` pomija wiersze bieżącego przebiegu (ponowienie kroku)."""
    if not istnieje(con):
        return set()
    sql = f"SELECT DISTINCT id_obiektu FROM {TABELA} WHERE rodzaj = ? AND id_przebiegu IS DISTINCT FROM ?"
    return {r[0] for r in con.execute(sql, [rodzaj, poza_przebiegiem]).fetchall()}


def _bez_nan(v):
    return None if isinstance(v, float) and math.isnan(v) else v
