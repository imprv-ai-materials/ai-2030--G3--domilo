"""v2_lgbm_geo: LightGBM jak v2_lightgbm (ln(ceny), wczesne zatrzymanie na walidacji, te same hiperparametry)
z dodatkowymi cechami otoczenia (geo.sql) i sąsiedztwa (sasiedztwo.sql).

Wejście: kolumny KOLUMNY_CECH z base.py + `cechy_liczbowe` (+ `cechy_kategorii`, np. geohash6). Domyślny zestaw
to wszystkie rodziny: POI, centrum i dane dzielnicy, sąsiedztwo. Ablacje (ewaluacja_v2_geo.py) używają tej samej
klasy z mniejszym zestawem cech.
Braki (odl_metro_m poza Warszawą, mediana sąsiadów bez sąsiadów) LightGBM obsługuje sam (gałąź dla braków).
Wycena dla lokalu poza RCN wymaga tych samych cech policzonych na dzień wyceny: sąsiedzi tylko z transakcji
znanych przed tym dniem.
"""

import pandas as pd
from api.ai.features.wycena.zbior import RODZINA_GEO_BEZ_POI, RODZINA_POI, RODZINA_SASIEDZTWO
from api.ai.valuation_model.versions.v2_lightgbm.model import KOLUMNY_LICZBOWE, ModelLightGBM

CECHY_DOMYSLNE = RODZINA_POI + RODZINA_GEO_BEZ_POI + RODZINA_SASIEDZTWO


class ModelLightGBMGeo(ModelLightGBM):
    wersja = "v2_lgbm_geo"

    def __init__(
        self,
        *,
        cechy_liczbowe: tuple[str, ...] = CECHY_DOMYSLNE,
        cechy_kategorii: tuple[str, ...] = (),
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.cechy_liczbowe = tuple(cechy_liczbowe)
        self.cechy_kategorii = tuple(cechy_kategorii)

    def _wartosci_kategorii(self, X: pd.DataFrame) -> dict[str, pd.Series]:
        return {**super()._wartosci_kategorii(X), **{k: X[k] for k in self.cechy_kategorii}}

    def _kolumny_liczbowe(self) -> list[str]:
        return list(KOLUMNY_LICZBOWE) + list(self.cechy_liczbowe)

    def _sprawdz(self, X: pd.DataFrame) -> None:
        self.sprawdz_kolumny(X)
        brak = [k for k in self.cechy_liczbowe + self.cechy_kategorii if k not in X.columns]
        if brak:
            raise ValueError(f"Brak kolumn wymaganych przez {self.wersja}: {', '.join(brak)}")
