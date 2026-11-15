"""v3_przedzialy: zapis wersji, metryki z przedziałem i odmowami, koszt wycen wewnętrznych (docs/b1_v3.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v3            # bez sprawdzenia uczenia od zera
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v3 --od-zera  # + fit() od zera i porównanie

v3 składamy z zapisanych składników (bez ponownego uczenia): versions/v2_lgbm_geo_cqr/model.joblib (P50 + P10/P90
CQR) i versions/v3_przedzialy/ood.joblib (detektor, progi = kwantyl 0,99 treningu). `--od-zera` uczy v3 przez
ModelWycenyV3.fit na tym samym podziale i sprawdza, że daje te same przedziały i odmowy.
Wariant B dokłada odmowę przy szerokości (P90 − P10) / P50 powyżej progu wybranego na walidacji
(docs/b1_ood.md, tabela 8).
Test był już otwarty dla wszystkich składników; tu nic na nim nie wybieramy.
Koszty: stałe z api/contexts_boundaries/valuation_bc/zalozenia.yaml (od użytkownika).
Zapisuje versions/v3_przedzialy/model.joblib i metryki.json.
"""

import json
import sys
from datetime import date

import joblib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.zbior import wczytaj_transakcje_z_cechami
from api.ai.valuation_model.base import ModelWyceny
from api.ai.valuation_model.evals.analiza_bledow_v2 import _f
from api.ai.valuation_model.evals.ewaluacja import KATALOG_WERSJI, _md
from api.ai.valuation_model.evals.ood_v3 import (
    PROG_MAPE_BANKU,
    krzywa,
    progi_wg_kwantyla,
    wczytaj_lokale_domilo,
    wczytaj_oferty,
)
from api.ai.valuation_model.versions.v3_przedzialy.model import ModelWycenyV3
from api.contexts_boundaries.valuation_bc.zalozenia import bez_odpowiedzialnego, wczytaj_zalozenia

KATALOG = KATALOG_WERSJI / ModelWycenyV3.wersja
POCZATEK_ODLOZONEJ = pd.Timestamp("2025-01-01")  # jak w przedzialy_v2.py

SQL_OPERATY_ROCZNE = """
SELECT year(data_wyceny) AS rok, strftime(min(data_wyceny), '%Y-%m-%d') AS od,
       strftime(max(data_wyceny), '%Y-%m-%d') AS do,
       count(*) AS operaty, count(DISTINCT id_lokalu) AS lokale
FROM operaty WHERE typ = 'roczny' GROUP BY ALL ORDER BY rok
"""


def metryki_v3(y: np.ndarray, p: pd.DataFrame) -> dict[str, float]:
    """Odmowy na wszystkich lokalach; błąd, pokrycie i szerokość tylko na przyjętych."""
    przyj = ~p["odmowa"].to_numpy()
    yy, pp = y[przyj], p[przyj]
    blad = (pp["p50"].to_numpy() - yy) / yy
    return {
        "n": int(len(y)),
        "odmowy_proc": float(100 * (~przyj).mean()),
        "n_przyjetych": int(przyj.sum()),
        "mae": float(np.mean(np.abs(pp["p50"].to_numpy() - yy))),
        "mape": float(100 * np.mean(np.abs(blad))),
        "mdape": float(100 * np.median(np.abs(blad))),
        "mediana_bledu_proc": float(100 * np.median(blad)),
        "pokrycie": float(100 * np.mean((yy >= pp["p10"].to_numpy()) & (yy <= pp["p90"].to_numpy()))),
        "ponizej_p10": float(100 * np.mean(yy < pp["p10"].to_numpy())),
        "powyzej_p90": float(100 * np.mean(yy > pp["p90"].to_numpy())),
        "mediana_szerokosci": float(100 * np.median((pp["p90"] - pp["p10"]) / pp["p50"])),
    }


def _wiersz(nazwa: str, zbior: str, m: dict) -> dict:
    return {
        "wersja": nazwa,
        "zbior": zbior,
        "lokale": m["n"],
        "odmowy_proc": _f(m["odmowy_proc"], 1),
        "MAE_przyjetych": _f(m["mae"], 0),
        "MAPE_przyjetych": _f(m["mape"], 2),
        "MdAPE_przyjetych": _f(m["mdape"], 2),
        "mediana_bledu": _f(m["mediana_bledu_proc"], 2),
        "pokrycie": _f(m["pokrycie"], 1),
        "pod_P10": _f(m["ponizej_p10"], 1),
        "nad_P90": _f(m["powyzej_p90"], 1),
        "szerokosc": _f(m["mediana_szerokosci"], 1),
    }


def prog_szerokosci(model: ModelWycenyV3, wal: pd.DataFrame) -> float:
    """Szerokość, przy której na walidacji przyjmujemy najwięcej lokali z MAPE ≤ 8% (jak b1_ood.md, tabela 8)."""
    p = model.przedzial.predict_interval(wal)
    szer = ((p["p90"] - p["p10"]) / p["p50"]).to_numpy()
    blad = np.abs(p["p50"].to_numpy() / wal["cena_pln"].to_numpy() - 1)
    przyjete = np.round(np.arange(0.5, 1.0001, 0.005), 3)
    ok = np.where(krzywa(szer, blad, przyjete) <= PROG_MAPE_BANKU)[0]
    return float(np.sort(szer)[int(round(przyjete[ok[-1]] * len(szer))) - 1])


def main(od_zera: bool = False) -> None:
    con = polacz()
    zal = wczytaj_zalozenia()
    df = wczytaj_transakcje_z_cechami(con)
    zb = {z: df[df["zbior"] == z].reset_index(drop=True) for z in ("trening", "walidacja", "test")}

    przedzial = ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lgbm_geo_cqr" / "model.joblib")
    detektor = joblib.load(KATALOG / "ood.joblib")
    v3 = ModelWycenyV3(przedzial=przedzial, detektor=detektor)
    max_szer = prog_szerokosci(v3, zb["walidacja"])
    v3b = ModelWycenyV3(przedzial=przedzial, detektor=detektor, max_szerokosc=max_szer)
    print(f"Wariant B: max_szerokosc = {max_szer:.4f} (próg z walidacji)\n")

    # 1. Metryki: v2_lgbm_geo_cqr (bez odmów) / v3 / v3 + szerokość.
    wyniki, wiersze = {}, []
    for z in ("walidacja", "test"):
        d, y = zb[z], zb[z]["cena_pln"].to_numpy(dtype=float)
        bez = przedzial.predict_interval(d).assign(odmowa=False)
        for nazwa, p in (
            ("v2_lgbm_geo_cqr (bez odmów)", bez),
            ("v3_przedzialy", v3.predict_interval(d)),
            ("v3_przedzialy + szerokość (wariant B)", v3b.predict_interval(d)),
        ):
            m = metryki_v3(y, p)
            wyniki.setdefault(nazwa, {})[z] = m
            wiersze.append(_wiersz(nazwa, z, m))
    print(f"### Metryki (błąd, pokrycie i szerokość na przyjętych)\n\n{_md(pd.DataFrame(wiersze))}\n")

    # 2. Odmowy: Katowice i Domilo, oba warianty.
    oferty = wczytaj_oferty(con)
    kat = oferty[oferty["miasto"] == "Katowice"].reset_index(drop=True)
    domilo = wczytaj_lokale_domilo(con)
    odmowy = []
    for nazwa, d in (("oferty z Katowic", kat), ("lokale Domilo", domilo)):
        for wariant, m in (("v3_przedzialy", v3), ("v3 + szerokość (B)", v3b)):
            p = m.predict_interval(d)
            odmowy.append(
                {"zbior": nazwa, "wariant": wariant, "lokale": int(len(d)), "odmowy": int(p["odmowa"].sum()),
                 "odmowy_proc": _f(100 * p["odmowa"].mean(), 1)}  # fmt: skip
            )
    print(f"### Odmowy: Katowice i Domilo\n\n{_md(pd.DataFrame(odmowy))}\n")
    p_dom_b = v3b.predict_interval(domilo)
    szeroki = p_dom_b["powod"].str.contains("Przedział za szeroki")
    print(
        "Domilo, wariant B: odmowy tylko za szerokość: "
        f"{int((szeroki & ~v3.predict_interval(domilo)['odmowa']).sum())}\n"
    )

    # 3. Koszt wycen wewnętrznych rocznie.
    roczne = con.execute(SQL_OPERATY_ROCZNE).df()
    print(f"### Operaty roczne w danych (typ = 'roczny')\n\n{_md(roczne)}\n")
    lokale_pms = int(con.execute("SELECT count(*) FROM pms_lokale").fetchone()[0])
    wolumen = int(roczne["lokale"].iloc[-1])
    k_op = zal["koszt_operatu_pln"]["wartosc"]
    k_ww = zal["koszt_wyceny_wewnetrznej_pln"]["wartosc"]
    probka = zal["probka_kontrolna_lokali"]["wartosc"]
    print(
        f"Wolumen roczny = lokale z operatem rocznym w {int(roczne['rok'].iloc[-1])}: {wolumen}; "
        f"pms_lokale: {lokale_pms}\n"
    )
    progi = progi_wg_kwantyla(detektor, zb["trening"])
    koszty = []
    for q, (pk, pi) in progi.items():
        for wariant, ms in (("v3 (OOD)", None), ("v3 + szerokość (B)", max_szer)):
            m = ModelWycenyV3(przedzial=przedzial, detektor=detektor, prog_knn=pk, prog_if=pi, max_szerokosc=ms)
            n_odm = int(m.predict_interval(domilo)["odmowa"].sum())
            udzial = n_odm / len(domilo)
            n_rok = udzial * wolumen
            koszty.append(
                {
                    "kwantyl_progu": _f(q, 3) + (" (propozycja)" if q == 0.99 else ""),
                    "wariant": wariant,
                    "odmowy_Domilo": n_odm,
                    "odmowy_proc": _f(100 * udzial, 1),
                    "wyceny_wewnetrzne_rocznie": _f(n_rok, 0),
                    "koszt_wycen_wewn_pln": _f(n_rok * k_ww, 0),
                }
            )
    print(
        f"### Koszt wycen wewnętrznych rocznie (wolumen {wolumen}, {k_ww} zł za wycenę)\n\n"
        f"{_md(pd.DataFrame(koszty))}\n"
    )
    print(
        "### Punkt odniesienia\n\n"
        + _md(
            pd.DataFrame(
                [
                    {"pozycja": "operaty roczne dziś (wolumen × koszt operatu)", "liczba": wolumen,
                     "koszt_pln": _f(wolumen * k_op, 0)},
                    {"pozycja": "jedna próbka kontrolna banku (próbka × koszt operatu)", "liczba": probka,
                     "koszt_pln": _f(probka * k_op, 0)},
                ]
            )  # fmt: skip
        )
        + "\n"
    )
    print(f"Pozycje zalozenia.yaml bez osoby odpowiedzialnej: {', '.join(bez_odpowiedzialnego(zal))}\n")

    # 4. Sprawdzenie: fit() od zera daje te same przedziały i odmowy.
    if od_zera:
        tr, wal, te = zb["trening"], zb["walidacja"], zb["test"]
        nowy = ModelWycenyV3().fit(tr, tr["cena_pln"], wal, wal["cena_pln"], poczatek_odlozonej=POCZATEK_ODLOZONEJ)
        a, b = v3.predict_interval(te), nowy.predict_interval(te)
        rozn = np.nanmax(np.abs(a[["p10", "p50", "p90"]].to_numpy() / b[["p10", "p50", "p90"]].to_numpy() - 1))
        print(
            f"fit() od zera: te same odmowy na teście: {bool((a['odmowa'] == b['odmowa']).all())}; "
            f"maks. względna różnica p10/p50/p90: {rozn:.2e}; "
            f"drzewa P50 {nowy.przedzial.punktowy.najlepsza_iteracja_}, "
            f"P10/P90 {nowy.przedzial.drzewa_}; korekta CQR {nowy.przedzial.korekta_:.6f} (zapisana "
            f"{przedzial.korekta_:.6f})\n"
        )

    # 5. Zapis wersji.
    v3.zapisz(KATALOG / "model.joblib")
    opis = {
        "wersja": v3.wersja,
        "skladniki": {
            "p50": "versions/v2_lgbm_geo/model.joblib (w v2_lgbm_geo_cqr/model.joblib)",
            "p10_p90": "versions/v2_lgbm_geo_cqr/model.joblib (kwantylowe LightGBM + CQR na walidacji)",
            "odmowa": "versions/v3_przedzialy/ood.joblib (reguły + kNN + Isolation Forest, "
            "progi kwantyl 0,99 treningu)",
        },
        "max_szerokosc": None,
        "wariant_B_max_szerokosc": max_szer,
        "policzono": date.today().isoformat(),
        "metryki": wyniki,
        "odmowy": odmowy,
        "koszty": {"wolumen_roczny": wolumen, "warianty": koszty},
    }
    (KATALOG / "metryki.json").write_text(json.dumps(opis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Zapisano versions/v3_przedzialy/model.joblib i metryki.json")


if __name__ == "__main__":
    main(od_zera="--od-zera" in sys.argv[1:])
