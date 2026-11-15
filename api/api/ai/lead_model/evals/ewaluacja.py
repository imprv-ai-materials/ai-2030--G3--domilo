"""Ewaluacja wersji kolejki zapytań na oknie migracji CRM (2025-03-03 – 2025-04-13), docs/kolejka_v0_v1.md.

Uruchomienie (wymaga domilo.duckdb z tabelą leady_cel: `pypyr baza`; v1 woła API, więc klucz w środowisku):
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja [--bez-mlflow]

Zbiór oceny: wszystkie zapytania z okna migracji (`leady_cel.okno_migracji`). W oknie call center obsłużyło każde
zapytanie, więc wynik nie zależy od tego, do kogo doradcy oddzwonili (docs/kolejka_target.md).
- v0_regula_zrodla: konwersja (źródło × linia) z historii poza oknem (niecenzurowane zapytania przed i po oknie,
  zgodnie z poleceniem). Wrażliwość: tylko historia przed oknem; tylko obsłużone zapytania przed oknem.
- v1_llm_zero_shot: ocena LLM / 10 (bez uczenia), odpowiedzi z ai/llm/cache/ albo z API.
Miary: AUC, lift@10% i precision@k, k = średnia dzienna liczba nowych zapytań w oknie; 95% przedziały z bootstrapu
par (te same losowania dla obu wersji). Koszt / 1 000 zapytań: tokeny z wywołań × cennik z
leasing_bc/zalozenia.yaml (brak cennika = koszt nieznany, podajemy same tokeny).
Zapis: versions/<wersja>/{model.joblib, metryki.json}, evals/wyniki/okno_migracji.parquet, MLflow (eksperyment
`leady`).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.leady.zbior import wczytaj_zbior
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.evals.metryki import bootstrap_par, dzienna_liczba_zapytan, metryki_rankingu
from api.ai.lead_model.versions.v0_regula_zrodla.model import ModelRegulaZrodla
from api.ai.lead_model.versions.v1_llm_zero_shot.model import ModelLLMZeroShot
from api.contexts_boundaries.leasing_bc.zalozenia import koszt_na_1000_zapytan, wczytaj_zalozenia

EKSPERYMENT_MLFLOW = "leady"
KATALOG_MODELU = Path(__file__).resolve().parents[1]
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")
ZBIOR_OCENY = "okno_migracji (2025-03-03 – 2025-04-13)"
POCZATEK_OKNA = pd.Timestamp("2025-03-03", tz="Europe/Warsaw")
WATKI_LLM = 16


def _katalog(model: ModelLeadow) -> Path:
    return KATALOG_MODELU / "versions" / model.wersja


def _zapisz_wersje(model: ModelLeadow, metryki: dict) -> Path:
    katalog = _katalog(model)
    model.zapisz(katalog / "model.joblib")
    plik = katalog / "metryki.json"
    plik.write_text(json.dumps(metryki, ensure_ascii=False, indent=2), encoding="utf-8")
    return plik


def _mlflow(model: ModelLeadow, metryki: dict, parametry: dict) -> str:
    plaskie = {f"okno_{k}": v for k, v in metryki["okno_migracji"].items() if isinstance(v, (int, float))}
    plaskie.update({k: v for k, v in metryki["koszt_na_1000"].items() if isinstance(v, (int, float))})
    return zapisz_run(
        model.wersja,
        parametry={"wersja": model.wersja, **parametry},
        metryki=plaskie,
        tagi={"zbior_oceny": ZBIOR_OCENY, "target": "leady_cel.umowa_45d"},
        artefakty=[_katalog(model) / "metryki.json", _katalog(model) / "model.joblib"],
    )


def _koszt(wyjasnienie: pd.DataFrame | None, n: int, cennik: dict) -> dict:
    if wyjasnienie is None:  # wersja bez LLM: brak wywołań API
        return {"tokeny_wejscia": 0, "tokeny_wejscia_z_cache": 0, "tokeny_wyjscia": 0, "koszt": 0.0, "waluta": None}
    suma = {k: int(wyjasnienie[k].sum()) for k in ("tokeny_wejscia", "tokeny_wejscia_z_cache", "tokeny_wyjscia")}
    koszt = koszt_na_1000_zapytan(*suma.values(), n, cennik)
    return {k: v / n * 1000 for k, v in suma.items()} | {"koszt": koszt, "waluta": cennik.get("waluta")}


def main(mlflow_wlaczony: bool = True) -> None:
    con = polacz()
    zbior = wczytaj_zbior(con)
    con.close()
    okno = zbior[zbior["okno_migracji"]].reset_index(drop=True)
    historia = zbior[~zbior["okno_migracji"] & ~zbior["cenzurowany"]]
    przed = historia[historia["utworzono"] < POCZATEK_OKNA]
    y = okno["umowa_45d"].astype(int).to_numpy()
    k = dzienna_liczba_zapytan(okno["utworzono"])
    cennik = wczytaj_zalozenia()["cennik_llm"]["wartosc"]

    v0 = ModelRegulaZrodla().fit(historia, historia["umowa_45d"])
    wynik_v0 = v0.predict(okno)
    wrazliwosc_v0 = {}
    for nazwa, dane in {
        "historia_przed_oknem": przed,
        "historia_przed_oknem_tylko_obsluzone": przed[przed["obsluzony"]],
    }.items():
        wariant = ModelRegulaZrodla().fit(dane, dane["umowa_45d"])
        wrazliwosc_v0[nazwa] = {"zapytan_w_historii": len(dane), **metryki_rankingu(y, wariant.predict(okno), k)}

    v1 = ModelLLMZeroShot(watki=WATKI_LLM)
    wyjasnienie_v1 = v1.explain(okno)
    bledy_v1 = int(wyjasnienie_v1["wynik"].isna().sum())
    if bledy_v1:
        raise RuntimeError(f"v1: {bledy_v1} zapytań bez oceny (błąd API); uruchom ponownie, cache zachowa resztę")
    wynik_v1 = wyjasnienie_v1["wynik"].to_numpy()

    ci = bootstrap_par(y, wynik_v1, wynik_v0, k)
    wersje = {
        v0: {
            "uczony_na": "leady_cel: niecenzurowane zapytania poza oknem migracji (2023-01-01 – 2026-08-16)",
            "zapytan_w_historii": len(historia),
            "okno_migracji": metryki_rankingu(y, wynik_v0, k)
            | {"auc_ci95": ci["auc_b"], "lift_10_ci95": ci["lift_b"], "precision_k_ci95": ci["prec_b"]},
            "koszt_na_1000": _koszt(None, len(okno), cennik),
            "wrazliwosc": wrazliwosc_v0,
        },
        v1: {
            "uczony_na": "brak (zero-shot); prompt ocena_leada_v1, model gpt-6-luna, reasoning none, temperatura 0",
            "okno_migracji": metryki_rankingu(y, wynik_v1, k)
            | {"auc_ci95": ci["auc_a"], "lift_10_ci95": ci["lift_a"], "precision_k_ci95": ci["prec_a"]},
            "koszt_na_1000": _koszt(wyjasnienie_v1, len(okno), cennik),
            "odpowiedzi_z_cache": int(wyjasnienie_v1["z_cache"].sum()),
            "roznica_v1_minus_v0_ci95": {
                "auc": ci["auc_roznica"],
                "lift_10": ci["lift_roznica"],
                "precision_k": ci["prec_roznica"],
            },
        },
    }

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    okno[["id_leada", "utworzono", "zrodlo", "linia_pref", "umowa_45d"]].assign(
        wynik_v0=wynik_v0, **{f"v1_{c}": wyjasnienie_v1[c] for c in wyjasnienie_v1.columns}
    ).to_parquet(KATALOG_WYNIKOW / "okno_migracji.parquet", index=False)

    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
    for model, metryki in wersje.items():
        metryki = {"wersja": model.wersja, "zbior_oceny": ZBIOR_OCENY, **metryki}
        _zapisz_wersje(model, metryki)
        if mlflow_wlaczony:
            parametry = {"k": k, "zbior_oceny": ZBIOR_OCENY, "uczony_na": metryki["uczony_na"][:250]}
            if isinstance(model, ModelLLMZeroShot):
                parametry |= {"prompt": model.nazwa_promptu, "model_llm": model.model_llm}
            print(
                f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run {model.wersja} = {_mlflow(model, metryki, parametry)}"
            )
        print(json.dumps(metryki, ensure_ascii=False, indent=2, default=_json))


def _json(o):
    return o.item() if isinstance(o, np.generic) else str(o)


if __name__ == "__main__":
    main(mlflow_wlaczony="--bez-mlflow" not in sys.argv[1:])
