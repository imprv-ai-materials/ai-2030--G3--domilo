"""Ewaluacja v2_lgbm_losowy i v2b_lgbm_czas_winda (wyniki: evals/porownanie.md, MLflow eksperyment `windy`).

Dane: features/windy/zbior.py (dni_wind + cechy_windy + cechy tsfresh wybrane na treningu 2023-03 – 2025-06).
- v2_lgbm_losowy, `podzial_losowy`: każdy wiersz losowo (ziarno ZIARNO_PODZIALU): 20% test, 10% walidacja
  (wczesne zatrzymanie), 70% trening; razem trening + walidacja = 80%.
- v2b_lgbm_czas_winda, `podzial_czas_winda`: trening 2023-03-01 – 2025-06-30, walidacja 2025-07-01 – 2025-12-31,
  test 2026-01-01 – 2026-09-22; WIND_POZA = 28 wind (20% ze 140) o najmniejszym md5(id_windy || ':' || SOL)
  nie trafia do treningu ani walidacji. Test raportujemy razem i osobno dla wind widzianych / niewidzianych.
Miary: ROC AUC, PR-AUC (average precision), odsetek dodatnich, PR-AUC / odsetek dodatnich; 95% CI z bootstrapu
wind (klaster = winda, LOSOWAN losowań). Baseline (evals/porownanie.md w katalogu głównym): reguła
`drzwi_ponowne_otwarcia_do_normy_24h` (wybrana na treningu 2023-03 – 2025-06, docs/b4_tsfresh.md) na tych samych
zbiorach testowych.
Uruchomienie (z api/): `python -m api.ai.failure_model.evals.ewaluacja_v2 [--bez-mlflow]`.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from api.ai.failure_model.versions.v2_lgbm_losowy.model import ModelLGBMWind
from api.ai.failure_model.versions.v2b_lgbm_czas_winda.model import ModelLGBMCzasWinda
from sklearn.metrics import average_precision_score, roc_auc_score

KATALOG_WERSJI = Path(__file__).resolve().parents[1] / "versions"
ZIARNO_PODZIALU = 2026
SOL = "v2b_lgbm_czas_winda"
WIND_POZA = 28
TRENING = ("2023-03-01", "2025-06-30")
WALIDACJA = ("2025-07-01", "2025-12-31")
TEST = ("2026-01-01", "2026-09-22")
LOSOWAN = 1000
REGULA = "drzwi_ponowne_otwarcia_do_normy_24h"


# --- podziały ------------------------------------------------------------------------------------------------


def podzial_losowy(df: pd.DataFrame, ziarno: int = ZIARNO_PODZIALU) -> dict[str, np.ndarray]:
    u = np.random.default_rng(ziarno).random(len(df))
    return {"trening": u >= 0.3, "walidacja": (u >= 0.2) & (u < 0.3), "test": u < 0.2}


def windy_poza_treningiem(windy: pd.Series, n: int = WIND_POZA, sol: str = SOL) -> list[str]:
    unikalne = sorted(set(windy))
    return sorted(unikalne, key=lambda w: hashlib.md5(f"{w}:{sol}".encode()).hexdigest())[:n]


def podzial_czas_winda(df: pd.DataFrame) -> tuple[dict[str, np.ndarray], list[str]]:
    poza = windy_poza_treningiem(df["id_windy"])
    nowe = df["id_windy"].isin(poza).to_numpy()
    dzien = df["dzien"]
    maski = {
        "trening": dzien.between(*TRENING).to_numpy() & ~nowe,
        "walidacja": dzien.between(*WALIDACJA).to_numpy() & ~nowe,
        "test": dzien.between(*TEST).to_numpy(),
    }
    maski["test_windy_widziane"] = maski["test"] & ~nowe
    maski["test_windy_niewidziane"] = maski["test"] & nowe
    return maski, poza


# --- miary ---------------------------------------------------------------------------------------------------


def wynik_reguly(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype="float64")
    return np.where(np.isnan(x), np.nanmin(x) - 1, x)


def ocen(zbior: pd.DataFrame, wynik: np.ndarray, ziarno: int = 7) -> dict:
    """ROC AUC, PR-AUC z 95% CI (bootstrap wind), odsetek dodatnich, PR-AUC / odsetek."""
    y = zbior["awaria_7d"].to_numpy()
    windy = zbior["id_windy"].to_numpy()
    unikalne = np.unique(windy)
    indeksy = {w: np.flatnonzero(windy == w) for w in unikalne}
    rng = np.random.default_rng(ziarno)
    roc, pr = [], []
    for _ in range(LOSOWAN):
        i = np.concatenate([indeksy[w] for w in rng.choice(unikalne, size=len(unikalne), replace=True)])
        if y[i].min() == y[i].max():
            continue
        roc.append(roc_auc_score(y[i], wynik[i]))
        pr.append(average_precision_score(y[i], wynik[i]))
    odsetek = float(y.mean())
    pr_auc = float(average_precision_score(y, wynik))
    return {
        "wiersze": int(len(y)),
        "windy": int(len(unikalne)),
        "dodatnie": int(y.sum()),
        "odsetek_dodatnich": odsetek,
        "roc_auc": float(roc_auc_score(y, wynik)),
        "roc_auc_lo": float(np.quantile(roc, 0.025)),
        "roc_auc_hi": float(np.quantile(roc, 0.975)),
        "pr_auc": pr_auc,
        "pr_auc_lo": float(np.quantile(pr, 0.025)),
        "pr_auc_hi": float(np.quantile(pr, 0.975)),
        "pr_auc_do_odsetka": pr_auc / odsetek,
    }


def roznica(zbior: pd.DataFrame, a: np.ndarray, b: np.ndarray, ziarno: int = 7) -> dict:
    """a − b: ROC AUC i PR-AUC z 95% CI (bootstrap wind, te same losowania dla a i b)."""
    y = zbior["awaria_7d"].to_numpy()
    windy = zbior["id_windy"].to_numpy()
    unikalne = np.unique(windy)
    indeksy = {w: np.flatnonzero(windy == w) for w in unikalne}
    rng = np.random.default_rng(ziarno)
    d_roc, d_pr = [], []
    for _ in range(LOSOWAN):
        i = np.concatenate([indeksy[w] for w in rng.choice(unikalne, size=len(unikalne), replace=True)])
        if y[i].min() == y[i].max():
            continue
        d_roc.append(roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i]))
        d_pr.append(average_precision_score(y[i], a[i]) - average_precision_score(y[i], b[i]))
    return {
        "roc_auc": float(roc_auc_score(y, a) - roc_auc_score(y, b)),
        "roc_auc_lo": float(np.quantile(d_roc, 0.025)),
        "roc_auc_hi": float(np.quantile(d_roc, 0.975)),
        "pr_auc": float(average_precision_score(y, a) - average_precision_score(y, b)),
        "pr_auc_lo": float(np.quantile(d_pr, 0.025)),
        "pr_auc_hi": float(np.quantile(d_pr, 0.975)),
    }


def przeciek(df: pd.DataFrame, maski: dict[str, np.ndarray], test: str = "test") -> dict:
    """Jak blisko testu jest trening: ta sama awaria (id_awarii) i sąsiedni dzień tej samej windy w treningu."""
    trening = df[maski["trening"] | maski["walidacja"]]
    t = df[maski[test]]
    dodatnie = t[t["awaria_7d"] == 1]
    awarie_treningu = set(trening.loc[trening["awaria_7d"] == 1, "id_awarii"])
    dni_treningu = set(zip(trening["id_windy"], trening["dzien"], strict=True))
    jeden = pd.Timedelta(days=1)
    sasiad = [
        (w, d - jeden) in dni_treningu or (w, d + jeden) in dni_treningu
        for w, d in zip(t["id_windy"], t["dzien"], strict=True)
    ]
    return {
        "proc_dodatnich_testu_z_ta_sama_awaria_w_treningu": float(
            100 * dodatnie["id_awarii"].isin(awarie_treningu).mean()
        ),
        "proc_wierszy_testu_z_sasiednim_dniem_w_treningu": float(100 * np.mean(sasiad)),
    }


def diagnoza_pamieci(df: pd.DataFrame, maski: dict[str, np.ndarray], zbiory: list[str]) -> dict:
    """Ten sam LightGBM, ale tylko na `nr_windy` (kod windy) i `nr_dnia` (dni od 2023-03-01): bez żadnej
    informacji o stanie windy. Wysoki wynik na teście = model może zapamiętać, kiedy która winda miała awarię."""
    from api.ai.failure_model.versions.v2_lgbm_losowy.model import ModelLGBMWind as Lgbm

    x = pd.DataFrame(
        {
            "id_windy": df["id_windy"],
            "dzien": df["dzien"],
            "awaria_7d": df["awaria_7d"],
            "nr_windy": df["id_windy"].astype("category").cat.codes.astype("float64"),
            "nr_dnia": (df["dzien"] - pd.Timestamp(TRENING[0])).dt.days.astype("float64"),
        }
    )
    tr, wa = x[maski["trening"]], x[maski["walidacja"]]
    model = Lgbm(["nr_windy", "nr_dnia"]).fit(tr, tr["awaria_7d"], wa, wa["awaria_7d"])
    return {z: ocen(x[maski[z]], model.predict(x[maski[z]])) for z in zbiory} | {"liczba_drzew": model.liczba_drzew_}


# --- uczenie -------------------------------------------------------------------------------------------------


def uczenie(klasa, df: pd.DataFrame, cechy: list[str], maski: dict[str, np.ndarray], opis: dict):
    tr, wa = df[maski["trening"]], df[maski["walidacja"]]
    model = klasa(cechy).fit(tr, tr["awaria_7d"], wa, wa["awaria_7d"], podzial=opis)
    return model


def ewaluacja_wersji(model, df: pd.DataFrame, maski: dict[str, np.ndarray], zbiory: list[str]) -> dict:
    wyniki = {}
    for nazwa in ["trening", "walidacja", *zbiory]:
        z = df[maski[nazwa]]
        wynik = model.predict(z)
        wyniki[nazwa] = {"model": ocen(z, wynik)}
        if nazwa.startswith("test"):
            regula = wynik_reguly(z[REGULA].to_numpy())
            wyniki[nazwa]["regula"] = ocen(z, regula)
            wyniki[nazwa]["model_minus_regula"] = roznica(z, wynik, regula)
    return wyniki


def zapisz_wersje(model, metryki: dict) -> Path:
    katalog = KATALOG_WERSJI / model.wersja
    model.zapisz(katalog / "model.joblib")
    (katalog / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=2), encoding="utf-8")
    return katalog


def main(z_mlflow: bool = True) -> dict:
    from api.adapters.duckdb_baza import polacz
    from api.ai.features.windy.zbior import wczytaj_zbior

    df, cechy = wczytaj_zbior(polacz())
    wyniki = {}

    maski_v2 = podzial_losowy(df)
    opis_v2 = {"rodzaj": "losowy podział wierszy", "ziarno": ZIARNO_PODZIALU, "test": 0.2, "walidacja": 0.1}
    v2 = uczenie(ModelLGBMWind, df, cechy, maski_v2, opis_v2)
    wyniki[v2.wersja] = {
        "podzial": opis_v2,
        "cechy": len(cechy),
        "liczba_drzew": v2.liczba_drzew_,
        "zbiory": ewaluacja_wersji(v2, df, maski_v2, ["test"]),
        "przeciek": przeciek(df, maski_v2),
        "diagnoza_pamieci": diagnoza_pamieci(df, maski_v2, ["test"]),
    }

    maski_v2b, poza = podzial_czas_winda(df)
    opis_v2b = {
        "rodzaj": "czas + windy poza treningiem",
        "trening": TRENING,
        "walidacja": WALIDACJA,
        "test": TEST,
        "windy_poza_treningiem": poza,
    }
    v2b = uczenie(ModelLGBMCzasWinda, df, cechy, maski_v2b, opis_v2b)
    wyniki[v2b.wersja] = {
        "podzial": opis_v2b,
        "cechy": len(cechy),
        "liczba_drzew": v2b.liczba_drzew_,
        "zbiory": ewaluacja_wersji(v2b, df, maski_v2b, ["test", "test_windy_widziane", "test_windy_niewidziane"]),
        "przeciek": przeciek(df, maski_v2b),
        "diagnoza_pamieci": diagnoza_pamieci(df, maski_v2b, ["test", "test_windy_niewidziane"]),
        "producenci_wind_poza": df.loc[df["id_windy"].isin(poza)].groupby("producent")["id_windy"].nunique().to_dict(),
    }

    for model in (v2, v2b):
        katalog = zapisz_wersje(model, wyniki[model.wersja])
        wyniki[model.wersja]["waznosc"] = model.waznosc_cech().head(15).to_dict("records")
        if z_mlflow:
            zapisz_mlflow(model, wyniki[model.wersja], katalog)
    return wyniki


def zapisz_mlflow(model, wynik: dict, katalog: Path) -> None:
    from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run

    ustaw_eksperyment("windy")
    metryki = {}
    for zbior, w in wynik["zbiory"].items():
        for rodzaj, m in w.items():
            for k in ("roc_auc", "pr_auc", "odsetek_dodatnich", "pr_auc_lo", "pr_auc_hi", "roc_auc_lo", "roc_auc_hi"):
                if k not in m:
                    continue
                metryki[f"{zbior}_{rodzaj}_{k}" if rodzaj != "model" else f"{zbior}_{k}"] = m[k]
    metryki.update({k: v for k, v in wynik["przeciek"].items()})
    for zbior, m in wynik["diagnoza_pamieci"].items():
        if isinstance(m, dict):
            metryki.update({f"pamiec_{zbior}_roc_auc": m["roc_auc"], f"pamiec_{zbior}_pr_auc": m["pr_auc"]})
    zapisz_run(
        model.wersja,
        {
            "wersja": model.wersja,
            "podzial": json.dumps(wynik["podzial"], ensure_ascii=False)[:500],
            "cechy": wynik["cechy"],
            "liczba_drzew": wynik["liczba_drzew"],
            **{k: v for k, v in model.parametry.items() if k != "verbose"},
        },
        metryki,
        {"model": "failure_model", "wersja": model.wersja},
        [katalog / "metryki.json"],
    )


if __name__ == "__main__":
    wynik = main(z_mlflow="--bez-mlflow" not in sys.argv)
    for wersja, w in wynik.items():
        print(f"== {wersja}: drzew {w['liczba_drzew']}, cech {w['cechy']}, przeciek {w['przeciek']}")
        for zbior, m in w["zbiory"].items():
            for rodzaj, x in m.items():
                if rodzaj == "model_minus_regula":
                    print(
                        f"  {zbior:24} model − reguła: roc {x['roc_auc']:+.4f} ({x['roc_auc_lo']:+.4f} … "
                        f"{x['roc_auc_hi']:+.4f}) pr {x['pr_auc']:+.4f} ({x['pr_auc_lo']:+.4f} … {x['pr_auc_hi']:+.4f})"
                    )
                    continue
                print(
                    f"  {zbior:24} {rodzaj:6} n={x['wiersze']:6} windy={x['windy']:3} dod={x['dodatnie']:5} "
                    f"odsetek={x['odsetek_dodatnich']:.4f} roc={x['roc_auc']:.4f} ({x['roc_auc_lo']:.4f}–"
                    f"{x['roc_auc_hi']:.4f}) pr={x['pr_auc']:.4f} ({x['pr_auc_lo']:.4f}–{x['pr_auc_hi']:.4f}) "
                    f"pr/odsetek={x['pr_auc_do_odsetka']:.2f}"
                )
        print(
            "  diagnoza pamięci (tylko nr_windy, nr_dnia):",
            {
                z: (round(m["roc_auc"], 4), round(m["pr_auc"], 4)) if isinstance(m, dict) else m
                for z, m in w["diagnoza_pamieci"].items()
            },
        )
        if "producenci_wind_poza" in w:
            print("  windy poza:", w["podzial"]["windy_poza_treningiem"], w["producenci_wind_poza"])
        print("  ważność:", [(r["cecha"], round(r["udzial"], 3)) for r in w["waznosc"][:10]])
