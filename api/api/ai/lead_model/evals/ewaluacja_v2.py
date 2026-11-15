"""Ewaluacja v2_lgbm_naiwny na zwykłym teście (2026-03 – 2026-06) i w oknie migracji, z v0 i v1 na tych samych
zapytaniach (docs/kolejka_v2_lgbm_naiwny.md).

Uruchomienie (wymaga domilo.duckdb z leady_cel: `pypyr baza`, oraz odpowiedzi v1 w ai/llm/cache dla treningu, testu
i okna: `python -m api.ai.features.leady.sygnaly_v1`; brakujące odpowiedzi v1 na teście i w oknie skrypt dociąga
z API, więc klucz w środowisku):
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja_v2 [--bez-mlflow]

- Trening (features/leady/podzial_v2.py): zamknięte zapytania 2023-01 – 2026-02 bez okna migracji; target
  `umowa_45d`, przy czym nieobsłużone zapytania (`obsluzony` = false) mają 0 („nieobsłużone = 0”).
- v0_regula_zrodla: uczona na tym samym zbiorze i tym samym targecie co v2 (w tym pliku nie nadpisujemy zapisanej
  wersji v0 z oceny okna, versions/v0_regula_zrodla/).
- v1_llm_zero_shot: ocena LLM / 10 z cache (bez uczenia).
- Ablacja: v2 bez każdej z rodzin cech (zapytanie, budzet, www, firma_b2b, tekst) i bez samych sygnałów LLM.
Miary jak w ewaluacja.py: AUC, lift@10%, precision@k (k = średnia dzienna liczba nowych zapytań w danym zbiorze),
95% CI z bootstrapu par (te same losowania dla wszystkich par wersji w zbiorze).
Zapis: versions/v2_lgbm_naiwny/{model.joblib, metryki.json}, evals/wyniki/v2_lgbm_naiwny.parquet, MLflow (`leady`).
"""

import json
import sys

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.leady.cechy import CECHY_RODZIN, KOLUMNY_CECH, RODZINY, SYGNALY_KOLUMNY, zbuduj_cechy
from api.ai.features.leady.podzial_v2 import OPIS, podziel
from api.ai.features.leady.sygnaly_v1 import wczytaj_sygnaly
from api.ai.features.leady.zbior import wczytaj_zbior
from api.ai.lead_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_MODELU, KATALOG_WYNIKOW
from api.ai.lead_model.evals.metryki import bootstrap_par, dzienna_liczba_zapytan, metryki_rankingu
from api.ai.lead_model.versions.v0_regula_zrodla.model import ModelRegulaZrodla
from api.ai.lead_model.versions.v1_llm_zero_shot.model import ModelLLMZeroShot
from api.ai.lead_model.versions.v2_lgbm_naiwny.model import ModelLGBMNaiwny

ZBIORY_OCENY = ("test", "okno_migracji")
WATKI_LLM = 32


def target_treningu(trening: pd.DataFrame) -> np.ndarray:
    """`umowa_45d`, ale nieobsłużone zapytania = 0 (naiwnie: brak kontaktu traktujemy jak brak umowy)."""
    return np.where(trening["obsluzony"], trening["umowa_45d"], 0).astype(int)


def przygotuj(con) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """(zbiory z wczytaj_zbior, cechy wyrównane wierszami do zbiorów: id_leada, utworzono + KOLUMNY_CECH)."""
    zbiory = podziel(wczytaj_zbior(con))
    sygnaly = wczytaj_sygnaly(pd.concat(zbiory.values(), ignore_index=True))
    cechy = zbuduj_cechy(con, sygnaly)
    wyrownane = {
        n: z[["id_leada", "utworzono"]].merge(cechy, on="id_leada", how="left", validate="1:1")
        for n, z in zbiory.items()
    }
    return zbiory, wyrownane


def _z_ci(metryki: dict, ci: dict, litera: str) -> dict:
    return metryki | {
        "auc_ci95": ci[f"auc_{litera}"],
        "lift_10_ci95": ci[f"lift_{litera}"],
        "precision_k_ci95": ci[f"prec_{litera}"],
    }


def _po_zrodle(zbior: pd.DataFrame, wyniki: dict[str, np.ndarray], y_tr: pd.DataFrame) -> list[dict]:
    """Źródło: konwersja w zbiorze, średni wynik wersji i udział w czołówce 10% każdej wersji."""
    n_czolowki = max(1, round(0.10 * len(zbior)))
    df = zbior[["zrodlo", "umowa_45d"]].copy()
    for nazwa, w in wyniki.items():
        df[nazwa] = w
        # czołówka po wyniku malejąco; przy remisach (v0, v1) kolejność losowa z ustalonym ziarnem
        losowe = np.random.default_rng(0).random(len(df))
        kolejnosc = np.lexsort((losowe, -np.asarray(w)))
        df[f"czolowka_{nazwa}"] = False
        df.iloc[kolejnosc[:n_czolowki], df.columns.get_loc(f"czolowka_{nazwa}")] = True
    trening = y_tr.groupby("zrodlo").agg(konwersja_treningu=("y", "mean"), obsluzone_treningu=("obsluzony", "mean"))
    wiersze = []
    for zrodlo, g in df.groupby("zrodlo"):
        w = {
            "zrodlo": zrodlo,
            "n": len(g),
            "umowy": int(g["umowa_45d"].sum()),
            "konwersja": float(g["umowa_45d"].mean()),
            "udzial_w_umowach": float(g["umowa_45d"].sum() / df["umowa_45d"].sum()),
            **{k: float(v) for k, v in trening.loc[zrodlo].items()},
        }
        for nazwa in wyniki:
            w[f"sredni_wynik_{nazwa}"] = float(g[nazwa].mean())
            w[f"udzial_czolowki_{nazwa}"] = float(g[f"czolowka_{nazwa}"].sum() / n_czolowki)
        wiersze.append(w)
    return wiersze


def main(mlflow_wlaczony: bool = True) -> None:
    con = polacz()
    zbiory, cechy = przygotuj(con)
    con.close()
    trening = zbiory["trening"]
    y_tr = target_treningu(trening)
    pokrycie_sygnalow = {n: float(c[SYGNALY_KOLUMNY[0]].notna().mean()) for n, c in cechy.items()}
    if min(pokrycie_sygnalow.values()) < 1.0:
        raise RuntimeError(f"Brak odpowiedzi v1 dla części zapytań: {pokrycie_sygnalow}; uruchom sygnaly_v1")

    v2 = ModelLGBMNaiwny().fit(cechy["trening"], y_tr)
    v0 = ModelRegulaZrodla().fit(trening, y_tr)
    v1 = ModelLLMZeroShot(watki=WATKI_LLM)
    ablacje = {f"bez_{r}": tuple(k for k in KOLUMNY_CECH if k not in CECHY_RODZIN[r]) for r in RODZINY}
    ablacje["bez_sygnalow_llm"] = tuple(k for k in KOLUMNY_CECH if k not in SYGNALY_KOLUMNY)
    modele_ablacji = {n: ModelLGBMNaiwny(cechy=c).fit(cechy["trening"], y_tr) for n, c in ablacje.items()}

    metryki = {
        "wersja": v2.wersja,
        "zbiory": OPIS,
        "uczony_na": OPIS["trening"] + "; target umowa_45d, nieobsłużone = 0",
        "trening": {
            "n": len(trening),
            "umowy_umowa_45d": int(trening["umowa_45d"].sum()),
            "pozytywne_po_nieobsluzone_0": int(y_tr.sum()),
            "umowy_nieobsluzonych_zamienione_na_0": int(trening["umowa_45d"].sum() - y_tr.sum()),
            "nieobsluzone": int((~trening["obsluzony"]).sum()),
            "liczba_drzew": v2.liczba_drzew_,
            "auc_walidacji_w_czasie": v2.auc_walidacji_,
            "walidacja_od": v2.granica_walidacji_,
        },
        "cechy": list(v2.cechy),
        "parametry": v2.parametry,
        "pokrycie_sygnalow_v1": pokrycie_sygnalow,
        "waznosc_cech": v2.waznosc_cech().to_dict("records"),
        "koszt_na_1000": {},
    }
    wyniki_plik = []
    for nazwa in ZBIORY_OCENY:
        zbior, X = zbiory[nazwa], cechy[nazwa]
        y = zbior["umowa_45d"].astype(int).to_numpy()
        k = dzienna_liczba_zapytan(zbior["utworzono"])
        wyj_v1 = v1.explain(zbior)
        if wyj_v1["wynik"].isna().any():
            raise RuntimeError(f"v1: {int(wyj_v1['wynik'].isna().sum())} zapytań bez oceny w zbiorze {nazwa}")
        wynik = {"v2": v2.predict(X), "v0": v0.predict(zbior), "v1": wyj_v1["wynik"].to_numpy()}
        ci_v0 = bootstrap_par(y, wynik["v2"], wynik["v0"], k)
        ci_v1 = bootstrap_par(y, wynik["v2"], wynik["v1"], k)
        metryki[nazwa] = {
            "v2_lgbm_naiwny": _z_ci(metryki_rankingu(y, wynik["v2"], k), ci_v0, "a"),
            "v0_regula_zrodla": _z_ci(metryki_rankingu(y, wynik["v0"], k), ci_v0, "b"),
            "v1_llm_zero_shot": _z_ci(metryki_rankingu(y, wynik["v1"], k), ci_v1, "b"),
            "roznica_v2_minus_v0_ci95": {m: ci_v0[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "roznica_v2_minus_v1_ci95": {m: ci_v1[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "ablacja": {n: metryki_rankingu(y, m.predict(X), k) for n, m in modele_ablacji.items()},
            "po_zrodle": _po_zrodle(zbior, wynik, trening[["zrodlo", "obsluzony"]].assign(y=y_tr)),
            "obsluzone_wsrod_czolowki_10_v2": None,
        }
        # Jaki odsetek czołówki v2 doradcy faktycznie obsłużyli (w oknie: 100% z definicji)
        czolowka = np.argsort(-wynik["v2"])[: max(1, round(0.10 * len(y)))]
        metryki[nazwa]["obsluzone_wsrod_czolowki_10_v2"] = float(zbior["obsluzony"].iloc[czolowka].mean())
        wyniki_plik.append(
            zbior[["id_leada", "utworzono", "zrodlo", "linia_pref", "obsluzony", "umowa_45d"]].assign(
                zbior=nazwa,
                wynik_v0=wynik["v0"],
                wynik_v1=wynik["v1"],
                wynik_v2=wynik["v2"],
                wynik_v2_bez_sygnalow_llm=modele_ablacji["bez_sygnalow_llm"].predict(X),
            )
        )
        kolumny_tokenow = ("tokeny_wejscia", "tokeny_wejscia_z_cache", "tokeny_wyjscia")
        tokeny = {c: float(wyj_v1[c].sum() / len(zbior) * 1000) for c in kolumny_tokenow}
        metryki["koszt_na_1000"][nazwa] = tokeny | {"uwaga": "tokeny v1 (sygnały); kwota: brak cennika"}

    katalog = KATALOG_MODELU / "versions" / v2.wersja
    v2.zapisz(katalog / "model.joblib")
    (katalog / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=2, default=_json), "utf-8")
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    pd.concat(wyniki_plik, ignore_index=True).to_parquet(KATALOG_WYNIKOW / "v2_lgbm_naiwny.parquet", index=False)

    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        plaskie = {
            f"{z}_{w}_{m}": metryki[z][w][m]
            for z in ZBIORY_OCENY
            for w in ("v2_lgbm_naiwny", "v0_regula_zrodla", "v1_llm_zero_shot")
            for m in ("auc", "lift_10", "precision_k")
        }
        plaskie |= {"liczba_drzew": v2.liczba_drzew_, "auc_walidacji_w_czasie": v2.auc_walidacji_}
        run = zapisz_run(
            v2.wersja,
            parametry={"wersja": v2.wersja, "uczony_na": metryki["uczony_na"][:250], "cechy": ",".join(v2.cechy)[:500],
                       **{k: v for k, v in v2.parametry.items() if k != "metric"}},  # fmt: skip
            metryki=plaskie,
            tagi={"zbior_oceny": "test 2026-03 – 2026-06 + okno migracji", "target": "leady_cel.umowa_45d"},
            artefakty=[katalog / "metryki.json", katalog / "model.joblib"],
        )
        print(f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run {v2.wersja} = {run}")
    print(json.dumps({z: {w: {m: metryki[z][w][m] for m in ("auc", "lift_10", "precision_k")}
                          for w in ("v2_lgbm_naiwny", "v0_regula_zrodla", "v1_llm_zero_shot")}
                      for z in ZBIORY_OCENY}, indent=2))  # fmt: skip


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    return str(o)


if __name__ == "__main__":
    main(mlflow_wlaczony="--bez-mlflow" not in sys.argv[1:])
