"""v3_przedzialy: wycena z przedziałem 80% albo odmowa z powodem („nie wiem”). Raport: docs/b1_v3.md.

Składniki (każdy opisany i oceniony osobno):
- P50: LightGBM v2_lgbm_geo (ln ceny, cechy otoczenia i sąsiedztwa), docs/b4_wycena_v2_lgbm_geo.md;
- P10 / P90: modele kwantylowe LightGBM + kalibracja CQR (v2_lgbm_geo_cqr), docs/b1_przedzialy.md;
- odmowa: detektor danych spoza zakresu (ood.py: reguły + kNN + Isolation Forest, progi = kwantyl 0,99 treningu),
  docs/b1_ood.md; opcjonalnie także odmowa przy szerokości (P90 − P10) / P50 > `max_szerokosc` (domyślnie wyłączona).

`predict_interval` zwraca p10, p50, p90, odmowa, powod. Przy odmowie p10/p50/p90 = NaN, a `powod` mówi słowami
dlaczego (kilka powodów rozdzielonych „; ”). `predict` = p50 (NaN przy odmowie).
"""

import numpy as np
import pandas as pd
from api.ai.valuation_model.base import KOLUMNY_ODMOWY, KOLUMNY_PRZEDZIALU, ModelWyceny
from api.ai.valuation_model.versions.v2_lgbm_geo.model import ModelLightGBMGeo
from api.ai.valuation_model.versions.v2_lgbm_geo_cqr.model import ModelPrzedzialuCQR
from api.ai.valuation_model.versions.v3_przedzialy.ood import DetektorOOD, _l


class ModelWycenyV3(ModelWyceny):
    wersja = "v3_przedzialy"

    def __init__(
        self,
        *,
        przedzial: ModelPrzedzialuCQR | None = None,
        detektor: DetektorOOD | None = None,
        prog_knn: float | None = None,
        prog_if: float | None = None,
        max_szerokosc: float | None = None,
        parametry_punktowe: dict | None = None,
        parametry_przedzialu: dict | None = None,
        parametry_detektora: dict | None = None,
    ):
        """Gotowe składniki (`przedzial` z nauczonym modelem punktowym i kalibracją, `detektor`) albo parametry do
        `fit`. prog_knn / prog_if: None = progi detektora (kwantyl 0,99 treningu). max_szerokosc: ułamek, np. 0,343."""
        self.przedzial = przedzial
        self.detektor = detektor
        self.prog_knn = prog_knn
        self.prog_if = prog_if
        self.max_szerokosc = max_szerokosc
        self.parametry_punktowe = parametry_punktowe or {}
        self.parametry_przedzialu = parametry_przedzialu or {}
        self.parametry_detektora = parametry_detektora or {}

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        X_wal: pd.DataFrame | None = None,
        y_wal: pd.Series | None = None,
        *,
        poczatek_odlozonej: pd.Timestamp | None = None,
    ) -> "ModelWycenyV3":
        """Uczy wszystkie składniki tak, jak powstały v2_lgbm_geo, v2_lgbm_geo_cqr i ood.py.

        P50: trening, wczesne zatrzymanie na (X_wal, y_wal). P10/P90: liczba drzew z wczesnego zatrzymania na części
        treningu z `data_aktu` >= poczatek_odlozonej, potem uczenie na całym treningu.
        CQR: kalibracja na (X_wal, y_wal).
        Detektor: trening. Bez zbioru walidacyjnego nie da się skalibrować przedziału.
        """
        if X_wal is None or y_wal is None:
            raise ValueError("v3_przedzialy wymaga zbioru walidacyjnego (wczesne zatrzymanie P50 i kalibracja CQR)")
        punktowy = ModelLightGBMGeo(**self.parametry_punktowe).fit(X, y, X_wal, y_wal)
        przedzial = ModelPrzedzialuCQR(punktowy, **self.parametry_przedzialu)
        y = pd.Series(np.asarray(y, dtype=float), index=X.index)
        if poczatek_odlozonej is not None:
            odl = (X["data_aktu"] >= poczatek_odlozonej).to_numpy()
            przedzial.fit(X[~odl], y[~odl], X[odl], y[odl])
        else:
            przedzial.fit(X, y)
        self.przedzial = przedzial.kalibruj(X_wal, y_wal)
        self.detektor = DetektorOOD(**self.parametry_detektora).fit(X)
        return self

    # --- kontrakt --------------------------------------------------------------------------------------------

    def predict_interval(self, X: pd.DataFrame) -> pd.DataFrame:
        """p10, p50, p90 (PLN) albo odmowa: NaN w p10/p50/p90, odmowa=True, powod słowami."""
        ocena = self.detektor.ocen(X, prog_knn=self.prog_knn, prog_if=self.prog_if)
        p = self.przedzial.predict_interval(X)
        odmowa = ocena["odmowa"].to_numpy().copy()
        powody = ocena["powody"].tolist()
        if self.max_szerokosc is not None:
            szer = ((p["p90"] - p["p10"]) / p["p50"]).to_numpy()
            for i in np.where(szer > self.max_szerokosc)[0]:
                tekst = (
                    f"Przedział za szeroki: (P90 − P10) / P50 = {_l(100 * szer[i])}% "
                    f"(dopuszczalne {_l(100 * self.max_szerokosc)}%)"
                )
                powody[i] = f"{powody[i]}; {tekst}" if powody[i] else tekst
                odmowa[i] = True
        wyj = p[list(KOLUMNY_PRZEDZIALU)].copy()
        wyj.loc[odmowa, list(KOLUMNY_PRZEDZIALU)] = np.nan
        wyj["odmowa"] = odmowa
        wyj["powod"] = powody
        return wyj[list(KOLUMNY_PRZEDZIALU) + list(KOLUMNY_ODMOWY)]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.predict_interval(X)["p50"].to_numpy()

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Wkłady cech do ln(P50) (SHAP modelu punktowego), p10, p90 i decyzja (odmowa, powod)."""
        p = self.predict_interval(X)
        return self.przedzial.punktowy.explain(X).join(p[["p10", "p90", "odmowa", "powod"]])

    # --- pomocnicze ------------------------------------------------------------------------------------------

    def ocen_ood(self, X: pd.DataFrame) -> pd.DataFrame:
        """Pełny wynik detektora (kody powodów, odl_knn, wynik_if, flagi) przy progach tej wersji."""
        return self.detektor.ocen(X, prog_knn=self.prog_knn, prog_if=self.prog_if)
