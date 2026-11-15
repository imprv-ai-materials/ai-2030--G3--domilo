# Porównanie modeli z punktem odniesienia (baseline)

Każdy model porównujemy z baseline: prostą regułą albo obecnym sposobem działania Domilo, liczonym na tym samym
podziale danych i tymi samymi metrykami. Wyniki pochodzą wyłącznie z obliczeń na `data/`; przy każdym wyniku
podajemy link do raportu w `docs/` z SQL i kodem.

| Model | Baseline | Metryka | Podział danych | Wynik baseline | Wynik modelu | Raport |
|---|---|---|---|---|---|---|
| Wycena lokali z przedziałem | — | MAPE (warunek banku ≤ 8% na operatach kontrolnych), pokrycie przedziału 80% (warunek 77–83%) | RCN wg `data_aktu`: trening 2023-01 – 2025-06 (38 522), walidacja 2025-07 – 2025-12 (7 686), test 2026-01 – 2026-06 (7 487); `api/api/ai/features/wycena/podzial.sql`; sprawdzian: 300 operatów kontrolnych 2026-09 | — | — | [b1_dane.md](../docs/b1_dane.md) |
| Kolejka zapytań dla doradców | — | — | — | — | — | — |
| Lista retencyjna najemców | — | — | — | — | — | — |
| Alerty o awariach wind | — | — | — | — | — | — |

„—” = jeszcze nie ustalone / nie policzone.
