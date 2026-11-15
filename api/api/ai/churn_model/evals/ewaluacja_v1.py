"""Ewaluacja v1_ryzyko wobec punktu odniesienia `score_polityki` (retencja_decyzje) na teście 2026-04 – 2026-09.

Uruchomienie (wymaga domilo.duckdb z migawki_najemcy i cechami: `pypyr baza`):
    cd api && poetry run python -m api.ai.churn_model.evals.ewaluacja_v1 [--bez-mlflow]

- Podział: features/najemcy/zbior.py (trening: końce umów 2023-03 – 2025-12; test: 2026-04 – 2026-09).
- v1_ryzyko: LightGBM uczony na całym treningu (versions/v1_ryzyko/model.py).
- Baseline: `retencja_decyzje.score_polityki`, score dostawcy, według którego firma dziś daje oferty (bez uczenia).
- Reguła kontrolna `regula_b2b_potem_score`: najpierw umowy B2B, w każdej linii według score_polityki. Sprawdza, ile
  przewagi v1 w całym teście daje samo ustawienie B2B na górze listy (B2B odchodzi znacznie częściej).
- Miary (evals/metryki.py): AUC, recall / precyzja / lift w górnym decylu; 95% CI z bootstrapu par (2 000 losowań,
  te same dla modelu i baseline). Segmenty testu: wszystkie, bez wypowiedzenia przed migawką, B2C, B2B, okres
  polityki z retencja_decyzje.
Zapis: versions/v1_ryzyko/{model.joblib, metryki.json}, evals/wyniki/v1_ryzyko.parquet, MLflow (`najemcy`).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.churn_model.evals.metryki import bootstrap_par, k_decyla, metryki_rankingu, odejscia_w_czolowce
from api.ai.churn_model.versions.v1_ryzyko.model import PARAMETRY, ModelRyzyko
from api.ai.features.najemcy.zbior import OPIS, podziel, wczytaj_zbior

EKSPERYMENT_MLFLOW = "najemcy"
KATALOG_MODELU = Path(__file__).resolve().parents[1]
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")
BASELINE = "score_polityki"
REGULA_LINII = "regula_b2b_potem_score"


def segmenty(test: pd.DataFrame) -> dict[str, np.ndarray]:
    seg = {
        "wszystkie": np.ones(len(test), dtype=bool),
        "bez_wypowiedzenia_przed_migawka": ~test["wypowiedzenie_przed_migawka"].to_numpy(dtype=bool),
        "B2C": (test["linia_umowy"] == "B2C").to_numpy(),
        "B2B": (test["linia_umowy"] == "B2B").to_numpy(),
    }
    for okres in sorted(test["okres"].dropna().unique()):
        seg[f"okres_{okres}"] = (test["okres"] == okres).to_numpy()
    return seg


def udzial_b2b_w_decylu(b2b: np.ndarray, wynik: np.ndarray) -> float:
    """Oczekiwany udział umów B2B w górnym decylu (remis na granicy jak w metryki.odejscia_w_czolowce)."""
    k = k_decyla(len(wynik))
    return odejscia_w_czolowce(b2b, wynik, k) / k


def rankingi_odniesienia(test: pd.DataFrame) -> dict[str, np.ndarray]:
    """Punkt odniesienia (score_polityki) i reguła kontrolna: najpierw B2B, w linii według score_polityki."""
    score = test[BASELINE].to_numpy(dtype=float)
    b2b = (test["linia_umowy"] == "B2B").to_numpy(dtype=float)
    return {BASELINE: score, REGULA_LINII: b2b + score}


def ocen(test: pd.DataFrame, ryzyko: np.ndarray) -> dict:
    wyniki = {}
    y = test["odejdzie"].to_numpy(dtype=int)
    b2b = (test["linia_umowy"] == "B2B").to_numpy(dtype=float)
    odniesienia = rankingi_odniesienia(test)
    for nazwa, maska in segmenty(test).items():
        seg = {}
        for nazwa_odn, wynik_odn in odniesienia.items():
            ci = bootstrap_par(y[maska], ryzyko[maska], wynik_odn[maska])
            seg.setdefault(
                "v1_ryzyko",
                metryki_rankingu(y[maska], ryzyko[maska])
                | {
                    "auc_ci95": ci["auc_a"],
                    "recall_10_ci95": ci["recall_a"],
                    "udzial_b2b_w_decylu": udzial_b2b_w_decylu(b2b[maska], ryzyko[maska]),
                },
            )
            seg[nazwa_odn] = metryki_rankingu(y[maska], wynik_odn[maska]) | {
                "auc_ci95": ci["auc_b"],
                "recall_10_ci95": ci["recall_b"],
                "udzial_b2b_w_decylu": udzial_b2b_w_decylu(b2b[maska], wynik_odn[maska]),
            }
            seg[f"roznica_v1_minus_{nazwa_odn}"] = {
                "auc_ci95": ci["auc_roznica"],
                "recall_10_ci95": ci["recall_roznica"],
            }
        wyniki[nazwa] = seg
    return wyniki


def main(z_mlflow: bool = True) -> dict:
    with polacz() as con:
        zbiory = podziel(wczytaj_zbior(con))
    trening, test = zbiory["trening"], zbiory["test"]
    if test[BASELINE].isna().any():
        raise ValueError("Test: brak score_polityki dla części umów")

    model = ModelRyzyko().fit(trening, trening["odejdzie"])
    katalog_wersji = KATALOG_MODELU / "versions" / model.wersja
    model.zapisz(katalog_wersji / "model.joblib")
    ryzyko = model.predict(test)

    metryki = {
        "wersja": model.wersja,
        "zbiory": OPIS,
        "trening": {
            "n": int(len(trening)),
            "odejscia": int(trening["odejdzie"].sum()),
            "miesiac_konca_od": str(trening["miesiac_konca"].min().date()),
            "miesiac_konca_do": str(trening["miesiac_konca"].max().date()),
            "liczba_drzew": model.liczba_drzew_,
            "auc_walidacji_w_czasie": model.auc_walidacji_,
            "walidacja_migawki_po": model.granica_walidacji_,
        },
        "test": {
            "n": int(len(test)),
            "odejscia": int(test["odejdzie"].sum()),
            "miesiac_konca_od": str(test["miesiac_konca"].min().date()),
            "miesiac_konca_do": str(test["miesiac_konca"].max().date()),
            "data_migawki_od": str(test["data_migawki"].min().date()),
            "data_migawki_do": str(test["data_migawki"].max().date()),
        },
        "cechy": list(model.cechy),
        "parametry": PARAMETRY,
        "wyniki": ocen(test, ryzyko),
        "waznosc_cech": model.waznosc_cech().head(15).to_dict("records"),
    }
    sciezka_metryk = katalog_wersji / "metryki.json"
    sciezka_metryk.write_text(json.dumps(metryki, ensure_ascii=False, indent=2), encoding="utf-8")

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    wyniki_testu = test[["id_umowy", "miesiac_konca", "linia_umowy", "okres", "grupa", "odejdzie", BASELINE]].copy()
    wyniki_testu["wypowiedzenie_przed_migawka"] = test["wypowiedzenie_przed_migawka"].astype(bool)
    wyniki_testu["ryzyko_v1"] = ryzyko
    wyniki_testu[REGULA_LINII] = rankingi_odniesienia(test)[REGULA_LINII]
    sciezka_wynikow = KATALOG_WYNIKOW / "v1_ryzyko.parquet"
    wyniki_testu.to_parquet(sciezka_wynikow, index=False)

    if z_mlflow:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        wsp = metryki["wyniki"]
        bez = "bez_wypowiedzenia_przed_migawka"
        opisy = {
            BASELINE: "retencja_decyzje.score_polityki (score dostawcy), bez uczenia",
            REGULA_LINII: "reguła kontrolna: najpierw B2B, w linii według score_polityki",
        }
        role = {model.wersja: "model", BASELINE: "baseline", REGULA_LINII: "regula_kontrolna"}
        for nazwa in (model.wersja, BASELINE, REGULA_LINII):
            zapisz_run(
                nazwa,
                parametry=(
                    {"zbior_treningu": OPIS["trening"], "liczba_drzew": model.liczba_drzew_, **PARAMETRY}
                    if nazwa == model.wersja
                    else {"opis": opisy[nazwa]}
                )
                | {"zbior_testu": OPIS["test"]},
                metryki={
                    "test_auc": wsp["wszystkie"][nazwa]["auc"],
                    "test_recall_10": wsp["wszystkie"][nazwa]["recall_10"],
                    "test_precision_10": wsp["wszystkie"][nazwa]["precision_10"],
                    "test_lift_10": wsp["wszystkie"][nazwa]["lift_10"],
                    "test_bez_wyp_auc": wsp[bez][nazwa]["auc"],
                    "test_bez_wyp_recall_10": wsp[bez][nazwa]["recall_10"],
                    "test_b2c_auc": wsp["B2C"][nazwa]["auc"],
                    "test_b2b_auc": wsp["B2B"][nazwa]["auc"],
                },
                tagi={"model": "churn_model", "rola": role[nazwa]},
                artefakty=[sciezka_metryk, sciezka_wynikow],
            )
    return metryki


if __name__ == "__main__":
    wynik = main(z_mlflow="--bez-mlflow" not in sys.argv)
    print(json.dumps({k: wynik[k] for k in ("trening", "test")}, ensure_ascii=False, indent=2))
    for seg, w in wynik["wyniki"].items():
        print(f"\n## {seg}")
        for nazwa, m in w.items():
            print(nazwa, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()})
    print("\n## waznosc_cech")
    for r in wynik["waznosc_cech"]:
        print(f"{r['cecha']}: {r['udzial']:.3f}")
