# Kolejka zapytań: porównanie wersji

Zbiór oceny: wszystkie 5 320 zapytań z okna migracji CRM (utworzone 2025-03-03 – 2025-04-13, `leady_cel.okno_migracji`),
559 umów (konwersja 10,51%). W oknie call center obsłużyło każde zapytanie, więc wynik nie zależy od tego, do kogo
doradcy oddzwonili ([docs/kolejka_target.md](../../../../../docs/kolejka_target.md)). Target: `umowa_45d`.
Wyniki liczy [`ewaluacja.py`](ewaluacja.py) i zapisuje je w `versions/<wersja>/metryki.json`. Te same runy są
w MLflow, eksperyment `leady`. Raport z tabelami i SQL:
[docs/kolejka_v0_v1.md](../../../../../docs/kolejka_v0_v1.md).

- **Miary:**
  - AUC;
  - lift@10%: konwersja 10% najwyżej ocenionych zapytań (532) / konwersja wszystkich;
  - precision@k: odsetek umów wśród k najwyżej ocenionych, k = 127 = średnia dzienna liczba nowych zapytań w oknie
    (5 320 / 42 dni).
- **Remisy:** przy remisie na granicy czołówki liczymy wartość oczekiwaną losowej kolejności.
- **Przedziały:** w nawiasach 95% przedział z bootstrapu par (2 000 losowań, te same dla obu wersji).
- **Koszt / 1 000 zapytań:** tokeny z rzeczywistych wywołań. Kwota wymaga cennika z
  `contexts_boundaries/leasing_bc/zalozenia.yaml`, a ten jest pusty, więc kwota to „brak cennika”.

| Wersja | Zbiór | AUC | lift@10% | precision@127 | Koszt / 1 000 zapytań | Uwagi |
|---|---|---:|---:|---:|---|---|
| **v0_regula_zrodla** | okno migracji (5 320) | **0,637** (0,612–0,662) | **1,89** (1,60–2,18) | **22,0%** (17,8–26,3) | 0 tokenów (bez API) | baseline: konwersja (źródło × linia) z 149 423 niecenzurowanych zapytań poza oknem (przed i po nim) |
| v1_llm_zero_shot | okno migracji (5 320) | 0,620 (0,597–0,642) | 1,40 (1,17–1,64) | 15,1% (11,5–18,8) | wejście 1 190 958 tokenów (w tym 1 058 000 z cache promptu OpenAI), wyjście 70 112; kwota: brak cennika | ocena LLM / 10, prompt `ocena_leada_v1`, `gpt-6-luna`, bez uczenia |

Różnica v1 − v0 (95% CI):

| Miara | Przedział |
|---|---|
| AUC | −0,053 … +0,017 (nierozstrzygnięta) |
| lift@10% | −0,83 … −0,12 |
| precision@127 | −12,0 … −1,7 pp |

v1 nie jest lepsza od baseline. Na czołówce kolejki jest gorsza.

Wrażliwość v0 na historię, z której liczymy konwersję (ten sam zbiór oceny):

| Wariant v0 | Zapytań w historii | AUC | lift@10% | precision@127 |
|---|---:|---:|---:|---:|
| poza oknem, przed i po nim (wersja zapisana) | 149 423 | 0,637 | 1,89 | 22,0% |
| tylko przed oknem (bez danych z przyszłości) | 88 432 | 0,630 | 1,89 | 21,7% |
| tylko obsłużone zapytania przed oknem | 72 232 | 0,651 | 1,89 | 21,7% |

`current.yaml` jest pusty: żadna wersja nie została wybrana do użycia.

## v2_lgbm_naiwny: zwykły test i okno migracji (2026-11-15)

LightGBM na cechach z chwili utworzenia zapytania (`features/leady/cechy_*.sql`: zapytanie, budżet, www, firma B2B,
tekst z sygnałami v1). Uczony na 127 527 zamkniętych zapytaniach 2023-01 – 2026-02 bez okna migracji, nieobsłużone
= 0. Liczy go [`ewaluacja_v2.py`](ewaluacja_v2.py); wynik w `versions/v2_lgbm_naiwny/metryki.json` i w MLflow
(`leady`, run `v2_lgbm_naiwny`). Raport: [docs/kolejka_v2_lgbm_naiwny.md](../../../../../docs/kolejka_v2_lgbm_naiwny.md).
v0 uczona tu na tym samym treningu (w oknie AUC 0,633 zamiast 0,637 wersji zapisanej wyżej).

| Wersja | Zbiór | AUC | lift@10% | precision@k |
|---|---|---:|---:|---:|
| v0_regula_zrodla (baseline) | test 2026-03 – 2026-06 (15 217; k = 125) | 0,684 (0,668–0,700) | 2,31 (2,11–2,52) | 17,7% (16,0–19,5) |
| v1_llm_zero_shot | test | 0,617 (0,601–0,632) | 1,49 (1,33–1,65) | 11,5% (9,7–13,5) |
| **v2_lgbm_naiwny** | test | **0,793** (0,780–0,806) | **3,75** (3,50–4,00) | **43,2%** (34,4–52,0) |
| v0_regula_zrodla (baseline) | okno migracji (5 320; k = 127) | 0,633 (0,608–0,659) | 1,89 (1,60–2,18) | 22,0% (17,8–26,3) |
| v1_llm_zero_shot | okno migracji | 0,620 (0,597–0,642) | 1,40 (1,17–1,64) | 15,1% (11,5–18,8) |
| **v2_lgbm_naiwny** | okno migracji | **0,764** (0,743–0,784) | **3,33** (3,00–3,68) | **49,6%** (40,9–57,5) |

Różnice (95% CI): v2 − v0 na teście: AUC +0,096 … +0,122, lift +1,18 … +1,71, precision +16,7 … +33,9 pp.
W oknie: AUC +0,111 … +0,150, lift +1,06 … +1,81, precision +18,8 … +35,3 pp. v2 − v1: wszystkie przedziały
powyżej zera (raport, T2–T3). Bez sygnałów LLM: test AUC 0,783, okno 0,751.

Wada wersji naiwnej: w oknie migracji `domteraz` dało 21,3% umów, a w czołówce 10% v2 jest 0,2% zapytań
z `domteraz` (raport, T5). Koszt: odpowiedź v1 dla każdego zapytania, ok. 1,19 mln tokenów wejścia i 70 tys. wyjścia
na 1 000 zapytań; kwota: brak cennika. `current.yaml` nadal pusty.

## v2b_lgbm_ipw: uczenie tylko na obsłużonych z wagą IPW (2026-11-15)

- **Model skłonności `P(obsłużony | cechy zapytania)`:** regresja logistyczna na cechach v2, uczona na
  127 527 zapytaniach treningu (dane spoza okna migracji). AUC dla obsłużenia na teście: 0,913.
- **LightGBM:** te same parametry co v2, tylko 104 479 obsłużonych zapytań, target `umowa_45d`, waga
  `min(1 / P, 10)`.
- **Gdzie wyniki:** liczy je [`ewaluacja_v2b.py`](ewaluacja_v2b.py); zapis w `versions/v2b_lgbm_ipw/metryki.json`
  i w MLflow (`leady`, run `v2b_lgbm_ipw`). Raport: [docs/kolejka_bias.md](../../../../../docs/kolejka_bias.md),
  B5–B9.

| Wersja | Zbiór | AUC | lift@10% | precision@k |
|---|---|---:|---:|---:|
| v0_regula_zrodla (baseline) | okno migracji (5 320; k = 127) | 0,633 (0,608–0,659) | 1,89 (1,60–2,18) | 22,0% (17,8–26,3) |
| v2_lgbm_naiwny | okno migracji | 0,764 (0,743–0,784) | 3,33 (3,00–3,68) | 49,6% (40,9–57,5) |
| **v2b_lgbm_ipw** | okno migracji | **0,785** (0,765–0,804) | **3,52** (3,19–3,86) | 48,0% (39,4–56,7) |
| v2b bez wag (kontrola) | okno migracji | 0,784 | 3,47 | 49,6% |
| v0_regula_zrodla (baseline) | test 2026-03 – 2026-06 (15 217; k = 125) | 0,684 (0,668–0,700) | 2,31 (2,11–2,52) | 17,7% (16,0–19,5) |
| v2_lgbm_naiwny | test | 0,793 (0,780–0,806) | 3,75 (3,50–4,00) | 43,2% (34,4–52,0) |
| **v2b_lgbm_ipw** | test | 0,790 (0,776–0,802) | 3,69 (3,44–3,94) | 40,8% (33,6–50,4) |
| v2b bez wag (kontrola) | test | 0,790 | 3,73 | 40,0% |

Różnice (95% CI):

| Para i zbiór | AUC | lift@10% | precision@k |
|---|---|---|---|
| v2b − v2, okno | +0,013 … +0,030 | +0,02 … +0,37 | −5,5 … +3,1 pp (nierozstrzygnięte) |
| v2b − v2, test | −0,008 … +0,001 | −0,17 … +0,05 | −5,6 … +4,0 pp |
| v2b − v0, okno | +0,126 … +0,175 | +1,25 … +2,00 | +18,0 … +34,2 pp |
| v2b − v0, test | +0,090 … +0,120 | +1,12 … +1,64 | +15,8 … +32,5 pp |

v1 na tych samych zbiorach: tabela v2 wyżej (v2b − v1: wszystkie przedziały powyżej zera).

- **`domteraz` w oknie:** średni wynik v2b 6,32% wobec konwersji 8,19% (v2: 2,92%). Udział w czołówce 10%: 7,1%
  (v2: 0,2%).
- **Wagi:** mediana 1,03, maksimum 6,77, przyciętych 0, efektywna liczebność 86 239.

`current.yaml` nadal pusty.
