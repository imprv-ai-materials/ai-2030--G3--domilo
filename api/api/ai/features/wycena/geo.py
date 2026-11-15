"""Cechy otoczenia transakcji RCN (odległości do POI, flagi, dane dzielnicy, geohash).

Definicja jest w `geo.sql` obok tego pliku; opis i statystyki w `docs/b3_wycena_v2_geo.md`.
"""

from pathlib import Path

import duckdb
import pandas as pd

SCIEZKA_GEO = Path(__file__).with_name("geo.sql")
KOLUMNY_GEO = (
    "odl_centrum_m",
    "odl_stacja_m",
    "odl_metro_m",
    "odl_tramwaj_m",
    "odl_park_m",
    "odl_uczelnia_m",
    "metro_do_700m",
    "tramwaj_do_300m",
    "park_do_400m",
    "gestosc_os_km2",
    "wskaznik_dochodu",
    "geohash6",
)


ZNACZNIK_ZRODLA = "/*ZRODLO_PUNKTOW*/ rcn_transakcje"


def sql_geo(sql_punktow: str | None = None) -> str:
    """Treść zapytania z geo.sql (bez średnika, do użycia jako podzapytanie).

    sql_punktow: zapytanie zwracające id_transakcji, miasto, dzielnica, lat, lon zamiast rcn_transakcje
    (np. oferty albo lokale Domilo; id_transakcji to wtedy ich identyfikator).
    """
    sql = SCIEZKA_GEO.read_text(encoding="utf-8").strip().rstrip(";")
    if ZNACZNIK_ZRODLA not in sql:
        raise ValueError(f"geo.sql nie zawiera znacznika źródła punktów: {ZNACZNIK_ZRODLA}")
    return sql if sql_punktow is None else sql.replace(ZNACZNIK_ZRODLA, f"({sql_punktow}) AS zrodlo_punktow")


def cechy_geo(con: duckdb.DuckDBPyConnection, sql_punktow: str | None = None) -> pd.DataFrame:
    """Jeden wiersz = punkt (domyślnie transakcja z rcn_transakcje): id_transakcji + KOLUMNY_GEO."""
    return con.execute(f"SELECT * FROM ({sql_geo(sql_punktow)}) ORDER BY id_transakcji").df()
