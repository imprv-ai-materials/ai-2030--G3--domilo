"""v0 (baseline): mediana ceny m² dzielnicy ze zbioru treningowego × metraż.

Dzielnica = para (miasto, dzielnica), bo te same nazwy dzielnic występują w kilku miastach.
Dzielnica nieobecna w treningu dostaje medianę ceny m² swojego miasta.
"""

import numpy as np
import pandas as pd
from api.ai.valuation_model.base import ModelWyceny


class ModelMedianaDzielnicy(ModelWyceny):
    wersja = "v0_mediana_dzielnicy"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelMedianaDzielnicy":
        self.sprawdz_kolumny(X)
        cena_m2 = pd.Series(np.asarray(y, dtype=float) / X["metraz"].to_numpy(), index=X.index)
        self.mediana_dzielnicy_ = cena_m2.groupby([X["miasto"], X["dzielnica"]]).median().to_dict()
        self.mediana_miasta_ = cena_m2.groupby(X["miasto"]).median().to_dict()
        return self

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        self.sprawdz_kolumny(X)
        klucze = list(zip(X["miasto"], X["dzielnica"]))
        z_dzielnicy = [self.mediana_dzielnicy_.get(k) for k in klucze]
        mediana = [
            m if m is not None else self.mediana_miasta_.get(miasto, np.nan)
            for m, miasto in zip(z_dzielnicy, X["miasto"])
        ]
        wyj = pd.DataFrame(
            {
                "zrodlo_mediany": ["dzielnica" if m is not None else "miasto" for m in z_dzielnicy],
                "mediana_ceny_m2": np.asarray(mediana, dtype=float),
                "metraz": X["metraz"].to_numpy(dtype=float),
            },
            index=X.index,
        )
        wyj["wycena_pln"] = wyj["mediana_ceny_m2"] * wyj["metraz"]
        return wyj

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.explain(X)["wycena_pln"].to_numpy()
