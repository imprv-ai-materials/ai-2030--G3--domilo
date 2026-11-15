"""v2: LightGBM (gradient boosting drzew) na ln(ceny transakcyjnej), te same cechy wejściowe co v1.

Cechy (KOLUMNY_CECH z base.py, bez cech otoczenia):
- miasto: kategoria;
- dzielnica: kategoria dla pary (miasto, dzielnica), bo te same nazwy dzielnic występują w kilku miastach;
- metraz, pokoje, pietro, rok_budowy: liczbowo (drzewa same dzielą zakresy, bez ln i bez przedziałów roku).

Kategorie ustalamy na zbiorze treningowym; dzielnica albo miasto nieznane w treningu trafiają do LightGBM jako brak
(NaN) i idą gałęzią dla braków.
Liczba drzew: wczesne zatrzymanie (`stopping_rounds` rund bez poprawy l2 na ln(ceny)) na zbiorze walidacyjnym
podanym w `fit(..., X_wal, y_wal)`; model uczy się wyłącznie na zbiorze treningowym, a predykcja używa najlepszej
iteracji. Bez zbioru walidacyjnego: `max_drzew` drzew.
Hiperparametry są stałe (PARAMETRY), nie strojone na walidacji.
Wycena = exp(przewidywany ln(ceny)), czyli mediana, nie średnia, ceny przy danych cechach (jak w v1).
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from api.ai.valuation_model.base import ModelWyceny

KOLUMNY_LICZBOWE = ("metraz", "pokoje", "pietro", "rok_budowy")
KOLUMNY_KATEGORII = ("miasto", "dzielnica")
PARAMETRY = {
    "objective": "regression",  # l2 na ln(ceny)
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "random_state": 42,
    "deterministic": True,
    "force_row_wise": True,
    "n_jobs": 4,
    "verbose": -1,
}


class ModelLightGBM(ModelWyceny):
    wersja = "v2_lightgbm"

    def __init__(self, *, max_drzew: int = 5000, stopping_rounds: int = 200, parametry: dict | None = None):
        self.max_drzew = max_drzew
        self.stopping_rounds = stopping_rounds
        self.parametry = {**PARAMETRY, **(parametry or {})}

    # --- cechy ---------------------------------------------------------------------------------------------------

    def _macierz(self, X: pd.DataFrame) -> pd.DataFrame:
        wartosci = {"miasto": X["miasto"], "dzielnica": X["miasto"].astype(str) + " | " + X["dzielnica"].astype(str)}
        A = pd.DataFrame(
            {
                k: pd.Categorical(v.where(v.isin(self.kategorie_[k])), categories=self.kategorie_[k])
                for k, v in wartosci.items()
            },
            index=X.index,
        )
        for k in KOLUMNY_LICZBOWE:
            A[k] = X[k].astype(float)
        return A

    # --- kontrakt ------------------------------------------------------------------------------------------------

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        X_wal: pd.DataFrame | None = None,
        y_wal: pd.Series | None = None,
    ) -> "ModelLightGBM":
        self.sprawdz_kolumny(X)
        self.kategorie_ = {
            "miasto": sorted(X["miasto"].unique()),
            "dzielnica": sorted((X["miasto"].astype(str) + " | " + X["dzielnica"].astype(str)).unique()),
        }
        self.reg_ = lgb.LGBMRegressor(n_estimators=self.max_drzew, **self.parametry)
        ln_y = np.log(np.asarray(y, dtype=float))
        if X_wal is not None and y_wal is not None:
            self.sprawdz_kolumny(X_wal)
            self.reg_.fit(
                self._macierz(X),
                ln_y,
                eval_X=(self._macierz(X_wal),),
                eval_y=(np.log(np.asarray(y_wal, dtype=float)),),
                eval_names=["walidacja"],
                categorical_feature=list(KOLUMNY_KATEGORII),
                callbacks=[lgb.early_stopping(self.stopping_rounds, verbose=False)],
            )
            self.najlepsza_iteracja_ = int(self.reg_.best_iteration_)
            self.l2_walidacja_ = float(self.reg_.best_score_["walidacja"]["l2"])
        else:
            self.reg_.fit(self._macierz(X), ln_y, categorical_feature=list(KOLUMNY_KATEGORII))
            self.najlepsza_iteracja_ = self.max_drzew
            self.l2_walidacja_ = None
        return self

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Wkłady cech do ln(wyceny) (wartości SHAP LightGBM): suma kolumn `wklad_*` = ln(wycena_pln)."""
        self.sprawdz_kolumny(X)
        A = self._macierz(X)
        wklady = self.reg_.predict(A, pred_contrib=True, num_iteration=self.najlepsza_iteracja_)
        wyj = pd.DataFrame(wklady, index=X.index, columns=[f"wklad_{k}" for k in A.columns] + ["wklad_bazowy"])
        wyj["wycena_pln"] = np.exp(wyj.sum(axis=1))
        return wyj

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self.sprawdz_kolumny(X)
        return np.exp(self.reg_.predict(self._macierz(X), num_iteration=self.najlepsza_iteracja_))

    def waznosc_cech(self) -> pd.DataFrame:
        """Ważność cech: łączny zysk (gain) z podziałów na danej cesze, w % sumy (dla najlepszej iteracji)."""
        zysk = self.reg_.booster_.feature_importance(importance_type="gain", iteration=self.najlepsza_iteracja_)
        df = pd.DataFrame({"cecha": self.reg_.booster_.feature_name(), "zysk": zysk})
        df["udzial_proc"] = 100 * df["zysk"] / df["zysk"].sum()
        return df.sort_values("udzial_proc", ascending=False, ignore_index=True)
