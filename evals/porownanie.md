# Porównanie modeli z punktem odniesienia (baseline)

Każdy model porównujemy z baseline: prostą regułą albo obecnym sposobem działania Domilo, liczonym na tym samym
podziale danych i tymi samymi metrykami. Wyniki pochodzą wyłącznie z obliczeń na `data/`; przy każdym wyniku
podajemy link do raportu w `docs/` z SQL i kodem.

| Model | Baseline | Metryka | Podział danych | Wynik baseline | Wynik modelu | Pokrycie przedziału 80% | Szerokość (P90 − P10) / P50 | Odsetek odmów | Raport |
|---|---|---|---|---|---|---|---|---|---|
| Wycena lokali z przedziałem | v0_mediana_dzielnicy: mediana ceny m² dzielnicy (trening) × metraż | MAE, RMSE, MAPE, MdAPE na transakcjach RCN; docelowo MAPE (warunek banku ≤ 8% na operatach kontrolnych) i pokrycie przedziału 80% (warunek 77–83%) | RCN wg `data_aktu`: trening 2023-01 – 2025-06 (38 522), walidacja 2025-07 – 2025-12 (7 686), test 2026-01 – 2026-06 (7 487); `api/api/ai/features/wycena/podzial.sql`; sprawdzian: 300 operatów kontrolnych 2026-09 (patrz pod tabelą) | test: MAE 83 401 zł, RMSE 118 320 zł, MAPE 13,4%, MdAPE 11,3% | v1_liniowa, test: MAE 63 252 zł, RMSE 94 999 zł, MAPE 10,2%, MdAPE 8,3% (bez przedziału); v2_lightgbm (te same cechy), test: MAE 63 095 zł, RMSE 95 538 zł, MAPE 10,2%, MdAPE 8,3%, czyli bez poprawy względem v1; **v2_lgbm_geo** (+ otoczenie + sąsiedztwo), test: MAE 50 540 zł, RMSE 78 933 zł, MAPE 8,55%, MdAPE 6,5% (ablacja, test MAPE: bez sąsiedztwa 9,32%, bez geo 8,87%, bez POI 8,61%); poza danymi (Katowice, 40 operatów due diligence) v2_lgbm_geo zawyża o +24,9% (mediana), cena ofertowa +5,5%; **przedział 80% v2_lgbm_geo_cqr** (kwantylowe LightGBM + CQR na walidacji), test: pokrycie 77,6% (przed kalibracją 71,3%), mediana szerokości 23,9%, w normie 77–83% 11 z 20 segmentów; baseline przedziału (stały −8,0% / +15,4% wokół wyceny): 79,1%, szerokość 23,4%, 9 z 20 segmentów; **detektor OOD v3_przedzialy** (reguły + kNN + Isolation Forest, próg = kwantyl 0,99 treningu z walidacji): odmowy test 5,6% (MAPE przyjętych 8,50% vs 8,55% bez odmów), Katowice 100%, Domilo 7,9%; baseline odmowy = bezpiecznik v1 „nieznane miasto”: Katowice 100%, test i Domilo 0%; **v3_przedzialy** (v2_lgbm_geo_cqr + odmowa OOD), test na przyjętych: MAE 49 018 zł, MAPE 8,50%, MdAPE 6,4%; **v4_llm_cechy (obecna, current.yaml)** (v3 + cechy lokalu z opisu odczytane przez LLM), test: MAPE 8,30% (z odmowami 8,28%), testowe dopasowania 8,26% vs v2_lgbm_geo 8,97%; operaty kontrolne 5,40% vs v1 7,14% ([b1_v4_llm_cechy.md](../docs/b1_v4_llm_cechy.md)) | test: v3_przedzialy 77,9%, v2_lgbm_geo_cqr 77,6%, przed kalibracją 71,3%; baseline stały ±%: 79,1% (norma banku 77–83%) | test: v3_przedzialy 23,7%, v2_lgbm_geo_cqr 23,9%; baseline stały ±%: 23,4% | v3_przedzialy: test 5,6%, oferty z Katowic 100%, lokale Domilo 7,9% (569 z 7 200); baseline (bezpiecznik v1: nieznane miasto): 0% / 100% / 0% | [b1_dane.md](../docs/b1_dane.md), [b2_wycena_v0_v1.md](../docs/b2_wycena_v0_v1.md), [b3_wycena_v2_geo.md](../docs/b3_wycena_v2_geo.md), [b4_wycena_v2_lgbm_geo.md](../docs/b4_wycena_v2_lgbm_geo.md), [b1_bledy.md](../docs/b1_bledy.md), [b1_przedzialy.md](../docs/b1_przedzialy.md), [b1_ood.md](../docs/b1_ood.md), [b1_v3.md](../docs/b1_v3.md); wersje: [valuation_model/evals/porownanie.md](../api/api/ai/valuation_model/evals/porownanie.md) |
| Kolejka zapytań dla doradców | v0_regula_zrodla: konwersja `umowa_45d` pary (źródło × linia) z niecenzurowanych zapytań poza oknem migracji (149 423) | AUC, lift@10%, precision@k (k = średnia dzienna liczba nowych zapytań w zbiorze: okno 127, test 125), koszt tokenów / 1 000 zapytań | v0/v1: wszystkie 5 320 zapytań z okna migracji CRM 2025-03-03 – 2025-04-13 (559 umów, każde zapytanie obsłużone przez call center); od v2 także zwykły test: wszystkie 15 217 niecenzurowanych zapytań 2026-03-01 – 2026-06-30 (`features/leady/podzial_v2.py`); target `leady_cel.umowa_45d` | okno: AUC 0,637, lift@10% 1,89, precision@127 22,0%; 0 tokenów; v0 uczona na treningu v2: okno AUC 0,633 / 1,89 / 22,0%, test AUC 0,684, lift@10% 2,31, precision@125 17,7% | v1_llm_zero_shot (ocena LLM / 10, bez uczenia): AUC 0,620, lift@10% 1,40, precision@127 15,1%, czyli **gorsza od baseline** na czołówce (v1 − v0: lift −0,83 … −0,12, precision −12,0 … −1,7 pp; AUC −0,053 … +0,017, nierozstrzygnięte); 1,19 mln tokenów wejścia i 70 tys. wyjścia / 1 000 zapytań, koszt w zł: brak cennika w `leasing_bc/zalozenia.yaml`; **v2_lgbm_naiwny** (LightGBM na cechach z chwili zapytania + sygnały v1, trening: zamknięte zapytania 2023-01 – 2026-02 bez okna, nieobsłużone = 0; v0 przeuczona na tym samym treningu): **zwykły test 2026-03 – 2026-06** (15 217 zapytań, 1 167 umów, k = 125): v2 AUC 0,793, lift@10% 3,75, precision@125 43,2% vs v0 0,684 / 2,31 / 17,7% i v1 0,617 / 1,49 / 11,5% (v2 − v0: AUC +0,096 … +0,122, lift +1,18 … +1,71, precision +16,7 … +33,9 pp); **okno migracji**: v2 AUC 0,764, lift@10% 3,33, precision@127 49,6% vs v0 0,633 / 1,89 / 22,0% i v1 0,620 / 1,40 / 15,1% (v2 − v0: AUC +0,111 … +0,150, lift +1,06 … +1,81, precision +18,8 … +35,3 pp), czyli **lepsza od baseline i od v1 na obu zbiorach**; wada: w oknie `domteraz` ma 21,3% umów, a 0,2% czołówki 10% v2 (model przejmuje nawyk nieobsługiwania `domteraz`); v2 wymaga odpowiedzi v1 dla każdego zapytania (te same tokeny / 1 000 co v1), bez sygnałów LLM: test AUC 0,783, okno 0,751; żadna wersja nie jest w `current.yaml` | — | — | — | [kolejka_target.md](../docs/kolejka_target.md), [llm_ocena_leada_v1.md](../docs/llm_ocena_leada_v1.md), [kolejka_v0_v1.md](../docs/kolejka_v0_v1.md), [kolejka_v2_lgbm_naiwny.md](../docs/kolejka_v2_lgbm_naiwny.md); wersje: [lead_model/evals/porownanie.md](../api/api/ai/lead_model/evals/porownanie.md) |
| Lista retencyjna najemców | — | — | — | — | — | — | — | — | — |
| Alerty o awariach wind | — | — | — | — | — | — | — | — | — |

„—” = jeszcze nie ustalone / nie policzone.

### Wycena: sprawdzian na 300 operatach kontrolnych i celowy przeciek (2026-11-15, [b1_przeciek_opisu.md](../docs/b1_przeciek_opisu.md))

| Model | MAPE na 300 operatach kontrolnych | Mediana błędu ze znakiem | MAPE test: dopasowania z ceną w opisie (2 533) | MAPE test: wszystkie (7 487) |
|---|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | 13,4% | −13,3% | 13,9% | 13,4% |
| v1_liniowa (obecna) | 7,1% | −5,4% | 10,6% | 10,2% |
| v2_lightgbm | 7,5% | −5,9% | 10,6% | 10,2% |
| v2_lgbm_geo (= P50 v3) | 5,9% | −3,2% | — | 8,55% |
| v3_przedzialy (z odmowami: 1,0% na operatach, 5,6% na teście) | 5,9% | −3,2% | — | 8,50% |
| **v4_llm_cechy** (P50; obecna od 2026-11-15) | **5,4%** | −2,8% | — | 8,30% |
| v2_lightgbm + cena z opisu (**celowy przeciek, nie do użycia**), opis Domilo bez ceny | 7,9% | −6,2% | 5,1% | 8,4% |
| jw., czynsz najmu z opisu Domilo wzięty za cenę | 56,8% | −69,2% | — | — |

Cechy lokali Domilo: `pms_lokale` + `pms_budynki` (`rok_oddania` jako rok budowy). Dla v2_lgbm_geo, v3 i v4
cechy otoczenia i sąsiedztwa budynku liczy `wczytaj_lokale_domilo` (`ood_v3.py`, sąsiedzi znani 2026-10-01);
wiersze v2_lgbm_geo, v3, v4: [b1_v4_llm_cechy.md](../docs/b1_v4_llm_cechy.md).

### Wycena: v4_llm_cechy, cechy lokalu z LLM (2026-11-15, [b1_v4_llm_cechy.md](../docs/b1_v4_llm_cechy.md))

Baseline: v0_mediana_dzielnicy; porównanie właściwe: v2_lgbm_geo / v3 (ten sam model bez cech LLM). P50 bez odmów,
te same lokale; różnica z bootstrapem par (2 000 prób, 95% CI). Reguła wyboru do `current.yaml` ustalona przed
uczeniem: MAPE v4 na operatach < MAPE wersji obecnej (v1_liniowa).

| Zbiór | v0 (baseline) | v1_liniowa | v2_lgbm_geo | v4_llm_cechy | v4 − v2_lgbm_geo (95% CI) | Pokrycie 80% v4 (v3) |
|---|---:|---:|---:|---:|---|---:|
| test: dopasowania (2 882) | 13,89% | 10,65% | 8,97% | **8,26%** | −0,71 pp (−0,81 … −0,60) | 76,4% (77,0%) |
| test: wszystkie (7 487) | 13,40% | 10,17% | 8,55% | **8,30%** | −0,24 pp (−0,29 … −0,20) | 77,8% (77,6%) |
| operaty kontrolne (300) | 13,39% | 7,14% | 5,90% | **5,40%** | −0,50 pp (−0,75 … −0,23) | 79,0% (82,3%) |

v4 − v1 na operatach: −1,74 pp (−2,22 … −1,29), więc v4 zastąpiła v1 w `current.yaml`. Ablacja (v4 z cechami LLM
= brak) na operatach: 6,02%. Standard ze zdjęć w miejsce standardu z opisu pogarsza v4: operaty 6,33%
(+0,93 pp), testowe dopasowania ze zdjęciami 8,56% wobec 7,89%. Tokeny na 1 000 opisów: 1,66 mln wejścia
(1,51 mln z cache OpenAI), 59 tys. wyjścia; na 1 000 lokali ze zdjęciami: 3,42 mln wejścia (1,30 mln z cache),
61 tys. wyjścia; koszt w zł: brak cennika w danych.
