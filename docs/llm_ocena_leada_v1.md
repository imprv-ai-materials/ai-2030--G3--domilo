# Ocena zapytań przez LLM (prompt `ocena_leada_v1`): stabilność odpowiedzi

Model `gpt-6-luna` (OpenAI), reasoning effort `none`, temperatura 0 (API ją przyjęło), wymuszony schemat JSON
(`api/api/ai/llm/schemas/ocena_leada.py`). Próba: 500 losowych zapytań z `crm_leady` (ziarno 42). Każde zapytanie
wysłano 2 razy z pominięciem cache. Uruchomienie z 2026-11-15.

## Wnioski

1. Na 1 000 wywołań nie było żadnego błędu. 427 z 500 zapytań (85,4%) dostało w obu przebiegach tę samą ocenę,
   a 494 (98,8%) różniło się najwyżej o 1 punkt. Temperatura 0 nie daje więc pełnej powtarzalności: mniej więcej
   co siódme zapytanie dostaje za drugim razem inną ocenę.
2. Dla kolejki ważniejsza jest kolejność zapytań niż dokładna ocena, a ta jest stabilna. Korelacja rang między
   przebiegami wynosi 0,967, a 93 ze 100 najwyżej ocenionych zapytań są w czołówce w obu przebiegach.
3. Wahania skupiają się w środku skali (ocena 5: 67,2% zgodnych, ocena 6: 77,0%). Najmniej stabilny sygnał to
   `budzet_niski`: zmienił się w 47 zapytaniach, a model zaznacza go aż w 229 z 500. Prompt v1 nie podaje
   czynszów Domilo, więc model ocenia budżet „na wyczucie”. W v2 trzeba mu dać progi z danych albo od zespołu.
4. Uzasadnienie jest za każdym razem inaczej sformułowane: identyczne było tylko w 64 z 500 zapytań. Nadaje się
   do pokazania doradcy, ale nie jako cecha do modelu. Limit 140 znaków jest dotrzymany (najdłuższe ma 140).
5. Badaliśmy tylko powtarzalność, a nie trafność. Zanim ocena trafi do kolejki, trzeba sprawdzić na podziale
   czasowym, czy przewiduje `umowa_45d` lepiej niż prosta reguła (np. źródło zapytania) i lepiej niż obecna
   kolejność od najnowszego.

## Co dostaje model

Wejście buduje `opis_leada` (`api/api/ai/features/leady/ocena_llm.py`). Zawiera tylko pola znane w chwili utworzenia
zapytania: źródło, miasto, linię, budżet, termin, liczbę osób, zwierzę, liczbę lokali i treść. Przykład
(`L161139`):

```text
źródło: social
miasto: Łódź
linia: B2C
budżet maks.: 1450 zł
termin wprowadzenia: brak
liczba osób: 2
zwierzę: nie
liczba lokali: brak
treść zapytania: Dzień dobry! jestem zainteresowany ofertą najmu w Łodzi Ile wynosi czynsz razem z opłatami administracyjnymi? Jakie dokumenty są potrzebne do podpisania umowy? Proszę o więcej informacji.
```

Decyzje:

- **Imię i język:** nie wysyłamy ani imienia, ani języka. Imię usuwamy też z treści (zastępuje je znacznik
  `[imię]`), bo podpis z imieniem jest w ok. 1/3 wiadomości: 33,2% przed migracją CRM i 33,6% po niej (zapytanie W1).
  Język nadal widać po samej treści, dlatego prompt zabrania oceniać po języku i pochodzeniu.
- **Termin:** podajemy go w dniach od zapytania, a nie jako datę. Model nie zna daty zapytania, więc termin z 2023
  wyglądałby na miniony. W danych termin nigdy nie jest wcześniejszy niż dzień zapytania: 113 149 zapytań
  z terminem, od 3 do 240 dni (W2).
- **Pola pominięte:** nie wysyłamy stanu na dzień eksportu (`status`, `data_statusu`, `powod_utraty`,
  `id_doradcy`, `id_umowy`). `metraz_min`, `id_budynku_pref` i `id_firmy_b2b` też są znane przy utworzeniu, ale nie
  było ich na liście pól, więc ich nie wysyłamy.
- **Opis oferty:** opis oferty Domilo w prompcie pochodzi z danych (O1): umowy roczne 364–730 dni, średnioterminowe
  27–183 dni, budynki w 6 miastach. Progów „pilny termin” i „niski budżet” prompt v1 nie podaje, bo nie ma ich
  od zespołu.
- **Cache:** klucz to `sha256(wersja promptu + wejście)` (istniejący `adapters/llm_client.py`). W pliku zapisany
  jest skrót treści promptu, a edycja treści bez zmiany wersji kończy się błędem, zamiast oddać starą odpowiedź.
- **Sygnały:** traktujemy je jako zbiór. Schemat usuwa powtórzenia i porządkuje je według słownika, więc sama
  kolejność sygnałów nie liczy się jako różnica.
- **Losowanie:** losujemy ze wszystkich 161 556 zapytań, także najmłodszych (cenzurowanych w `leady_cel`), bo
  powtarzalność nie zależy od tego, czy znamy wynik.

## Tabele

### Odsetek zapytań z identyczną odpowiedzią w obu przebiegach

| Zakres | Identyczne | Zapytań | Odsetek |
|---|---:|---:|---:|
| **ocena** | **427** | 500 | **85,4%** |
| ocena różni się najwyżej o 1 | 494 | 500 | 98,8% |
| sygnały (cały zbiór) | 383 | 500 | 76,6% |
| uzasadnienie | 64 | 500 | 12,8% |
| cała odpowiedź | 50 | 500 | 10,0% |
| surowy tekst JSON z API | 50 | 500 | 10,0% |

Błędne wywołania: 0 z 1 000. Tokeny łącznie (2 × 500 wywołań): wejście 1 191 966, wyjście 70 504. Kosztu w zł nie
podajemy, bo cennika nie ma w danych.

### Różnica ocen: przebieg 2 − przebieg 1 (A2)

| Różnica | −2 | −1 | 0 | +1 | +2 |
|---|---:|---:|---:|---:|---:|
| Zapytań | 4 | 42 | 427 | 25 | 2 |

Średnia ocena: 4,818 w przebiegu 1 i 4,776 w przebiegu 2. Korelacja rang (Spearman) 0,967 (A3). Ze 100 najwyżej
ocenionych zapytań 93 jest w czołówce obu przebiegów (remisy rozstrzyga `id_leada`, A8).

### Rozkład ocen (A1) i zgodność według oceny z przebiegu 1 (A4)

| Ocena | Przebieg 1 | Przebieg 2 | Zgodne (wg przebiegu 1) | Odsetek zgodnych |
|---:|---:|---:|---:|---:|
| 1 | 1 | 0 | 0 | 0,0% |
| 2 | 28 | 28 | 26 | 92,9% |
| 3 | 112 | 119 | 107 | 95,5% |
| 4 | 108 | 117 | 93 | 86,1% |
| 5 | 64 | 52 | 43 | 67,2% |
| 6 | 74 | 71 | 57 | 77,0% |
| 7 | 84 | 83 | 74 | 88,1% |
| 8 | 29 | 30 | 27 | 93,1% |
| 9–10 | 0 | 0 | — | — |

Model w ogóle nie użył ocen 9 i 10, a ocenę 1 dał raz na 1 000 odpowiedzi.

### Zgodność oceny według grupy (A5)

| Grupa | Zapytań | Identyczna ocena | Odsetek |
|---|---:|---:|---:|
| bez treści wiadomości | 83 | 76 | 91,6% |
| z treścią | 417 | 351 | 84,2% |
| linia B2B | 56 | 43 | 76,8% |
| linia B2C | 273 | 236 | 86,4% |
| linia MID | 171 | 148 | 86,5% |

### Sygnały: częstość i zgodność (A6)

| Sygnał | Przebieg 1 | Przebieg 2 | Ta sama obecność w obu | Odsetek |
|---|---:|---:|---:|---:|
| budzet_niski | 229 | 226 | 453 | 90,6% |
| brak_informacji | 133 | 141 | 462 | 92,4% |
| niedopasowanie_oferty | 69 | 71 | 470 | 94,0% |
| pilny_termin | 158 | 167 | 489 | 97,8% |
| konkretne_pytania | 187 | 182 | 493 | 98,6% |
| relokacja | 94 | 92 | 494 | 98,8% |

Rozbieżne oceny a sygnały (A10): spośród 73 zapytań z różną oceną 28 miało też inne sygnały, w tym 15 inną flagę
`budzet_niski`. W 45 sygnały się nie zmieniły. W 89 zapytaniach ocena była ta sama, a zmieniły się sygnały.

### Długość uzasadnienia (A7)

| Najdłuższe | Mediana | Uzasadnienia ≥ 130 znaków | Wszystkich |
|---:|---:|---:|---:|
| 140 | 114 | 78 | 1 000 |

### Przykłady: ocena różni się o 2 punkty (A9, 6 zapytań)

| Zapytanie | Ocena 1 → 2 | Sygnały przebieg 1 → 2 | Co się zmieniło |
|---|---|---|---|
| L161139 | 6 → 4 | `konkretne_pytania` → + `budzet_niski` | ten sam budżet 1 450 zł dla 2 osób w Łodzi: raz „może ograniczać”, raz „wyraźnie niski” |
| L116466 | 4 → 6 | `konkretne_pytania`, `budzet_niski` → bez `budzet_niski` | odwrotnie: budżet 1 750 zł w Gdańsku raz „wyraźnie niski”, raz „może ograniczać” |
| L079834 | 6 → 4 | + `budzet_niski` | budżet 1 900 zł dla 2 osób w Poznaniu |
| L050104 | 6 → 4 | − `relokacja` | budżet 2 700 zł w Warszawie raz „może ograniczać”, raz „niski” |
| L112854 | 6 → 4 | bez zmian | relokacja B2B, w treści rodzina, a nie firma: raz plus, raz minus |
| L093419 | 2 → 4 | bez zmian (`brak_informacji`) | puste zapytanie: raz „znikoma szansa”, raz „utrudnia ocenę” |

## SQL i kod

- Schemat: `api/api/ai/llm/schemas/ocena_leada.py`.
- Prompt: `api/api/ai/llm/prompts/ocena_leada_v1.yaml` (pola: `wersja`, `data`, `instrukcja`, `szablon`).
- Wejście: `api/api/ai/features/leady/ocena_llm.py`.
- Klient: `api/api/adapters/llm_client.py`.
- Testy: `api/tests/test_llm_ocena_leada.py`.

Uruchomienie pomiaru (wymaga `pypyr baza` i klucza w środowisku). Wyniki trafiają do
`api/api/ai/llm/evals/wyniki/stabilnosc_ocena_leada_v1.parquet`, razem z wejściem każdego zapytania:

```bash
set -a && . ./.env && set +a
cd api && poetry run python -m api.ai.llm.evals.stabilnosc_ocena_leada
```

Tabela zgodności (pierwsza tabela) to wynik tego polecenia. Pozostałe tabele liczą zapytania niżej na pliku
Parquet z wynikami. Uruchom je z katalogu głównego repozytorium, na przykład w CLI `duckdb` 1.5 albo w Pythonie
przez `duckdb.connect()`.

```sql
CREATE TEMP TABLE w AS
SELECT przebieg, id_leada, wejscie,
    CAST(json_extract(dane, '$.ocena') AS INTEGER) AS ocena,
    json_extract_string(dane, '$.uzasadnienie') AS uzasadnienie,
    CAST(json_extract(dane, '$.sygnaly') AS VARCHAR[]) AS sygnaly,
    tokeny_wejscia, tokeny_wyjscia
FROM 'api/api/ai/llm/evals/wyniki/stabilnosc_ocena_leada_v1.parquet';

CREATE TEMP TABLE pary AS
SELECT a.id_leada, a.wejscie, a.ocena AS o1, b.ocena AS o2, a.sygnaly AS s1, b.sygnaly AS s2,
    a.uzasadnienie AS u1, b.uzasadnienie AS u2,
    a.wejscie LIKE '%treść zapytania: brak' AS bez_tresci,
    regexp_extract(a.wejscie, 'linia: (\w+)', 1) AS linia
FROM w AS a JOIN w AS b ON a.id_leada = b.id_leada AND a.przebieg = 1 AND b.przebieg = 2;

-- A1 rozkład ocen
SELECT ocena, count(*) FILTER (WHERE przebieg = 1) AS przebieg_1, count(*) FILTER (WHERE przebieg = 2) AS przebieg_2
FROM w GROUP BY ocena ORDER BY ocena;

-- A2 różnica ocen
SELECT o2 - o1 AS roznica, count(*) AS leadow FROM pary GROUP BY 1 ORDER BY 1;

-- A3 korelacja rang (Spearman = korelacja Pearsona rang) i średnie
SELECT round(corr(r1, r2), 3) AS spearman, round(avg(o1), 3) AS sr1, round(avg(o2), 3) AS sr2
FROM (SELECT rank() OVER (ORDER BY o1) AS r1, rank() OVER (ORDER BY o2) AS r2, o1, o2 FROM pary);

-- A4 zgodność wg oceny z przebiegu 1
SELECT o1 AS ocena_p1, count(*) AS leadow, sum((o1 = o2)::INT) AS identyczne, round(avg((o1 = o2)::INT), 3) AS odsetek
FROM pary GROUP BY 1 ORDER BY 1;

-- A5 zgodność wg treści i linii
SELECT CASE WHEN bez_tresci THEN 'bez treści' ELSE 'z treścią' END AS grupa, count(*) AS leadow,
    sum((o1 = o2)::INT) AS identyczne, round(avg((o1 = o2)::INT), 3) AS odsetek
FROM pary GROUP BY 1
UNION ALL
SELECT 'linia ' || linia, count(*), sum((o1 = o2)::INT), round(avg((o1 = o2)::INT), 3) FROM pary GROUP BY linia
ORDER BY 1;

-- A6 sygnały: częstość i zgodność obecności
WITH s(sygnal) AS (VALUES ('konkretne_pytania'), ('niedopasowanie_oferty'), ('pilny_termin'), ('relokacja'),
                          ('budzet_niski'), ('brak_informacji'))
SELECT sygnal, sum(list_contains(s1, sygnal)::INT) AS w_p1, sum(list_contains(s2, sygnal)::INT) AS w_p2,
    sum((list_contains(s1, sygnal) = list_contains(s2, sygnal))::INT) AS zgodne,
    round(avg((list_contains(s1, sygnal) = list_contains(s2, sygnal))::INT), 3) AS odsetek
FROM pary, s GROUP BY sygnal ORDER BY odsetek;

-- A7 długość uzasadnień
SELECT max(length(uzasadnienie)) AS maks, round(median(length(uzasadnienie)), 0) AS mediana,
    count(*) FILTER (WHERE length(uzasadnienie) >= 130) AS od_130, count(*) AS n
FROM w;

-- A8 wspólne zapytania w 100 najwyżej ocenionych (remisy rozstrzyga id_leada)
WITH r AS (
    SELECT id_leada, row_number() OVER (ORDER BY o1 DESC, id_leada) AS n1,
        row_number() OVER (ORDER BY o2 DESC, id_leada) AS n2
    FROM pary
)
SELECT count(*) FILTER (WHERE n1 <= 100 AND n2 <= 100) AS wspolne_w_top100 FROM r;

-- A9 zapytania z oceną różną o 2 i więcej
SELECT id_leada, o1, o2, s1, s2, u1, u2, wejscie FROM pary WHERE abs(o1 - o2) >= 2;

-- A10 rozbieżne oceny a zmiana sygnałów
SELECT
    count(*) FILTER (WHERE o1 <> o2) AS rozne_oceny,
    count(*) FILTER (WHERE o1 <> o2
        AND list_contains(s1, 'budzet_niski') <> list_contains(s2, 'budzet_niski')) AS z_inna_flaga_budzetu,
    count(*) FILTER (WHERE o1 <> o2 AND s1 <> s2) AS z_innymi_sygnalami,
    count(*) FILTER (WHERE o1 = o2 AND s1 <> s2) AS ta_sama_ocena_inne_sygnaly,
    count(*) FILTER (WHERE list_contains(s1, 'budzet_niski') <> list_contains(s2, 'budzet_niski')) AS flaga_budzetu_zmieniona
FROM pary;
```

Zapytania o dane wejściowe i ofertę uruchamiamy na `domilo.duckdb` przez `polacz()`:

```sql
-- W1 imię w treści wiadomości (przed migracją CRM 2025-03-03 i po niej)
SELECT utworzono < TIMESTAMPTZ '2025-03-03 00:00:00+01' AS migracja, count(*) AS n,
    round(avg((wiadomosc ILIKE '%' || imie || '%')::INT) FILTER (WHERE wiadomosc IS NOT NULL), 3) AS imie_w_wiadomosci
FROM crm_leady GROUP BY 1;

-- W2 termin względem dnia zapytania
SELECT count(*) AS n, count(*) FILTER (WHERE termin_wprowadzenia < CAST(utworzono AS DATE)) AS przed_zapytaniem,
    quantile_cont(date_diff('day', CAST(utworzono AS DATE), termin_wprowadzenia), [0, 0.5, 1]) AS dni
FROM crm_leady WHERE termin_wprowadzenia IS NOT NULL;

-- O1 oferta Domilo: długość umów według typu i miasta budynków
SELECT typ, count(*) AS umow, min(date_diff('day', data_od, data_do)) AS min_dni,
    max(date_diff('day', data_od, data_do)) AS max_dni
FROM pms_umowy GROUP BY typ;
SELECT DISTINCT miasto FROM pms_budynki;
```
