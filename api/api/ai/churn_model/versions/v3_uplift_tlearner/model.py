"""v3_uplift_tlearner: T-learner (dwa modele LightGBM) – o ile oferta retencyjna zmienia szansę przedłużenia.

Inny kontrakt niż base.ModelNajemcow (ryzyko odejścia): wynik `predict` to uplift = P(przedłużenie | oferta, cechy)
− P(przedłużenie | kontrola, cechy), w punktach prawdopodobieństwa; wyżej = większy sens dawać rabat. Wspólna jest
ochrona przed kolumnami zakazanymi (base.KOLUMNY_ZAKAZANE: m.in. wynik, `score_polityki`, `grupa`). Przydział
oferty podajemy osobno (`oferta`), nie jako cechę.

Dane: tylko losowy test `retencja_decyzje.okres = 'test_2025'` (oferta 50/50), uczenie na ok. 70% umów według
id_umowy (features/najemcy/zbior.py, podziel_uplift). Cechy: `KOLUMNY_CECH` v1 na dzień migawki (przed ofertą,
która przychodzi 45 dni przed końcem umowy, czyli 15 dni po migawce); `linia` jako 0/1 `b2b`.

Uczenie: osobny LightGBM dla grupy oferta i kontrola. Liczba drzew każdego z 5-krotnej walidacji krzyżowej
(warstwowanej po wyniku) na jego części treningu, z wczesnym zatrzymaniem po log-loss. Parametry ustalone przed
oceną na teście; mniejsze drzewa i większe `min_child_samples` niż v1, bo każda grupa ma ok. 1,6 tys. umów.
"""

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from api.ai.churn_model.base import ModelNajemcow
from api.ai.features.najemcy.cechy import KOLUMNY_CECH

PARAMETRY = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 50,
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
MAKS_DRZEW = 2000
ZATRZYMANIE_PO = 50
FOLDY = 5


def macierz(df: pd.DataFrame, cechy: tuple[str, ...] = KOLUMNY_CECH) -> pd.DataFrame:
    """Cechy jako float64; `linia` -> `b2b` (1 = B2B). Braki zostają NaN (LightGBM obsługuje je sam)."""
    X = pd.DataFrame(index=df.index)
    for k in cechy:
        if k == "linia":
            X["b2b"] = (df["linia"] == "B2B").astype("float64")
        else:
            X[k] = df[k].astype("float64")
    return X


def liczba_drzew(X: pd.DataFrame, y, parametry: dict = PARAMETRY) -> int:
    """Liczba drzew z 5-krotnej CV (warstwy po y) z wczesnym zatrzymaniem po log-loss."""
    wynik = lgb.cv(
        parametry,
        lgb.Dataset(X, label=np.asarray(y, dtype=float)),
        num_boost_round=MAKS_DRZEW,
        nfold=FOLDY,
        stratified=True,
        seed=parametry.get("seed", 42),
        callbacks=[lgb.early_stopping(ZATRZYMANIE_PO, verbose=False)],
    )
    return max(1, len(next(iter(wynik.values()))))


class ModelUpliftT:
    wersja = "v3_uplift_tlearner"

    def __init__(self, cechy: tuple[str, ...] = KOLUMNY_CECH, parametry: dict | None = None):
        ModelNajemcow.sprawdz_cechy(cechy, self.wersja)
        self.cechy = tuple(cechy)
        self.parametry = {**PARAMETRY, **(parametry or {})}

    def fit(self, df: pd.DataFrame, oferta, y) -> "ModelUpliftT":
        oferta = np.asarray(oferta, dtype=bool)
        y = np.asarray(y, dtype=float)
        X = macierz(df, self.cechy)
        self.modele_, self.liczba_drzew_, self.n_ = {}, {}, {}
        for grupa, maska in (("oferta", oferta), ("kontrola", ~oferta)):
            n = liczba_drzew(X[maska], y[maska], self.parametry)
            self.modele_[grupa] = lgb.train(self.parametry, lgb.Dataset(X[maska], label=y[maska]), num_boost_round=n)
            self.liczba_drzew_[grupa] = n
            self.n_[grupa] = int(maska.sum())
        return self

    def predict_skladowe(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """P(przedłużenie) przy ofercie i bez oferty."""
        X = macierz(df, self.cechy)
        return self.modele_["oferta"].predict(X), self.modele_["kontrola"].predict(X)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        p_o, p_k = self.predict_skladowe(df)
        return p_o - p_k

    def waznosc_cech(self) -> pd.DataFrame:
        """Udział cech w gain każdego z dwóch modeli."""
        kolumny = list(macierz(pd.DataFrame(columns=list(self.cechy)), self.cechy).columns)
        wyj = pd.DataFrame({"cecha": kolumny})
        for grupa, model in self.modele_.items():
            gain = model.feature_importance(importance_type="gain")
            wyj[f"udzial_{grupa}"] = gain / gain.sum()
        return wyj.sort_values("udzial_oferta", ascending=False).reset_index(drop=True)

    def zapisz(self, sciezka) -> None:
        joblib.dump(self, sciezka)
