"""Liczby do raportu docs/b3_wycena_v2_geo.md: opis cech otoczenia (geo.sql) i ich związek z błędem v2.

Uruchomienie (wymaga domilo.duckdb: `pypyr baza` oraz versions/v2_lightgbm/model.joblib), z katalogu api/:
    poetry run python -m api.ai.features.wycena.opis_geo
Korelacje z błędem v2 liczymy tylko na zbiorze `walidacja` (test pozostaje nietknięty).
"""

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.geo import KOLUMNY_GEO, sql_geo
from api.ai.features.wycena.podzial import sql_podzialu
from api.ai.features.wycena.zbior import wczytaj_transakcje
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.ewaluacja import KATALOG_WERSJI, _md

SQL_MIASTA = """
SELECT t.miasto,
       count(*) AS transakcje,
       round(median(g.odl_centrum_m))::BIGINT AS med_odl_centrum_m,
       round(median(g.odl_stacja_m))::BIGINT AS med_odl_stacja_m,
       round(median(g.odl_metro_m))::BIGINT AS med_odl_metro_m,
       round(median(g.odl_tramwaj_m))::BIGINT AS med_odl_tramwaj_m,
       round(median(g.odl_park_m))::BIGINT AS med_odl_park_m,
       round(median(g.odl_uczelnia_m))::BIGINT AS med_odl_uczelnia_m,
       round(100 * avg(g.metro_do_700m), 1) AS proc_metro_do_700m,
       round(100 * avg(g.tramwaj_do_300m), 1) AS proc_tramwaj_do_300m,
       round(100 * avg(g.park_do_400m), 1) AS proc_park_do_400m,
       count(DISTINCT g.geohash6) AS komorki_geohash6,
       count(*) FILTER (g.odl_metro_m IS NULL) AS brak_metra
FROM rcn_transakcje t JOIN ({geo}) g USING (id_transakcji)
GROUP BY t.miasto ORDER BY transakcje DESC
"""

SQL_BRAKI = """
SELECT count(*) AS transakcje,
       {braki}
FROM ({geo})
"""

SQL_GEOHASH = """
WITH z AS (
    SELECT p.zbior, g.geohash6 FROM ({podzial}) p JOIN ({geo}) g USING (id_transakcji)
),
tr AS (SELECT geohash6, count(*) AS n FROM z WHERE zbior = 'trening' GROUP BY geohash6)
SELECT z.zbior,
       count(*) AS transakcje,
       count(DISTINCT z.geohash6) AS komorki,
       count(*) FILTER (tr.geohash6 IS NULL) AS transakcje_w_komorce_bez_treningu,
       count(*) FILTER (coalesce(tr.n, 0) < 10) AS transakcje_w_komorce_z_mniej_niz_10_w_treningu
FROM z LEFT JOIN tr USING (geohash6)
GROUP BY z.zbior ORDER BY min(z.zbior = 'test'), min(z.zbior = 'walidacja')
"""


def main() -> None:
    con = polacz()
    geo = sql_geo()
    miasta = con.execute(SQL_MIASTA.format(geo=geo)).df()
    print(f"### Cechy otoczenia według miasta (wszystkie transakcje RCN)\n\n{_md(miasta)}\n")
    braki = ",\n       ".join(f"count(*) FILTER ({k} IS NULL) AS brak_{k}" for k in KOLUMNY_GEO)
    print(f"### Braki\n\n{_md(con.execute(SQL_BRAKI.format(geo=geo, braki=braki)).df())}\n")
    print(f"### geohash6 a zbiory\n\n{_md(con.execute(SQL_GEOHASH.format(geo=geo, podzial=sql_podzialu())).df())}\n")

    # Związek cech otoczenia z tym, czego v2 nie wyjaśnia: reszta ln(cena) − ln(wycena v2) na walidacji.
    df = wczytaj_transakcje(con)
    wal = df[df["zbior"] == "walidacja"].merge(con.execute(geo).df(), on="id_transakcji", how="left")
    v2 = ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lightgbm" / "model.joblib")
    wal["reszta_ln"] = np.log(wal["cena_pln"]) - np.log(v2.predict(wal[list(KOLUMNY_CECH)]))
    liczbowe = [k for k in KOLUMNY_GEO if k != "geohash6"]
    wiersze = []
    for k in liczbowe:
        d = wal[[k, "reszta_ln"]].dropna()
        wiersze.append(
            {
                "cecha": k,
                "transakcje": int(len(d)),
                "spearman_z_reszta": f'{d[k].corr(d["reszta_ln"], method="spearman"):.3f}'.replace(".", ","),
            }
        )
    print(f"### Korelacja Spearmana cechy z resztą ln(ceny) v2 (walidacja)\n\n{_md(pd.DataFrame(wiersze))}\n")
    flagi = []
    for k in ("metro_do_700m", "tramwaj_do_300m", "park_do_400m"):
        for wartosc, g in wal.groupby(k):
            flagi.append(
                {
                    "flaga": k,
                    "wartosc": int(wartosc),
                    "transakcje": int(len(g)),
                    "mediana_reszty_proc": f'{100 * (np.exp(g["reszta_ln"].median()) - 1):.2f}'.replace(".", ","),
                }
            )
    print(f"### Mediana reszty v2 według flag (walidacja; > 0 = v2 zaniża)\n\n{_md(pd.DataFrame(flagi))}\n")


if __name__ == "__main__":
    main()
