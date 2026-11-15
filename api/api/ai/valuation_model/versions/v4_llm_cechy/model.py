"""v4_llm_cechy: v3_przedzialy + cechy lokalu odczytane przez LLM z opisu ogłoszenia (docs/b1_v4_llm_cechy.md).

Różnice względem v3_przedzialy:
- P50, P10 i P90 (LightGBM, ln ceny) dostają cechy z LLM (api/api/ai/features/wycena/cechy_llm.py):
  `llm_standard` (standard wykończenia 1–5, liczbowo) oraz kategorie `llm_ekspozycja`, `llm_widok`, `llm_balkon`,
  `llm_stan_budynku`. Brak opisu (transakcja bez dopasowanej oferty) = NaN, LightGBM idzie gałęzią dla braków;
  „brak_info” (opis milczy) to osobna wartość kategorii.
- Przedział: ta sama metoda (kwantylowe LightGBM + CQR na walidacji), uczona od nowa z cechami LLM.
- Odmowa: ten sam detektor OOD co v3 (`detektor=` w konstruktorze, np. versions/v3_przedzialy/ood.joblib),
  bez ponownego uczenia; przestrzeń detektora nie zawiera cech LLM.
"""

import pandas as pd
from api.ai.features.wycena.cechy_llm import LLM_KATEGORII, LLM_LICZBOWE
from api.ai.valuation_model.versions.v2_lgbm_geo.model import CECHY_DOMYSLNE
from api.ai.valuation_model.versions.v3_przedzialy.model import ModelWycenyV3
from api.ai.valuation_model.versions.v3_przedzialy.ood import DetektorOOD

PARAMETRY_PUNKTOWE_V4 = {
    "cechy_liczbowe": tuple(CECHY_DOMYSLNE) + tuple(LLM_LICZBOWE),
    "cechy_kategorii": tuple(LLM_KATEGORII),
}


class ModelWycenyV4(ModelWycenyV3):
    wersja = "v4_llm_cechy"

    def __init__(self, *, parametry_punktowe: dict | None = None, **kwargs):
        super().__init__(parametry_punktowe={**PARAMETRY_PUNKTOWE_V4, **(parametry_punktowe or {})}, **kwargs)

    def _detektor_do_wersji(self, X: pd.DataFrame) -> DetektorOOD:
        return self.detektor if self.detektor is not None else super()._detektor_do_wersji(X)
