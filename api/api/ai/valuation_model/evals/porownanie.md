# Wycena lokali: porównanie wersji

Wszystkie wersje uczone na zbiorze `trening` i oceniane na `walidacja` / `test` z podziału czasowego
[`podzial.sql`](../../features/wycena/podzial.sql) (transakcje RCN według `data_aktu`: trening 2023-01 – 2025-06,
38 522; walidacja 2025-07 – 2025-12, 7 686; test 2026-01 – 2026-06, 7 487). Target: cena transakcyjna `cena_pln`.
MAE w PLN, MAPE i MdAPE w %. Wyniki liczy [`ewaluacja.py`](ewaluacja.py) i zapisuje je w
`versions/<wersja>/metryki.json`. Raport z RMSE, podziałem na miasta i rynek oraz kodem:
[docs/b2_wycena_v0_v1.md](../../../../../docs/b2_wycena_v0_v1.md).

Te same runy (parametry, metryki, model) są w MLflow, eksperyment `wycena` (`mlflow.db`, zapis: `ewaluacja.py`).
Podział losowy 85/15 dla porównania: [docs/b1_v1.md](../../../../../docs/b1_v1.md).

Warunek banku: MAPE ≤ 8% na operatach kontrolnych (jeszcze nie liczone, tu MAPE na transakcjach RCN).

| Wersja | Zbiór | MAE | MAPE | MdAPE | Uwagi |
|---|---|---:|---:|---:|---|
| v0_mediana_dzielnicy | walidacja | 80 020 | 13,6 | 11,0 | baseline: mediana ceny m² dzielnicy (trening) × metraż |
| v0_mediana_dzielnicy | test | 83 401 | 13,4 | 11,3 | baseline; zaniża wycenę (mediana błędu −6,4%), bo nie uwzględnia wzrostu cen |
| v1_liniowa | walidacja | 57 814 | 10,2 | 7,6 | regresja liniowa na ln(ceny); ln(metraż) wybrany na walidacji (MAPE 10,2 vs 13,4 dla metrażu w m²) |
| v1_liniowa | test | 63 252 | 10,2 | 8,3 | lepsza od v0 na wszystkich metrykach i w każdym mieście; bez czasu transakcji: mediana błędu −6,3%; 3 dzielnice (< 30 transakcji) w „reszcie miasta”; brak przedziału |
