"""Zbiór do uczenia modelu wind: dni_wind (target) + cechy_windy (ręczne) + wybrane cechy tsfresh.

Wybrane cechy tsfresh: `tsfresh_wybrane.yaml` (selekcja tylko na treningu 2023-03 – 2025-06, docs/b4_tsfresh.md).
Kolumny pomocnicze (`awaria_7d`, `id_awarii`, `producent`) są w ramce do ewaluacji, ale nie są cechami
(failure_model/base.py: KOLUMNY_ZAKAZANE; `producent` nie jest zakazany, ale wersje v2 go nie używają).
"""

import duckdb
import pandas as pd
import yaml
from api.ai.features.windy.tsfresh_cechy import PLIK_WYBRANYCH

KOLUMNY_POMOCNICZE = ("id_windy", "dzien", "awaria_7d", "id_awarii", "producent")


def cechy_tsfresh_wybrane() -> list[str]:
    return list(yaml.safe_load(PLIK_WYBRANYCH.read_text(encoding="utf-8"))["wybrane"])


def cechy_reczne(con: duckdb.DuckDBPyConnection, tabela: str = "cechy_windy") -> list[str]:
    return [r[0] for r in con.execute(f"DESCRIBE {tabela}").fetchall() if r[0] not in ("id_windy", "dzien")]


def wczytaj_zbior(
    con: duckdb.DuckDBPyConnection,
    tabela_cech: str = "cechy_windy",
    tabela_tsfresh: str = "cechy_windy_tsfresh",
) -> tuple[pd.DataFrame, list[str]]:
    """(ramka: kolumny pomocnicze + cechy, lista cech = ręczne + tsfresh wybrane), wiersze jak dni_wind.
    Inne tabele cech (te same kolumny) tylko w porównaniach, np. wariant z oknami serwisowymi."""
    tsfresh = cechy_tsfresh_wybrane()
    cechy = cechy_reczne(con, tabela_cech) + tsfresh
    df = con.execute(f"""
        SELECT d.id_windy, d.dzien, d.awaria_7d, d.id_awarii, w.producent,
            c.* EXCLUDE (id_windy, dzien), {', '.join(f't.{k}' for k in tsfresh)}
        FROM dni_wind AS d
        JOIN serwis_windy AS w USING (id_windy)
        JOIN {tabela_cech} AS c USING (id_windy, dzien)
        LEFT JOIN {tabela_tsfresh} AS t USING (id_windy, dzien)
        ORDER BY d.dzien, d.id_windy
        """).df()
    df["dzien"] = pd.to_datetime(df["dzien"])
    return df, cechy
