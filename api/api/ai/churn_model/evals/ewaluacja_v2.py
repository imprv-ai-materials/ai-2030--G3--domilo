"""Ewaluacja v2_przezycie_cox: hazard ratio, reszty Schoenfelda i C-index na najmach rozpoczętych od 2025-01.

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`):
    cd api && poetry run python -m api.ai.churn_model.evals.ewaluacja_v2 [--bez-mlflow]

Dane: okresy umów rocznych B2C / B2B z cechami v1 na początek okresu (features/najemcy/cechy_okresow.py).
- Trening: okresy z data_od 2023-04-01 – 2024-12-31, obserwacja ucięta na 2024-12-31 (model nie widzi nic
  późniejszego). Od 2023-04-01 okno płatności 90 dni jest pełne (pms_platnosci od 2023-01).
- Test: okresy najmów z data_wprowadzenia 2025-01-01 – 2026-09-30, obserwacja do 2026-09-30. Główny wynik:
  pierwszy okres (jeden wiersz na najem); dodatkowo wszystkie okresy tych najmów.
- Wrażliwość HR: ta sama specyfikacja na tych samych okresach treningu, ale z obserwacją do 2026-09-30.
Modele: `glowny` (wszystkie cechy jako współczynniki), `warstwy` (osobna krzywa bazowa dla 12 / 18 / 24 mies.),
`v2` = warstwy + interakcje z czasem (model.py: WARSTWY_V2, INTERAKCJE_V2), zapisywany jako v2_przezycie_cox.
Proporcjonalność: lifelines.statistics.proportional_hazard_test (skalowane reszty Schoenfelda, czas jako ranga)
dla modeli `glowny` i `warstwy`; progi p: 0,05 i Bonferroni 0,05 / liczba cech. Dla cech kluczowych także czas
`km` i `identity`. Diagnostyka (tylko trening): model `diagnostyka_okres` = v2 + interakcja z czasem (próg 11,5 mies.)
dla cech kluczowych, czyli HR „w trakcie okresu” i „na końcu okresu” (exp(β + β_po), wariancja sumy z macierzy
kowariancji); większość zdarzeń ma ten sam czas (koniec umowy), więc test z rangą czasu słabo widzi takie naruszenie.
C-index (Harrell): czas od początku okresu i zdarzenie z okresy_umow.sql, wynik = ryzyko 1 - S(12 mies.).
Kalibracja: średnie przewidywane S(12) (baza Kalbfleischa-Prentice'a, domyślna, i Breslowa z lifelines) wobec
Kaplana-Meiera w grupach: zbiór × linia × pierwszy okres / przedłużenie, tylko umowy 12-miesięczne.
Baseline: reguła „B2B najpierw” (wynik = 1 dla B2B, 0 dla B2C; remisy liczą się jako 0,5).
95% przedziały: bootstrap klastrów (najemców), 1 000 losowań, te same dla modelu i baseline.
Zapis: versions/v2_przezycie_cox/{model.joblib, metryki.json}, evals/wyniki/v2_przezycie_cox.parquet,
docs/img/cox_schoenfeld.png, MLflow (eksperyment `najemcy`).
"""

import json
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.churn_model.evals.przezycie import KATALOG_REPO, SIATKA, TLO, TUSZ, TUSZ_DRUGI
from api.ai.churn_model.versions.v2_przezycie_cox.model import (
    CECHY,
    HORYZONT_RYZYKA,
    INTERAKCJE_V2,
    WARSTWY_V2,
    ModelCox,
)
from api.ai.features.najemcy.cechy_okresow import zbior_okresow
from lifelines.statistics import proportional_hazard_test
from lifelines.utils import concordance_index

EKSPERYMENT_MLFLOW = "najemcy"
KATALOG_WERSJI = Path(__file__).resolve().parents[1] / "versions" / "v2_przezycie_cox"
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")
SCIEZKA_WYKRESU = KATALOG_REPO / "docs" / "img" / "cox_schoenfeld.png"
TRENING_OD, KONIEC_TRENINGU = "2023-04-01", "2024-12-31"
TEST_NAJMY_OD, KONIEC_DANYCH = "2025-01-01", "2026-09-30"
CECHY_KLUCZOWE = ("indeksacja_powyzej_6", "b2b", "windy_awarie_90d")
LOSOWANIA, ZIARNO = 1000, 42
BASELINE = "regula_b2b"


def zbiory(con) -> dict[str, pd.DataFrame]:
    tr = zbior_okresow(con, KONIEC_TRENINGU)
    tr = tr[tr["data_od"] >= TRENING_OD].reset_index(drop=True)
    wszystko = zbior_okresow(con, KONIEC_DANYCH)
    wrazliwosc = wszystko[wszystko["id_umowy"].isin(tr["id_umowy"])].reset_index(drop=True)
    test = wszystko[wszystko["data_wprowadzenia"] >= TEST_NAJMY_OD].reset_index(drop=True)
    return {"trening": tr, "trening_pelna_obserwacja": wrazliwosc, "test": test}


def test_ph(model: ModelCox, okresy: pd.DataFrame) -> pd.DataFrame:
    wynik = proportional_hazard_test(model.cph_, model.ramka_treningu(okresy), time_transform="rank").summary
    return wynik[["test_statistic", "p"]].sort_values("p")


def c_index(okresy: pd.DataFrame, wynik: np.ndarray) -> float:
    return float(concordance_index(okresy["czas"], -np.asarray(wynik, dtype=float), okresy["zdarzenie"]))


def bootstrap_c(okresy: pd.DataFrame, wyniki: dict[str, np.ndarray]) -> dict:
    """C-index i 95% CI dla każdego wyniku oraz różnic względem baseline i modelu głównego (klaster = najemca)."""
    rng = np.random.default_rng(ZIARNO)
    klastry = okresy["id_najemcy"].to_numpy()
    unikalne, odwrotne = np.unique(klastry, return_inverse=True)
    wiersze = [np.flatnonzero(odwrotne == i) for i in range(len(unikalne))]
    proby = {k: [] for k in wyniki}
    for _ in range(LOSOWANIA):
        idx = np.concatenate([wiersze[i] for i in rng.integers(0, len(unikalne), len(unikalne))])
        probka = okresy.iloc[idx]
        for k, w in wyniki.items():
            proby[k].append(c_index(probka, w[idx]))
    proby = {k: np.array(v) for k, v in proby.items()}
    wynik = {
        k: {"c_index": c_index(okresy, w), "ci_95": list(np.percentile(proby[k], [2.5, 97.5]))}
        for k, w in wyniki.items()
    }
    for k in wyniki:
        if k != BASELINE:
            wynik[f"{k}_minus_{BASELINE}"] = {
                "roznica": wynik[k]["c_index"] - wynik[BASELINE]["c_index"],
                "ci_95": list(np.percentile(proby[k] - proby[BASELINE], [2.5, 97.5])),
            }
    if "v2" in wyniki and "glowny" in wyniki:
        wynik["v2_minus_glowny"] = {
            "roznica": wynik["v2"]["c_index"] - wynik["glowny"]["c_index"],
            "ci_95": list(np.percentile(proby["v2"] - proby["glowny"], [2.5, 97.5])),
        }
    return wynik


def wykres_schoenfeld(model: ModelCox, okresy: pd.DataFrame, cechy: list[str], sciezka: Path = SCIEZKA_WYKRESU):
    """Skalowane reszty Schoenfelda (model główny): średnia w przedziałach czasu z 95% przedziałem i linia β."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ramka = model.ramka_treningu(okresy)
    reszty = model.cph_.compute_residuals(ramka, "scaled_schoenfeld")
    czas = ramka.loc[reszty.index, "czas"]
    przedzialy = pd.cut(czas, [0, 3, 6, 9, 11.5, 12.5, np.inf], labels=["0–3", "3–6", "6–9", "9–11,5", "≈12", ">12,5"])
    fig, osie = plt.subplots(2, 3, figsize=(13, 7), dpi=150, facecolor=TLO)
    for ax, cecha in zip(osie.flat, cechy):
        g = (reszty[cecha] + model.cph_.params_[cecha]).groupby(przedzialy, observed=False)
        sr, bl = g.mean(), 1.96 * g.std() / np.sqrt(g.size())
        x = np.arange(len(sr))
        ax.set_facecolor(TLO)
        ax.axhline(model.cph_.params_[cecha], color=TUSZ_DRUGI, lw=1, ls=":")
        ax.axhline(0, color=SIATKA, lw=1)
        ax.errorbar(x, sr, yerr=bl, fmt="o", ms=6, color="#2a78d6", ecolor="#2a78d6", elinewidth=2, capsize=0)
        ax.set_xticks(x, [f"{e}\n(n={n})" for e, n in zip(sr.index, g.size())], fontsize=7, color=TUSZ_DRUGI)
        ax.set_title(cecha, fontsize=10, color=TUSZ, loc="left")
        ax.grid(axis="y", color=SIATKA, lw=0.8)
        ax.tick_params(colors=TUSZ_DRUGI, length=0, labelsize=7)
        for bok in ("top", "right", "left"):
            ax.spines[bok].set_visible(False)
        ax.spines["bottom"].set_color(SIATKA)
    fig.suptitle(
        "β(t) = β + skalowana reszta Schoenfelda według czasu od początku okresu (mies.), średnia ± 95%; "
        "kropkowana linia = β z modelu. Proporcjonalność: punkty wokół β bez trendu",
        fontsize=10,
        color=TUSZ,
        x=0.01,
        ha="left",
    )
    fig.tight_layout()
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(sciezka, facecolor=TLO, bbox_inches="tight")
    plt.close(fig)


def kalibracja(model: ModelCox, zbiory_: dict[str, pd.DataFrame]) -> list[dict]:
    """Średnie przewidywane S(12) (KP i Breslow) wobec Kaplana-Meiera S(12) w grupach umów 12-miesięcznych."""
    from api.ai.churn_model.evals.przezycie import krzywa_km, przezycie_po

    wiersze = []
    for nazwa, d in zbiory_.items():
        for linia in ("B2C", "B2B"):
            for pierwszy in (True, False):
                x = d[(d["linia"] == linia) & (d["miesiecy_umowy"] == 12) & ((d["nr_okresu"] == 1) == pierwszy)]
                if len(x) < 50:
                    continue
                km = przezycie_po(krzywa_km(x.rename(columns={"czas": "miesiace"})), 12)
                wiersze.append(
                    {
                        "zbior": nazwa,
                        "linia": linia,
                        "okres": "pierwszy" if pierwszy else "przedluzenie",
                        "okresy": int(len(x)),
                        "km_S12": km,
                        "kp_S12": float(1 - model.ryzyko(x).mean()),
                        "breslow_S12": float(1 - model.ryzyko(x, metoda="breslow").mean()),
                    }
                )
    return wiersze


def _hr(model: ModelCox) -> dict:
    return model.hazard_ratio().to_dict("index")


def hr_na_koncu_okresu(model: ModelCox, cechy: tuple[str, ...], prog: float) -> dict:
    """HR w trakcie okresu (czas <= prog) i na jego końcu (exp(β + β_po)) z 95% przedziałem z kowariancji."""
    beta, V = model.cph_.params_, model.cph_.variance_matrix_
    wynik = {}
    for c in cechy:
        po = f"{c}_po_{prog:g}"
        suma = beta[c] + beta[po]
        se = float(np.sqrt(V.loc[c, c] + V.loc[po, po] + 2 * V.loc[c, po]))
        se_w = float(np.sqrt(V.loc[c, c]))
        wynik[c] = {
            "hr_w_trakcie": float(np.exp(beta[c])),
            "hr_w_trakcie_95": [float(np.exp(beta[c] - 1.96 * se_w)), float(np.exp(beta[c] + 1.96 * se_w))],
            "hr_na_koncu": float(np.exp(suma)),
            "hr_na_koncu_95": [float(np.exp(suma - 1.96 * se)), float(np.exp(suma + 1.96 * se))],
            "p_roznicy": float(model.cph_.summary.loc[po, "p"]),
        }
    return wynik


def main(z_mlflow: bool = True) -> dict:
    con = polacz()
    z = zbiory(con)
    con.close()
    tr, test = z["trening"], z["test"]
    cechy_glowne = tuple(k for k in CECHY)
    modele = {
        "glowny": ModelCox(warstwy=(), interakcje_czasu={}).fit(tr),
        "warstwy": ModelCox(warstwy=WARSTWY_V2, interakcje_czasu={}).fit(tr),
        "v2": ModelCox().fit(tr),
    }
    wrazliwosc = ModelCox().fit(z["trening_pelna_obserwacja"])
    ph = {k: test_ph(modele[k], tr) for k in ("glowny", "warstwy")}
    ramka_glowna = modele["glowny"].ramka_treningu(tr)
    ph_transformacje = {
        tt: proportional_hazard_test(modele["glowny"].cph_, ramka_glowna, time_transform=tt)
        .summary.loc[list(CECHY_KLUCZOWE), ["test_statistic", "p"]]
        .to_dict("index")
        for tt in ("rank", "km", "identity")
    }
    prog = INTERAKCJE_V2["czynsz_m2"]
    diagnostyka = ModelCox(interakcje_czasu={**INTERAKCJE_V2, **{c: prog for c in CECHY_KLUCZOWE}}).fit(tr)
    hr_okres = hr_na_koncu_okresu(diagnostyka, (*CECHY_KLUCZOWE, *INTERAKCJE_V2), prog)
    prog_bonferroni = 0.05 / len(cechy_glowne)

    pierwsze = test[test["nr_okresu"] == 1].reset_index(drop=True)
    oceny = {}
    for nazwa, zbior in (("test_pierwszy_okres", pierwsze), ("test_wszystkie_okresy", test)):
        wyniki = {k: m.ryzyko(zbior) for k, m in modele.items()}
        wyniki[BASELINE] = (zbior["linia"] == "B2B").to_numpy(dtype=float)
        oceny[nazwa] = bootstrap_c(zbior, wyniki)
        for linia in ("B2C", "B2B"):
            maska = (zbior["linia"] == linia).to_numpy()
            oceny[nazwa][f"v2_tylko_{linia}"] = c_index(zbior[maska], wyniki["v2"][maska])
            oceny[nazwa][f"glowny_tylko_{linia}"] = c_index(zbior[maska], wyniki["glowny"][maska])
    wykres_schoenfeld(modele["glowny"], tr, [*CECHY_KLUCZOWE, "miesiecy_umowy", "czynsz_m2", "zgl_365d"])

    opis_zbioru = lambda d: {  # noqa: E731
        "okresy": int(len(d)),
        "zdarzenia": int(d["zdarzenie"].sum()),
        "najmy": int(d["id_najmu"].nunique()),
        "najemcy": int(d["id_najemcy"].nunique()),
        "B2B_okresy": int((d["linia"] == "B2B").sum()),
        "miesiecy_umowy": {str(k): int(v) for k, v in d["miesiecy_umowy"].value_counts().sort_index().items()},
    }
    metryki = {
        "wersja": ModelCox.wersja,
        "zbiory": {
            "trening": {
                "opis": f"okresy z data_od {TRENING_OD} – {KONIEC_TRENINGU}, obserwacja do {KONIEC_TRENINGU}",
                **opis_zbioru(tr),
            },
            "trening_pelna_obserwacja": {
                "opis": f"te same okresy, obserwacja do {KONIEC_DANYCH}",
                **opis_zbioru(z["trening_pelna_obserwacja"]),
            },
            "test_pierwszy_okres": {
                "opis": f"najmy z data_wprowadzenia {TEST_NAJMY_OD} – {KONIEC_DANYCH}, okres 1",
                **opis_zbioru(pierwsze),
            },
            "test_wszystkie_okresy": {"opis": "wszystkie okresy tych najmów", **opis_zbioru(test)},
        },
        "specyfikacja_v2": {
            "warstwy": list(WARSTWY_V2),
            "interakcje_czasu": INTERAKCJE_V2,
            "horyzont_ryzyka_mies": HORYZONT_RYZYKA,
            "cechy": list(CECHY),
        },
        "zdarzenia_na_koncu_umowy_trening": int(
            np.isclose(tr.loc[tr["zdarzenie"] == 1, "czas"], tr.loc[tr["zdarzenie"] == 1, "miesiecy_umowy"]).sum()
        ),
        "korelacja_nr_okresu_staz_trening": float(tr["nr_okresu"].corr(tr["staz_dni"])),
        "hazard_ratio": {k: _hr(m) for k, m in modele.items()} | {"v2_pelna_obserwacja": _hr(wrazliwosc)},
        "proporcjonalnosc": {
            "prog_bonferroni": prog_bonferroni,
            **{k: v.to_dict("index") for k, v in ph.items()},
            "glowny_cechy_kluczowe_wg_transformacji_czasu": ph_transformacje,
        },
        "diagnostyka_hr_w_trakcie_i_na_koncu_okresu": hr_okres,
        "c_index": oceny,
        "kalibracja_S12": kalibracja(modele["v2"], {"trening": tr, "test": test}),
    }
    KATALOG_WERSJI.mkdir(parents=True, exist_ok=True)
    joblib.dump(modele["v2"], KATALOG_WERSJI / "model.joblib")
    sciezka_metryk = KATALOG_WERSJI / "metryki.json"
    sciezka_metryk.write_text(json.dumps(metryki, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    wyniki_testu = test[
        ["id_umowy", "id_najmu", "id_najemcy", "linia", "nr_okresu", "miesiecy_umowy", "data_od", "czas", "zdarzenie"]
    ].copy()
    for k, m in modele.items():
        wyniki_testu[f"ryzyko_{k}"] = m.ryzyko(test)
    sciezka_wynikow = KATALOG_WYNIKOW / "v2_przezycie_cox.parquet"
    wyniki_testu.to_parquet(sciezka_wynikow, index=False)

    if z_mlflow:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        glowne = oceny["test_pierwszy_okres"]
        for nazwa, rola in (("v2", "model"), (BASELINE, "baseline")):
            zapisz_run(
                ModelCox.wersja if nazwa == "v2" else BASELINE,
                parametry=(
                    {
                        "warstwy": ",".join(WARSTWY_V2),
                        "interakcje_czasu": json.dumps(INTERAKCJE_V2),
                        "zbior_treningu": metryki["zbiory"]["trening"]["opis"],
                    }
                    if nazwa == "v2"
                    else {"opis": "reguła: B2B najpierw (1 = B2B)"}
                )
                | {"zbior_testu": metryki["zbiory"]["test_pierwszy_okres"]["opis"]},
                metryki={
                    "test_c_index_pierwszy_okres": glowne[nazwa]["c_index"],
                    "test_c_index_wszystkie_okresy": oceny["test_wszystkie_okresy"][nazwa]["c_index"],
                },
                tagi={"model": "churn_model", "rola": rola},
                artefakty=[sciezka_metryk, sciezka_wynikow],
            )
    return metryki


if __name__ == "__main__":
    wynik = main(z_mlflow="--bez-mlflow" not in sys.argv)
    print(json.dumps({k: wynik[k] for k in ("zbiory", "c_index")}, ensure_ascii=False, indent=2, default=float))
    for k, hr in wynik["hazard_ratio"].items():
        print(f"\n## HR {k}")
        for c in (*CECHY_KLUCZOWE, "czynsz_m2", "czynsz_m2_po_11.5", "zgl_365d", "zgl_365d_po_11.5"):
            if c in hr:
                print(c, {a: round(b, 4) for a, b in hr[c].items()})
    print(
        "\n## PH transformacje", json.dumps(wynik["proporcjonalnosc"]["glowny_cechy_kluczowe_wg_transformacji_czasu"])
    )
    print("\n## HR w trakcie / na koncu", json.dumps(wynik["diagnostyka_hr_w_trakcie_i_na_koncu_okresu"], indent=1))
    for k in ("glowny", "warstwy"):
        print(f"\n## PH {k}")
        for c, v in list(wynik["proporcjonalnosc"][k].items())[:8]:
            print(c, {a: round(b, 5) for a, b in v.items()})
