# Porównanie modeli z punktem odniesienia (baseline)

Każdy model porównujemy z baseline: prostą regułą albo obecnym sposobem działania Domilo, liczonym na tym samym
podziale danych i tymi samymi metrykami. Wyniki pochodzą wyłącznie z obliczeń na `data/`; przy każdym wyniku
podajemy link do raportu w `docs/` z SQL i kodem.

| Model | Baseline | Metryka | Podział danych | Wynik baseline | Wynik modelu | Raport |
|---|---|---|---|---|---|---|
| Wycena lokali z przedziałem | v0_mediana_dzielnicy: mediana ceny m² dzielnicy (trening) × metraż | MAE, RMSE, MAPE, MdAPE na transakcjach RCN; docelowo MAPE (warunek banku ≤ 8% na operatach kontrolnych) i pokrycie przedziału 80% (warunek 77–83%) | RCN wg `data_aktu`: trening 2023-01 – 2025-06 (38 522), walidacja 2025-07 – 2025-12 (7 686), test 2026-01 – 2026-06 (7 487); `api/api/ai/features/wycena/podzial.sql`; sprawdzian: 300 operatów kontrolnych 2026-09 (jeszcze nie liczony) | test: MAE 83 401 zł, RMSE 118 320 zł, MAPE 13,4%, MdAPE 11,3% | v1_liniowa, test: MAE 63 252 zł, RMSE 94 999 zł, MAPE 10,2%, MdAPE 8,3% (bez przedziału); v2_lightgbm (te same cechy), test: MAE 63 095 zł, RMSE 95 538 zł, MAPE 10,2%, MdAPE 8,3%, czyli bez poprawy względem v1; **v2_lgbm_geo** (+ otoczenie + sąsiedztwo), test: MAE 50 540 zł, RMSE 78 933 zł, MAPE 8,55%, MdAPE 6,5% (ablacja, test MAPE: bez sąsiedztwa 9,32%, bez geo 8,87%, bez POI 8,61%) | [b1_dane.md](../docs/b1_dane.md), [b2_wycena_v0_v1.md](../docs/b2_wycena_v0_v1.md), [b3_wycena_v2_geo.md](../docs/b3_wycena_v2_geo.md), [b4_wycena_v2_lgbm_geo.md](../docs/b4_wycena_v2_lgbm_geo.md); wersje: [valuation_model/evals/porownanie.md](../api/api/ai/valuation_model/evals/porownanie.md) |
| Kolejka zapytań dla doradców | — | — | — | — | — | — |
| Lista retencyjna najemców | — | — | — | — | — | — |
| Alerty o awariach wind | — | — | — | — | — | — |

„—” = jeszcze nie ustalone / nie policzone.
