"""Przeciek ceny z opisu ogłoszenia do modelu wyceny: celowy eksperyment (docs/b1_przeciek_opisu.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.przeciek_opisu

Kroki:
1. Wzmianki o cenie w radar_oferty.opis (kwota, zł/m², rata, obniżka) i ich zgodność z cena_ofertowa.
2. Co jest w lokale_domilo_opisy: czynsz najmu, porównany z pms_lokale.czynsz_katalogowy.
3. Grupy ofert (ten sam lokal na kilku portalach, grupy_lokali.sql) i rozłączność zbiorów po grupie.
4. Dwa modele LightGBM o tych samych hiperparametrach i tych samych wierszach treningu:
   - bez przecieku: ModelLightGBM (cechy v2_lightgbm: miasto, dzielnica, metraż, pokoje, piętro, rok budowy);
   - z przeciekiem: to samo + `cena_z_opisu` (cena z opisu dopasowanej oferty albo innej oferty z tej samej grupy).
   MAPE na testowym zbiorze dopasowań (transakcje testu z dopasowaną ofertą), na całym teście i na 300 operatach
   kontrolnych (lokale Domilo; ich opis podaje czynsz najmu, nie cenę). Model z przeciekiem jest CELOWO błędny
   i nie trafia do versions/.
"""

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.ceny_w_opisie import cena_z_opisu, czynsz_najmu_z_opisu, szablon_ceny, wzmianki_o_cenie
from api.ai.features.wycena.grupy_lokali import bez_grup_z_wczesniejszych_zbiorow, grupy_transakcji, sql_grup_ofert
from api.ai.features.wycena.podzial import sql_podzialu
from api.ai.features.wycena.zbior import wczytaj_transakcje
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.ewaluacja import KATALOG_WERSJI, _md
from api.ai.valuation_model.evals.metryki import metryki
from api.ai.valuation_model.versions.v2_lightgbm.model import ModelLightGBM

CECHA_PRZECIEKU = "cena_z_opisu"
TYPY_WZMIANEK = ("kwota", "zl_m2", "rata", "obnizka")

SQL_OFERTY = "SELECT id_oferty, portal, metraz, cena_ofertowa, opis FROM radar_oferty"

# Oferty, z których bierzemy cenę dla transakcji: dopasowana oferta i pozostałe oferty z jej grupy,
# opublikowane nie później niż akt (inaczej byłaby to informacja z przyszłości).
SQL_OFERTY_TRANSAKCJI = f"""
WITH g AS ({sql_grup_ofert()})
SELECT d.id_transakcji, o.id_oferty, o.data_publikacji, o.metraz, o.opis, (o.id_oferty = d.id_oferty) AS dopasowana
FROM radar_dopasowania d
JOIN g gd ON gd.id_oferty = d.id_oferty
JOIN g ON g.id_grupy = gd.id_grupy
JOIN radar_oferty o ON o.id_oferty = g.id_oferty
JOIN rcn_transakcje t ON t.id_transakcji = d.id_transakcji
WHERE o.data_publikacji <= t.data_aktu
"""

SQL_OPERATY_KONTROLNE = """
SELECT op.id_operatu, op.id_lokalu, op.data_wyceny, op.wartosc_pln,
       b.miasto, b.dzielnica, l.metraz, l.pokoje, l.pietro, b.rok_oddania AS rok_budowy,
       l.czynsz_katalogowy, ld.opis_marketingowy
FROM operaty op
JOIN pms_lokale l USING (id_lokalu)
JOIN pms_budynki b USING (id_budynku)
LEFT JOIN lokale_domilo_opisy ld USING (id_lokalu)
WHERE op.typ = 'kontrolny'
ORDER BY op.id_operatu
"""

SQL_STATYSTYKI_GRUP = f"""
WITH g AS ({sql_grup_ofert()}),
o AS (SELECT * FROM radar_oferty JOIN g USING (id_oferty)),
grupy AS (
    SELECT id_grupy, count(*) AS oferty, count(DISTINCT portal) AS portale,
           max(data_publikacji) - min(data_publikacji) AS rozpietosc,
           count(*) FILTER (rok_budowy IS NULL) AS puste_rok_budowy
    FROM o GROUP BY id_grupy
)
SELECT (SELECT count(*) FROM radar_oferty) AS oferty,
       count(*) AS grupy,
       count(*) FILTER (oferty > 1) AS grupy_z_wiecej_niz_1_oferta,
       CAST(sum(oferty) FILTER (oferty > 1) AS INTEGER) AS ich_oferty,
       count(*) FILTER (oferty > 1 AND puste_rok_budowy > 0) AS w_tym_rok_budowy_pusty_w_jednej,
       count(*) FILTER (oferty > 1 AND portale = oferty) AS kazda_oferta_na_innym_portalu,
       count(*) FILTER (oferty > portale) AS ten_sam_portal_dwa_razy,
       count(*) FILTER (rozpietosc > INTERVAL 3 DAY) AS grupy_dluzsze_niz_3_dni,
       max(oferty) AS max_ofert_w_grupie
FROM grupy
"""


# Ten sam fizyczny lokal (bez okna dat) z kilkoma transakcjami w podziale: odsprzedaże, których grupa ofert nie łączy.
SQL_ODSPRZEDAZE = f"""
WITH p AS ({sql_podzialu()}),
t AS (SELECT t.*, p.zbior FROM rcn_transakcje t JOIN p USING (id_transakcji)),
l AS (SELECT lat, lon, metraz, pietro, count(*) AS n, count(DISTINCT zbior) AS zbiory,
             bool_or(zbior = 'test') AS z_testem
      FROM t GROUP BY ALL HAVING count(*) > 1)
SELECT count(*) AS lokale_z_kilkoma_transakcjami, CAST(sum(n) AS INTEGER) AS ich_transakcje,
       count(*) FILTER (zbiory > 1) AS w_roznych_zbiorach, count(*) FILTER (zbiory > 1 AND z_testem) AS w_tym_z_testem
FROM l
"""


class ModelZPrzeciekiem(ModelLightGBM):
    """CELOWO BŁĘDNY: v2_lightgbm + cena z opisu oferty (cena ofertowa tego samego lokalu). Tylko do eksperymentu."""

    wersja = "przeciek_cena_z_opisu"

    def _kolumny_liczbowe(self) -> list[str]:
        return [*super()._kolumny_liczbowe(), CECHA_PRZECIEKU]

    def _sprawdz(self, X: pd.DataFrame) -> None:
        super()._sprawdz(X)
        if CECHA_PRZECIEKU not in X.columns:
            raise ValueError(f"Brak kolumny {CECHA_PRZECIEKU}")


def _proc(licznik: int, mianownik: int) -> float:
    return round(100 * licznik / mianownik, 2)


# --- 1. wzmianki o cenie w ofertach ------------------------------------------------------------------------------


def wzmianki_w_ofertach(con) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    of = con.execute(SQL_OFERTY).df()
    wzm = of["opis"].map(wzmianki_o_cenie)
    for typ in TYPY_WZMIANEK:
        of[typ] = wzm.map(lambda s, t=typ: t in s)
    of["dowolna"] = wzm.map(bool)
    of["cena_z_opisu"] = [cena_z_opisu(o, m) for o, m in zip(of["opis"], of["metraz"])]
    n = len(of)
    wzmianki = pd.DataFrame(
        [{"wzmianka": t, "oferty": int(of[t].sum()), "odsetek_proc": _proc(int(of[t].sum()), n)} for t in TYPY_WZMIANEK]
        + [
            {
                "wzmianka": "dowolna kwota (co najmniej jedna z powyższych)",
                "oferty": int(of["dowolna"].sum()),
                "odsetek_proc": _proc(int(of["dowolna"].sum()), n),
            },
            {
                "wzmianka": "cena sprzedaży do odczytania (kwota, obniżka albo zł/m² × metraż)",
                "oferty": int(of["cena_z_opisu"].notna().sum()),
                "odsetek_proc": _proc(int(of["cena_z_opisu"].notna().sum()), n),
            },
            {"wzmianka": "wszystkie oferty", "oferty": n, "odsetek_proc": 100.0},
        ]
    )
    portale = (
        of.groupby("portal")
        .agg(oferty=("id_oferty", "size"), z_kwota=("dowolna", "sum"), z_cena=("cena_z_opisu", "count"))
        .reset_index()
        .assign(odsetek_z_kwota_proc=lambda d: (100 * d["z_kwota"] / d["oferty"]).round(2))
    )
    # Zgodność z cena_ofertowa według szablonu, z którego wzięto cenę (oferty z ceną ofertową > 0)
    z = of[of["cena_z_opisu"].notna() & (of["cena_ofertowa"] > 0)].copy()
    z["szablon"] = z["opis"].map(szablon_ceny)
    z["iloraz"] = z["cena_z_opisu"] / z["cena_ofertowa"]
    wiersze = []
    for szablon, g in [*z.groupby("szablon", sort=False), ("razem", z)]:
        rozne = g[g["iloraz"] != 1]
        wiersze.append(
            {
                "szablon": szablon,
                "oferty": len(g),
                "rowna_ofertowej_proc": _proc(int((g["iloraz"] == 1).sum()), len(g)),
                "w_granicach_1proc": _proc(int((g["iloraz"] - 1).abs().le(0.01).sum()), len(g)),
                "wyzsza_niz_ofertowa": int((g["iloraz"] > 1).sum()),
                "nizsza_niz_ofertowa": int((g["iloraz"] < 1).sum()),
                "rozne: min ilorazu": f"{rozne['iloraz'].min():.4f}" if len(rozne) else "—",
                "rozne: mediana": f"{rozne['iloraz'].median():.4f}" if len(rozne) else "—",
                "rozne: max": f"{rozne['iloraz'].max():.4f}" if len(rozne) else "—",
            }
        )
    zgodnosc = pd.DataFrame(wiersze)
    pominiete = int((of["cena_z_opisu"].notna() & (of["cena_ofertowa"] <= 0)).sum())
    return wzmianki, portale, zgodnosc, pominiete


# --- 2. opisy lokali Domilo --------------------------------------------------------------------------------------


def opisy_domilo(con) -> pd.DataFrame:
    df = con.execute(
        "SELECT ld.id_lokalu, ld.opis_marketingowy, l.metraz, l.czynsz_katalogowy "
        "FROM lokale_domilo_opisy ld LEFT JOIN pms_lokale l USING (id_lokalu)"
    ).df()
    df["czynsz_z_opisu"] = df["opis_marketingowy"].map(czynsz_najmu_z_opisu)
    df["wzmianka_ceny_sprzedazy"] = df["opis_marketingowy"].map(lambda o: bool(wzmianki_o_cenie(o)))
    df["cena_sprzedazy_z_opisu"] = [cena_z_opisu(o, m) for o, m in zip(df["opis_marketingowy"], df["metraz"])]
    z = df[df["czynsz_z_opisu"].notna() & df["czynsz_katalogowy"].notna()]
    return pd.DataFrame(
        [
            {
                "opisy": len(df),
                "z_czynszem_najmu": int(df["czynsz_z_opisu"].notna().sum()),
                "z_wzmianka_ceny_sprzedazy": int(df["wzmianka_ceny_sprzedazy"].sum()),
                "z_cena_sprzedazy": int(df["cena_sprzedazy_z_opisu"].notna().sum()),
                "czynsz_rowny_katalogowemu": int((z["czynsz_z_opisu"] == z["czynsz_katalogowy"]).sum()),
                "czynsz_min": int(df["czynsz_z_opisu"].min()),
                "czynsz_mediana": int(df["czynsz_z_opisu"].median()),
                "czynsz_max": int(df["czynsz_z_opisu"].max()),
            }
        ]
    )


# --- 3. grupy i rozłączność zbiorów -------------------------------------------------------------------------------


def transakcje_z_grupami(con) -> pd.DataFrame:
    df = wczytaj_transakcje(con).merge(grupy_transakcji(con), on="id_transakcji", how="left", validate="one_to_one")
    dop = con.execute("SELECT id_transakcji FROM radar_dopasowania").df()
    df["z_dopasowaniem"] = df["id_transakcji"].isin(dop["id_transakcji"])
    return df


def rozlacznosc(df: pd.DataFrame, po: pd.DataFrame) -> pd.DataFrame:
    zbiory_grupy = df.groupby("id_grupy")["zbior"].nunique()
    wiersze = []
    for zbior in ("trening", "walidacja", "test"):
        d, p = df[df["zbior"] == zbior], po[po["zbior"] == zbior]
        wiersze.append(
            {
                "zbior": zbior,
                "transakcje": len(d),
                "z_dopasowana_oferta": int(d["z_dopasowaniem"].sum()),
                "grupa_w_kilku_zbiorach": int(d["id_grupy"].map(zbiory_grupy).gt(1).sum()),
                "usuniete": len(d) - len(p),
                "po_usunieciu": len(p),
            }
        )
    return pd.DataFrame(wiersze)


def dolacz_cene_z_opisu(con, df: pd.DataFrame) -> pd.DataFrame:
    of = con.execute(SQL_OFERTY_TRANSAKCJI).df()
    of["cena"] = [cena_z_opisu(o, m) for o, m in zip(of["opis"], of["metraz"])]
    of = of[of["cena"].notna()].sort_values(
        ["id_transakcji", "dopasowana", "data_publikacji"], ascending=[True, False, False]
    )
    pierwsza = of.drop_duplicates("id_transakcji")  # najpierw dopasowana oferta, potem najnowsza z grupy
    wynik = df.merge(
        pierwsza[["id_transakcji", "cena", "dopasowana"]].rename(
            columns={"cena": CECHA_PRZECIEKU, "dopasowana": "cena_z_dopasowanej"}
        ),
        on="id_transakcji",
        how="left",
        validate="one_to_one",
    )
    return wynik


# --- 4. modele ---------------------------------------------------------------------------------------------------


def _wiersz_metryk(model: str, zbior: str, y, p) -> dict:
    m = metryki(y, p)
    return {
        "model": model,
        "zbior": zbior,
        "n": m["n"],
        "MAPE_proc": round(m["mape"], 2),
        "MdAPE_proc": round(m["mdape"], 2),
        "mediana_bledu_proc": round(m["mediana_bledu_proc"], 2),
        "MAE_pln": round(m["mae"]),
    }


def main() -> None:
    con = polacz()

    wzmianki, portale, zgodnosc, pominiete = wzmianki_w_ofertach(con)
    print(f"### 1. Wzmianki o cenie w radar_oferty.opis\n\n{_md(wzmianki)}\n\n{_md(portale)}\n\n{_md(zgodnosc)}\n")
    print(f"Pominięte w zgodności (cena_ofertowa <= 0): {pominiete}\n")
    print(f"### 2. lokale_domilo_opisy\n\n{_md(opisy_domilo(con))}\n")

    print(f"### 3a. Grupy ofert\n\n{_md(con.execute(SQL_STATYSTYKI_GRUP).df())}\n")
    df = transakcje_z_grupami(con)
    po = bez_grup_z_wczesniejszych_zbiorow(df)
    print(f"### 3b. Rozłączność zbiorów po grupie\n\n{_md(rozlacznosc(df, po))}\n")
    print(f"### 3c. Ten sam lokal (bez okna dat) w kilku transakcjach\n\n{_md(con.execute(SQL_ODSPRZEDAZE).df())}\n")

    df = dolacz_cene_z_opisu(con, po)
    pokrycie = (
        df.groupby("zbior")
        .agg(
            transakcje=("id_transakcji", "size"),
            z_dopasowaniem=("z_dopasowaniem", "sum"),
            z_cena_z_opisu=(CECHA_PRZECIEKU, "count"),
            z_ceny_dopasowanej_oferty=("cena_z_dopasowanej", lambda s: int((s == True).sum())),  # noqa: E712
        )
        .reindex(["trening", "walidacja", "test"])
        .reset_index()
    )
    print(f"### 4a. Pokrycie cechy {CECHA_PRZECIEKU}\n\n{_md(pokrycie)}\n")

    tr, wal, te = (df[df["zbior"] == z] for z in ("trening", "walidacja", "test"))
    cechy = list(KOLUMNY_CECH)
    bez = ModelLightGBM().fit(tr[cechy], tr["cena_pln"], wal[cechy], wal["cena_pln"])
    z = ModelZPrzeciekiem().fit(
        tr[[*cechy, CECHA_PRZECIEKU]], tr["cena_pln"], wal[[*cechy, CECHA_PRZECIEKU]], wal["cena_pln"]
    )
    v1 = ModelWyceny.wczytaj(KATALOG_WERSJI / "v1_liniowa" / "model.joblib")
    v0 = ModelWyceny.wczytaj(KATALOG_WERSJI / "v0_mediana_dzielnicy" / "model.joblib")
    print(
        f"Drzewa (wczesne zatrzymanie): bez przecieku {bez.najlepsza_iteracja_}, z przeciekiem {z.najlepsza_iteracja_}"
    )
    waznosc = z.waznosc_cech()
    waznosc = waznosc.assign(udzial_proc=waznosc["udzial_proc"].round(2)).drop(columns="zysk")
    print(f"\n### 4b. Ważność cech modelu z przeciekiem (gain)\n\n{_md(waznosc)}\n")

    op = con.execute(SQL_OPERATY_KONTROLNE).df()
    op["czynsz_z_opisu"] = op["opis_marketingowy"].map(czynsz_najmu_z_opisu)
    op[CECHA_PRZECIEKU] = [
        cena_z_opisu(o, m) if isinstance(o, str) else None for o, m in zip(op["opis_marketingowy"], op["metraz"])
    ]
    op[CECHA_PRZECIEKU] = op[CECHA_PRZECIEKU].astype(float)

    zbiory = {
        "test: dopasowania z ceną w opisie": te[te["z_dopasowaniem"] & te[CECHA_PRZECIEKU].notna()],
        "test: wszystkie dopasowania": te[te["z_dopasowaniem"]],
        "test: bez dopasowania": te[~te["z_dopasowaniem"]],
        "test: wszystkie": te,
    }
    wiersze = []
    for nazwa, d in zbiory.items():
        wiersze.append(_wiersz_metryk("v0_mediana_dzielnicy (baseline)", nazwa, d["cena_pln"], v0.predict(d[cechy])))
        wiersze.append(_wiersz_metryk("v1_liniowa (obecna)", nazwa, d["cena_pln"], v1.predict(d[cechy])))
        wiersze.append(_wiersz_metryk("bez przecieku (v2_lightgbm)", nazwa, d["cena_pln"], bez.predict(d[cechy])))
        wiersze.append(
            _wiersz_metryk(
                "z przeciekiem (+ cena z opisu)", nazwa, d["cena_pln"], z.predict(d[[*cechy, CECHA_PRZECIEKU]])
            )
        )
    nazwa_op = "300 operatów kontrolnych"
    wiersze.append(
        _wiersz_metryk("v0_mediana_dzielnicy (baseline)", nazwa_op, op["wartosc_pln"], v0.predict(op[cechy]))
    )
    wiersze.append(_wiersz_metryk("v1_liniowa (obecna)", nazwa_op, op["wartosc_pln"], v1.predict(op[cechy])))
    wiersze.append(_wiersz_metryk("bez przecieku (v2_lightgbm)", nazwa_op, op["wartosc_pln"], bez.predict(op[cechy])))
    wiersze.append(
        _wiersz_metryk(
            "z przeciekiem: cena z opisu = brak (opis Domilo nie ma ceny)",
            nazwa_op,
            op["wartosc_pln"],
            z.predict(op[[*cechy, CECHA_PRZECIEKU]]),
        )
    )
    jak_czynsz = op.assign(**{CECHA_PRZECIEKU: op["czynsz_z_opisu"].astype(float)})
    wiersze.append(
        _wiersz_metryk(
            "z przeciekiem: kwota z opisu Domilo (czynsz najmu) wzięta za cenę",
            nazwa_op,
            op["wartosc_pln"],
            z.predict(jak_czynsz[[*cechy, CECHA_PRZECIEKU]]),
        )
    )
    print(f"### 4c. MAPE: model bez przecieku vs z przeciekiem\n\n{_md(pd.DataFrame(wiersze))}\n")
    print(
        f"Operaty kontrolne: {len(op)}, z ceną sprzedaży w opisie: {int(op[CECHA_PRZECIEKU].notna().sum())}, "
        f"z czynszem w opisie: {int(op['czynsz_z_opisu'].notna().sum())}, "
        f"data_wyceny {op['data_wyceny'].min():%Y-%m-%d} – {op['data_wyceny'].max():%Y-%m-%d}\n"
    )

    # Cena z opisu sama w sobie jako „wycena” (bez modelu): ile brakuje do ceny transakcyjnej
    d = zbiory["test: dopasowania z ceną w opisie"]
    sama = _wiersz_metryk(
        "cena z opisu (bez modelu)", "test: dopasowania z ceną w opisie", d["cena_pln"], d[CECHA_PRZECIEKU]
    )
    print(f"### 4d. Sama cena z opisu jako wycena (test, dopasowania z ceną)\n\n{_md(pd.DataFrame([sama]))}\n")
    con.close()


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
