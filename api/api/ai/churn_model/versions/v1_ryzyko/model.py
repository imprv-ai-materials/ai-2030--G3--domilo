"""v1_ryzyko: LightGBM na cechach z dnia migawki (features/najemcy/cechy.py), target `odejdzie`.

Wejście: wiersze z `KOLUMNY_WEJSCIA` (base.py). Model uczy się wyłącznie na `KOLUMNY_CECH`; nie widzi flagi
wypowiedzenia, `score_polityki` ani wyniku (base.py, KOLUMNY_ZAKAZANE).

Uczenie (`fit`): liczba drzew z wczesnego zatrzymania na ostatnich `MIESIECY_WALIDACJI` miesiącach migawek zbioru
uczącego (walidacja w czasie), potem model uczony od nowa na całym zbiorze z tą liczbą drzew. Parametry ustalone
przed oceną na teście (bez strojenia na teście); jak w lead_model/versions/v2_lgbm_naiwny, z mniejszym
`min_child_samples`, bo zbiór jest ok. 9 razy mniejszy.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from api.ai.churn_model.base import ModelNajemcow
from api.ai.features.najemcy.cechy import KATEGORIE, KOLUMNY_CECH

PARAMETRY = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 100,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 4,
    "verbose": -1,
}
MAKS_DRZEW = 3000
ZATRZYMANIE_PO = 100
MIESIECY_WALIDACJI = 6


class ModelRyzyko(ModelNajemcow):
    wersja = "v1_ryzyko"

    def __init__(self, cechy: tuple[str, ...] = KOLUMNY_CECH, parametry: dict | None = None):
        self.sprawdz_cechy(cechy, self.wersja)
        self.cechy = tuple(cechy)
        self.parametry = {**PARAMETRY, **(parametry or {})}

    # --- macierz cech ------------------------------------------------------------------------------------------

    def _macierz(self, migawki: pd.DataFrame) -> pd.DataFrame:
        self.sprawdz_kolumny(migawki)
        self.sprawdz_cechy(self.cechy, self.wersja)
        X = migawki[list(self.cechy)].copy()
        for k in self.cechy:
            if k in KATEGORIE:
                X[k] = pd.Categorical(X[k].astype("object"), categories=self.kategorie_[k])
            else:
                X[k] = X[k].astype("float64")
        return X

    def _zbior(self, migawki: pd.DataFrame, y) -> lgb.Dataset:
        return lgb.Dataset(self._macierz(migawki), label=np.asarray(y, dtype=float), free_raw_data=False)

    # --- uczenie i wynik ---------------------------------------------------------------------------------------

    def fit(self, migawki: pd.DataFrame, y: pd.Series) -> "ModelRyzyko":
        y = np.asarray(y, dtype=float)
        self.kategorie_ = {k: sorted(migawki[k].dropna().astype(str).unique()) for k in self.cechy if k in KATEGORIE}
        data_migawki = pd.to_datetime(migawki["data_migawki"])
        granica = data_migawki.max() - pd.DateOffset(months=MIESIECY_WALIDACJI)
        walid = (data_migawki > granica).to_numpy()
        self.granica_walidacji_ = str(granica.date())
        proba = lgb.train(
            self.parametry,
            self._zbior(migawki[~walid], y[~walid]),
            num_boost_round=MAKS_DRZEW,
            valid_sets=[self._zbior(migawki[walid], y[walid])],
            callbacks=[lgb.early_stopping(ZATRZYMANIE_PO, verbose=False)],
        )
        self.liczba_drzew_ = max(1, int(proba.best_iteration))
        self.auc_walidacji_ = float(proba.best_score["valid_0"]["auc"])
        self.booster_ = lgb.train(self.parametry, self._zbior(migawki, y), num_boost_round=self.liczba_drzew_)
        return self

    def predict(self, migawki: pd.DataFrame) -> np.ndarray:
        return self.booster_.predict(self._macierz(migawki))

    def explain(self, migawki: pd.DataFrame) -> pd.DataFrame:
        """`wynik` + wkład każdej cechy w log-szansę odejścia (SHAP z LightGBM, pred_contrib) + `wklad_staly`."""
        X = self._macierz(migawki)
        wklady = self.booster_.predict(X, pred_contrib=True)
        wyj = pd.DataFrame(wklady, index=migawki.index, columns=[f"wklad_{k}" for k in self.cechy] + ["wklad_staly"])
        wyj.insert(0, "wynik", self.booster_.predict(X))
        return wyj

    def waznosc_cech(self) -> pd.DataFrame:
        """Ważność cech (gain, udział w sumie) malejąco."""
        gain = self.booster_.feature_importance(importance_type="gain")
        return (
            pd.DataFrame({"cecha": self.cechy, "gain": gain, "udzial": gain / gain.sum()})
            .sort_values("gain", ascending=False)
            .reset_index(drop=True)
        )
