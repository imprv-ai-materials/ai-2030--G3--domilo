"""Grupy lokali: deduplikacja ofert między portalami i rozłączność zbiorów po grupie (docs/b1_przeciek_opisu.md).

Definicja grupy ofert: `grupy_lokali.sql`. Transakcja RCN dostaje grupę swojej oferty z `radar_dopasowania`;
transakcja bez dopasowanej oferty tworzy własną grupę ('T' + id_transakcji).
"""

from pathlib import Path

import duckdb
import pandas as pd

SCIEZKA_GRUP = Path(__file__).with_name("grupy_lokali.sql")
KOLEJNOSC_ZBIOROW = ("trening", "walidacja", "test")


def sql_grup_ofert() -> str:
    return SCIEZKA_GRUP.read_text(encoding="utf-8").strip().rstrip(";")


def grupy_ofert(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """id_oferty, id_grupy dla każdej oferty z radar_oferty."""
    return con.execute(sql_grup_ofert()).df()


def grupy_transakcji(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """id_transakcji, id_grupy dla każdej transakcji RCN (przez dopasowaną ofertę albo własna grupa)."""
    return con.execute(f"""
        SELECT t.id_transakcji, coalesce(g.id_grupy, 'T' || t.id_transakcji) AS id_grupy
        FROM rcn_transakcje t
        LEFT JOIN radar_dopasowania d USING (id_transakcji)
        LEFT JOIN ({sql_grup_ofert()}) g ON g.id_oferty = d.id_oferty
        """).df()


def bez_grup_z_wczesniejszych_zbiorow(df: pd.DataFrame) -> pd.DataFrame:
    """Usuwa z walidacji i testu wiersze z id_grupy widzianym we wcześniejszym zbiorze (trening < walidacja < test).

    Trening zostaje cały: podział jest czasowy, więc lokal należy do zbioru, w którym pojawił się najpierw.
    """
    widziane: set = set()
    zostaja = pd.Series(True, index=df.index)
    for zbior in KOLEJNOSC_ZBIOROW:
        w_zbiorze = df["zbior"] == zbior
        zostaja &= ~(w_zbiorze & df["id_grupy"].isin(widziane))
        widziane |= set(df.loc[w_zbiorze, "id_grupy"])
    return df[zostaja]
