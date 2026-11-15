"""Zbiór dla modelu kolejki: wejście z crm_leady (kontrakt lead_model/base.py) + cel i flagi z leady_cel.

Wymaga tabeli `leady_cel` w domilo.duckdb (`pypyr baza`). Stanu na dzień eksportu (`crm_leady.status`, `id_umowy`,
…) nie czytamy: do modelu wchodzą tylko `KOLUMNY_WEJSCIA`, a `umowa_45d` i flagi służą do uczenia i oceny.
"""

import duckdb
import pandas as pd
from api.ai.lead_model.base import KOLUMNY_WEJSCIA

KOLUMNY_CELU = ("umowa_45d", "okno_migracji", "cenzurowany", "obsluzony")


def wczytaj_zbior(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    wejscie = ", ".join(f"l.{k}" for k in KOLUMNY_WEJSCIA)
    cel = ", ".join(f"c.{k}" for k in KOLUMNY_CELU)
    return con.execute(
        f"SELECT {wejscie}, {cel} FROM crm_leady AS l JOIN leady_cel AS c USING (id_leada) ORDER BY l.id_leada"
    ).df()
