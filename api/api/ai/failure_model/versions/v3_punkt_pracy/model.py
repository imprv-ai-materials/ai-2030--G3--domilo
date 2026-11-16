"""v3_punkt_pracy: aktywna wersja modelu wind = nauczony model bazowy (wariant cech wybrany w
contexts_boundaries/maintenance_bc/tryb_serwisowy.py) + kalibracja izotoniczna na walidacji + opis punktu pracy.

- `predict` = wynik modelu bazowego (ranking; tym wynikiem reguła alarmu wybiera 3 windy w poniedziałek,
  maintenance_bc/alarmy_wind.py). Bez zmian względem modelu bazowego, żeby izotonia (schodki = remisy) nie zmieniała
  kolejności wind.
- `prawdopodobienstwo` = P(awaria w 7 dni) po kalibracji (regresja izotoniczna dopasowana w `fit` na walidacji
  2025-07-01 – 2025-12-31); do progu opłacalności p* (maintenance_bc/wartosc_alarmow.py).
- `punkt_pracy` = stałe reguły alarmu w chwili zapisu (alarmy_na_tydzien, dzien_alarmu, przerwa_dni z
  maintenance_bc/zalozenia.yaml); `bez_serwisu` = czy cechy liczone bez okien `tryb = 'serwis'` (tabele cechy_windy
  i cechy_windy_tsfresh, jeśli True).
Wyniki i wybór: docs/b4_punkt_pracy.md, metryki.json.
"""

import numpy as np
import pandas as pd
from api.ai.failure_model.base import ModelWind
from sklearn.isotonic import IsotonicRegression

KLUCZE_PUNKTU_PRACY = ("alarmy_na_tydzien", "dzien_alarmu", "przerwa_dni")


class ModelPunktPracy(ModelWind):
    wersja = "v3_punkt_pracy"

    def __init__(self, model_bazowy: ModelWind, punkt_pracy: dict, bez_serwisu: bool = True):
        self.sprawdz_cechy(model_bazowy.cechy, self.wersja)
        self.model_bazowy = model_bazowy
        self.cechy = tuple(model_bazowy.cechy)
        self.punkt_pracy = {k: punkt_pracy[k] for k in KLUCZE_PUNKTU_PRACY}
        self.bez_serwisu = bool(bez_serwisu)

    def fit(self, dni: pd.DataFrame, y: pd.Series, **kwargs) -> "ModelPunktPracy":
        """Kalibracja na zbiorze walidacyjnym (model bazowy jest już nauczony i się nie zmienia)."""
        self.kalibrator_ = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(
            self.model_bazowy.predict(dni), np.asarray(y, dtype=float)
        )
        return self

    def predict(self, dni: pd.DataFrame) -> np.ndarray:
        return self.model_bazowy.predict(dni)

    def prawdopodobienstwo(self, dni: pd.DataFrame) -> np.ndarray:
        return self.kalibrator_.predict(self.predict(dni))

    def explain(self, dni: pd.DataFrame) -> pd.DataFrame:
        wyj = self.model_bazowy.explain(dni)
        wyj.insert(1, "p_awarii_7d", self.kalibrator_.predict(wyj["wynik"].to_numpy()))
        return wyj
