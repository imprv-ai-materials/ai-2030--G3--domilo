"""v2_lgbm_geo_cqr: wycena v2_lgbm_geo + przedział 80% (P10–P90) z modeli kwantylowych LightGBM i kalibracji CQR.

Składniki:
- P50 = wycena zapisanego modelu punktowego v2_lgbm_geo (exp przewidywanego ln(ceny)), bez ponownego uczenia;
- P10, P90 = dwa modele kwantylowe LightGBM (`objective='quantile'`, alpha 0,1 i 0,9) na ln(ceny), z tymi samymi
  cechami i hiperparametrami co model punktowy (klasa ModelLightGBMGeo). Kwantyl ln(ceny) = ln(kwantyla ceny), więc
  exp(prognozy) to kwantyl ceny;
- kalibracja konformalna CQR (Romano, Patterson, Candès 2019) na osobnym zbiorze kalibracyjnym, w skali ln:
  wynik zgodności E_i = max(q_lo(x_i) − ln y_i, ln y_i − q_hi(x_i)), korekta Q = ⌈(n+1)·0,8⌉-ty najmniejszy E_i,
  przedział [q_lo − Q, q_hi + Q]. W złotych to mnożenie granic przez exp(∓Q): korekta jest względna, więc przedział
  zostaje szerszy w złotych dla drogich lokali i węższy dla tanich.
  Wariant asymetryczny (`cqr_asymetryczny`): osobne korekty dla dołu (q_lo − ln y) i góry (ln y − q_hi), każda na
  poziomie 0,9, czyli docelowo po 10% cen pod P10 i nad P90.

Na koniec granice porządkujemy względem P50: p10 = min(dolna, p50), p90 = max(górna, p50) (modele kwantylowe i model
punktowy uczą się osobno, więc dolna granica mogłaby wyjść powyżej P50). To może tylko poszerzyć przedział.

Liczba drzew modeli kwantylowych: wczesne zatrzymanie (strata kwantylowa) na podanej części odłożonej
(`fit(X, y, X_odl, y_odl)`), potem ponowne uczenie na X ∪ X_odl z wybraną liczbą drzew. Zbiór kalibracyjny nie
może brać udziału ani w uczeniu, ani w wyborze liczby drzew, inaczej gwarancja pokrycia przestaje obowiązywać.
"""

import math

import numpy as np
import pandas as pd
from api.ai.valuation_model.base import KOLUMNY_PRZEDZIALU, ModelWyceny
from api.ai.valuation_model.versions.v2_lgbm_geo.model import ModelLightGBMGeo

POZIOM = 0.8
ALFA_DOLNA, ALFA_GORNA = 0.1, 0.9
METODY = ("surowy", "cqr", "cqr_asymetryczny")


def kwantyl_konformalny(wyniki, poziom: float) -> float:
    """⌈(n+1)·poziom⌉-ty najmniejszy wynik (skończona poprawka próby); +∞, gdy n jest za małe."""
    w = np.sort(np.asarray(wyniki, dtype=float))
    k = math.ceil((len(w) + 1) * poziom)
    return math.inf if k > len(w) else float(w[k - 1])


def korekta_cqr(dolna, gorna, y, poziom: float = POZIOM) -> float:
    """Korekta CQR (symetryczna): kwantyl konformalny z max(dolna − y, y − gorna)."""
    dolna, gorna, y = (np.asarray(a, dtype=float) for a in (dolna, gorna, y))
    return kwantyl_konformalny(np.maximum(dolna - y, y - gorna), poziom)


def korekta_cqr_asymetryczna(dolna, gorna, y, poziom: float = POZIOM) -> tuple[float, float]:
    """Korekty (dół, góra): każda na poziomie 1 − (1 − poziom)/2 z osobnych wyników dolna − y oraz y − gorna."""
    dolna, gorna, y = (np.asarray(a, dtype=float) for a in (dolna, gorna, y))
    poziom_ogona = 1 - (1 - poziom) / 2
    return kwantyl_konformalny(dolna - y, poziom_ogona), kwantyl_konformalny(y - gorna, poziom_ogona)


class ModelPrzedzialuCQR(ModelWyceny):
    wersja = "v2_lgbm_geo_cqr"

    def __init__(
        self,
        punktowy: ModelLightGBMGeo,
        *,
        alfa_dolna: float = ALFA_DOLNA,
        alfa_gorna: float = ALFA_GORNA,
        poziom: float = POZIOM,
        max_drzew: int = 5000,
        stopping_rounds: int = 200,
    ):
        self.punktowy = punktowy
        self.alfa_dolna = alfa_dolna
        self.alfa_gorna = alfa_gorna
        self.poziom = poziom
        self.max_drzew = max_drzew
        self.stopping_rounds = stopping_rounds

    # --- uczenie i kalibracja --------------------------------------------------------------------------------

    def _kwantylowy(self, alfa: float, max_drzew: int) -> ModelLightGBMGeo:
        p = self.punktowy
        return ModelLightGBMGeo(
            cechy_liczbowe=p.cechy_liczbowe,
            cechy_kategorii=p.cechy_kategorii,
            max_drzew=max_drzew,
            stopping_rounds=self.stopping_rounds,
            parametry={**p.parametry, "objective": "quantile", "alpha": alfa},
        )

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        X_odl: pd.DataFrame | None = None,
        y_odl: pd.Series | None = None,
    ) -> "ModelPrzedzialuCQR":
        """Uczy modele kwantylowe (model punktowy musi być już nauczony). Bez X_odl: `max_drzew` drzew."""
        modele = {}
        for nazwa, alfa in (("p10", self.alfa_dolna), ("p90", self.alfa_gorna)):
            if X_odl is not None and y_odl is not None:
                drzewa = self._kwantylowy(alfa, self.max_drzew).fit(X, y, X_odl, y_odl).najlepsza_iteracja_
                X_cale = pd.concat([X, X_odl], ignore_index=True)
                y_cale = pd.concat([pd.Series(y), pd.Series(y_odl)], ignore_index=True)
                modele[nazwa] = self._kwantylowy(alfa, drzewa).fit(X_cale, y_cale)
            else:
                modele[nazwa] = self._kwantylowy(alfa, self.max_drzew).fit(X, y)
        self.dolny_, self.gorny_ = modele["p10"], modele["p90"]
        self.drzewa_ = {k: m.najlepsza_iteracja_ for k, m in modele.items()}
        return self

    def _granice_ln(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return np.log(self.dolny_.predict(X)), np.log(self.gorny_.predict(X))

    def kalibruj(self, X_kal: pd.DataFrame, y_kal: pd.Series) -> "ModelPrzedzialuCQR":
        """Korekty CQR z ln(cen) zbioru kalibracyjnego (nieużytego do uczenia ani wyboru liczby drzew)."""
        dolna, gorna = self._granice_ln(X_kal)
        ln_y = np.log(np.asarray(y_kal, dtype=float))
        self.korekta_ = korekta_cqr(dolna, gorna, ln_y, self.poziom)
        self.korekta_asym_ = korekta_cqr_asymetryczna(dolna, gorna, ln_y, self.poziom)
        self.n_kalibracji_ = int(len(ln_y))
        return self

    # --- kontrakt --------------------------------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.punktowy.predict(X)

    def predict_interval(self, X: pd.DataFrame, metoda: str = "cqr") -> pd.DataFrame:
        """p10, p50, p90 w PLN. metoda: `cqr` (domyślnie), `cqr_asymetryczny` albo `surowy` (bez kalibracji)."""
        if metoda not in METODY:
            raise ValueError(f"Nieznana metoda przedziału: {metoda} (dozwolone: {', '.join(METODY)})")
        if metoda != "surowy" and not hasattr(self, "korekta_"):
            raise RuntimeError("Przedział nieskalibrowany: najpierw kalibruj(X_kal, y_kal) albo metoda='surowy'")
        dolna, gorna = self._granice_ln(X)
        if metoda == "cqr":
            dolna, gorna = dolna - self.korekta_, gorna + self.korekta_
        elif metoda == "cqr_asymetryczny":
            dolna, gorna = dolna - self.korekta_asym_[0], gorna + self.korekta_asym_[1]
        p50 = self.punktowy.predict(X)
        wyj = pd.DataFrame(
            {"p10": np.minimum(np.exp(dolna), p50), "p50": p50, "p90": np.maximum(np.exp(gorna), p50)},
            index=X.index,
        )
        return wyj[list(KOLUMNY_PRZEDZIALU)]

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Wkłady cech do ln(P50) z modelu punktowego (SHAP) + granice przedziału CQR."""
        return self.punktowy.explain(X).join(self.predict_interval(X)[["p10", "p90"]])
