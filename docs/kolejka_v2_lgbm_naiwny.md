# Kolejka zapytań: v2_lgbm_naiwny (LightGBM na historii) wobec v0 i v1

Uruchomienie z 2026-11-15 (`ewaluacja_v2.py`, run MLflow `ff3788228acf42f7a8262fa4fd11a6f7` w eksperymencie `leady`).
Target: `leady_cel.umowa_45d` ([kolejka_target.md](kolejka_target.md)). Wszystkie trzy wersje są oceniane na tych
samych zapytaniach i tymi samymi miarami. v0 jest tu uczona na tym samym zbiorze co v2.

## Wnioski

1. Model uczony na historii (v2) układa kolejkę wyraźnie lepiej niż reguła źródła (v0) i ocena LLM (v1). Na
   zwykłym teście (marzec–czerwiec 2026) wśród 125 najwyżej ocenionych zapytań (średnio tyle przychodzi dziennie)
   umową skończyło się 43,2% przy v2, 17,7% przy v0 i 11,5% przy v1. W oknie migracji, gdzie call center
   obsłużyło każde zapytanie, było to 49,6% wobec 22,0% i 15,1%. Przedziały ufności wszystkich różnic (AUC, lift,
   precyzja) leżą powyżej zera na obu zbiorach.
2. Najwięcej dają pola formularza: źródło, budżet względem typowego czynszu w mieście i termin wprowadzenia.
   Zapytania z budżetem poniżej 0,8 mediany czynszu kończą się umową w 2,6%, bez terminu w 4,7%, a z terminem
   za 2–4 tygodnie w 11,6%, przy średniej 7,66% (T7, C5). Sesje www sprzed zapytania (spacer 3D, kalkulator)
   i sygnały LLM dokładają mniej: bez sygnałów AUC spada o 0,010 na teście i o 0,013 w oknie (przedziałów dla tej
   różnicy nie liczyliśmy).
3. Model jest „naiwny” i to widać. Nauczył się, że `domteraz` rzadko daje umowę, bo doradcy oddzwaniają tylko
   do 41% tych zapytań. W oknie migracji `domteraz` dało 21,3% wszystkich umów (konwersja 8,19%, wyższa niż
   `lokum24` i `social`). Mimo to w czołówce 10% kolejki v2 znalazło się 0,2% zapytań z `domteraz`. Wdrożony
   w tej postaci model utrwali obecny nawyk pomijania `domteraz`.
4. Sygnały LLM mają koszt: v2 potrzebuje odpowiedzi v1 dla każdego zapytania, czyli ok. 1,19 mln tokenów wejścia
   i 70 tys. wyjścia na 1 000 zapytań. Jednorazowe uzupełnienie historii (141 053 wywołania) zużyło łącznie
   176 mln tokenów wejścia i 10 mln wyjścia (tabela T6). Kwoty w zł nie da się podać, bo w
   `leasing_bc/zalozenia.yaml` nie ma cennika. Wariant bez sygnałów (bez API) traci niewiele, patrz punkt 2.
5. `current.yaml` pozostaje pusty. Przed wdrożeniem trzeba zdecydować, co z efektem `domteraz` (np. uczyć tylko na
   obsłużonych zapytaniach albo z wagami) i czy sygnały LLM są warte swojej ceny.

## Tabele

### T1. Zbiory (`features/leady/podzial_v2.py`)

| Zbiór | Zapytania | Umowy 45 dni | Konwersja | Obsłużone | Opis |
|---|---:|---:|---:|---:|---|
| trening | 127 527 | 9 654 (po „nieobsłużone = 0”: 9 407) | 7,57% | 81,9% | zamknięte, niecenzurowane zapytania 2023-01-01 – 2026-02-28 bez okna migracji |
| test | 15 217 | 1 167 | 7,67% | 82,6% | wszystkie niecenzurowane zapytania 2026-03-01 – 2026-06-30 |
| okno migracji | 5 320 | 559 | 10,51% | 100,0% | wszystkie zapytania 2025-03-03 – 2025-04-13 |

- **„Nieobsłużone = 0”:** 247 umów w treningu dotyczyło zapytań bez kontaktu doradcy w 45 dni. Do uczenia v2 i v0
  dostały etykietę 0. Na teście i w oknie oceniamy na niezmienionym `umowa_45d`.
- **Liczba drzew:** wczesne zatrzymanie na ostatnich 6 miesiącach treningu (od 2025-08-29) dało 199 drzew
  (AUC walidacji 0,806). Potem model uczony od nowa na całym treningu.
- **Sygnały v1:** są dla 100% zapytań w każdym zbiorze.

### T2. Wyniki: zwykły test 2026-03 – 2026-06 (15 217 zapytań, 1 167 umów, k = 125)

| Wersja | AUC | lift@10% | precision@125 |
|---|---:|---:|---:|
| v0_regula_zrodla (baseline) | 0,684 (0,668–0,700) | 2,31 (2,11–2,52) | 17,7% (16,0–19,5) |
| v1_llm_zero_shot | 0,617 (0,601–0,632) | 1,49 (1,33–1,65) | 11,5% (9,7–13,5) |
| **v2_lgbm_naiwny** | **0,793** (0,780–0,806) | **3,75** (3,50–4,00) | **43,2%** (34,4–52,0) |
| v2 − v0 (95% CI) | +0,096 … +0,122 | +1,18 … +1,71 | +16,7 … +33,9 pp |
| v2 − v1 (95% CI) | +0,159 … +0,194 | +1,97 … +2,54 | +22,7 … +40,5 pp |

Z czołówki 10% v2 na teście doradcy obsłużyli 99,3% zapytań. Wynik na teście zależy więc od obsługi tylko
w niewielkim stopniu.

### T3. Wyniki: okno migracji (5 320 zapytań, 559 umów, k = 127)

| Wersja | AUC | lift@10% | precision@127 |
|---|---:|---:|---:|
| v0_regula_zrodla (baseline, ten sam trening co v2) | 0,633 (0,608–0,659) | 1,89 (1,60–2,18) | 22,0% (17,8–26,3) |
| v1_llm_zero_shot | 0,620 (0,597–0,642) | 1,40 (1,17–1,64) | 15,1% (11,5–18,8) |
| **v2_lgbm_naiwny** | **0,764** (0,743–0,784) | **3,33** (3,00–3,68) | **49,6%** (40,9–57,5) |
| v2 − v0 (95% CI) | +0,111 … +0,150 | +1,06 … +1,81 | +18,8 … +35,3 pp |
| v2 − v1 (95% CI) | +0,116 … +0,172 | +1,54 … +2,33 | +25,5 … +42,9 pp |

- **v0 w oknie:** AUC 0,633 różni się od zapisanej wersji v0 (0,637,
  [kolejka_v0_v1.md](kolejka_v0_v1.md)), bo tu v0 liczy konwersję z treningu v2. Zapisana wersja liczyła ją ze
  wszystkich niecenzurowanych zapytań poza oknem, do 2026-08.
- **Miary:** jak w [kolejka_v0_v1.md](kolejka_v0_v1.md). k to średnia dzienna liczba nowych zapytań w zbiorze.
  Przy remisach (v0, v1) liczymy wartość oczekiwaną losowej kolejności. W nawiasach 95% CI z bootstrapu par:
  2 000 losowań z ziarnem 42, te same dla wszystkich wersji w zbiorze.

### T4. Ablacja: v2 bez jednej rodziny cech (te same zbiory)

| Wariant | Test AUC | Test lift@10% | Test precision@125 | Okno AUC | Okno lift@10% | Okno precision@127 |
|---|---:|---:|---:|---:|---:|---:|
| v2 (wszystkie cechy) | 0,793 | 3,75 | 43,2% | 0,764 | 3,33 | 49,6% |
| bez `zapytanie` | 0,737 | 2,95 | 37,6% | 0,739 | 2,75 | 40,9% |
| bez `budzet` | 0,771 | 3,40 | 37,6% | 0,743 | 3,02 | 40,2% |
| bez `www` | 0,779 | 3,44 | 44,0% | 0,749 | 3,33 | 45,7% |
| bez `firma_b2b` | 0,793 | 3,74 | 37,6% | 0,763 | 3,40 | 52,0% |
| bez `tekst` (długość + sygnały) | 0,782 | 3,65 | 43,2% | 0,747 | 3,18 | 44,1% |
| bez sygnałów LLM (zostaje długość) | 0,783 | 3,58 | 43,2% | 0,751 | 3,15 | 44,9% |

Ablacje to pojedyncze uczenia bez przedziałów ufności. precision@k opiera się na 125–127 zapytaniach (CI v2 ma
szerokość ok. 17 pp), więc różnice rzędu kilku punktów w tej kolumnie mogą być przypadkowe.

### T5. Źródła: konwersja, wynik v2 i udział w czołówce 10% kolejki

Okno migracji (każde zapytanie obsłużone):

| Źródło | Zapytania | Umowy | Konwersja | Udział w umowach | Konwersja w treningu (nieobsł. = 0) | Obsłużone w treningu | Średni wynik v2 | Czołówka 10%: v0 | v1 | v2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| domteraz | 1 453 | 119 | 8,19% | 21,3% | 2,87% | 41,1% | 2,92% | 0,0% | 37,0% | **0,2%** |
| lokum24 | 2 040 | 133 | 6,52% | 23,8% | 4,77% | 95,7% | 4,60% | 0,0% | 31,8% | 5,3% |
| polecenie | 249 | 46 | 18,47% | 8,2% | 15,79% | 98,9% | 15,81% | 32,5% | 3,6% | 15,6% |
| relokacja_b2b | 359 | 79 | 22,01% | 14,1% | 19,95% | 99,5% | 19,08% | 67,5% | 9,6% | 29,3% |
| social | 248 | 12 | 4,84% | 2,1% | 3,07% | 90,5% | 3,68% | 0,0% | 4,1% | 0,0% |
| www | 971 | 170 | 17,51% | 30,4% | 13,01% | 99,0% | 13,69% | 0,0% | 13,9% | 49,6% |

Test 2026-03 – 2026-06:

| Źródło | Zapytania | Umowy | Konwersja | Udział w umowach | Średni wynik v2 | Czołówka 10%: v0 | v1 | v2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| domteraz | 3 849 | 139 | 3,61% | 11,9% | 2,98% | 0,0% | 29,2% | 0,1% |
| lokum24 | 5 506 | 268 | 4,87% | 23,0% | 4,83% | 0,0% | 31,5% | 4,1% |
| polecenie | 778 | 113 | 14,52% | 9,7% | 15,50% | 0,0% | 4,7% | 13,7% |
| relokacja_b2b | 1 710 | 303 | 17,72% | 26,0% | 21,15% | 100,0% | 14,9% | 49,4% |
| social | 722 | 23 | 3,19% | 2,0% | 3,45% | 0,0% | 3,9% | 0,0% |
| www | 2 652 | 321 | 12,10% | 27,5% | 12,95% | 0,0% | 15,6% | 32,7% |

- **Czołówka:** 10% zapytań z najwyższym wynikiem. Remisy v0 i v1 rozstrzyga losowanie z ziarnem 0.
- **Obsłużone `domteraz`:** w danych kończą się umową w 6,96%, a nieobsłużone w 1,09% (poza oknem;
  [kolejka_target.md](kolejka_target.md), R2). v2 przewiduje dla `domteraz` średnio 2,9%, czyli tyle, ile wynosi
  konwersja w treningu przy „nieobsłużone = 0” (2,87%).
- **Średni wynik v2 w oknie:** jest niższy od konwersji w oknie dla wszystkich źródeł. v2 przewiduje konwersję
  przy dzisiejszej obsłudze, a nie przy obsłudze każdego zapytania.

### T6. Ważność cech v2 (udział w sumie gain) i tokeny

| Cecha | Udział | Cecha | Udział |
|---|---:|---|---:|
| zrodlo | 34,8% | www_kalkulator | 1,9% |
| budzet_do_mediany | 19,7% | miasto | 1,8% |
| termin_dni | 14,8% | liczba_osob | 1,5% |
| dlugosc_wiadomosci | 4,0% | syg_pilny_termin | 1,1% |
| www_liczba_sesji | 3,6% | zwierze | 0,5% |
| www_spacer_3d | 3,5% | syg_budzet_niski | 0,4% |
| linia | 3,3% | syg_relokacja | 0,4% |
| syg_niedopasowanie_oferty | 2,9% | umowa_ramowa | 0,4% |
| liczba_lokali | 2,6% | syg_brak_informacji | 0,1% |
| syg_konkretne_pytania | 2,6% | | |

| Zbiór (odpowiedzi v1) | Wywołania | Tokeny wejścia | w tym z cache promptu OpenAI | Tokeny wyjścia |
|---|---:|---:|---:|---:|
| trening | 127 527 | 151 797 550 | 134 924 883 | 8 949 872 |
| test | 15 217 | 18 119 387 | 16 099 586 | 1 069 715 |
| okno migracji | 5 320 | 6 335 895 | 5 628 560 | 372 995 |

Tokeny pochodzą z pierwszego wywołania każdego zapytania, a cache odpowiedzi zachowuje je w pliku. Uzupełnienie
z 2026-11-15 to 141 053 nowe wywołania, 0 błędów, ok. 42 zapytania/s przy 64 wątkach. Reszta odpowiedzi była już
w cache z oceny v1. Na 1 000 zapytań testu wychodzi 1 190 733 tokenów wejścia (1 058 000 z cache) i 70 297
tokenów wyjścia.

### T7. Kontrole danych pod cechy (C1–C4)

| Kontrola | Wynik | Co z tego wynika |
|---|---|---|
| C1: sesje www powiązane z zapytaniem | 486 260 z 884 109. Przed `utworzono`: 284 078, po: 202 182 | Sesje po utworzeniu byłyby przeciekiem przyszłości, więc liczymy tylko sesje sprzed |
| C2: firmy z umową ramową | 3 (F001–F003), wszystkie od 2025-06-02. Przed tą datą zapytały 35, 31 i 39 razy (na 1 130, 1 085 i 1 154 zapytania) | `crm_firmy_b2b.umowa_ramowa` to stan na eksport. Flaga obowiązuje od daty umowy, w oknie migracji wynosi 0 |
| C3: mediana `czynsz_katalogowy` w mieście | Gdańsk 2 585, Kraków 2 360, Poznań 2 050, Warszawa 2 760, Wrocław 2 300, Łódź 1 940 zł | Stan na eksport, bez historii cennika (brak w danych). Jedna wartość na miasto |
| C4: czy formularz nie jest nadpisany po fakcie | z 12 111 zapytań z umową: termin = `pms_umowy.data_od` w 1,08% (9 903 z terminem); budżet = czynsz umowy w 0,37% (9 928 z budżetem) | Brak śladów nadpisywania terminu i budżetu danymi z umowy |

C5: konwersja 45 dni według terminu i budżetu (wszystkie 154 743 niecenzurowane zapytania):

| Termin wprowadzenia (dni od zapytania) | Zapytania | Konwersja | Budżet / mediana czynszu w mieście | Zapytania | Konwersja |
|---|---:|---:|---|---:|---:|
| < 14 | 10 871 | 10,74% | < 0,8 | 17 096 | 2,61% |
| 14–29 | 32 683 | 11,60% | 0,8–1 | 27 457 | 6,53% |
| 30–59 | 37 712 | 8,71% | 1–1,3 | 37 669 | 9,73% |
| 60+ | 27 116 | 5,36% | ≥ 1,3 | 35 185 | 10,82% |
| brak | 46 361 | 4,65% | brak | 37 336 | 5,74% |

Zastrzeżenia:

- **Czynsz katalogowy:** to stan na dzień eksportu. Polecenie wskazało go wprost, a mediana na miasto jest
  odporna na pojedyncze zmiany. Przeciek nie jest jednak wykluczony, jeśli cennik zmieniał się w zależności od
  popytu.
- **Etykiety końca treningu:** trening kończy się 2026-02-28, a etykiety zapytań z końca lutego znamy dopiero
  w połowie kwietnia 2026. Model wdrożony 2026-03-01 nie miałby ich jeszcze. Wynik testu może więc być nieco
  optymistyczny co do świeżości danych.
- **Sygnały LLM w produkcji:** wymagają wywołania v1 przy każdym nowym zapytaniu, zanim trafi do kolejki.

## SQL i kod

Cechy, po jednym pliku SQL na rodzinę, w `api/api/ai/features/leady/`. Składa je `cechy.py`
(`zbuduj_cechy(con, sygnaly)`): złączenie po `id_leada`, liczby jako float64 z NaN.

```sql
-- cechy_zapytanie.sql
SELECT
    id_leada, zrodlo, miasto, linia_pref AS linia,
    datediff('day', CAST(utworzono AS DATE), CAST(termin_wprowadzenia AS DATE)) AS termin_dni,
    liczba_osob, CAST(zwierze AS INTEGER) AS zwierze, liczba_lokali
FROM crm_leady

-- cechy_budzet.sql
WITH mediana_miasta AS (
    SELECT b.miasto, median(l.czynsz_katalogowy) AS mediana_czynszu_miasta
    FROM pms_lokale AS l JOIN pms_budynki AS b USING (id_budynku)
    GROUP BY b.miasto
)
SELECT l.id_leada, l.budzet_max, m.mediana_czynszu_miasta,
       l.budzet_max / m.mediana_czynszu_miasta AS budzet_do_mediany
FROM crm_leady AS l LEFT JOIN mediana_miasta AS m USING (miasto)

-- cechy_www.sql
SELECT l.id_leada,
       count(s.id_sesji) AS www_liczba_sesji,
       CAST(coalesce(bool_or(s.czy_spacer_3d), FALSE) AS INTEGER) AS www_spacer_3d,
       CAST(coalesce(bool_or(s.czy_kalkulator), FALSE) AS INTEGER) AS www_kalkulator
FROM crm_leady AS l
LEFT JOIN www_sesje AS s ON s.id_leada = l.id_leada AND s.data_czas < l.utworzono
GROUP BY l.id_leada

-- cechy_firma_b2b.sql
SELECT l.id_leada,
       CAST(coalesce(f.umowa_ramowa
            AND CAST(CAST(f.data_umowy_ramowej AS TIMESTAMP) AS TIMESTAMPTZ) <= l.utworzono, FALSE) AS INTEGER)
           AS umowa_ramowa
FROM crm_leady AS l LEFT JOIN crm_firmy_b2b AS f ON f.id_firmy = l.id_firmy_b2b

-- cechy_tekst.sql (sygnaly_v1 = relacja z ai/llm/cache, rejestrowana przez cechy.py)
WITH s AS (SELECT id_leada, string_split(sygnaly, ',') AS lista FROM sygnaly_v1)
SELECT l.id_leada,
       coalesce(length(l.wiadomosc), 0) AS dlugosc_wiadomosci,
       CAST(list_contains(s.lista, 'konkretne_pytania') AS INTEGER) AS syg_konkretne_pytania,
       -- … tak samo: niedopasowanie_oferty, pilny_termin, relokacja, budzet_niski, brak_informacji
FROM crm_leady AS l LEFT JOIN s USING (id_leada)
```

Żadna rodzina nie czyta `crm_leady.status`, `data_statusu`, `powod_utraty`, `id_doradcy` ani `id_umowy`. Sprawdza
to test `test_brak_kolumn_stanu_crm_w_cechach`, w którym kolumny stanu w danych testowych mają celowo fałszywe
wartości.

Kontrole C1–C4 (na `domilo.duckdb` przez `polacz()`):

```sql
-- C1
SELECT count(*) AS sesje, count(s.id_leada) AS z_zapytaniem,
       sum((s.data_czas < l.utworzono)::INT) AS przed_utworzeniem,
       sum((s.data_czas >= l.utworzono)::INT) AS po_utworzeniu
FROM www_sesje AS s LEFT JOIN crm_leady AS l USING (id_leada);
-- C2
SELECT f.id_firmy, f.data_umowy_ramowej, count(*) AS zapytania,
       sum((l.utworzono < CAST(CAST(f.data_umowy_ramowej AS TIMESTAMP) AS TIMESTAMPTZ))::INT) AS przed_umowa
FROM crm_leady AS l JOIN crm_firmy_b2b AS f ON f.id_firmy = l.id_firmy_b2b
WHERE f.umowa_ramowa GROUP BY ALL ORDER BY 1;
-- C3
SELECT b.miasto, median(l.czynsz_katalogowy) AS mediana_czynszu, count(*) AS lokale
FROM pms_lokale AS l JOIN pms_budynki AS b USING (id_budynku) GROUP BY 1 ORDER BY 1;
-- C4
SELECT count(*) AS zapytania_z_umowa, count(l.termin_wprowadzenia) AS z_terminem,
       avg((CAST(l.termin_wprowadzenia AS DATE) = CAST(u.data_od AS DATE))::INT) AS termin_rowny_data_od,
       count(l.budzet_max) AS z_budzetem, avg((l.budzet_max = u.czynsz)::INT) AS budzet_rowny_czynszowi
FROM crm_leady AS l JOIN pms_umowy AS u ON u.id_umowy = l.id_umowy;
-- C5 (termin; budżet analogicznie z l.budzet_max / mediana miasta jak w cechy_budzet.sql, progi 0,8 / 1 / 1,3)
SELECT CASE WHEN t IS NULL THEN 'brak' WHEN t < 14 THEN '<14' WHEN t < 30 THEN '14-29'
            WHEN t < 60 THEN '30-59' ELSE '60+' END AS termin, count(*) AS zapytania, avg(umowa_45d) AS konwersja
FROM (SELECT datediff('day', CAST(l.utworzono AS DATE), CAST(l.termin_wprowadzenia AS DATE)) AS t, c.umowa_45d
      FROM crm_leady AS l JOIN leady_cel AS c USING (id_leada) WHERE c.umowa_45d IS NOT NULL)
GROUP BY 1 ORDER BY 1;
```

Uruchomienie (z katalogu głównego repozytorium, po `pypyr baza`):

```bash
set -a && . ./.env && set +a
cd api
# 1. odpowiedzi v1 (sygnały) dla treningu, testu i okna; ponowne uruchomienie woła API tylko dla braków
poetry run python -m api.ai.features.leady.sygnaly_v1 --watki 64
# 2. uczenie v2, v0 na tym samym treningu, ablacje, ocena na teście i w oknie, zapis + MLflow
poetry run python -m api.ai.lead_model.evals.ewaluacja_v2
```

- `features/leady/podzial_v2.py`: zbiory trening / test / okno (T1).
- `features/leady/sygnaly_v1.py`: odczyt sygnałów z cache i uzupełnianie cache.
- `lead_model/versions/v2_lgbm_naiwny/model.py`: LightGBM (learning_rate 0,03, 31 liści, min. 200 zapytań
  w liściu, feature/bagging fraction 0,8, L2 = 1, ziarno 42, `deterministic`). Liczba drzew z wczesnego zatrzymania
  na ostatnich 6 miesiącach treningu. `explain` zwraca wkład cech (SHAP z LightGBM).
- `lead_model/evals/ewaluacja_v2.py`: target „nieobsłużone = 0”, ablacje, tabele T2–T5. Zapisuje
  `versions/v2_lgbm_naiwny/{model.joblib, metryki.json}` i `evals/wyniki/v2_lgbm_naiwny.parquet` (wyniki v0, v1,
  v2 i v2 bez sygnałów dla każdego zapytania testu i okna).
- Testy: `api/tests/test_cechy_leadow.py` (punkt w czasie dla www i umowy ramowej, termin w czasie warszawskim,
  budżet / mediana, sygnały NaN przy braku odpowiedzi, podział) oraz sekcja v2 w `api/tests/test_lead_model.py`.
