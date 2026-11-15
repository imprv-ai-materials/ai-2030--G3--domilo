# Kolejka doradców: zadanie dzienne 05:30, webhook do CRM i GET /leads/next (2026-11-15)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-15 (`pypyr baza`).
Pokaz: dwa przebiegi dla dnia kolejki 2026-11-16 do atrapy CRM (`dev/mock_lejek/`), model `v3_ev_kalibracja`
z `current.yaml`, sygnały i zdania z LLM.

## Wnioski

1. Każdego dnia o 05:30 każdy z 11 aktywnych doradców dostaje do 40 zapytań ze swojego miasta, ułożonych od
   największej wartości oczekiwanej (EV), z jednym zdaniem uzasadnienia. Na 2026-11-16 to 440 z 2 360 otwartych
   zapytań (17–23% w każdym mieście), które niosą 63,1% EV wszystkich otwartych zapytań.
2. Dwa przebiegi zadania dla tego samego dnia dały identyczny stan atrapy CRM: 440 pozycji i ten sam skrót SHA-256
   (`53836455…5d25`). Drugi przebieg nie dopisał ani nie zmienił żadnej pozycji (440 powtórzeń, 0 konfliktów)
   i nie wywołał LLM ani razu, bo wszystkie odpowiedzi były już w cache.
3. Zadanie ma osobny krok na każdy etap i na każdego doradcę przy wysyłce do CRM. Po awarii Inngest ponawia tylko
   krok, który padł. W teście z awarią sieci przy wysyłce kolejki D04 ponowienie
   wykonuje jeszcze raz tylko krok D04, wysyła kolejki doradców D05–D11 (wcześniej nie doszło do nich) i nie liczy
   drugi raz cech, modelu ani LLM.
4. `GET /leads/next?doradca=D01` oddaje te same pozycje, które poszły do CRM. Oba czytają jedną tabelę
   (`kolejka_doradcow`) przez tę samą funkcję.
5. Uwaga: dane kończą się 2026-09-30, więc kolejka na każdy kolejny dzień jest liczona na stanie z końca eksportu i
   będzie taka sama, dopóki nie przyjdą nowe dane. W kolejkach prawie nie ma najmu średnioterminowego (8 z 440),
   bo EV zakłada dla MID krótki najem (docs/kolejka_ev.md).

## Wyniki

### T1. Otwarte zapytania i kolejki, dzień kolejki 2026-11-16 (stan danych 2026-10-01 00:00)

| Miasto | Otwarte zapytania | Doradcy | W kolejkach | % otwartych |
|---|---:|---:|---:|---:|
| Gdańsk | 237 | 1 | 40 | 16,9% |
| Kraków | 405 | 2 | 80 | 19,8% |
| Poznań | 239 | 1 | 40 | 16,7% |
| Warszawa | 939 | 4 | 160 | 17,0% |
| Wrocław | 351 | 2 | 80 | 22,8% |
| Łódź | 189 | 1 | 40 | 21,2% |
| **razem** | **2 360** | **11** | **440** | 18,6% |

Otwarte: 1 271 ze statusem `otwarty` i 1 089 `w_toku`, wszystkie utworzone od 2026-08-17 (najwyżej 45 dni).
W kolejkach: 247 `w_toku` i 193 `otwarty`. Średnie p w kolejkach 20,9%, wśród wszystkich otwartych 8,1%.
Σ EV w kolejkach 5 100 086 zł, a wszystkich otwartych 8 088 884 zł.

### T2. Kolejka każdego doradcy

| Doradca | Miasto | Pozycje | EV min (zł) | EV maks (zł) | Σ EV (zł) | Średnie p |
|---|---|---:|---:|---:|---:|---:|
| D07 | Gdańsk | 40 | 5 402 | 32 791 | 420 559 | 17,7% |
| D04 | Kraków | 40 | 4 959 | 33 861 | 442 202 | 21,4% |
| D09 | Kraków | 40 | 4 875 | 29 568 | 425 371 | 21,8% |
| D06 | Poznań | 40 | 4 303 | 25 392 | 348 497 | 20,5% |
| D01 | Warszawa | 40 | 6 011 | 71 122 | 592 241 | 21,6% |
| D02 | Warszawa | 40 | 6 011 | 59 268 | 571 309 | 22,7% |
| D03 | Warszawa | 40 | 5 925 | 50 812 | 554 094 | 22,6% |
| D08 | Warszawa | 40 | 5 925 | 46 025 | 539 917 | 21,8% |
| D05 | Wrocław | 40 | 3 944 | 27 920 | 364 832 | 20,2% |
| D10 | Wrocław | 40 | 3 944 | 27 920 | 352 099 | 19,4% |
| D11 | Łódź | 40 | 4 120 | 59 176 | 488 966 | 20,6% |

W mieście z kilkoma doradcami zapytania są rozdawane po kolei (1. do pierwszego doradcy, 2. do drugiego, …), więc
kolejki się nie pokrywają, a sumy EV doradców jednego miasta są podobne.

### T3. Skład kolejek (440 pozycji)

| Linia z zapytania | Pozycje | | Źródło | Pozycje |
|---|---:|---|---|---:|
| B2B | 191 | | relokacja_b2b | 180 |
| B2C | 241 | | www | 107 |
| MID | 8 | | domteraz | 72 |
| | | | lokum24 | 47 |
| | | | polecenie | 34 |
| | | | social | 0 |

### T4. Początek kolejki D01 (`GET /leads/next?doradca=D01`)

| Poz. | Zapytanie | Linia | Status | p | EV (zł) | Uzasadnienie |
|---:|---|---|---|---:|---:|---|
| 1 | L160439 | B2B | w_toku | 0,2310 | 71 121,55 | Zapytanie pochodzi z programu relokacji B2B, budżet wynosi 4 600 zł (167% mediany w mieście), a wprowadzenie nastąpi za 36 dni. |
| 2 | L161555 | B2B | otwarty | 0,1794 | 36 820,33 | Źródłem jest program relokacji B2B, budżet wynosi 3 400 zł, czyli 123% mediany w mieście, a najem jest firmowy B2B. |
| 3 | L160027 | B2B | w_toku | 0,2750 | 28 225,37 | Zapytanie pochodzi z programu relokacji B2B, budżet wynosi 4 000 zł (145% mediany w mieście), a spacer 3D został obejrzany. |
| 4 | L161542 | B2B | otwarty | 0,2641 | 27 105,91 | Zapytanie pochodzi z programu relokacji B2B, budżet wynosi 5 300 zł (192% mediany w mieście), a wprowadzenie nastąpi za 57 dni. |
| 5 | L160272 | B2B | w_toku | 0,4737 | 24 305,65 | Źródłem jest program relokacji B2B, budżet wynosi 3 900 zł (141% mediany w mieście), a wprowadzenie nastąpi za 35 dni. |

Zdania: 440 z 440 z LLM (żadne nie spadło do szablonu), długość 63–137 znaków (mediana 100), 384 różne zdania
(zapytania o tych samych faktach top 3 dostają to samo zdanie z cache).

### T5. Dwa przebiegi dla dnia 2026-11-16 (atrapa CRM)

| | Przebieg 1 | Przebieg 2 |
|---|---:|---:|
| sygnały LLM: w cache przed krokiem / wywołania / błędy | 108 / 2 252 / 0 | 2 360 / 0 / 0 |
| zdania uzasadnień: z cache / nowe wywołania | 75 / 365 | 440 / 0 |
| średnie p otwartych / Σ EV otwartych | 0,0814 / 8 088 883,96 zł | 0,0814 / 8 088 883,96 zł |
| webhook: utworzono / powtórzenia / konflikty | 440 / 0 / 0 | 0 / 440 / 0 |
| stan atrapy: pozycje | 440 | 440 |
| stan atrapy: skrót SHA-256 | `53836455cf409d60f93c9ffc549cd9769ba846ca3c96a42c53134aef38265d25` | ten sam |
| odpowiedź `GET /stan` | — | bajt w bajt taka sama (`cmp`) |
| czas przebiegu | poniżej 5 min (id przebiegów: 21:52:28 i 21:57:24 UTC) | 3,9 s |

Tabela `kolejka_doradcow` ma po drugim przebiegu 440 wierszy dnia 2026-11-16 i jeden `id_przebiegu`: zapis
zastępuje cały dzień, a nie dopisuje. `id_przebiegu` nie trafia do CRM, bo dwa przebiegi miałyby wtedy różną
treść pod tym samym kluczem. Sprawdziliśmy to: z `id_przebiegu` w treści drugi przebieg kończy się konfliktem 409
i test pada.

Tokeny LLM zapisane w cache dla tego dnia: sygnały (2 360 zapytań, w tym 108 policzonych wcześniej) 2 810 711
wejścia (2 491 590 z cache promptu OpenAI) i 165 329 wyjścia. Zdania (384 różne wejścia) 171 749 wejścia i 19 295
wyjścia. Koszt w zł: brak cennika w `leasing_bc/zalozenia.yaml`.

Bez LLM (próba na kopii bazy, `KOLEJKA_LLM=0`) sygnały 2 252 zapytań są brakiem. Średnie p wynosi wtedy 0,0737,
a Σ EV 7 371 631,27 zł, więc kolejka jest inna. Brak klucza API zmienia kolejność, a nie tylko zdania.

## Jak działa zadanie

| Krok Inngest (`ctx.step.run`) | Co robi | Plik w katalogu przebiegu |
|---|---|---|
| `parametry` | dzień kolejki (z wywołania albo dziś w Europe/Warsaw) i chwila stanu danych: 05:30 tego dnia, najpóźniej 2026-10-01 00:00 | — |
| `otwarte-zapytania` | ostatni status przed chwilą stanu = `otwarty` / `w_toku`, zapytanie najwyżej 45 dni (Q1) | `otwarte.parquet` |
| `sygnaly-llm` | sygnały v1 z cache, brakujące z LLM; błąd przerywa krok | `sygnaly.parquet` |
| `cechy` | `features/leady/cechy.zbuduj_cechy` (na moment utworzenia zapytania) | `cechy.parquet` |
| `wynik-modelu` | `current.yaml` → `ModelLeadow.predict` i `explain` (p + wkłady SHAP) | `wynik.parquet` |
| `ev` | EV = p × mediana czynszu × czas najmu × liczba lokali (`leasing_bc/wartosc.py`) | `ev.parquet` |
| `kolejki` | aktywni doradcy (Q2), zapytania z ich miasta według EV, po kolei, maks. 40 | `kolejki.parquet` |
| `uzasadnienia` | top 3 SHAP → fakty → zdanie z LLM (`ai/lead_model/uzasadnienie.py`); błąd API przerywa krok | `uzasadnienia.parquet` |
| `zapis-kolejki` | tabela `kolejka_doradcow` (zastępuje dzień) | — |
| `webhook-crm-<doradca>` | kolejka doradcy z tabeli → `POST /webhook/kolejka-doradcy` | — |

- **Ponawianie.** Wynik udanego kroku Inngest zapamiętuje (krótki JSON), a dane przechodzą przez pliki Parquet
  w `kolejka_dzienna/<dzień>/<id przebiegu>/` (poza gitem). Ponowiony krok czyta pliki poprzednich kroków. Funkcja
  ma `retries=3` i `concurrency=1`.
- **Idempotencja.** Klucz `"{id_leada}:{data_kolejki}"`. CRM zapisuje pozycję tylko przy pierwszym kluczu.
  Ten sam klucz z tą samą treścią to powtórzenie (200, bez zmian), a z inną treścią to 409 dla całej paczki
  (`KonfliktIdempotencji`, nic nie zapisane). Zapytanie jest danego dnia u najwyżej jednego doradcy, więc klucz
  wystarcza. p i EV są zaokrąglone (6 i 2 miejsca), żeby treść była stała.
- **Deterministyczność LLM.** Odpowiedzi LLM są w cache (temperatura 0), a błąd wywołania przerywa krok zamiast
  zostawić brak albo zdanie z szablonu. Inaczej drugi przebieg mógłby dostać odpowiedź tam, gdzie pierwszy jej nie
  miał, i treść pod kluczem by się różniła.
- Uruchomienie: `pypyr api` (funkcje Inngest w API), ręcznie `pypyr kolejka data=RRRR-MM-DD`, zdarzenie
  `domilo/kolejka.doradcow` z `{"data_kolejki": "RRRR-MM-DD"}`. Atrapa: `pypyr mock_lejek` (port 8102), adres CRM:
  `CRM_LEJEK_URL`.

## Decyzje do potwierdzenia

- **Kilku doradców w mieście:** rozdzielam zapytania po kolei zamiast dawać każdemu tę samą listę. Inaczej dwóch
  doradców dzwoniłoby do tego samego klienta, a klucz (id_leada, data_kolejki) nie odróżniłby ich pozycji.
- **Otwarte = najwyżej 45 dni:** w danych żadna umowa nie powstała później niż 45 dni po zapytaniu
  (docs/kolejka_target.md, R5). Pomijam 584 zapytania `w_toku` starsze niż 45 dni na koniec eksportu.
- **p nie uwzględnia wieku zapytania:** model ocenia zapytanie na chwilę utworzenia, więc 40-dniowe zapytanie bez
  umowy ma to samo p co nowe.
- **Uzasadnienia tylko dla 440 zapytań w kolejkach**, nie dla wszystkich 2 360, bo tylko te widzi doradca.
  Kolejność kroków jest więc EV → kolejka → uzasadnienie. Wynik dla kolejki jest ten sam.
- **Aktywny doradca** = zatrudniony w dniu kolejki według `crm_doradcy` (`data_od`, `data_do`), bez call center.
  Grafiku (`crm_grafik`) po 2026-09-30 brak w danych, więc nie sprawdzam, czy doradca pracuje danego dnia.
- **Inngest:** kroki i ponawianie sprawdziłem w testach (atrapa zapamiętywania jak w Inngest) i w przebiegach CLI.
  Przebiegu na serwerze deweloperskim Inngest nie robiłem.

## SQL i kod

```bash
pypyr baza
pypyr mock_lejek                                    # osobny terminal; stan: dev/mock_lejek/stan.json
set -a && . ./.env && set +a
curl -X DELETE http://127.0.0.1:8102/stan
pypyr kolejka data=2026-11-16 && curl -s http://127.0.0.1:8102/stan > /tmp/stan_po_1.json
pypyr kolejka data=2026-11-16 && curl -s http://127.0.0.1:8102/stan > /tmp/stan_po_2.json
cmp /tmp/stan_po_1.json /tmp/stan_po_2.json && echo IDENTYCZNE
poetry run pytest api/tests/test_kolejka_dzienna.py   # bez LLM, na kopii bazy, z atrapą w pamięci
```

Kod: `api/api/contexts_boundaries/leasing_bc/kolejka_dzienna.py` (kroki), `api/api/inngest_app.py` (funkcja
`kolejka-doradcow`), `api/api/ai/lead_model/obecny.py` (current.yaml), `api/api/adapters/kolejka_doradcow.py`
(tabela, `pozycje()` dla webhooka i API), `api/api/adapters/crm_lejek.py` (webhook), `dev/mock_lejek/app.py`
(atrapa), `api/api/main.py` (`GET /leads/next`).

**Q1. Otwarte zapytania** (`SQL_OTWARTE`; `$stan` = chwila stanu danych):

```sql
WITH status_w_chwili AS (
    SELECT id_leada, status_na
    FROM crm_historia_statusow
    WHERE data_czas < $stan
    QUALIFY row_number() OVER (
        PARTITION BY id_leada
        ORDER BY data_czas DESC,
                 CASE status_na WHEN 'otwarty' THEN 0 WHEN 'w_toku' THEN 1 ELSE 2 END DESC,
                 status_na DESC
    ) = 1
)
SELECT l.id_leada, l.utworzono, l.zrodlo, l.miasto, l.linia_pref, l.budzet_max, l.termin_wprowadzenia,
       l.liczba_osob, l.zwierze, l.liczba_lokali, l.wiadomosc, l.imie, s.status_na AS status_crm
FROM crm_leady AS l JOIN status_w_chwili AS s USING (id_leada)
WHERE l.utworzono < $stan AND l.utworzono >= $stan - INTERVAL 45 DAY
  AND s.status_na IN ('otwarty', 'w_toku')
ORDER BY l.id_leada;
```

`imie` jest w wejściu kontraktu tylko po to, żeby LLM dostał wiadomość bez imienia (`opis_leada`); nie jest cechą.

**Q2. Aktywni doradcy** (`SQL_DORADCY`; `$dzien` = dzień kolejki):

```sql
SELECT id_doradcy, miasto FROM crm_doradcy
WHERE id_doradcy <> 'CC' AND miasto IS NOT NULL
  AND CAST(data_od AS DATE) <= $dzien AND (data_do IS NULL OR CAST(data_do AS DATE) >= $dzien)
ORDER BY miasto, id_doradcy;
```

**Q3. Przydział** (`przydziel_kolejki`): w mieście z k doradcami (posortowanymi po id) bierzemy k × 40 zapytań
o największym EV (remis: `id_leada`), a zapytanie nr r (od 0) dostaje doradca `r mod k` na pozycji `r div k + 1`.

**Q4. Tabele T1–T3** (na `domilo.duckdb`, katalog przebiegu 2):

```sql
SELECT id_doradcy, miasto, count(*) AS pozycje, min(ev_pln), max(ev_pln), sum(ev_pln), avg(p)
FROM kolejka_doradcow WHERE data_kolejki = DATE '2026-11-16' GROUP BY ALL ORDER BY miasto, id_doradcy;
SELECT linia_pref, count(*) FROM kolejka_doradcow WHERE data_kolejki = DATE '2026-11-16' GROUP BY 1;
SELECT zrodlo, count(*) FROM kolejka_doradcow WHERE data_kolejki = DATE '2026-11-16' GROUP BY 1;
SELECT status_crm, count(*) FROM kolejka_doradcow WHERE data_kolejki = DATE '2026-11-16' GROUP BY 1;
WITH k AS (SELECT sum(ev_pln) AS ev_kolejek, avg(p) AS p_kolejek FROM kolejka_doradcow
           WHERE data_kolejki = DATE '2026-11-16'),
     o AS (SELECT sum(ev) AS ev_otwartych, avg(p) AS p_otwartych
           FROM read_parquet('kolejka_dzienna/2026-11-16/reczny-20261115T215724207901/ev.parquet'))
SELECT ev_kolejek, ev_otwartych, 100 * ev_kolejek / ev_otwartych, p_kolejek, p_otwartych FROM k, o;
```

Tokeny: suma pól `tokeny_wejscia`, `tokeny_wejscia_z_cache`, `tokeny_wyjscia` z wpisów `ai/llm/cache/` o kluczach
`klucz_cache(opis_leada(zapytanie), "ocena_leada_v1")` dla 2 360 otwartych zapytań i
`klucz_cache(wejscie_llm(fakty top 3), "uzasadnienie_v1")` dla 384 różnych wejść zdań.
