# Panel kierownika zespołu najmu: adopcja kolejki, przychód na godzinę, górny decyl, pominięcia (2026-11-15)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-15 (`pypyr baza`,
`dbt build`: 127 kroków, w tym nowe modele panelu i ich testy, wszystkie przeszły). Panel: `ui/app/zespol`
(`pnpm --dir ui dev`, http://localhost:3100/zespol), dane z `GET /team/dashboard`.

## Wnioski

1. Kolejka działa w CRM od 2026-11-16, ale kontakty i umowy w danych kończą się 2026-09-30. Skutków wdrożenia
   nie da się więc jeszcze zmierzyć: adopcja, konwersja i czas do kontaktu dla kolejki z CRM to „brak w danych”.
   Panel pokazuje punkt odniesienia: kolejkę policzoną wstecz tym samym kodem dla 2026-04-15 – 2026-06-30, której
   doradcy nie widzieli.
2. Przed wdrożeniem doradcy zaczynali od zapytań z góry (przyszłej) kolejki prawie tak rzadko, jak przy wyborze
   losowym: 7,7% pierwszych kontaktów dotyczyło pozycji 1–20 kolejki doradcy, a losowo byłoby 6,3%. W Warszawie,
   gdzie czterech doradców dzieli średnio 769 otwartych zapytań, to 2–3%. Wzrost adopcji po wdrożeniu będzie
   pierwszym sygnałem, że kolejka zmienia pracę.
3. Zapytania z górnych 10% rankingu kończyły się umową w 26,5% (276 z 1 042), a pozostałe w 5,4%. Mimo to
   kontaktowano się z nimi niewiele szybciej: mediana 70,5 h wobec 75,6 h od utworzenia zapytania. To jest miejsce,
   w którym kolejka może pomóc. Że szybszy kontakt podniesie konwersję, z tych danych nie wynika.
4. Przychód na godzinę doradcy w tygodniach symulacji wyniósł 5 445 zł/h, czyli −0,9% wobec wartości wyjściowej
   2026-Q2 (5 497 zł/h). Okresy prawie się pokrywają, więc to kontrola zgodności, a nie efekt. W ostatnich czterech
   pełnych tygodniach przed końcem danych podpisań jest coraz mniej (79, 59, 50, 36 tygodniowo) przy stałej
   liczbie zapytań (ok. 1 000 tygodniowo). Przychód tych tygodni spada do 1 895 zł/h, a przyczyny brak w danych.
5. Pominięcia z powodem działają od CRM do panelu. Doradca wybiera w CRM jeden z czterech powodów (znam_klienta,
   brak_lokalu, duplikat, inne + komentarz), CRM przekazuje go do Domilo, a panel widzi go od razu, bez przebudowy
   modeli. Prawdziwych pominięć jeszcze nie ma: tabela jest pusta.

## Wyniki (symulacja wstecz 2026-04-15 – 2026-06-30, 77 dni)

### T1. Panel: wartości dla całego okresu

| Metryka | Wartość | Porównanie |
|---|---:|---|
| Adopcja: pierwsze kontakty z top 20 kolejki doradcy | **7,7%** (614 z 8 018) | losowy wybór 6,3% |
| Przychód na godzinę doradcy, 12 pełnych tygodni 2026-04-13 – 2026-07-05 | **5 445 zł/h** (25 461 110 zł / 4 676 h) | wartość wyjściowa 2026-Q2: 5 497 zł/h (−0,9%) |
| Konwersja górnego decyla (umowa w 45 dni) | **26,5%** (276 z 1 042) | pozostałe 5,4% (466 z 8 705) |
| Mediana czasu od utworzenia do pierwszego kontaktu, górne 10% | **70,5 h** | pozostałe 75,6 h |
| Bez kontaktu w 45 dni, górne 10% | 2,7% | pozostałe 19,6% |
| Pominięcia z powodem | 0 | słownik: znam_klienta, brak_lokalu, duplikat, inne |

123 z 8 018 pierwszych kontaktów dotyczyło zapytań spoza rankingu dnia (np. utworzonych po 05:30 i obsłużonych
tego samego dnia); liczą się jako kontakty spoza top 20. Zapytania z `domteraz` to 4,7% górnego decyla
i 27,9% pozostałych.

### T2. Tydzień po tygodniu

| Tydzień od | Dni kolejki | Pierwsze kontakty | Z top 20 | Adopcja | Losowo | Górny decyl: zapytania / umowy | Konwersja decyla | Pozostałe | Mediana h: decyl / pozostałe | Bez kontaktu (decyl) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-04-13 | 5 | 537 | 36 | 6,7% | 6,2% | 59 / 18 | 30,5% | 5,7% | 74,2 / 76,8 | 1,7% |
| 2026-04-20 | 7 | 738 | 55 | 7,5% | 6,2% | 100 / 28 | 28,0% | 3,8% | 72,0 / 75,5 | 1,0% |
| 2026-04-27 | 7 | 710 | 48 | 6,8% | 6,4% | 93 / 30 | 32,3% | 5,5% | 70,1 / 75,1 | 4,3% |
| 2026-05-04 | 7 | 663 | 46 | 6,9% | 6,3% | 78 / 19 | 24,4% | 4,0% | 79,7 / 78,0 | 1,3% |
| 2026-05-11 | 7 | 685 | 72 | 10,5% | 6,9% | 97 / 17 | 17,5% | 7,3% | 64,4 / 75,8 | 1,0% |
| 2026-05-18 | 7 | 724 | 55 | 7,6% | 6,7% | 90 / 30 | 33,3% | 5,7% | 76,1 / 72,8 | 3,3% |
| 2026-05-25 | 7 | 666 | 49 | 7,4% | 6,7% | 78 / 22 | 28,2% | 4,4% | 85,6 / 73,7 | 1,3% |
| 2026-06-01 | 7 | 760 | 62 | 8,2% | 6,5% | 103 / 26 | 25,2% | 5,4% | 62,5 / 78,7 | 2,9% |
| 2026-06-08 | 7 | 777 | 62 | 8,0% | 6,2% | 114 / 32 | 28,1% | 7,0% | 68,3 / 72,1 | 0,9% |
| 2026-06-15 | 7 | 781 | 61 | 7,8% | 6,0% | 113 / 20 | 17,7% | 5,2% | 76,0 / 80,0 | 4,4% |
| 2026-06-22 | 7 | 773 | 55 | 7,1% | 5,9% | 91 / 26 | 28,6% | 5,6% | 70,7 / 75,6 | 4,4% |
| 2026-06-29 | 2 | 204 | 13 | 6,4% | 5,9% | 26 / 8 | 30,8% | 2,8% | 65,7 / 82,7 | 11,5% |

Tydzień 2026-04-13 ma 5 dni kolejki, a 2026-06-29 tylko 2, więc ich wartości opierają się na mniejszej liczbie
zapytań.

### T3. Adopcja według doradcy

| Doradca | Miasto | Pierwsze kontakty | Z top 20 | Adopcja | Losowo | Otwarte zapytania w mieście (średnio dziennie) |
|---|---|---:|---:|---:|---:|---:|
| D07 | Gdańsk | 742 | 101 | 13,6% | 11,5% | 173 |
| D04 | Kraków | 702 | 56 | 8,0% | 6,1% | 330 |
| D09 | Kraków | 682 | 50 | 7,3% | 6,1% | 330 |
| D06 | Poznań | 781 | 105 | 13,4% | 11,0% | 183 |
| D01 | Warszawa | 787 | 24 | 3,0% | 2,6% | 769 |
| D02 | Warszawa | 820 | 24 | 2,9% | 2,6% | 769 |
| D03 | Warszawa | 831 | 17 | 2,0% | 2,6% | 769 |
| D08 | Warszawa | 790 | 24 | 3,0% | 2,6% | 769 |
| D05 | Wrocław | 618 | 43 | 7,0% | 6,9% | 288 |
| D10 | Wrocław | 598 | 58 | 9,7% | 7,0% | 288 |
| D11 | Łódź | 667 | 112 | 16,8% | 12,6% | 158 |

Odsetek losowy zależy od liczby otwartych zapytań w mieście, dlatego adopcję porównujemy z nim, a nie między
miastami.

### T4. Przychód na godzinę: tygodnie przed końcem danych

| Tydzień od | Podpisania z zapytań | Wartość umów | Godziny | Przychód / h |
|---|---:|---:|---:|---:|
| 2026-08-31 | 79 | 1 847 210 zł | 385 | 4 798 zł/h |
| 2026-09-07 | 59 | 1 477 340 zł | 420 | 3 517 zł/h |
| 2026-09-14 | 50 | 1 076 300 zł | 392 | 2 746 zł/h |
| 2026-09-21 | 36 | 756 000 zł | 399 | 1 895 zł/h |

Zapytań było w tych tygodniach 1 031, 1 072, 1 096 i 1 035, a mediana czasu od zapytania do umowy podpisanej
w tych tygodniach wynosiła 10–12 dni. Samo ucięcie na dniu eksportu nie tłumaczy więc spadku podpisań (Q6).

## Definicje (modele dbt `api/api/data_platform/dbt/models/panel/`, schemat `metryki`)

| Model | 1 wiersz = | Definicja |
|---|---|---|
| `ranking_dzien` (widok) | otwarte zapytanie × dzień kolejki | z tabeli `kolejka_ranking`: ranga EV w mieście, p, EV, doradca i pozycja; `gorny_decyl` = ranga ≤ ⌈0,1 × liczba otwartych w mieście⌉, `top_adopcji` = pozycja 1–20 kolejki doradcy |
| `pierwszy_kontakt` (tabela) | zapytanie | pierwsza aktywność doradcy lub call center w 45 dni od utworzenia (filtr jak `obsluzony`; test: ten sam moment). `data_kolejki_kontaktu` = kolejka obowiązująca w chwili kontaktu (od 05:30 czasu warszawskiego) |
| `adopcja_dzien` (widok) | doradca × dzień kolejki | pierwsze kontakty doradcy w czasie obowiązywania kolejki, z nich z top 20 jego kolejki; `adopcja_losowa` = min(20, długość kolejki) / otwarte w mieście |
| `kolejka_zapytania` (widok) | zapytanie | pierwszy dzień w rankingu (ranga, górny decyl) + `umowa_45d`, `obsluzony`, czas do pierwszego kontaktu; `nowe` = pierwszy ranking to pierwsza kolejka po utworzeniu |
| `pominiecia` (widok) | pominięta pozycja | z tabeli `kolejka_pominiecia` + miejsce w rankingu dnia |
| `panel_tydzien` (widok) | tydzień | wszystkie metryki tygodnia; konwersja i czas do kontaktu na zapytaniach `nowe` i niecenzurowanych według tygodnia pierwszej kolejki; przychód na godzinę z `przychod_na_godzine_doradcy` i wartość wyjściowa (kwartał 2026-04-01) |

Modele panelu są widokami (poza `pierwszy_kontakt`). Dzienne zadanie (ranking) i CRM (pominięcia) dopisują
dane, a panel widzi je od razu, bez przebudowy modeli. Parametry (20 pozycji, 10%, 05:30, kwartał wyjściowy) są
w `vars` w `dbt_project.yml`.

Testy dbt: unikalność kluczy (`data_kolejki` + `id_leada` w rankingu i pominięciach, doradca × dzień, tydzień),
not null, zakresy (adopcja, konwersje i brak kontaktu 0–1, mediana godzin 0–1 080, pozycja 1–40, ranga ≥ 1),
słowniki (`zrodlo_kolejki`, `powod`), relacja ranking → `umowa_45d` i trzy testy własne. `pierwszy_kontakt`
musi dać ten sam moment co `obsluzony`. Pominięta pozycja musi być w kolejce tego doradcy z tą samą pozycją.
Liczniki adopcji muszą zgadzać się z liczbą pierwszych kontaktów.

### Skąd ranking i pominięcia

- **`kolejka_ranking`** (`api/api/adapters/kolejka_ranking.py`): dzienne zadanie zapisuje teraz cały ranking dnia
  (2 360 zapytań 2026-11-16, `zrodlo_kolejki = 'zadanie'`), a nie tylko 440 pozycji wysłanych do CRM.
  Symulacja wstecz (`leasing_bc/kolejka_wstecz.py`, `pypyr kolejka_wstecz`) liczy ranking tym samym kodem
  (`otwarte_zapytania`, `aktywni_doradcy`, `ranking_kolejki`, model z `current.yaml`, EV), bez uzasadnień
  i webhooka. Dla 2026-04-15 – 2026-06-30 dała 146 387 wierszy w 77 dniach, w tym 33 880 pozycji kolejek
  (77 × 440). Test sprawdza, że dla tego samego dnia ranking wstecz jest identyczny z rankingiem zadania
  (ranga, doradca, pozycja, p, EV). Symulacja nie nadpisuje dni z zadania.
- **`kolejka_pominiecia`** (`api/api/adapters/kolejka_pominiecia.py`): atrapa CRM (`dev/mock_lejek/app.py`) ma
  stronę `GET /doradca/{id}` z polem „powód pominięcia” i `POST /kolejka/pominiecie`. CRM sprawdza kod w słowniku
  i wysyła `POST /leads/skips` do API Domilo. API zapisuje tylko pozycję z kolejki tego doradcy tego dnia, a dla
  „inne” wymaga komentarza. Ten sam powód drugi raz to powtórzenie, a inny powód to poprawka. Klucz:
  (data_kolejki, id_leada). Słownik jest w `leasing_bc/pominiecia.py`, a jego zgodność z atrapą, typem API
  i ograniczeniem CHECK tabeli pilnuje test.
- Pokaz 2026-11-15 na prawdziwej bazie: przez atrapę zapisano trzy pominięcia (znam_klienta, brak_lokalu,
  inne z komentarzem). Dwie błędne próby zostały odrzucone: „inne” bez komentarza (422 z API Domilo) i kod spoza
  słownika (422 w CRM). Powtórzenie zwróciło „powtorzenie”. Panel pokazał wszystkie trzy wpisy. Po zrzutach
  ekranu usunąłem je z `kolejka_pominiecia` i ze stanu atrapy, bo nie pochodzą od doradców.

## Decyzje do potwierdzenia

- **„Pierwszy kontakt dnia”** czytam jako pierwszy kontakt z zapytaniem (pierwsza aktywność przy tym zapytaniu
  w ogóle), który doradca wykonał w czasie obowiązywania kolejki danego dnia, a nie pierwszy telefon doradcy
  danego dnia. W danych godziny aktywności rozkładają się równo na całą dobę (dane syntetyczne), więc „pierwszy
  telefon rano” nie miałby sensu.
- **Górny decyl** to 10% rankingu miasta (wszystkie otwarte zapytania), a nie 10% kolejki doradcy (4 z 40
  pozycji). Zapytanie liczymy raz, w pierwszej kolejce po utworzeniu.
- **Czas do kontaktu** liczę od utworzenia zapytania (jak `obsluzony`), a nie od wejścia do kolejki.
- **Okres symulacji** zaczyna się 2026-04-15, żeby 45-dniowe okno otwartych zapytań nie sięgało okresu kalibracji
  modelu (do 2026-02). Kończy się 2026-06-30, bo dla zapytań z lipca–września brakuje ok. 10 600 sygnałów LLM
  w cache (lipiec: 4 204 brakujących z 4 401, sierpień: 4 255 z 4 547, wrzesień: 2 154 z 4 544). Rozszerzenie
  wymaga tych wywołań.
- **Pominięcia zapisuje API Domilo, a nie sama atrapa.** CRM wysyła je przez `POST /leads/skips`, tak jak zrobiłby
  prawdziwy CRM. Bezpośredni zapis z innego procesu do `domilo.duckdb` kolidowałby z blokadą pliku DuckDB, gdy
  API ma otwarte połączenie.
- **Kafel przychodu** pokazuje Σ wartości / Σ godzin w pełnych tygodniach wybranego okresu kolejki, a nie ostatni
  tydzień, bo ostatnie tygodnie danych mają coraz mniej podpisań (T4).

## SQL i kod

```bash
pypyr baza                          # baza, leady_cel, dbt build (modele metryki.*, w tym panel, z testami)
pypyr kolejka_wstecz                # ranking wstecz 2026-04-15 – 2026-06-30 do kolejka_ranking
pypyr mock_lejek                    # atrapa CRM (port 8102), osobny terminal
pypyr api                           # API Domilo (port 8101): GET /team/dashboard, POST /leads/skips
pnpm --dir ui dev                   # panel: http://localhost:3100/zespol
poetry run pytest api/tests/test_panel_kierownika.py
```

Kod: modele `api/api/data_platform/dbt/models/panel/*.sql` i `panel.yml`, testy
`api/api/data_platform/dbt/tests/singular/{pierwszy_kontakt_jak_obsluzony,pominiecie_z_kolejki_doradcy,adopcja_liczniki_spojne}.sql`,
odczyt `api/api/contexts_boundaries/leasing_bc/panel.py`, UI `ui/app/zespol/page.tsx`,
`ui/components/{WykresLinii,WykresPowodow}.tsx`.

**Q1. T1, okres** (`SQL_OKRES_ADOPCJA`, `SQL_OKRES_DECYL`, `SQL_OKRES_PRZYCHOD` w `panel.py`):

```sql
SELECT zrodlo_kolejki, sum(pierwsze_kontakty), sum(z_top), sum(poza_rankingiem),
       sum(z_top) / nullif(sum(pierwsze_kontakty), 0) AS adopcja,
       sum(adopcja_losowa * pierwsze_kontakty) / nullif(sum(pierwsze_kontakty), 0) AS adopcja_losowa
FROM metryki.adopcja_dzien GROUP BY zrodlo_kolejki;

SELECT zrodlo_kolejki, gorny_decyl, count(*), sum(umowa_45d), avg(umowa_45d),
       median(godz_do_pierwszego_kontaktu) FILTER (WHERE obsluzony),
       avg(CASE WHEN obsluzony THEN 0.0 ELSE 1.0 END)
FROM metryki.kolejka_zapytania WHERE nowe AND NOT cenzurowany GROUP BY ALL;

WITH t AS (
    SELECT unnest(string_split(zrodlo_kolejki, ',')) AS zrodlo_kolejki, tydzien, wartosc_umow_z_zapytan,
           godziny_doradcow
    FROM metryki.panel_tydzien WHERE zrodlo_kolejki IS NOT NULL AND pelny_tydzien_przychodu
)
SELECT zrodlo_kolejki, count(*), sum(wartosc_umow_z_zapytan), sum(godziny_doradcow),
       sum(wartosc_umow_z_zapytan) / nullif(sum(godziny_doradcow), 0)
FROM t GROUP BY zrodlo_kolejki;
```

**Q2. T2** (`metryki.panel_tydzien`):

```sql
SELECT tydzien, dni_kolejki, pierwsze_kontakty, pierwsze_kontakty_z_top, adopcja, adopcja_losowa,
       zapytania_decyl, umowy_decyl, konwersja_decyl, konwersja_poza_decylem,
       mediana_godz_kontaktu_decyl, mediana_godz_kontaktu_poza_decylem, bez_kontaktu_decyl, pominiecia
FROM metryki.panel_tydzien WHERE zrodlo_kolejki = 'symulacja_wstecz' ORDER BY tydzien;
```

**Q3. T3** (`metryki.adopcja_dzien`):

```sql
SELECT id_doradcy, any_value(miasto), sum(pierwsze_kontakty), sum(z_top),
       sum(z_top) / sum(pierwsze_kontakty), sum(adopcja_losowa * pierwsze_kontakty) / sum(pierwsze_kontakty),
       avg(otwarte_w_miescie)
FROM metryki.adopcja_dzien WHERE zrodlo_kolejki = 'symulacja_wstecz' GROUP BY 1 ORDER BY 2, 1;
```

**Q4. Udział `domteraz`** (górny decyl / pozostałe):

```sql
SELECT k.gorny_decyl, avg(CASE WHEN c.zrodlo = 'domteraz' THEN 1 ELSE 0 END)
FROM metryki.kolejka_zapytania AS k JOIN metryki.umowa_45d AS c USING (id_leada)
WHERE k.nowe AND NOT k.cenzurowany AND k.zrodlo_kolejki = 'symulacja_wstecz' GROUP BY 1;
```

**Q5. T4** (`metryki.panel_tydzien`):

```sql
SELECT tydzien, podpisania_z_zapytan, wartosc_umow_z_zapytan, godziny_doradcow, przychod_na_godzine_doradcy
FROM metryki.panel_tydzien WHERE tydzien BETWEEN DATE '2026-08-31' AND DATE '2026-09-21' ORDER BY tydzien;
```

**Q6. Podpisania i zapytania przed końcem danych:**

```sql
SELECT cast(date_trunc('week', w.data_podpisania) AS date) AS tydzien, count(*) AS podpisania,
       median(c.dni_do_umowy) AS mediana_dni_do_umowy
FROM metryki.wartosc_umowy AS w JOIN metryki.umowa_45d AS c USING (id_leada)
WHERE w.z_zapytania AND w.data_podpisania >= DATE '2026-07-27' GROUP BY 1 ORDER BY 1;

SELECT cast(date_trunc('week', utworzono) AS date) AS tydzien, count(*) AS zapytania, count(id_umowy) AS z_umowa
FROM metryki.umowa_45d WHERE utworzono >= TIMESTAMPTZ '2026-06-29 00:00:00+02' GROUP BY 1 ORDER BY 1;
```

**Q7. Sygnały LLM w cache** (zapytania od 2026-03 według miesiąca; `wczytaj_sygnaly` na `wczytaj_zbior`):
marzec–czerwiec 15 217 z 15 217, lipiec 197 z 4 401, sierpień 292 z 4 547, wrzesień 2 390 z 4 544.
