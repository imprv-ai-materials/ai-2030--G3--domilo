"""Cechy ręczne vs ręczne + tsfresh: PR-AUC modelu „awaria windy w 7 dni” (docs/b4_tsfresh.md).

Dane: `dni_wind` (target `awaria_7d`), `cechy_windy` (168 cech ręcznych), `cechy_windy_tsfresh` (21 cech tsfresh,
api/api/ai/features/windy/tsfresh_cechy.py).
Podział w czasie: trening dzien 2023-03-01 – 2025-06-30; przerwa 2025-07-01 – 2025-07-07 (okno targetu ostatnich
dni treningu sięga 2025-07-07 06:00, więc te awarie byłyby i w treningu, i w teście); test 2025-07-08 – 2026-09-22.
Selekcja cech tsfresh (tsfresh_cechy.wybierz_cechy) tylko na treningu; wynik w features/windy/tsfresh_wybrane.yaml.
Modele: LightGBM o stałych parametrach (bez strojenia, te same dla wszystkich), średnia z 3 ziaren.
Baseline: jedna cecha ręczna o najwyższym PR-AUC na treningu (wybór i kierunek tylko na treningu) oraz losowy
ranking (PR-AUC = odsetek dodatnich). 95% CI: bootstrap wind (klaster = winda, 1 000 losowań, te same dla modeli).
Uruchomienie (z api/): `python -m api.ai.failure_model.evals.tsfresh_porownanie` (MLflow: eksperyment `windy`).
"""

import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from api.ai.features.windy.tsfresh_cechy import nazwy_cech, wybierz_cechy, zapisz_wybrane
from sklearn.metrics import average_precision_score, roc_auc_score

TRENING = ("2023-03-01", "2025-06-30")
TEST = ("2025-07-08", "2026-09-22")
ZIARNA = (11, 22, 33)
LOSOWAN = 1000
PARAMETRY = {
    "objective": "binary",
    "n_estimators": 500,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 200,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
    "n_jobs": 8,
}


def wczytaj(con) -> pd.DataFrame:
    return con.execute("""
        SELECT d.id_windy, d.dzien, d.awaria_7d, c.* EXCLUDE (id_windy, dzien), t.* EXCLUDE (id_windy, dzien)
        FROM dni_wind AS d
        JOIN cechy_windy AS c USING (id_windy, dzien)
        LEFT JOIN cechy_windy_tsfresh AS t USING (id_windy, dzien)
        ORDER BY d.dzien, d.id_windy
        """).df()


def podziel(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dzien = pd.to_datetime(df["dzien"])
    trening = df[dzien.between(*TRENING)].reset_index(drop=True)
    test = df[dzien.between(*TEST)].reset_index(drop=True)
    return trening, test


def przewidz(trening: pd.DataFrame, test: pd.DataFrame, kolumny: list[str]) -> np.ndarray:
    wyniki = []
    for ziarno in ZIARNA:
        model = lgb.LGBMClassifier(**PARAMETRY, random_state=ziarno)
        model.fit(trening[kolumny], trening["awaria_7d"])
        wyniki.append(model.predict_proba(test[kolumny])[:, 1])
    return np.mean(wyniki, axis=0)


def wynik_reguly(x: np.ndarray, znak: int) -> np.ndarray:
    """znak × cecha; NULL dostaje wynik niższy od wszystkich (sklearn nie przyjmuje NaN ani ±inf)."""
    s = znak * np.asarray(x, dtype="float64")
    return np.where(np.isnan(s), np.nanmin(s) - 1, s)


def regula_jednej_cechy(trening: pd.DataFrame, kolumny: list[str]) -> tuple[str, int]:
    """Cecha ręczna i znak (+1 / −1) o najwyższym PR-AUC na treningu; NULL = najniższy wynik."""
    y = trening["awaria_7d"].to_numpy()
    najlepsza = ("", 1, -1.0)
    for k in kolumny:
        x = trening[k].to_numpy(dtype="float64")
        if np.isnan(x).all():
            continue
        for znak in (1, -1):
            pr = average_precision_score(y, wynik_reguly(x, znak))
            if pr > najlepsza[2]:
                najlepsza = (k, znak, pr)
    return najlepsza[0], najlepsza[1]


def bootstrap(test: pd.DataFrame, wyniki: dict[str, np.ndarray], ziarno: int = 2026) -> pd.DataFrame:
    """PR-AUC i ROC AUC z 95% CI (bootstrap wind) dla każdego wyniku."""
    rng = np.random.default_rng(ziarno)
    windy = test["id_windy"].to_numpy()
    unikalne = np.unique(windy)
    indeksy = {w: np.flatnonzero(windy == w) for w in unikalne}
    y = test["awaria_7d"].to_numpy()
    probki = []
    for _ in range(LOSOWAN):
        wybrane = rng.choice(unikalne, size=len(unikalne), replace=True)
        probki.append(np.concatenate([indeksy[w] for w in wybrane]))
    wiersze = []
    for nazwa, s in wyniki.items():
        pr = np.array([average_precision_score(y[i], s[i]) for i in probki])
        wiersze.append(
            {
                "model": nazwa,
                "pr_auc": average_precision_score(y, s),
                "pr_auc_lo": np.quantile(pr, 0.025),
                "pr_auc_hi": np.quantile(pr, 0.975),
                "roc_auc": roc_auc_score(y, s),
                "_probki": pr,
            }
        )
    return pd.DataFrame(wiersze)


def roznice(tabela: pd.DataFrame, pary: list[tuple[str, str]]) -> pd.DataFrame:
    p = tabela.set_index("model")
    wiersze = []
    for a, b in pary:
        d = p.loc[a, "_probki"] - p.loc[b, "_probki"]
        wiersze.append(
            {
                "roznica": f"{a} − {b}",
                "pr_auc": p.loc[a, "pr_auc"] - p.loc[b, "pr_auc"],
                "lo": np.quantile(d, 0.025),
                "hi": np.quantile(d, 0.975),
                "proc_losowan_a_lepszy": 100 * (d > 0).mean(),
            }
        )
    return pd.DataFrame(wiersze)


def main(z_mlflow: bool = True) -> dict:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    df = wczytaj(con)
    trening, test = podziel(df)
    tsfresh = nazwy_cech()
    reczne = [k for k in df.columns if k not in ("id_windy", "dzien", "awaria_7d", *tsfresh)]

    istotnosc = wybierz_cechy(trening[tsfresh], trening["awaria_7d"])
    wybrane = zapisz_wybrane(istotnosc)

    cecha, znak = regula_jednej_cechy(trening, reczne)
    wyniki = {
        "losowy": np.random.default_rng(0).random(len(test)),
        f"regula: {cecha} ({'+' if znak > 0 else '−'})": wynik_reguly(test[cecha].to_numpy(), znak),
        "lgbm_reczne": przewidz(trening, test, reczne),
        "lgbm_reczne_tsfresh_wybrane": przewidz(trening, test, reczne + wybrane),
        "lgbm_reczne_tsfresh_wszystkie": przewidz(trening, test, reczne + tsfresh),
        "lgbm_tylko_tsfresh_wybrane": przewidz(trening, test, wybrane),
    }
    tabela = bootstrap(test, wyniki)
    regula = next(k for k in wyniki if k.startswith("regula"))
    tabela_roznic = roznice(
        tabela,
        [
            ("lgbm_reczne_tsfresh_wybrane", "lgbm_reczne"),
            ("lgbm_reczne_tsfresh_wszystkie", "lgbm_reczne"),
            ("lgbm_reczne", regula),
            ("lgbm_reczne_tsfresh_wybrane", regula),
        ],
    )
    podsumowanie = {
        "trening": (len(trening), int(trening["awaria_7d"].sum())),
        "test": (len(test), int(test["awaria_7d"].sum())),
        "reczne": len(reczne),
        "wybrane": wybrane,
    }
    if z_mlflow:
        from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run

        ustaw_eksperyment("windy")
        for _, w in tabela.iterrows():
            zapisz_run(
                f"tsfresh_porownanie: {w['model']}",
                {"trening": f"{TRENING[0]}..{TRENING[1]}", "test": f"{TEST[0]}..{TEST[1]}", **PARAMETRY},
                {
                    "pr_auc": w["pr_auc"],
                    "pr_auc_lo": w["pr_auc_lo"],
                    "pr_auc_hi": w["pr_auc_hi"],
                    "roc_auc": w["roc_auc"],
                },
                {"tsfresh_wybrane": ",".join(wybrane)},
            )
    return {
        "podsumowanie": podsumowanie,
        "istotnosc": istotnosc,
        "tabela": tabela.drop(columns="_probki"),
        "roznice": tabela_roznic,
    }


if __name__ == "__main__":
    wynik = main(z_mlflow="--bez-mlflow" not in sys.argv)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print(wynik["podsumowanie"])
    print(wynik["istotnosc"][["feature", "grupa", "wiersze", "dodatnie", "p_value", "relevant"]].to_string())
    print(wynik["tabela"].round(4).to_string())
    print(wynik["roznice"].round(4).to_string())
