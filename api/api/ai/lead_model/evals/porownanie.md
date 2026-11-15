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
