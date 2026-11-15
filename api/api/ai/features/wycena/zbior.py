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


# --- cechy otoczenia i sąsiedztwa (v2_lgbm_geo, docs/b4_wycena_v2_lgbm_geo.md) -----------------------------------

# Rodziny cech do ablacji. „geo” = wszystkie kolumny z geo.sql (POI + centrum/dzielnica/geohash);
# „poi” = odległości do punktów z geo_poi i flagi; „sasiedztwo” = sasiedztwo.sql.
RODZINA_POI = (
    "odl_stacja_m",
    "odl_metro_m",
    "odl_tramwaj_m",
    "odl_park_m",
    "odl_uczelnia_m",
    "metro_do_700m",
    "tramwaj_do_300m",
    "park_do_400m",
)
RODZINA_GEO_BEZ_POI = ("odl_centrum_m", "gestosc_os_km2", "wskaznik_dochodu")
RODZINA_SASIEDZTWO = ("sasiedzi_mediana_ceny_m2", "sasiedzi_liczba")
KATEGORIA_GEOHASH = "geohash6"


def wczytaj_transakcje_z_cechami(
    con: duckdb.DuckDBPyConnection, *, sasiedzi_wg_publikacji: bool = False
) -> pd.DataFrame:
    """wczytaj_transakcje + kolumny geo.sql + sasiedztwo.sql (jeden wiersz = transakcja z podziału)."""
    from api.ai.features.wycena.geo import cechy_geo
    from api.ai.features.wycena.sasiedztwo import cechy_sasiedztwa

    df = wczytaj_transakcje(con)
    geo = cechy_geo(con)
    sas = cechy_sasiedztwa(con, wg_publikacji=sasiedzi_wg_publikacji)
    wynik = df.merge(geo, on="id_transakcji", how="left", validate="one_to_one")
    wynik = wynik.merge(sas, on="id_transakcji", how="left", validate="one_to_one")
    if len(wynik) != len(df):
        raise ValueError("Złączenie cech zmieniło liczbę transakcji")
    return wynik
