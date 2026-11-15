# Kolejka zapytań: v0 (reguła źródła) i v1 (ocena LLM) na oknie migracji

Ocena: wszystkie 5 320 zapytań z okna migracji CRM (2025-03-03 – 2025-04-13), 559 umów w 45 dni (10,51%). W tym
oknie call center skontaktowało się z każdym zapytaniem, więc wynik nie zależy od tego, do kogo doradcy oddzwonili
(docs/kolejka_target.md). Uruchomienie z 2026-11-15.

## Wnioski

1. Prosta reguła „konwersja źródła i linii z historii” (v0) układa kolejkę lepiej niż ocena LLM (v1). Spośród 127
   najwyżej ocenionych zapytań (tyle nowych zapytań przychodzi średnio dziennie) umową skończyło się 22,0% przy v0
   i 15,1% przy v1, wobec 10,5% wśród wszystkich. Przewaga v0 w czołówce kolejki jest pewna (przedziały ufności
   różnicy nie obejmują zera), a w AUC nierozstrzygnięta.
2. LLM nie wie, które źródła dają umowy. Wszystkim źródłom daje średnio podobną ocenę (4,66–5,55 na 10), choć
   konwersja w oknie waha się od 4,84% (`social`) do 22,01% (`relokacja_b2b`). Jego ocena nie rośnie też równo
   z konwersją: zapytania z oceną 6 kończyły się umową w 17,0%, a z oceną 8 tylko w 15,1%.
3. W obrębie jednego źródła LLM rozróżnia zapytania lepiej niż przypadek (AUC 0,60–0,66), a reguła źródła tego
   nie umie. Kandydat na v2 to połączenie obu: konwersja źródła jako punkt wyjścia, ocena LLM jako korekta.
4. Kosztu w zł nie da się podać, bo `leasing_bc/zalozenia.yaml` nie zawiera cennika. Na 1 000 zapytań v1 zużywa
   1,19 mln tokenów wejścia, z czego 89% to stała instrukcja odczytana z cache promptu OpenAI, i 70 tys. tokenów
   wyjścia. v0 nie wywołuje API.
5. Na razie żadna wersja nie trafia do użycia (`current.yaml` jest pusty). v0 jest punktem odniesienia dla
   kolejnych wersji.

## Tabele

### Wyniki na oknie migracji (5 320 zapytań, 559 umów)

| Wersja | AUC | lift@10% | precision@127 | Tokeny / 1 000 zapytań | Koszt / 1 000 zapytań |
|---|---:|---:|---:|---|---|
| **v0_regula_zrodla** (baseline) | **0,637** (0,612–0,662) | **1,89** (1,60–2,18) | **22,0%** (17,8–26,3) | 0 | 0 (bez API) |
| v1_llm_zero_shot | 0,620 (0,597–0,642) | 1,40 (1,17–1,64) | 15,1% (11,5–18,8) | wejście 1 190 958 (z cache promptu 1 058 000), wyjście 70 112 | brak cennika w `leasing_bc/zalozenia.yaml` |
| v1 − v0 (95% CI) | −0,053 … +0,017 | −0,83 … −0,12 | −12,0 … −1,7 pp | | |

W nawiasach 95% przedział z bootstrapu par: 2 000 losowań z ziarnem 42, te same dla obu wersji. Definicje miar:

- **lift@10%:** konwersja 532 najwyżej ocenionych zapytań (10% z 5 320) / 10,51%.
- **precision@127:** odsetek umów wśród 127 najwyżej ocenionych zapytań. k = 127 to średnia dzienna liczba nowych
  zapytań w oknie (5 320 / 42 dni; najmniej 63, najwięcej 179 dziennie).
- **Remisy:** v0 ma 16 różnych wyników, a v1 tylko 8 (oceny 1–8), więc granica czołówki przecina grupę remisów.
  Liczymy wtedy wartość oczekiwaną losowej kolejności wewnątrz remisu.

### Wrażliwość v0 na historię, z której liczymy konwersję

| Wariant v0 | Zapytań w historii | AUC | lift@10% | precision@127 |
|---|---:|---:|---:|---:|
| poza oknem, przed i po nim (zapisana wersja, zgodnie z poleceniem) | 149 423 | 0,637 | 1,89 | 22,0% |
| tylko przed oknem (bez danych z przyszłości) | 88 432 | 0,630 | 1,89 | 21,7% |
| tylko obsłużone zapytania przed oknem | 72 232 | 0,651 | 1,89 | 21,7% |

Użycie historii sprzed i spoza okna prawie nie zmienia wyniku. W każdym wariancie 10% czołówki tworzą te same pary
(`relokacja_b2b` i `polecenie`). W wariantach „przed oknem” na początek kolejki trafiają 2 zapytania `polecenie`/B2B
bez umowy, stąd precision@127 21,7% zamiast 22,0%.

### Pary źródło × linia: konwersja w oknie, wynik v0 i średnia ocena v1 (C1)

| Źródło | Linia | Zapytań | Umowy | Konwersja w oknie | v0: konwersja w historii | v1: średnia ocena |
|---|---|---:|---:|---:|---:|---:|
| relokacja_b2b | B2B | 359 | 79 | 22,01% | 19,55% | 5,55 |
| polecenie | B2B | 2 | 0 | 0,00% | 19,41% | 7,50 |
| polecenie | B2C | 153 | 22 | 14,38% | 16,46% | 4,54 |
| polecenie | MID | 94 | 24 | 25,53% | 14,72% | 4,98 |
| www | B2C | 578 | 115 | 19,90% | 13,20% | 4,34 |
| www | MID | 371 | 51 | 13,75% | 12,27% | 5,11 |
| www | B2B | 22 | 4 | 18,18% | 11,24% | 5,32 |
| lokum24 | B2C | 1 186 | 93 | 7,84% | 4,98% | 4,29 |
| lokum24 | B2B | 44 | 5 | 11,36% | 4,91% | 4,75 |
| lokum24 | MID | 810 | 35 | 4,32% | 4,53% | 5,19 |
| domteraz | B2B | 28 | 0 | 0,00% | 4,45% | 4,86 |
| domteraz | B2C | 869 | 78 | 8,98% | 3,54% | 4,67 |
| domteraz | MID | 556 | 41 | 7,37% | 3,35% | 5,44 |
| social | B2C | 152 | 11 | 7,24% | 3,29% | 4,45 |
| social | MID | 90 | 1 | 1,11% | 2,89% | 5,20 |
| social | B2B | 6 | 0 | 0,00% | 1,27% | 4,33 |

v0 nie docenia `domteraz`: historia daje 3,35–3,54%, a w oknie było 7,37–8,98%. Wynika to z tego, że poza oknem
doradcy kontaktowali się tylko z 40,8% zapytań z `domteraz` (docs/kolejka_target.md). Mimo to kolejność par jest na
tyle trafna, że v0 wygrywa.

### Konwersja według oceny v1 (C2)

| Ocena | Zapytań | Umowy | Konwersja |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 0,00% |
| 2 | 281 | 1 | 0,36% |
| 3 | 1 143 | 66 | 5,77% |
| 4 | 1 289 | 132 | 10,24% |
| 5 | 683 | 63 | 9,22% |
| 6 | 822 | 140 | 17,03% |
| 7 | 716 | 99 | 13,83% |
| 8 | 385 | 58 | 15,06% |

Ocena dobrze odsiewa zapytania bez szans (oceny 1–3: 67 umów na 1 425 zapytań). Powyżej 5 nie porządkuje już
zapytań: ocena 6 konwertuje lepiej niż 7 i 8.

### Źródła: średnia ocena v1, konwersja w oknie i AUC wewnątrz źródła (C3, C7)

| Źródło | Zapytań | Umowy | Konwersja w oknie | v1: średnia ocena | AUC v1 w źródle | AUC v0 w źródle |
|---|---:|---:|---:|---:|---:|---:|
| relokacja_b2b | 359 | 79 | 22,01% | 5,55 | 0,629 | 0,500 |
| polecenie | 249 | 46 | 18,47% | 4,73 | 0,657 | 0,409 |
| www | 971 | 170 | 17,51% | 4,66 | 0,601 | 0,548 |
| domteraz | 1 453 | 119 | 8,19% | 4,97 | 0,635 | 0,514 |
| lokum24 | 2 040 | 133 | 6,52% | 4,66 | 0,595 | 0,568 |
| social | 248 | 12 | 4,84% | 4,72 | 0,657 | 0,661 |

Wewnątrz źródła v0 rozróżnia zapytania tylko po linii (dla `relokacja_b2b` jest jedna linia, więc AUC = 0,5).
Przy `social` (12 umów) i `polecenie` (46) AUC jest bardzo niepewne.

### Sygnały v1 a konwersja w oknie (C4)

| Sygnał | Zapytań z sygnałem | Konwersja |
|---|---:|---:|
| relokacja | 821 | 15,71% |
| pilny_termin | 1 685 | 15,49% |
| konkretne_pytania | 1 937 | 13,16% |
| bez żadnego sygnału | 301 | 8,97% |
| budzet_niski | 2 407 | 8,85% |
| brak_informacji | 1 543 | 8,23% |
| niedopasowanie_oferty | 626 | 3,19% |

Model zaznacza `budzet_niski` w 45% zapytań (2 407 z 5 320). Konwersja tych zapytań (8,85%) jest tylko nieco
niższa niż ogólna (10,51%). To kolejny argument za progami budżetu z danych w promptcie v2.

### Tokeny (C5)

| Zapytań | Tokeny wejścia | w tym z cache promptu OpenAI | Tokeny wyjścia | Odpowiedzi z naszego cache |
|---:|---:|---:|---:|---:|
| 5 320 | 6 335 895 | 5 628 560 | 372 995 | 29 |

29 odpowiedzi pochodzi z cache z pomiaru stabilności (docs/llm_ocena_leada_v1.md). Cache zapisuje tokeny
pierwszego wywołania, więc liczba tokenów odpowiada rzeczywistemu zużyciu.

## SQL i kod

- Kontrakt: `api/api/ai/lead_model/base.py`.
- Wersje: `versions/v0_regula_zrodla/model.py`, `versions/v1_llm_zero_shot/model.py`.
- Zbiór: `api/api/ai/features/leady/zbior.py`.
- Miary: `api/api/ai/lead_model/evals/metryki.py`.
- Cennik: `api/api/contexts_boundaries/leasing_bc/zalozenia.yaml`.
- Testy: `api/tests/test_lead_model.py`.

Ewaluacja wykonuje zapis wyników w trzech miejscach: `versions/<wersja>/{model.joblib, metryki.json}`,
`evals/wyniki/okno_migracji.parquet` (każde zapytanie z wynikami v0 i v1) oraz runy w MLflow (eksperyment `leady`).

```bash
pypyr baza                       # domilo.duckdb z tabelą leady_cel
set -a && . ./.env && set +a     # klucz OpenAI (v1; odpowiedzi z cache nie wołają API)
cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja
```

Zbiór oceny i historia v0 (`wczytaj_zbior` + filtry w `ewaluacja.py`):

```sql
SELECT l.id_leada, l.utworzono, l.zrodlo, l.miasto, l.linia_pref, l.budzet_max, l.termin_wprowadzenia,
    l.liczba_osob, l.zwierze, l.liczba_lokali, l.wiadomosc, l.imie,
    c.umowa_45d, c.okno_migracji, c.cenzurowany, c.obsluzony
FROM crm_leady AS l JOIN leady_cel AS c USING (id_leada);
-- ocena: okno_migracji; historia v0: NOT okno_migracji AND NOT cenzurowany
-- wrażliwość: dodatkowo utworzono < 2025-03-03 (i obsluzony)
```

Tabele C1–C6 liczą zapytania niżej na pliku wyników. Uruchom je z katalogu głównego repozytorium, np. w CLI
`duckdb` 1.5:

```sql
-- C1 pary źródło × linia
SELECT zrodlo, linia_pref, count(*) AS zapytan, sum(umowa_45d) AS umowy,
    round(100 * avg(umowa_45d), 2) AS konwersja_okno_pct,
    round(100 * any_value(wynik_v0), 2) AS v0_konwersja_historii_pct, round(avg(v1_ocena), 2) AS v1_srednia_ocena
FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet'
GROUP BY ALL ORDER BY v0_konwersja_historii_pct DESC;

-- C2 konwersja według oceny v1
SELECT v1_ocena AS ocena, count(*) AS zapytan, sum(umowa_45d) AS umowy, round(100 * avg(umowa_45d), 2) AS konwersja_pct
FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet' GROUP BY 1 ORDER BY 1;

-- C3 źródła: średnia ocena v1 i konwersja
SELECT zrodlo, count(*) AS zapytan, sum(umowa_45d) AS umowy, round(avg(v1_ocena), 2) AS srednia_ocena,
    round(100 * avg(umowa_45d), 2) AS konwersja_pct
FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet' GROUP BY 1 ORDER BY konwersja_pct DESC;

-- C4 sygnały v1
WITH s AS (
    SELECT umowa_45d, unnest(string_split(v1_sygnaly, ',')) AS sygnal
    FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet' WHERE v1_sygnaly <> ''
)
SELECT sygnal, count(*) AS zapytan, round(100 * avg(umowa_45d), 2) AS konwersja_pct FROM s GROUP BY 1 ORDER BY 3 DESC;
SELECT count(*) FILTER (WHERE v1_sygnaly = '') AS bez_sygnalow,
    round(100 * avg(umowa_45d) FILTER (WHERE v1_sygnaly = ''), 2) AS konwersja_pct
FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet';

-- C5 tokeny
SELECT count(*) AS n, sum(v1_tokeny_wejscia) AS wejscie, sum(v1_tokeny_wejscia_z_cache) AS wejscie_z_cache,
    sum(v1_tokeny_wyjscia) AS wyjscie, sum(v1_z_cache::INT) AS z_naszego_cache
FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet';

-- C6 dni w oknie i dzienna liczba zapytań (czas warszawski)
SELECT count(DISTINCT dzien) AS dni, count(*) AS zapytan, min(c) AS min_dziennie, max(c) AS max_dziennie
FROM (
    SELECT CAST(utworzono AT TIME ZONE 'Europe/Warsaw' AS DATE) AS dzien,
        count(*) OVER (PARTITION BY CAST(utworzono AT TIME ZONE 'Europe/Warsaw' AS DATE)) AS c
    FROM 'api/api/ai/lead_model/evals/wyniki/okno_migracji.parquet'
);
```

C7, AUC wewnątrz źródła (Python):

```python
# cd api && poetry run python
import pandas as pd
from sklearn.metrics import roc_auc_score

d = pd.read_parquet("api/ai/lead_model/evals/wyniki/okno_migracji.parquet")
for zrodlo, g in d.groupby("zrodlo"):
    print(zrodlo, len(g), g.umowa_45d.sum(),
          round(roc_auc_score(g.umowa_45d, g.v1_wynik), 3), round(roc_auc_score(g.umowa_45d, g.wynik_v0), 3))
```
