"""Statystyki sąsiedztwa transakcji RCN: mediana ceny m² i liczba wśród 20 najbliższych z 12 miesięcy wstecz.

Definicja (okno czasu, out-of-fold w treningu, remisy) jest w `sasiedztwo.sql` obok tego pliku;
wyniki w `docs/b4_wycena_v2_lgbm_geo.md`.
"""

from pathlib import Path

import duckdb
import pandas as pd
from api.ai.features.wycena.podzial import sql_podzialu

SCIEZKA_SASIEDZTWA = Path(__file__).with_name("sasiedztwo.sql")
KOLUMNY_SASIEDZTWA = ("sasiedzi_mediana_ceny_m2", "sasiedzi_liczba")
LICZBA_SASIADOW = 20
MIESIECY_WSTECZ = 12
LICZBA_FOLDOW = 5


def sql_sasiedztwa() -> str:
    """Treść sasiedztwo.sql z wstawionym podziałem (bez średnika)."""
    sql = SCIEZKA_SASIEDZTWA.read_text(encoding="utf-8").strip().rstrip(";")
    return sql.replace("{podzial}", sql_podzialu())


def cechy_sasiedztwa(
    con: duckdb.DuckDBPyConnection, *, wg_publikacji: bool = False, z_lista_sasiadow: bool = False
) -> pd.DataFrame:
    """Jeden wiersz = transakcja z podziału: id_transakcji + KOLUMNY_SASIEDZTWA (+ sasiedzi_id).

    wg_publikacji=True: sąsiadem może być tylko transakcja opublikowana w rejestrze przed dniem aktu.
    """
    con.execute("SET enable_progress_bar = false")
    con.execute(f"SET VARIABLE sasiedzi_wg_publikacji = {'true' if wg_publikacji else 'false'}")
    try:
        kolumny = ["id_transakcji", *KOLUMNY_SASIEDZTWA] + (["sasiedzi_id"] if z_lista_sasiadow else [])
        return con.execute(f"SELECT {', '.join(kolumny)} FROM ({sql_sasiedztwa()}) ORDER BY id_transakcji").df()
    finally:
        con.execute("RESET VARIABLE sasiedzi_wg_publikacji")
