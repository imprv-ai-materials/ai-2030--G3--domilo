"""v2: LightGBM uczony na historii zapytań, „naiwny”, czyli uczony na `umowa_45d` z nieobsłużonymi zapytaniami = 0.

Naiwny, bo target łączy jakość zapytania z decyzją zespołu, do kogo oddzwonić (docs/kolejka_target.md): model uczy
się też obecnych nawyków (np. `domteraz` obsługiwane w ok. 41%). Dlatego oceniamy go także w oknie migracji.

Wejście: wiersze z kolumnami `KOLUMNY_CECH` (features/leady/cechy.py, stan na moment utworzenia zapytania). To
więcej niż `KOLUMNY_WEJSCIA` z base.py: sesje www, umowa ramowa i sygnały LLM v1 przychodzą z `zbuduj_cechy`.
Sygnały wymagają odpowiedzi v1 (LLM) dla każdego zapytania; brak odpowiedzi = NaN.

Uczenie (`fit`): liczba drzew z wczesnego zatrzymania na ostatnich `MIESIECY_WALIDACJI` miesiącach zbioru uczącego
(walidacja w czasie), potem model uczony od nowa na całym zbiorze z tą liczbą drzew.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from api.ai.features.leady.cechy import KATEGORIE, KOLUMNY_CECH
from api.ai.lead_model.base import ModelLeadow

PARAMETRY = {
    "objective": "binary",
    "metric": "auc",
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
    "num_threads": 4,
    "verbose": -1,
}
MAKS_DRZEW = 3000
ZATRZYMANIE_PO = 100
MIESIECY_WALIDACJI = 6


class ModelLGBMNaiwny(ModelLeadow):
    wersja = "v2_lgbm_naiwny"

    def __init__(self, cechy: tuple[str, ...] = KOLUMNY_CECH, parametry: dict | None = None):
        self.cechy = tuple(cechy)
        self.parametry = {**PARAMETRY, **(parametry or {})}

    # --- macierz cech ------------------------------------------------------------------------------------------

    def _macierz(self, leady: pd.DataFrame) -> pd.DataFrame:
        brak = [k for k in self.cechy if k not in leady.columns]
        if brak:
            raise ValueError(f"Brak cech wymaganych przez {self.wersja}: {', '.join(brak)} (features/leady/cechy.py)")
        X = leady[list(self.cechy)].copy()
        for k in self.cechy:
            if k in KATEGORIE:
                X[k] = pd.Categorical(X[k].astype("object"), categories=self.kategorie_[k])
            else:
                X[k] = X[k].astype("float64")
        return X

    def _zbior(self, leady: pd.DataFrame, y) -> lgb.Dataset:
        return lgb.Dataset(self._macierz(leady), label=np.asarray(y, dtype=float), free_raw_data=False)

    # --- uczenie i wynik ---------------------------------------------------------------------------------------

    def fit(self, leady: pd.DataFrame, y: pd.Series) -> "ModelLGBMNaiwny":
        y = np.asarray(y, dtype=float)
        self.kategorie_ = {k: sorted(leady[k].dropna().astype(str).unique()) for k in self.cechy if k in KATEGORIE}
        utworzono = pd.to_datetime(leady["utworzono"], utc=True)
        granica = utworzono.max() - pd.DateOffset(months=MIESIECY_WALIDACJI)
        walid = (utworzono > granica).to_numpy()
        self.granica_walidacji_ = str(granica)
        zbior_uczacy = self._zbior(leady[~walid], y[~walid])
        zbior_walid = self._zbior(leady[walid], y[walid])
        proba = lgb.train(
            self.parametry,
            zbior_uczacy,
            num_boost_round=MAKS_DRZEW,
            valid_sets=[zbior_walid],
            callbacks=[lgb.early_stopping(ZATRZYMANIE_PO, verbose=False)],
        )
        self.liczba_drzew_ = int(proba.best_iteration)
        self.auc_walidacji_ = float(proba.best_score["valid_0"]["auc"])
        self.booster_ = lgb.train(self.parametry, self._zbior(leady, y), num_boost_round=self.liczba_drzew_)
        return self

    def predict(self, leady: pd.DataFrame) -> np.ndarray:
        return self.booster_.predict(self._macierz(leady))

    def explain(self, leady: pd.DataFrame) -> pd.DataFrame:
        """`wynik` + wkład każdej cechy w log-szansę (SHAP z LightGBM, pred_contrib) + `wklad_staly`."""
        X = self._macierz(leady)
        wklady = self.booster_.predict(X, pred_contrib=True)
        wyj = pd.DataFrame(wklady, index=leady.index, columns=[f"wklad_{k}" for k in self.cechy] + ["wklad_staly"])
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
