# Porównanie modeli z punktem odniesienia (baseline)

Każdy model porównujemy z baseline: prostą regułą albo obecnym sposobem działania Domilo, liczonym na tym samym
podziale danych i tymi samymi metrykami. Wyniki pochodzą wyłącznie z obliczeń na `data/`; przy każdym wyniku
podajemy link do raportu w `docs/` z SQL i kodem.

| Model | Baseline | Metryka | Podział danych | Wynik baseline | Wynik modelu | Pokrycie przedziału 80% | Szerokość (P90 − P10) / P50 | Odsetek odmów | Raport |
|---|---|---|---|---|---|---|---|---|---|
| Wycena lokali z przedziałem | v0_mediana_dzielnicy: mediana ceny m² dzielnicy (trening) × metraż | MAE, RMSE, MAPE, MdAPE na transakcjach RCN; docelowo MAPE (warunek banku ≤ 8% na operatach kontrolnych) i pokrycie przedziału 80% (warunek 77–83%) | RCN wg `data_aktu`: trening 2023-01 – 2025-06 (38 522), walidacja 2025-07 – 2025-12 (7 686), test 2026-01 – 2026-06 (7 487); `api/api/ai/features/wycena/podzial.sql`; sprawdzian: 300 operatów kontrolnych 2026-09 (policzony dla v0, v1, v2_lightgbm: patrz pod tabelą) | test: MAE 83 401 zł, RMSE 118 320 zł, MAPE 13,4%, MdAPE 11,3% | v1_liniowa, test: MAE 63 252 zł, RMSE 94 999 zł, MAPE 10,2%, MdAPE 8,3% (bez przedziału); v2_lightgbm (te same cechy), test: MAE 63 095 zł, RMSE 95 538 zł, MAPE 10,2%, MdAPE 8,3%, czyli bez poprawy względem v1; **v2_lgbm_geo** (+ otoczenie + sąsiedztwo), test: MAE 50 540 zł, RMSE 78 933 zł, MAPE 8,55%, MdAPE 6,5% (ablacja, test MAPE: bez sąsiedztwa 9,32%, bez geo 8,87%, bez POI 8,61%); poza danymi (Katowice, 40 operatów due diligence) v2_lgbm_geo zawyża o +24,9% (mediana), cena ofertowa +5,5%; **przedział 80% v2_lgbm_geo_cqr** (kwantylowe LightGBM + CQR na walidacji), test: pokrycie 77,6% (przed kalibracją 71,3%), mediana szerokości 23,9%, w normie 77–83% 11 z 20 segmentów; baseline przedziału (stały −8,0% / +15,4% wokół wyceny): 79,1%, szerokość 23,4%, 9 z 20 segmentów; **detektor OOD v3_przedzialy** (reguły + kNN + Isolation Forest, próg = kwantyl 0,99 treningu z walidacji): odmowy test 5,6% (MAPE przyjętych 8,50% vs 8,55% bez odmów), Katowice 100%, Domilo 7,9%; baseline odmowy = bezpiecznik v1 „nieznane miasto”: Katowice 100%, test i Domilo 0%; **v3_przedzialy** (v2_lgbm_geo_cqr + odmowa OOD), test na przyjętych: MAE 49 018 zł, MAPE 8,50%, MdAPE 6,4% | test: v3_przedzialy 77,9%, v2_lgbm_geo_cqr 77,6%, przed kalibracją 71,3%; baseline stały ±%: 79,1% (norma banku 77–83%) | test: v3_przedzialy 23,7%, v2_lgbm_geo_cqr 23,9%; baseline stały ±%: 23,4% | v3_przedzialy: test 5,6%, oferty z Katowic 100%, lokale Domilo 7,9% (569 z 7 200); baseline (bezpiecznik v1: nieznane miasto): 0% / 100% / 0% | [b1_dane.md](../docs/b1_dane.md), [b2_wycena_v0_v1.md](../docs/b2_wycena_v0_v1.md), [b3_wycena_v2_geo.md](../docs/b3_wycena_v2_geo.md), [b4_wycena_v2_lgbm_geo.md](../docs/b4_wycena_v2_lgbm_geo.md), [b1_bledy.md](../docs/b1_bledy.md), [b1_przedzialy.md](../docs/b1_przedzialy.md), [b1_ood.md](../docs/b1_ood.md), [b1_v3.md](../docs/b1_v3.md); wersje: [valuation_model/evals/porownanie.md](../api/api/ai/valuation_model/evals/porownanie.md) |
| Kolejka zapytań dla doradców | — | — | — | — | — | — | — | — | — |
| Lista retencyjna najemców | — | — | — | — | — | — | — | — | — |
| Alerty o awariach wind | — | — | — | — | — | — | — | — | — |

„—” = jeszcze nie ustalone / nie policzone.

### Wycena: sprawdzian na 300 operatach kontrolnych i celowy przeciek (2026-11-15, [b1_przeciek_opisu.md](../docs/b1_przeciek_opisu.md))

| Model | MAPE na 300 operatach kontrolnych | Mediana błędu ze znakiem | MAPE test: dopasowania z ceną w opisie (2 533) | MAPE test: wszystkie (7 487) |
|---|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | 13,4% | −13,3% | 13,9% | 13,4% |
| v1_liniowa (obecna) | 7,1% | −5,4% | 10,6% | 10,2% |
| v2_lightgbm | 7,5% | −5,9% | 10,6% | 10,2% |
| v2_lightgbm + cena z opisu (**celowy przeciek, nie do użycia**), opis Domilo bez ceny | 7,9% | −6,2% | 5,1% | 8,4% |
| jw., czynsz najmu z opisu Domilo wzięty za cenę | 56,8% | −69,2% | — | — |

Cechy lokali Domilo: `pms_lokale` + `pms_budynki` (`rok_oddania` jako rok budowy). Wersji z cechami otoczenia
(v2_lgbm_geo, v3_przedzialy) na operatach jeszcze nie liczyliśmy, bo brak cech otoczenia dla lokali Domilo.
