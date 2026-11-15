"""Ewaluacja v2b_lgbm_ipw (LightGBM na obsłużonych, waga 1 / P(obsłużony) przycięta do 10) w oknie migracji i na
zwykłym teście, z v0, v1 i v2_lgbm_naiwny na tych samych zapytaniach (docs/kolejka_bias.md, część v2b).

Uruchomienie (po `pypyr baza`; sygnały v1 muszą być w ai/llm/cache, patrz ewaluacja_v2.py):
    cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja_v2b [--bez-mlflow]

- Zbiór uczący: ten sam co dla v2 (features/leady/podzial_v2.py), czyli dane spoza okna migracji. Model skłonności
  uczy się na wszystkich 127 527 zapytaniach, LightGBM tylko na obsłużonych (wynik po 45 dniach jest znany dla
  wszystkich, bo zbiór nie zawiera zapytań cenzurowanych), target `umowa_45d` bez zmian.
- v2_lgbm_naiwny: zapisany model (versions/v2_lgbm_naiwny/model.joblib), bez ponownego uczenia.
- v0_regula_zrodla: jak w ewaluacja_v2.py (ten sam trening, „nieobsłużone = 0”), żeby baseline był ten sam.
- Wariant kontrolny `v2b_bez_wag`: LightGBM tylko na obsłużonych, bez wag. Pokazuje, ile daje samo wykluczenie
  nieobsłużonych, a ile wagi.
Miary jak w ewaluacja_v2.py; 95% CI z bootstrapu par (te same losowania dla par v2b–v0, v2b–v2, v2b–v1).
Zapis: versions/v2b_lgbm_ipw/{model.joblib, metryki.json}, evals/wyniki/v2b_lgbm_ipw.parquet, MLflow (`leady`).
"""

import json
import sys

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.leady.ocena_llm import _bez_imienia
from api.ai.features.leady.podzial_v2 import OPIS
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_MODELU, KATALOG_WYNIKOW
from api.ai.lead_model.evals.ewaluacja_v2 import ZBIORY_OCENY, _json, _po_zrodle, _z_ci, przygotuj, target_treningu
from api.ai.lead_model.evals.metryki import bootstrap_par, dzienna_liczba_zapytan, metryki_rankingu
from api.ai.lead_model.versions.v0_regula_zrodla.model import ModelRegulaZrodla
from api.ai.lead_model.versions.v1_llm_zero_shot.model import ModelLLMZeroShot
from api.ai.lead_model.versions.v2_lgbm_naiwny.model import ModelLGBMNaiwny
from api.ai.lead_model.versions.v2b_lgbm_ipw.model import ModelLGBMIPW
from sklearn.metrics import roc_auc_score

KWANTYLE_WAG = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0)
KOLUMNY_TOP = (
    "id_leada",
    "utworzono",
    "zrodlo",
    "miasto",
    "linia",
    "budzet_do_mediany",
    "termin_dni",
    "liczba_osob",
    "dlugosc_wiadomosci",
    "www_liczba_sesji",
)
DLUGOSC_FRAGMENTU = 120


def _rozklad_wag(model: ModelLGBMIPW, X_obsl: pd.DataFrame, zrodlo: pd.Series, y: np.ndarray) -> dict:
    w = model.wagi(X_obsl)
    df = pd.DataFrame({"zrodlo": zrodlo.to_numpy(), "waga": w, "y": y})
    po_zrodle = (
        df.groupby("zrodlo")
        .agg(
            obsluzone=("waga", "size"),
            srednia_waga=("waga", "mean"),
            mediana_wagi=("waga", "median"),
            maks_waga=("waga", "max"),
            suma_wag=("waga", "sum"),
            przyciete=("waga", lambda s: int((s >= model.maks_waga).sum())),
            umowy=("y", "sum"),
        )
        .reset_index()
    )
    po_zrodle["udzial_w_sumie_wag"] = po_zrodle["suma_wag"] / w.sum()
    po_zrodle["udzial_w_obsluzonych"] = po_zrodle["obsluzone"] / len(w)
    progi = [1, 1.25, 1.5, 2, 3, 5, 10, np.inf]
    przedzialy = pd.cut(pd.Series(w), bins=progi, right=False).value_counts(sort=False)
    return {
        "kwantyle": {f"q{int(q * 100):02d}": float(np.quantile(w, q)) for q in KWANTYLE_WAG},
        "srednia": float(w.mean()),
        "histogram": {str(k): int(v) for k, v in przedzialy.items()},
        "po_zrodle": po_zrodle.to_dict("records"),
        **model.statystyki_wag_,
    }


def _top_wagi(model: ModelLGBMIPW, X_obsl: pd.DataFrame, zbior_obsl: pd.DataFrame, n: int = 5) -> list[dict]:
    p = model.sklonnosc(X_obsl)
    kolejnosc = np.argsort(p)[:n]  # najmniejsza skłonność = największa waga
    wiersze = []
    for i in kolejnosc:
        lead = zbior_obsl.iloc[i]
        tresc = lead["wiadomosc"]
        fragment = None if pd.isna(tresc) else _bez_imienia(str(tresc), lead["imie"])[:DLUGOSC_FRAGMENTU]
        wiersze.append(
            {k: X_obsl.iloc[i][k] for k in KOLUMNY_TOP}
            | {
                "sklonnosc": float(p[i]),
                "waga_przed_przycieciem": float(1 / p[i]),
                "waga": float(min(1 / p[i], model.maks_waga)),
                "umowa_45d": int(lead["umowa_45d"]),
                "sygnaly": ",".join(
                    c.removeprefix("syg_") for c in X_obsl.columns if c.startswith("syg_") and X_obsl.iloc[i][c] == 1
                ),
                "wiadomosc_fragment": fragment,
            }
        )
    return wiersze


def _sklonnosc_po_zrodle(model: ModelLGBMIPW, X: pd.DataFrame, zbior: pd.DataFrame) -> list[dict]:
    df = pd.DataFrame({"zrodlo": zbior["zrodlo"], "obsluzony": zbior["obsluzony"], "p": model.sklonnosc(X)})
    return (
        df.groupby("zrodlo")
        .agg(zapytania=("p", "size"), obsluzone=("obsluzony", "mean"), srednia_sklonnosc=("p", "mean"))
        .reset_index()
        .to_dict("records")
    )


def main(mlflow_wlaczony: bool = True) -> None:
    con = polacz()
    zbiory, cechy = przygotuj(con)
    con.close()
    trening = zbiory["trening"]
    X_tr = cechy["trening"].assign(obsluzony=trening["obsluzony"].to_numpy())
    y_tr = trening["umowa_45d"].astype(int).to_numpy()
    obsl_tr = trening["obsluzony"].to_numpy(dtype=bool)

    v2b = ModelLGBMIPW().fit(X_tr, y_tr)
    v2b_bez_wag = ModelLGBMNaiwny().fit(X_tr[obsl_tr].reset_index(drop=True), y_tr[obsl_tr])
    v2 = ModelLeadow.wczytaj(KATALOG_MODELU / "versions" / "v2_lgbm_naiwny" / "model.joblib")
    v0 = ModelRegulaZrodla().fit(trening, target_treningu(trening))
    v1 = ModelLLMZeroShot(watki=32)

    X_tr_obsl = X_tr[obsl_tr].reset_index(drop=True)
    metryki = {
        "wersja": v2b.wersja,
        "zbiory": OPIS,
        "uczony_na": (
            "skłonność: regresja logistyczna na wszystkich zapytaniach treningu (" + OPIS["trening"] + "); "
            "LightGBM: tylko obsłużone z treningu, target umowa_45d, waga min(1/P(obsłużony), 10)"
        ),
        "trening": {
            "n_wszystkich": len(trening),
            "n_obsluzonych": int(obsl_tr.sum()),
            "umowy_obsluzonych": int(y_tr[obsl_tr].sum()),
            "liczba_drzew": v2b.liczba_drzew_,
            "auc_walidacji_w_czasie_wazone": v2b.auc_walidacji_,
            "walidacja_od": v2b.granica_walidacji_,
            "liczba_drzew_v2b_bez_wag": v2b_bez_wag.liczba_drzew_,
        },
        "cechy": list(v2b.cechy),
        "parametry": v2b.parametry | {"maks_waga": v2b.maks_waga},
        "sklonnosc": {
            "model": "LogisticRegression (one-hot kategorii; mediana + wskaźnik braku, standaryzacja liczb)",
            "auc_trening": float(roc_auc_score(obsl_tr, v2b.sklonnosc(X_tr))),
            "auc_test": float(roc_auc_score(zbiory["test"]["obsluzony"], v2b.sklonnosc(cechy["test"]))),
            "po_zrodle_trening": _sklonnosc_po_zrodle(v2b, X_tr, trening),
            "po_zrodle_test": _sklonnosc_po_zrodle(v2b, cechy["test"], zbiory["test"]),
            "srednia_okno_migracji": float(v2b.sklonnosc(cechy["okno_migracji"]).mean()),
        },
        "wagi": _rozklad_wag(v2b, X_tr_obsl, trening.loc[obsl_tr, "zrodlo"], y_tr[obsl_tr]),
        "top5_wag": _top_wagi(v2b, X_tr_obsl, trening[obsl_tr].reset_index(drop=True)),
        "waznosc_cech": v2b.waznosc_cech().to_dict("records"),
    }

    wyniki_plik = []
    for nazwa in ZBIORY_OCENY:
        zbior, X = zbiory[nazwa], cechy[nazwa]
        y = zbior["umowa_45d"].astype(int).to_numpy()
        k = dzienna_liczba_zapytan(zbior["utworzono"])
        wynik_v1 = v1.explain(zbior)["wynik"].to_numpy()
        if np.isnan(wynik_v1).any():
            raise RuntimeError(f"v1: brak ocen w zbiorze {nazwa} (uruchom sygnaly_v1)")
        wynik = {
            "v2b": v2b.predict(X),
            "v0": v0.predict(zbior),
            "v1": wynik_v1,
            "v2": v2.predict(X),
        }
        ci_v0 = bootstrap_par(y, wynik["v2b"], wynik["v0"], k)
        ci_v2 = bootstrap_par(y, wynik["v2b"], wynik["v2"], k)
        ci_v1 = bootstrap_par(y, wynik["v2b"], wynik["v1"], k)
        obsl = zbior["obsluzony"].to_numpy(dtype=bool)
        wynik_bez_wag = v2b_bez_wag.predict(X)
        metryki[nazwa] = {
            "v2b_lgbm_ipw": _z_ci(metryki_rankingu(y, wynik["v2b"], k), ci_v0, "a")
            | {"sredni_wynik": float(wynik["v2b"].mean())},
            "v0_regula_zrodla": _z_ci(metryki_rankingu(y, wynik["v0"], k), ci_v0, "b"),
            "v1_llm_zero_shot": _z_ci(metryki_rankingu(y, wynik["v1"], k), ci_v1, "b"),
            "v2_lgbm_naiwny": _z_ci(metryki_rankingu(y, wynik["v2"], k), ci_v2, "b")
            | {"sredni_wynik": float(wynik["v2"].mean())},
            "v2b_bez_wag": metryki_rankingu(y, wynik_bez_wag, k) | {"sredni_wynik": float(wynik_bez_wag.mean())},
            "roznica_v2b_minus_v0_ci95": {m: ci_v0[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "roznica_v2b_minus_v2_ci95": {m: ci_v2[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "roznica_v2b_minus_v1_ci95": {m: ci_v1[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "konwersja_obsluzonych": float(y[obsl].mean()),
            "obsluzone": float(obsl.mean()),
            "auc_tylko_obsluzone": {w: float(roc_auc_score(y[obsl], wynik[w][obsl])) for w in ("v2b", "v2", "v0")},
            "auc_wyniku_dla_obsluzenia": (
                {w: float(roc_auc_score(obsl, wynik[w])) for w in ("v2b", "v2")} if 0 < obsl.sum() < len(obsl) else None
            ),
            "po_zrodle": _po_zrodle(zbior, wynik, trening[["zrodlo", "obsluzony"]].assign(y=target_treningu(trening))),
        }
        wyniki_plik.append(
            zbior[["id_leada", "utworzono", "zrodlo", "linia_pref", "obsluzony", "umowa_45d"]].assign(
                zbior=nazwa,
                wynik_v0=wynik["v0"],
                wynik_v1=wynik["v1"],
                wynik_v2=wynik["v2"],
                wynik_v2b=wynik["v2b"],
                wynik_v2b_bez_wag=wynik_bez_wag,
                sklonnosc=v2b.sklonnosc(X),
            )
        )

    katalog = KATALOG_MODELU / "versions" / v2b.wersja
    v2b.zapisz(katalog / "model.joblib")
    (katalog / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=2, default=_json), "utf-8")
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    pd.concat(wyniki_plik, ignore_index=True).to_parquet(KATALOG_WYNIKOW / "v2b_lgbm_ipw.parquet", index=False)

    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        plaskie = {
            f"{z}_{w}_{m}": metryki[z][w][m]
            for z in ZBIORY_OCENY
            for w in ("v2b_lgbm_ipw", "v0_regula_zrodla", "v1_llm_zero_shot", "v2_lgbm_naiwny", "v2b_bez_wag")
            for m in ("auc", "lift_10", "precision_k")
        }
        plaskie |= {
            "liczba_drzew": v2b.liczba_drzew_,
            "auc_sklonnosci_test": metryki["sklonnosc"]["auc_test"],
            "efektywna_liczebnosc": metryki["wagi"]["efektywna_liczebnosc"],
            "wagi_przyciete": metryki["wagi"]["przyciete"],
        }
        run = zapisz_run(
            v2b.wersja,
            parametry={
                "wersja": v2b.wersja,
                "uczony_na": metryki["uczony_na"][:250],
                "maks_waga": v2b.maks_waga,
                "model_sklonnosci": "LogisticRegression",
                "cechy": ",".join(v2b.cechy)[:500],
                **{k: v for k, v in v2b.parametry.items() if k != "metric"},
            },
            metryki=plaskie,
            tagi={"zbior_oceny": "okno migracji + test 2026-03 – 2026-06", "target": "leady_cel.umowa_45d"},
            artefakty=[katalog / "metryki.json", katalog / "model.joblib"],
        )
        print(f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run {v2b.wersja} = {run}")
    for z in ZBIORY_OCENY:
        for w in ("v0_regula_zrodla", "v1_llm_zero_shot", "v2_lgbm_naiwny", "v2b_bez_wag", "v2b_lgbm_ipw"):
            print(z, w, {m: round(float(metryki[z][w][m]), 4) for m in ("auc", "lift_10", "precision_k")})


if __name__ == "__main__":
    main(mlflow_wlaczony="--bez-mlflow" not in sys.argv[1:])
