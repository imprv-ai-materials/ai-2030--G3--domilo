"""Transakcje RCN z cechami, targetem i zbiorem z podziału czasowego (podzial.sql)."""

import duckdb
import pandas as pd
from api.ai.features.wycena.podzial import sql_podzialu

SQL_TRANSAKCJI = """
SELECT t.id_transakcji, p.zbior, t.data_aktu, t.data_publikacji_rejestru,
       t.miasto, t.dzielnica, t.metraz, t.pokoje, t.pietro, t.rok_budowy, t.rynek,
       t.cena_pln, t.cena_m2
FROM rcn_transakcje t JOIN ({podzial}) p USING (id_transakcji)
ORDER BY t.data_aktu, t.id_transakcji
"""


def wczytaj_transakcje(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Jeden wiersz = transakcja objęta podziałem; `zbior` ∈ {trening, walidacja, test}."""
    return con.execute(SQL_TRANSAKCJI.format(podzial=sql_podzialu())).df()
