# Wycena lokali: porównanie wersji

Wszystkie wersje uczone na zbiorze `trening` i oceniane na `walidacja` / `test` z podziału czasowego
[`podzial.sql`](../../features/wycena/podzial.sql) (transakcje RCN według `data_aktu`: trening 2023-01 – 2025-06,
38 522; walidacja 2025-07 – 2025-12, 7 686; test 2026-01 – 2026-06, 7 487). Target: cena transakcyjna `cena_pln`.
MAE w PLN, MAPE i MdAPE w %. Wyniki liczy [`ewaluacja.py`](ewaluacja.py) i zapisuje je w
`versions/<wersja>/metryki.json`. Raport z RMSE, podziałem na miasta i rynek oraz kodem:
[docs/b2_wycena_v0_v1.md](../../../../../docs/b2_wycena_v0_v1.md).

Te same runy (parametry, metryki, model) są w MLflow, eksperyment `wycena` (`mlflow.db`, zapis: `ewaluacja.py`;
v2: [`ewaluacja_v2.py`](ewaluacja_v2.py)).
Podział losowy 85/15 dla porównania: [docs/b1_v1.md](../../../../../docs/b1_v1.md).

Warunek banku: MAPE ≤ 8% na operatach kontrolnych (jeszcze nie liczone, tu MAPE na transakcjach RCN).

| Wersja | Zbiór | MAE | MAPE | MdAPE | Uwagi |
|---|---|---:|---:|---:|---|
| v0_mediana_dzielnicy | walidacja | 80 020 | 13,6 | 11,0 | baseline: mediana ceny m² dzielnicy (trening) × metraż |
| v0_mediana_dzielnicy | test | 83 401 | 13,4 | 11,3 | baseline; zaniża wycenę (mediana błędu −6,4%), bo nie uwzględnia wzrostu cen |
| v1_liniowa | walidacja | 57 814 | 10,2 | 7,6 | regresja liniowa na ln(ceny); ln(metraż) wybrany na walidacji (MAPE 10,2 vs 13,4 dla metrażu w m²) |
| v1_liniowa | test | 63 252 | 10,2 | 8,3 | lepsza od v0 na wszystkich metrykach i w każdym mieście; bez czasu transakcji: mediana błędu −6,3%; 3 dzielnice (< 30 transakcji) w „reszcie miasta”; brak przedziału |
| v2_lightgbm | walidacja | 57 667 | 10,2 | 7,5 | LightGBM na ln(ceny), te same cechy co v1; walidacja użyta do wczesnego zatrzymania (265 drzew), więc wynik lekko optymistyczny |
| v2_lightgbm | test | 63 095 | 10,2 | 8,3 | sam boosting ≈ v1 (MAPE −0,01 pp, MAE −157 zł, RMSE +540 zł); mediana błędu −6,4%; test otwarty raz 2026-11-15; [b3_wycena_v2_geo.md](../../../../../docs/b3_wycena_v2_geo.md) |
| v2_lgbm_geo | walidacja | 46 772 | 8,7 | 6,0 | LightGBM + otoczenie (geo.sql bez geohash6) + sąsiedztwo (20 najbliższych z 12 mies. wstecz, trening out-of-fold); 261 drzew; geohash6 odrzucony na walidacji (MAPE 8,9) |
| **v2_lgbm_geo** | **test** | **50 540** | **8,6** | **6,5** | najlepsza wersja: MAPE 8,55 vs 10,17 w v1; lepsza w każdym mieście i na obu rynkach; mediana błędu −4,5%; test otwarty raz 2026-11-15; [b4_wycena_v2_lgbm_geo.md](../../../../../docs/b4_wycena_v2_lgbm_geo.md) |

## Ablacja rodzin cech v2_lgbm_geo

Każdy wariant: ta sama klasa, hiperparametry i podział, własne wczesne zatrzymanie na walidacji. Zmiana = wariant −
wariant główny (dodatnia = bez tej rodziny gorzej). Test policzony jednym przebiegiem dla wszystkich wariantów,
bez wybierania na teście. Szczegóły: `versions/v2_lgbm_geo/ablacja.json`, [b4_wycena_v2_lgbm_geo.md](../../../../../docs/b4_wycena_v2_lgbm_geo.md).

| Wariant | Walidacja MAPE | Zmiana | Test MAE | Test MAPE | Zmiana | Test MdAPE | Test mediana błędu |
|---|---:|---:|---:|---:|---:|---:|---:|
| główny (geo + sąsiedztwo) | 8,72 | — | 50 540 | 8,55 | — | 6,49 | −4,46 |
| bez geo (tylko sąsiedztwo) | 9,25 | +0,53 | 52 519 | 8,87 | +0,32 | 6,69 | −3,53 |
| bez sąsiedztwa (tylko geo) | 9,16 | +0,44 | 57 016 | 9,32 | +0,77 | 7,49 | −6,33 |
| bez POI (sąsiedztwo + centrum, GUS) | 8,82 | +0,10 | 51 132 | 8,61 | +0,07 | 6,61 | −4,30 |
| bez geo i sąsiedztwa (= v2_lightgbm) | 10,16 | +1,44 | 63 095 | 10,16 | +1,61 | 8,30 | −6,43 |
| sąsiedzi tylko opublikowani przed dniem aktu | 8,69 | −0,03 | 50 765 | 8,56 | +0,01 | 6,54 | −4,58 |
