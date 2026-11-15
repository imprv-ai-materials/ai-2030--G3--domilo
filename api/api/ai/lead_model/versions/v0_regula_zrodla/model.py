"""v0 (baseline): konwersja `umowa_45d` pary (źródło × linia) w historii.

Para nieobecna w historii dostaje konwersję swojego źródła, a nieznane źródło konwersję ogólną. Na czym uczony
(okres, które zapytania) zapisuje ewaluacja w `metryki.json`; reguła sama nie wybiera okresu.
"""

import numpy as np
import pandas as pd
from api.ai.lead_model.base import ModelLeadow

KLUCZ = ["zrodlo", "linia_pref"]


class ModelRegulaZrodla(ModelLeadow):
    wersja = "v0_regula_zrodla"

    def fit(self, leady: pd.DataFrame, y: pd.Series) -> "ModelRegulaZrodla":
        historia = leady[KLUCZ].assign(y=np.asarray(y, dtype=float))
        self.konwersja_pary_ = historia.groupby(KLUCZ)["y"].mean().to_dict()
        self.liczba_pary_ = historia.groupby(KLUCZ)["y"].size().to_dict()
        self.konwersja_zrodla_ = historia.groupby("zrodlo")["y"].mean().to_dict()
        self.konwersja_ogolna_ = float(historia["y"].mean())
        return self

    def explain(self, leady: pd.DataFrame) -> pd.DataFrame:
        pary = list(zip(leady["zrodlo"], leady["linia_pref"]))
        wynik, poziom = [], []
        for zrodlo, linia in pary:
            if (zrodlo, linia) in self.konwersja_pary_:
                wynik.append(self.konwersja_pary_[(zrodlo, linia)])
                poziom.append("para")
            elif zrodlo in self.konwersja_zrodla_:
                wynik.append(self.konwersja_zrodla_[zrodlo])
                poziom.append("zrodlo")
            else:
                wynik.append(self.konwersja_ogolna_)
                poziom.append("ogolna")
        return pd.DataFrame(
            {
                "wynik": np.asarray(wynik, dtype=float),
                "poziom": poziom,
                "zapytan_w_historii_pary": [self.liczba_pary_.get(p, 0) for p in pary],
            },
            index=leady.index,
        )

    def predict(self, leady: pd.DataFrame) -> np.ndarray:
        return self.explain(leady)["wynik"].to_numpy()
