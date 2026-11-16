"""v2: LightGBM na cechach ręcznych (`cechy_windy`) + wybranych cechach tsfresh, podział LOSOWY wierszy 80/20.

Podział losowy (evals/ewaluacja_v2.py, `podzial_losowy`) to wariant celowo naiwny: sąsiednie dni tej samej windy
i tej samej awarii trafiają jednocześnie do treningu i testu, więc wynik testu jest zawyżony
(evals/porownanie.md). Realistyczny wariant tej samej metody: v2b_lgbm_czas_winda.

Uczenie (`fit`): liczba drzew z wczesnego zatrzymania (metryka: average_precision = PR-AUC) na zbiorze
walidacyjnym podanym przez ewaluację, potem bez douczania (model = drzewa do najlepszej iteracji).
Wynik: prawdopodobieństwo z LightGBM (nie kalibrowane osobno).
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from api.ai.failure_model.base import ModelWind

PARAMETRY = {
    "objective": "binary",
    "metric": "average_precision",
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 200,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 8,
    "verbose": -1,
}
MAKS_DRZEW = 3000
ZATRZYMANIE_PO = 100


class ModelLGBMWind(ModelWind):
    wersja = "v2_lgbm_losowy"

    def __init__(self, cechy: list[str] | tuple[str, ...], parametry: dict | None = None):
        self.sprawdz_cechy(cechy, self.wersja)
        self.cechy = tuple(cechy)
        self.parametry = {**PARAMETRY, **(parametry or {})}

    def _macierz(self, dni: pd.DataFrame) -> pd.DataFrame:
        self.sprawdz_kolumny(dni)
        return dni[list(self.cechy)].astype("float64")

    def fit(
        self,
        dni: pd.DataFrame,
        y: pd.Series,
        dni_walid: pd.DataFrame | None = None,
        y_walid: pd.Series | None = None,
        podzial: dict | None = None,
    ) -> "ModelLGBMWind":
        """Uczy na (dni, y); wczesne zatrzymanie na (dni_walid, y_walid). `podzial` = opis podziału do metryk."""
        if dni_walid is None or y_walid is None:
            raise ValueError(f"{self.wersja}: fit wymaga zbioru walidacyjnego (wczesne zatrzymanie)")
        uczacy = lgb.Dataset(self._macierz(dni), label=np.asarray(y, dtype=float))
        walid = lgb.Dataset(self._macierz(dni_walid), label=np.asarray(y_walid, dtype=float), reference=uczacy)
        self.booster_ = lgb.train(
            self.parametry,
            uczacy,
            num_boost_round=MAKS_DRZEW,
            valid_sets=[walid],
            callbacks=[lgb.early_stopping(ZATRZYMANIE_PO, verbose=False)],
        )
        self.liczba_drzew_ = int(self.booster_.best_iteration)
        self.pr_auc_walidacji_ = float(self.booster_.best_score["valid_0"]["average_precision"])
        self.podzial_ = dict(podzial or {})
        return self

    def predict(self, dni: pd.DataFrame) -> np.ndarray:
        return self.booster_.predict(self._macierz(dni), num_iteration=self.liczba_drzew_)

    def explain(self, dni: pd.DataFrame) -> pd.DataFrame:
        """`wynik` + wkład każdej cechy w log-szansę (SHAP z LightGBM, pred_contrib) + `wklad_staly`."""
        X = self._macierz(dni)
        wklady = self.booster_.predict(X, num_iteration=self.liczba_drzew_, pred_contrib=True)
        wyj = pd.DataFrame(wklady, index=dni.index, columns=[f"wklad_{k}" for k in self.cechy] + ["wklad_staly"])
        wyj.insert(0, "wynik", self.predict(dni))
        return wyj

    def waznosc_cech(self) -> pd.DataFrame:
        """Ważność cech (gain, udział w sumie) malejąco."""
        gain = self.booster_.feature_importance(importance_type="gain", iteration=self.liczba_drzew_)
        return (
            pd.DataFrame({"cecha": self.cechy, "gain": gain, "udzial": gain / gain.sum()})
            .sort_values("gain", ascending=False)
            .reset_index(drop=True)
        )
