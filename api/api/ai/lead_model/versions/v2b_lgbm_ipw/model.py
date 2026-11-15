"""v2b: LightGBM uczony tylko na obsłużonych zapytaniach, ważonych odwrotnością skłonności do obsługi (IPW).

Problem v2_lgbm_naiwny (docs/kolejka_bias.md): target „nieobsłużone = 0” miesza jakość zapytania z decyzją doradcy,
czy w ogóle zadzwonić. v2b rozdziela te dwie rzeczy:

1. Model skłonności `P(obsłużony | cechy zapytania)`: regresja logistyczna na tych samych cechach co v2
   (`KOLUMNY_CECH`), uczona na wszystkich zapytaniach zbioru uczącego (dane spoza okna migracji).
   Kategorie: one-hot. Liczby: mediana w miejsce braku + wskaźnik braku, standaryzacja.
2. LightGBM (te same parametry co v2) na obsłużonych zapytaniach z wynikiem po 45 dniach, target `umowa_45d`,
   waga `min(1 / P(obsłużony), MAKS_WAGA)`. Obsłużone zapytania podobne do tych, które zwykle zostają bez kontaktu
   (np. `domteraz`), ważą więcej i „zastępują” nieobsłużone.

Wynik (`predict`): szansa na umowę zapytania, gdyby doradca się z nim skontaktował (przy założeniu, że decyzję
o kontakcie wyjaśniają cechy zapytania). Model skłonności nie jest potrzebny do predykcji, zapisujemy go do opisu
wag (`sklonnosc`, `wagi`).
"""

import numpy as np
import pandas as pd
from api.ai.features.leady.cechy import KATEGORIE, KOLUMNY_CECH
from api.ai.lead_model.versions.v2_lgbm_naiwny.model import ModelLGBMNaiwny
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

MAKS_WAGA = 10.0


def model_sklonnosci(cechy: tuple[str, ...] = KOLUMNY_CECH) -> Pipeline:
    kategorie = [k for k in cechy if k in KATEGORIE]
    liczby = [k for k in cechy if k not in KATEGORIE]
    przygotowanie = ColumnTransformer(
        [
            ("kategorie", OneHotEncoder(handle_unknown="ignore"), kategorie),
            ("liczby", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), liczby),
        ]
    )
    return make_pipeline(przygotowanie, LogisticRegression(max_iter=2000))


class ModelLGBMIPW(ModelLGBMNaiwny):
    wersja = "v2b_lgbm_ipw"

    def __init__(self, cechy: tuple[str, ...] = KOLUMNY_CECH, parametry: dict | None = None, maks_waga=MAKS_WAGA):
        super().__init__(cechy=cechy, parametry=parametry)
        self.maks_waga = float(maks_waga)

    def _x_sklonnosci(self, leady: pd.DataFrame) -> pd.DataFrame:
        X = leady[list(self.cechy)].copy()
        for k in self.cechy:
            X[k] = X[k].astype("object") if k in KATEGORIE else X[k].astype("float64")
        return X

    def sklonnosc(self, leady: pd.DataFrame) -> np.ndarray:
        """P(obsłużony | cechy zapytania) z modelu skłonności."""
        return self.sklonnosc_.predict_proba(self._x_sklonnosci(leady))[:, 1]

    def wagi(self, leady: pd.DataFrame) -> np.ndarray:
        """min(1 / P(obsłużony), maks_waga)."""
        return np.minimum(1.0 / self.sklonnosc(leady), self.maks_waga)

    def fit(self, leady: pd.DataFrame, y: pd.Series, obsluzony=None) -> "ModelLGBMIPW":
        """`leady`: wszystkie zapytania zbioru uczącego; `obsluzony`: flaga obsługi (domyślnie kolumna `obsluzony`).

        Model skłonności uczy się na wszystkich wierszach, LightGBM tylko na obsłużonych z wagą IPW.
        """
        obsluzony = np.asarray(leady["obsluzony"] if obsluzony is None else obsluzony, dtype=bool)
        y = np.asarray(y, dtype=float)
        self.sklonnosc_ = model_sklonnosci(self.cechy).fit(self._x_sklonnosci(leady), obsluzony.astype(int))
        obsluzone = leady[obsluzony].reset_index(drop=True)
        wagi = self.wagi(obsluzone)
        self.statystyki_wag_ = {
            "n_uczacych": int(len(obsluzone)),
            "przyciete": int((1.0 / self.sklonnosc(obsluzone) > self.maks_waga).sum()),
            "suma_wag": float(wagi.sum()),
            # efektywna liczebność (Kish): (Σw)² / Σw²
            "efektywna_liczebnosc": float(wagi.sum() ** 2 / (wagi**2).sum()),
        }
        return super().fit(obsluzone, y[obsluzony], wagi=wagi)
