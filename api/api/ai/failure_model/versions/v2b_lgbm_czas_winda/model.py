"""v2b: ten sam LightGBM co v2_lgbm_losowy, ale uczony i oceniany jak w praktyce (evals/ewaluacja_v2.py,
`podzial_czas_winda`): trening dni 2023-03-01 – 2025-06-30, walidacja (wczesne zatrzymanie) 2025-07-01 –
2025-12-31, test 2026-01-01 – 2026-09-22; 28 losowych wind (20%) w ogóle nie trafia do treningu ani walidacji,
żeby sprawdzić model na windach, których nie widział (np. nowy budynek).
"""

from api.ai.failure_model.versions.v2_lgbm_losowy.model import ModelLGBMWind


class ModelLGBMCzasWinda(ModelLGBMWind):
    wersja = "v2b_lgbm_czas_winda"
