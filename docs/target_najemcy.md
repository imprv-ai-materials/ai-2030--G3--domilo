# Lista retencyjna: target `odejdzie` (tabela `migawki_najemcy`)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw; tabela zbudowana w `domilo.duckdb` 2026-11-16
(`cd api && poetry run python -m api.ai.features.najemcy.migawki`, także krok `pypyr baza`).

## Wnioski

1. Spośród 19 231 umów rocznych B2C i B2B, które skończyły się między 2023-03-01 a 2026-09-30, najemca nie został
   na kolejny okres w 7 562 przypadkach (39,32%). W poszczególnych miesiącach do 2024-01 odsetek odejść wynosił
   od 37,8% do 51,7%, a od 2024-02 mieści się w przedziale 34,5–41,6%.
2. Klienci firmowi (B2B) odchodzą znacznie częściej niż prywatni: 74,45% wobec 32,59%. Model i lista powinny
   traktować obie grupy osobno albo przynajmniej mieć linię jako cechę. Inaczej lista wypełni się samymi
   umowami B2B.
3. Na 60 dni przed końcem umowy 2 521 z 7 562 odchodzących (33,34%) już złożyło wypowiedzenie w PMS. Tych osób model
   nie musi przewidywać, a oferta prawdopodobnie przychodzi dla nich za późno. Wśród umów bez wypowiedzenia odchodzi
   30,19%, i to jest właściwa grupa dla listy retencyjnej.
4. Od 2024-02 część najemców dostaje ofertę retencyjną (`retencja_decyzje`), więc wynik częściowo zależy od tego,
   komu firma ją dała. W losowym teście z lat 2025–2026 z grupy z ofertą odeszło 36,88%, a z grupy kontrolnej 42,09%
   (różnica 5,21 p.p. ± 2,78 p.p., 95%). Model uczony na historii nauczy się więc także dotychczasowej polityki
   ofert. W latach 2024-02 – 2025-06 rabat dostawał praktycznie każdy najemca z wysokim score, więc z tych danych
   nie da się odczytać, jak ryzykowny byłby bez rabatu (sekcja „Dlaczego model nie mierzy ryzyka bez rabatu”).
5. Przeprowadzka do innego lokalu Domilo zdarza się rzadko (36 umów) i prawie nie zmienia odsetka odejść.

## Definicja

Jeden wiersz to jedna umowa z `pms_umowy` (jeden lokal; umowa ramowa B2B ma tyle wierszy, ile lokali).
SQL: [`api/api/ai/features/najemcy/migawki.sql`](../api/api/ai/features/najemcy/migawki.sql), budowa:
`api/api/ai/features/najemcy/migawki.py`, testy: `api/tests/test_migawki_najemcy.py`.

| Element | Definicja |
|---|---|
| Populacja | `pms_umowy.typ` = `pierwsza` albo `przedłużenie` (linie B2C i B2B), `data_do` od 2023-03-01 do 2026-09-30 włącznie |
| Pominięte | umowy `średnioterminowa` (linia MID); umowy, w których najemca wyprowadził się przed `data_do` (`pms_najmy.data_wyprowadzenia < data_do`) |
| `data_migawki` | `data_do` − 60 dni. Stan na **początek** tego dnia: zdarzenia z datą < `data_migawki` są znane, późniejsze nie |
| `odejdzie` | 1: najem nie ma kolejnego okresu (`nr_okresu + 1` w `pms_umowy`) i nie było przeprowadzki; 0: jest kolejny okres albo przeprowadzka |
| `przeprowadzka` | najem bez kolejnego okresu, a ten sam `id_najemcy` wprowadził się do innego najmu Domilo (dowolna linia) między `data_migawki` a `data_do` + 30 dni. Najem zaczęty wcześniej jest równoległy, a później oznacza powrót po przerwie (lokal stał pusty) |
| `wypowiedzenie_przed_migawka` | `pms_najmy.wypowiedzenie_data < data_migawki`: wypowiedzenie znane w dniu migawki |
| `miesiecy_umowy` | długość umowy: 12, a dla pierwszych umów B2B także 18 albo 24 |
| `miesiac_konca` | pierwszy dzień miesiąca `data_do` |

Kolumny wyniku (`id_umowy_nastepnej`, `id_najmu_przeprowadzki`, `data_wyprowadzenia`, `powod_odejscia`,
`wypowiedzenie_data`) opisują to, co stało się po migawce. **Nie są cechami do modelu.**

Decyzje przy definicji:

- **„Umowa roczna” obejmuje też pierwsze umowy B2B na 18 i 24 miesiące.** Tak samo liczy je firma: od 2024-02
  populacja `migawki_najemcy` pokrywa się 1:1 z `retencja_decyzje` („kończąca się umowa roczna”), czyli 15 206 umów
  po obu stronach i 0 brakujących. Kto chce wyłącznie umów 12-miesięcznych, filtruje `miesiecy_umowy = 12`.
- **Przedłużenia nie widać w dniu migawki:** kolejny okres podpisano od 12 do 41 dni po `data_migawki`
  (11 633 przedłużenia, żadne nie było podpisane wcześniej), więc `data_podpisania` następnej umowy nie zdradza
  wyniku.
- **Wynik jest znany dla całego okna:** każdy najem bez wyprowadzki ma w PMS okres umowy kończący się po
  2026-09-30, a przedłużenia umów kończących się we wrześniu 2026 podpisano przed eksportem.
- Wcześniejsze rozwiązania pomijamy zgodnie z definicją zadania. 85 z nich to wyprowadzki między dniem migawki
  a `data_do`, a tego w dniu migawki jeszcze nie wiadomo (patrz pytania na końcu).
- 4 526 umów (23,5%) zaczęło się przed 2023-03-01, czyli pochodzi z importu PMS: mają puste `data_podpisania`,
  a ich migawki z 2023 roku mają krótką historię zdarzeń (dane zdarzeniowe od 2023-01-01; najwcześniejsza migawka
  to 2022-12-31).

## Wyniki

### Całość

| Umowy | Odejścia | % odejść | Przedłużone (kolejny okres) | Przeprowadzki | Wypowiedzenie przed migawką | % odejść bez wypowiedzenia przed migawką (16 699 umów) |
|---:|---:|---:|---:|---:|---:|---:|
| 19 231 | 7 562 | 39,32 | 11 633 | 36 | 2 532 (2 521 odejść, 11 przeprowadzek) | 30,19 |

### Linia i długość umowy

| Linia | Miesięcy umowy | Umowy | Odejścia | % odejść |
|---|---:|---:|---:|---:|
| B2B | 12 | 2 129 | 1 580 | 74,21 |
| B2B | 18 | 639 | 488 | 76,37 |
| B2B | 24 | 324 | 234 | 72,22 |
| **B2B** | razem | **3 092** | **2 302** | **74,45** |
| **B2C** | 12 | **16 139** | **5 260** | **32,59** |

| Linia | Typ umowy | Umowy | Odejścia | % odejść |
|---|---|---:|---:|---:|
| B2B | pierwsza | 2 470 | 1 854 | 75,06 |
| B2B | przedłużenie | 622 | 448 | 72,03 |
| B2C | pierwsza | 7 703 | 2 788 | 36,19 |
| B2C | przedłużenie | 8 436 | 2 472 | 29,30 |

### Liczba umów i odsetek odejść w każdym miesiącu (miesiąc `data_do`)

| Miesiąc końca | Umowy | Odejścia | % odejść | Umowy B2C | % B2C | Umowy B2B | % B2B | % odejść bez wypowiedzenia przed migawką |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-03 | 260 | 111 | 42,7 | 226 | 36,3 | 34 | 85,3 | 30,3 |
| 2023-04 | 322 | 161 | 50,0 | 261 | 45,6 | 61 | 68,9 | 43,3 |
| 2023-05 | 300 | 138 | 46,0 | 248 | 40,7 | 52 | 71,2 | 36,9 |
| 2023-06 | 339 | 159 | 46,9 | 289 | 40,5 | 50 | 84,0 | 36,4 |
| 2023-07 | 390 | 175 | 44,9 | 333 | 41,1 | 57 | 66,7 | 34,5 |
| 2023-08 | 386 | 164 | 42,5 | 337 | 39,2 | 49 | 65,3 | 32,1 |
| 2023-09 | 431 | 163 | 37,8 | 375 | 33,1 | 56 | 69,6 | 30,0 |
| 2023-10 | 419 | 176 | 42,0 | 365 | 37,0 | 54 | 75,9 | 31,9 |
| 2023-11 | 380 | 159 | 41,8 | 324 | 35,5 | 56 | 78,6 | 31,2 |
| 2023-12 | 356 | 184 | 51,7 | 299 | 47,8 | 57 | 71,9 | 42,1 |
| 2024-01 | 442 | 192 | 43,4 | 359 | 37,9 | 83 | 67,5 | 35,0 |
| 2024-02 | 326 | 116 | 35,6 | 267 | 29,2 | 59 | 64,4 | 28,6 |
| 2024-03 | 401 | 156 | 38,9 | 328 | 32,3 | 73 | 68,5 | 29,0 |
| 2024-04 | 434 | 163 | 37,6 | 338 | 29,0 | 96 | 67,7 | 28,7 |
| 2024-05 | 410 | 157 | 38,3 | 337 | 31,5 | 73 | 69,9 | 30,7 |
| 2024-06 | 466 | 163 | 35,0 | 404 | 27,7 | 62 | 82,3 | 24,8 |
| 2024-07 | 535 | 190 | 35,5 | 449 | 29,6 | 86 | 66,3 | 28,5 |
| 2024-08 | 513 | 203 | 39,6 | 440 | 33,6 | 73 | 75,3 | 30,8 |
| 2024-09 | 548 | 206 | 37,6 | 483 | 33,3 | 65 | 69,2 | 27,8 |
| 2024-10 | 513 | 192 | 37,4 | 457 | 32,4 | 56 | 78,6 | 26,9 |
| 2024-11 | 455 | 165 | 36,3 | 385 | 29,9 | 70 | 71,4 | 27,3 |
| 2024-12 | 423 | 155 | 36,6 | 347 | 31,4 | 76 | 60,5 | 27,4 |
| 2025-01 | 480 | 176 | 36,7 | 396 | 28,8 | 84 | 73,8 | 26,7 |
| 2025-02 | 400 | 156 | 39,0 | 327 | 31,2 | 73 | 74,0 | 29,6 |
| 2025-03 | 440 | 165 | 37,5 | 348 | 26,1 | 92 | 80,4 | 27,6 |
| 2025-04 | 414 | 158 | 38,2 | 332 | 29,2 | 82 | 74,4 | 30,2 |
| 2025-05 | 417 | 168 | 40,3 | 330 | 31,8 | 87 | 72,4 | 32,7 |
| 2025-06 | 441 | 155 | 35,1 | 382 | 28,8 | 59 | 76,3 | 25,7 |
| 2025-07 | 549 | 213 | 38,8 | 449 | 32,5 | 100 | 67,0 | 29,5 |
| 2025-08 | 507 | 203 | 40,0 | 423 | 32,4 | 84 | 78,6 | 30,9 |
| 2025-09 | 549 | 228 | 41,5 | 481 | 35,8 | 68 | 82,4 | 34,2 |
| 2025-10 | 564 | 224 | 39,7 | 488 | 33,2 | 76 | 81,6 | 29,6 |
| 2025-11 | 576 | 236 | 41,0 | 498 | 34,3 | 78 | 83,3 | 31,5 |
| 2025-12 | 517 | 201 | 38,9 | 420 | 32,6 | 97 | 66,0 | 30,6 |
| 2026-01 | 537 | 206 | 38,4 | 452 | 30,5 | 85 | 80,0 | 29,8 |
| 2026-02 | 435 | 167 | 38,4 | 359 | 29,5 | 76 | 80,3 | 29,7 |
| 2026-03 | 500 | 193 | 38,6 | 406 | 30,0 | 94 | 75,5 | 29,3 |
| 2026-04 | 440 | 157 | 35,7 | 352 | 27,0 | 88 | 70,5 | 24,5 |
| 2026-05 | 404 | 145 | 35,9 | 338 | 27,2 | 66 | 80,3 | 27,2 |
| 2026-06 | 426 | 152 | 35,7 | 367 | 28,1 | 59 | 83,1 | 27,5 |
| 2026-07 | 533 | 184 | 34,5 | 441 | 25,6 | 92 | 77,2 | 26,4 |
| 2026-08 | 510 | 201 | 39,4 | 435 | 31,3 | 75 | 86,7 | 30,1 |
| 2026-09 | 543 | 226 | 41,6 | 464 | 33,6 | 79 | 88,6 | 32,3 |

Odejścia B2C przed 2024-02 i od 2024-02 (start `retencja_decyzje`): 39,26% z 3 416 umów wobec 30,80% z 12 723 umów.
B2B: 72,41% z 609 wobec 74,95% z 2 483. Zbieżność w czasie z początkiem ofert retencyjnych nie dowodzi, że to
skutek ofert.

### Umowy pominięte (`data_do` 2023-03-01 – 2026-09-30)

| Typ | Powód | Umowy |
|---|---|---:|
| pierwsza | wyprowadzka przed dniem migawki | 301 |
| pierwsza | wyprowadzka między dniem migawki a `data_do` | 41 |
| przedłużenie | wyprowadzka przed dniem migawki | 246 |
| przedłużenie | wyprowadzka między dniem migawki a `data_do` | 44 |
| średnioterminowa | linia MID | 4 571 |

### Przeprowadzki: wrażliwość na okno

Okno zaczyna się w dniu migawki i kończy `data_do` + N dni. Przyjęte N = 30.

| N (dni po `data_do`) | Przeprowadzki | % odejść |
|---:|---:|---:|
| 0 | 9 | 39,46 |
| **30** | **36** | **39,32** |
| 60 | 83 | 39,08 |
| 90 | 138 | 38,79 |

Spośród 36 przeprowadzek przy N = 30 nowy najem był w 28 przypadkach B2C, a w 8 MID. Kolejny najem tego samego
najemcy w tym samym lokalu nie występuje w danych.

### Oferty retencyjne (`retencja_decyzje`, od 2024-02)

| Okres | Grupa | Umowy | % odejść |
|---|---|---:|---:|
| polityka_2024 | brak_oferty | 4 950 | 30,22 |
| polityka_2024 | oferta | 2 666 | 50,56 |
| test_2025 | kontrola | 2 402 | 42,09 |
| test_2025 | oferta | 2 332 | 36,88 |
| polityka_2026 | brak_oferty | 826 | 29,06 |
| polityka_2026 | oferta | 444 | 48,20 |
| kampania_2026q3 | brak_oferty | 1 031 | 30,94 |
| kampania_2026q3 | kontrola | 111 | 60,36 |
| kampania_2026q3 | oferta | 444 | 50,68 |

W okresach „polityka” ofertę dostają umowy z wysokim score, więc wyższy odsetek odejść w grupie `oferta` nie znaczy,
że oferta szkodzi. Bez takiego obciążenia porównać można tylko grupy z losowego `test_2025`: kontrola − oferta =
5,21 p.p., połowa 95% przedziału 2,78 p.p., z = 3,67.

### Dlaczego model nie mierzy „ryzyka bez rabatu” (umowy z końcem 2024-02 – 2025-06)

Po prostu:

- W tym okresie Domilo dawało ofertę według score dostawcy (`polityka_2024`). Oferta to rabat 150 zł miesięcznie
  w nowej umowie: mają go wszystkie 1 314 przedłużeń z grupy z ofertą.
- Ofertę dostało 2 666 z 7 616 kończących się umów (35,01%). Z 2 422 umów ze score od 0,5455 w górę ofertę dostało
  2 421, a poniżej 0,5011 nie dostał jej nikt. To nie był los, tylko próg.
- **Co widzimy w danych:** najemcy z ofertą przedłużali rzadziej (49,44%) niż bez oferty (69,78%). Nie znaczy to, że
  rabat szkodzi. Ofertę dostali ci, którzy i tak częściej odchodzą. Gdy porównamy osoby losowo przydzielone do
  oferty i do kontroli (test 2025), oferta zmniejsza odejścia o 5,21 p.p.
- **Czego w danych brakuje:** jak zachowałby się ryzykowny najemca **bez** rabatu. W tym okresie praktycznie każdy
  ryzykowny najemca rabat dostał, więc takiego przypadku nie ma w danych.
- **Co z tego wynika dla modelu:** model uczony na tym okresie widzi u ryzykownych najemców wynik **po rabacie**,
  a u pozostałych bez rabatu. Uczy się więc „ryzyka przy obecnej polityce ofert”, a nie „ryzyka bez rabatu”.
  - Najbardziej zaniża ryzyko tym, którym firma dawała rabat. Rabat obniżył ich odejścia, a model widzi tylko ten
    niższy wynik.
  - Jeśli takim modelem wybierać, komu dać rabat, firma będzie oceniać najemców tak, jakby już go dostali. Do tego
    nie potrzebujemy ryzyka, tylko tego, o ile rabat zmienia decyzję konkretnego najemcy, a tego model nie liczy.
- W treningu v1_ryzyko (końce umów 2023-03 – 2025-12, 14 903 umowy) ten okres to 7 616 umów, czyli ponad połowa.
  Pozostałe to 4 025 umów sprzed programu ofert (bez `retencja_decyzje`) i 3 262 umowy z losowego testu 2025
  (1 662 kontrola, 1 600 oferta).
- Jedyne miejsce w tym okresie, gdzie są obok siebie umowy z ofertą i bez, to wąski pas score 0,5011–0,5455. Bez
  oferty przedłużyło tam 47,5% z 162 umów, z ofertą 56,3% z 245. Przydział nie był tam losowy, a umów jest mało,
  więc to tylko wskazówka.

| Grupa (`polityka_2024`) | Umowy | Udział | Przedłużone | % przedłużeń | % odejść |
|---|---:|---:|---:|---:|---:|
| oferta (rabat 150 zł / mies.) | 2 666 | 35,01% | 1 318 | 49,44 | 50,56 |
| brak oferty | 4 950 | 64,99% | 3 454 | 69,78 | 30,22 |
| razem | 7 616 | 100% | 4 772 | 62,66 | 37,34 |

| Linia | % przedłużeń z ofertą | % przedłużeń bez oferty |
|---|---:|---:|
| B2C | 58,83 (2 084 umowy) | 74,80 (4 266) |
| B2B | 15,81 (582) | 38,45 (684) |

| Score dostawcy | Umowy | % z ofertą | % przedłużeń |
|---|---:|---:|---:|
| 0,0–0,1 | 459 | 0,0 | 92,8 |
| 0,1–0,2 | 1 022 | 0,0 | 82,6 |
| 0,2–0,3 | 1 136 | 0,0 | 72,3 |
| 0,3–0,4 | 1 100 | 0,0 | 63,3 |
| 0,4–0,5 | 1 059 | 0,0 | 55,1 |
| 0,5–0,6 | 906 | 80,8 | 55,1 |
| 0,6–0,7 | 814 | 100,0 | 51,5 |
| 0,7–0,8 | 614 | 100,0 | 45,9 |
| 0,8–0,9 | 401 | 100,0 | 42,4 |
| 0,9–1,0 | 105 | 100,0 | 30,5 |

## SQL i kod

Budowa tabeli (z katalogu `api/`): `poetry run python -m api.ai.features.najemcy.migawki`, czyli
`CREATE OR REPLACE TABLE migawki_najemcy AS <migawki.sql>`. Wynik: `migawki_najemcy: 19 231 wierszy`.
Testy: `poetry run pytest tests/test_migawki_najemcy.py` (6 testów).

Zapytania z raportu (na `domilo.duckdb` przez `polacz()`, strefa Europe/Warsaw):

```sql
-- Całość
SELECT count(*) AS umowy, sum(odejdzie) AS odejscia, round(100 * avg(odejdzie), 2) AS pct,
       count(id_umowy_nastepnej) AS przedluzone, sum(przeprowadzka::INT) AS przeprowadzki,
       sum(wypowiedzenie_przed_migawka::INT) AS wyp_przed,
       sum((wypowiedzenie_przed_migawka AND odejdzie = 1)::INT) AS wyp_przed_odejscia,
       count(*) FILTER (WHERE NOT wypowiedzenie_przed_migawka) AS n_bez_wyp,
       round(100 * avg(odejdzie) FILTER (WHERE NOT wypowiedzenie_przed_migawka), 2) AS pct_bez_wyp
FROM migawki_najemcy;

-- Linia i długość umowy; linia i typ
SELECT linia, miesiecy_umowy, count(*) AS umowy, sum(odejdzie) AS odejscia, round(100 * avg(odejdzie), 2) AS pct
FROM migawki_najemcy GROUP BY ROLLUP (linia, miesiecy_umowy) ORDER BY ALL;
SELECT linia, typ, count(*), sum(odejdzie), round(100 * avg(odejdzie), 2) FROM migawki_najemcy GROUP BY ALL ORDER BY ALL;

-- Miesiące
SELECT strftime(miesiac_konca, '%Y-%m') AS miesiac, count(*) AS umowy, sum(odejdzie) AS odejscia,
       round(100 * avg(odejdzie), 1) AS pct_odejsc,
       count(*) FILTER (WHERE linia = 'B2C') AS umowy_b2c,
       round(100 * avg(odejdzie) FILTER (WHERE linia = 'B2C'), 1) AS pct_b2c,
       count(*) FILTER (WHERE linia = 'B2B') AS umowy_b2b,
       round(100 * avg(odejdzie) FILTER (WHERE linia = 'B2B'), 1) AS pct_b2b,
       round(100 * avg(odejdzie) FILTER (WHERE NOT wypowiedzenie_przed_migawka), 1) AS pct_bez_wypowiedzenia
FROM migawki_najemcy GROUP BY ALL ORDER BY miesiac;

-- Przed i od 2024-02
SELECT linia, data_do >= DATE '2024-02-01' AS od_2024_02, count(*), round(100 * avg(odejdzie), 2)
FROM migawki_najemcy GROUP BY ALL ORDER BY ALL;

-- Pominięte umowy
SELECT u.typ,
       CASE WHEN u.typ = 'średnioterminowa' THEN 'MID'
            WHEN n.data_wyprowadzenia::DATE < u.data_do::DATE - 60 THEN 'wyprowadzka przed migawką'
            WHEN n.data_wyprowadzenia::DATE < u.data_do::DATE THEN 'wyprowadzka między migawką a data_do'
            ELSE 'w tabeli' END AS grupa,
       count(*)
FROM pms_umowy AS u JOIN pms_najmy AS n USING (id_najmu)
WHERE u.data_do::DATE BETWEEN DATE '2023-03-01' AND DATE '2026-09-30'
GROUP BY ALL ORDER BY ALL;

-- Przeprowadzki: wrażliwość na okno (N dni po data_do) i linia nowego najmu
WITH k AS (
    SELECT m.*,
           (SELECT min(date_diff('day', m.data_do, b.data_wprowadzenia::DATE)) FROM pms_najmy AS b
            WHERE b.id_najemcy = m.id_najemcy AND b.id_najmu <> m.id_najmu
              AND b.data_wprowadzenia::DATE >= m.data_migawki) AS dni
    FROM migawki_najemcy AS m WHERE m.id_umowy_nastepnej IS NULL
)
SELECT okno, count(*) FILTER (WHERE dni <= okno) AS przeprowadzki,
       round(100.0 * (count(*) - count(*) FILTER (WHERE dni <= okno)) / (SELECT count(*) FROM migawki_najemcy), 2)
FROM k, (VALUES (0), (30), (60), (90)) AS t(okno) GROUP BY okno ORDER BY okno;
SELECT b.linia, count(*) FROM migawki_najemcy AS m JOIN pms_najmy AS b ON b.id_najmu = m.id_najmu_przeprowadzki
GROUP BY ALL;

-- Przedłużenie podpisane względem dnia migawki
SELECT min(date_diff('day', m.data_migawki, u.data_podpisania::DATE)), max(date_diff('day', m.data_migawki, u.data_podpisania::DATE)),
       count(*) FILTER (WHERE u.data_podpisania::DATE < m.data_migawki), count(*)
FROM migawki_najemcy AS m JOIN pms_umowy AS u ON u.id_umowy = m.id_umowy_nastepnej;

-- Import PMS i zakres dat; udział odchodzących z wypowiedzeniem przed migawką
SELECT count(*) FILTER (WHERE data_od < DATE '2023-03-01'), count(*), min(data_migawki),
       round(100.0 * count(*) FILTER (WHERE data_od < DATE '2023-03-01') / count(*), 2) AS pct_import,
       round(100.0 * sum((wypowiedzenie_przed_migawka AND odejdzie = 1)::INT) / sum(odejdzie), 2) AS pct_odejsc_z_wyp
FROM migawki_najemcy;

-- Zakres miesięcznego odsetka odejść przed i od 2024-02
WITH m AS (SELECT miesiac_konca, avg(odejdzie) AS p FROM migawki_najemcy GROUP BY 1)
SELECT miesiac_konca >= DATE '2024-02-01' AS od_2024_02, round(100 * min(p), 1), round(100 * max(p), 1)
FROM m GROUP BY 1;

-- Zgodność z retencja_decyzje (od 2024-02)
SELECT count(*) FILTER (WHERE r.id_umowy IS NULL AND m.data_do >= DATE '2024-02-01') AS brak_w_retencji,
       count(*) FILTER (WHERE m.data_do >= DATE '2024-02-01') AS od_2024_02,
       (SELECT count(*) FROM retencja_decyzje) AS w_retencji
FROM migawki_najemcy AS m LEFT JOIN retencja_decyzje AS r USING (id_umowy);

-- Oferty 2024-02 – 2025-06: udział, przedłużenia według grupy, linii i score
SELECT count(*) AS umowy, count(*) FILTER (WHERE r.grupa = 'oferta') AS z_oferta,
       round(100.0 * count(*) FILTER (WHERE r.grupa = 'oferta') / count(*), 2) AS pct_oferta
FROM migawki_najemcy AS m LEFT JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30';
SELECT r.grupa, count(*), sum(1 - odejdzie), round(100 * avg(1 - odejdzie), 2), round(100 * avg(odejdzie), 2)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30' GROUP BY ROLLUP (r.grupa) ORDER BY 1;
SELECT m.linia, r.grupa, count(*), round(100 * avg(1 - odejdzie), 2)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30' GROUP BY ALL ORDER BY ALL;
SELECT floor(score_polityki * 10) / 10 AS przedzial_score, count(*),
       round(100 * avg((r.grupa = 'oferta')::INT), 1) AS pct_z_oferta, round(100 * avg(1 - odejdzie), 1)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30' GROUP BY 1 ORDER BY 1;
-- Próg: score oferty i braku oferty, pas wspólny, umowy od 0,5455 w górę
SELECT r.kwalifikuje, r.grupa, count(*), min(score_polityki), max(score_polityki)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30' GROUP BY ALL;
SELECT r.grupa, count(*), round(100 * avg(1 - odejdzie), 1)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30' AND r.score_polityki BETWEEN 0.5011 AND 0.5455
GROUP BY 1;
SELECT count(*) FILTER (WHERE score_polityki >= 0.5455),
       count(*) FILTER (WHERE score_polityki >= 0.5455 AND r.grupa = 'oferta')
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30';
-- Rabat w przedłużeniach z ofertą
SELECT r.grupa, u.rabat_mies, count(*)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
JOIN pms_umowy AS u ON u.id_umowy = m.id_umowy_nastepnej
WHERE m.data_do BETWEEN DATE '2024-02-01' AND DATE '2025-06-30' GROUP BY ALL;
-- Skład treningu v1_ryzyko według polityki ofert
SELECT coalesce(r.okres, 'przed programem') AS okres, coalesce(r.grupa, '-') AS grupa, count(*)
FROM migawki_najemcy AS m LEFT JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.miesiac_konca <= DATE '2025-12-01' GROUP BY ALL ORDER BY ALL;

-- Oferty retencyjne i losowy test 2025
SELECT r.okres, r.grupa, count(*), round(100 * avg(m.odejdzie), 2)
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy) GROUP BY ALL ORDER BY ALL;
WITH g AS (
    SELECT r.grupa, count(*) AS n, avg(m.odejdzie) AS p
    FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
    WHERE r.okres = 'test_2025' GROUP BY ALL
), k AS (SELECT * FROM g WHERE grupa = 'kontrola'), o AS (SELECT * FROM g WHERE grupa = 'oferta')
SELECT round(100 * (k.p - o.p), 2) AS roznica_pp,
       round(100 * 1.96 * sqrt(k.p * (1 - k.p) / k.n + o.p * (1 - o.p) / o.n), 2) AS pol_przedzialu_95_pp,
       round((k.p - o.p) / sqrt(k.p * (1 - k.p) / k.n + o.p * (1 - o.p) / o.n), 2) AS z
FROM k, o;
```
