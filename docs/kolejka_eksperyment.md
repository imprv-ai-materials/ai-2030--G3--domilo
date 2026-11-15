# Eksperyment switchback: kolejka modelu czy kolejka od najnowszego (projekt, 2026-11-15)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-15 (`pypyr baza`,
`dbt build`: 149 kroków, wszystkie przeszły). Zmienność liczona na 51 pełnych tygodniach 2025-07-07 – 2026-06-28,
tak jak w [kolejka_metryki.md](kolejka_metryki.md). Wszystkie liczby: `api/api/data_platform/wyniki/eksperyment_moc.json`.

## Wnioski

1. Rekomendacja: **16 tygodni** (8 par: tydzień kolejki modelu + tydzień od najnowszego, w losowej kolejności).
   Eksperyment wykryje z mocą 80% wzrost o co najmniej **1 444 zł na godzinę doradcy**, czyli ok. **563 tys. zł
   wartości umów tygodniowo** przy średnio 390 godzinach. Wynik będzie po ok. 22–23 tygodniach (16 tygodni + 45 dni), bo na umowy z kontaktów
   ostatniego tygodnia czekamy 45 dni.
2. Wzrostu o 15% (824 zł/h, ok. **321 tys. zł wartości umów tygodniowo**) 16 tygodni nie potwierdzi. Do tego trzeba
   44 tygodni. Jeśli model naprawdę daje +15%, 22 tygodnie pracy po staremu kosztują 7,07 mln zł wartości umów
   wobec 2,57 mln zł przy 16 tygodniach. Te 4,5 mln zł różnicy to cena odpowiedzi na pytanie „czy aż 15%”, a nie
   „czy model pomaga”.
3. Przychodu według tygodnia podpisania nie da się użyć jako miary. W tygodniu kontaktu podpisuje się tylko 29,5%
   wartości umów, a reszta przychodzi w kolejnych tygodniach, czyli często w tygodniach drugiego wariantu. Przy
   zmianie wariantu co tydzień różnica wyniesie ok. 15% prawdziwego efektu. Taka miara nie wykryje nawet podwojenia
   przychodu (MDE 187% przy 16 tygodniach).
4. Proponowana miara główna: przychód z zapytań przypisany do tygodnia **pierwszego kontaktu**, na godzinę doradcy.
   Wartość jednej umowy jest ograniczona do 74 529 zł (95. percentyl), a wynik skorygowany o godziny i napływ
   zapytań. Waha się mniej niż miara z polecenia (17,2% wobec 18,7% średniej) i nie rozmywa efektu.
5. Do kolejki dodałem 5% pozycji losowych (2 z 40 u każdego doradcy). Dają ocenę modelu wolną od tego, kogo model
   sam wybrał. W kolejce z 2026-11-17 obniżają łączną wartość oczekiwaną kolejek o 51 276 zł (1,0%).

## Projekt eksperymentu

| Element | Ustalenie |
|---|---|
| Warianty | **model**: kolejka według EV z modelu z `current.yaml` (`v3_ev_kalibracja`); **od_najnowszego**: najnowsze zapytania najpierw (obecny sposób pracy, baseline). W obu wariantach ta sama reguła rozdziału między doradców, 40 pozycji, 5% pozycji losowych i te same uzasadnienia |
| Jednostka | tydzień kalendarzowy (kolejki od poniedziałku 05:30 do następnego poniedziałku 05:30), cały zespół naraz |
| Losowanie | tygodnie w parach; w każdej parze jeden tydzień modelu i jeden kontrolny, kolejność losowa (`wylosuj_plan`, ziarno zapisane w planie). Pary równoważą warianty w czasie (sezon, święta, urlopy) i dają równą liczbę tygodni po każdej parze |
| Długość | 16 tygodni (8 par), analiza po 16 tygodniach + 45 dniach |
| Metryka główna | **przychód z kontaktów tygodnia na godzinę doradcy** (`metryki.przychod_z_kontaktow.przychod_z_kontaktow_na_godzine`). Licznik: wartość podpisań z zapytań, z którymi pierwszy kontakt doradcy był w kolejce tego tygodnia, z wartością umowy do 74 529 zł. Mianownik: godziny doradców z grafiku |
| Metryka z polecenia | przychód na godzinę doradcy według tygodnia podpisania (`przychod_na_godzine_doradcy`): raportujemy obok, ale nie decyduje (wniosek 3) |
| Metryki pomocnicze | **adopcja**: odsetek pierwszych kontaktów z pozycji 1–20 kolejki doradcy. Sprawdza, czy doradcy w ogóle pracują z kolejką. **Konwersja górnego decyla**: umowa w 45 dni dla zapytań z górnych 10% rankingu EV miasta (ranking EV jest ten sam w obu wariantach) |
| Analiza | regresja metryki tygodnia na wariant + godziny doradców + nowe zapytania w tym i poprzednim tygodniu (`eksperyment_kolejki.analiza`, test t, 16 − 4 = 12 stopni swobody); wynik w zł/h, % średniej tygodni kontrolnych, 95% CI, p. Sprawdzenie: bez korekty i z efektem pary |
| Stałe w trakcie | model i `current.yaml`, założenia EV (`leasing_bc/zalozenia.yaml`), 5% pozycji losowych, limit 74 529 zł (`vars.limit_wartosci_umowy`), zmienne korekty, reguły kolejki |

### Reguła zakończenia (ustalona przed startem)

1. **Stały horyzont:** 8 par (16 tygodni). Wynik liczymy raz, gdy umowy z ostatniego tygodnia są kompletne
   (`przychod_z_kontaktow.kompletny`, 45 dni po końcu tygodnia).
2. **Bez wcześniejszego zakończenia z powodu sukcesu.** Wielokrotne zaglądanie w wynik zawyża ryzyko fałszywego
   sukcesu ponad 5%.
3. **Zatrzymanie z powodu szkody:** po 4 parach (8 tygodni) liczymy tę samą regresję na umowach, które już
   przyszły. Jeśli tygodnie modelu mają przychód z kontaktów istotnie niższy (dwustronnie p < 0,05, oszacowanie
   ujemne), kończymy eksperyment i wracamy do kolejki od najnowszego. Zatrzymanie z powodu szkody nie zwiększa ryzyka
   fałszywego sukcesu.
4. **Wstrzymanie z powodu braku adopcji:** jeśli po 2 parach adopcja w tygodniach modelu nie jest wyższa niż
   w tygodniach kontrolnych, doradcy nie pracują z kolejką i eksperyment nic nie zmierzy. Wstrzymujemy go,
   poprawiamy wdrożenie (szkolenie, widok w CRM) i zaczynamy od nowa. Tygodnie sprzed wstrzymania się nie liczą.
5. **Tydzień nieważny, para powtarzana na końcu:** zadanie nie dało kolejki w którymś dniu roboczym; w tygodniu
   były dwa warianty (`eksperyment_tydzien.wariant = 'mieszany'`); w trakcie zmieniono model, założenia EV albo
   reguły kolejki; CRM nie przyjął kolejek (webhook).
6. **Decyzja po 16 tygodniach:** oszacowanie dodatnie i istotne → kolejka modelu zostaje. Brak istotności →
   eksperyment nie rozstrzyga. Wybieramy wtedy według znaku oszacowania i metryk pomocniczych, pamiętając, że efekt
   poniżej MDE (26,3%) mógł zostać niewykryty.

### Część losowa kolejki (5%) i `kolejka_historia`

- W każdej kolejce doradcy `int(0,05 × długość + 0,5)` pozycji (40 → 2) zajmują zapytania wylosowane bez zwracania
  ze **wszystkich** otwartych zapytań miasta, na losowych miejscach. Pozostałe miejsca wypełnia wariant
  w dotychczasowej kolejności. Dotyczy to obu wariantów i dni poza eksperymentem.
- Losowanie ma ziarno `dzień:miasto:wariant`, więc drugi przebieg tego samego dnia daje tę samą kolejkę, a webhook
  do CRM pozostaje idempotentny. Pokaz: dwa przebiegi dla 2026-11-17 dały ten sam skrót stanu atrapy CRM
  (`897922b9…`), 440 powtórzeń i 0 konfliktów.
- Tabela `kolejka_historia` (`api/api/adapters/kolejka_historia.py`): pozycja kolejki × dzień z `wariant`,
  `losowa`, `p_losowania` (pozycje losowe w mieście / otwarte zapytania miasta), `pula_losowania`, `ziarno`,
  `ranga_ev`, p, EV, wersją modelu i przebiegiem. Te same zapytania i pozycje co `kolejka_doradcow` (test).
- Po co: konwersja zapytań z pozycji losowych to ocena modelu na zapytaniach, których nie wybrał model. Waga
  1 / `p_losowania` pozwala też porównać inne sposoby układania kolejki bez nowego eksperymentu. Pozycje losowe nie
  są oznaczone w CRM, żeby doradcy traktowali je jak resztę kolejki.
- Ranga (`ranking_dzien.ranga`, `kolejka_historia.ranga_ev`) jest zawsze liczona według EV, w obu wariantach.
  Dlatego górny decyl i konwersja górnego decyla znaczą to samo w tygodniach modelu i kontrolnych.

## Wyniki

### T1. Metryka z polecenia: przychód na godzinę doradcy (tydzień podpisania)

| | Wartość |
|---|---:|
| Tygodnie (2025-07-07 – 2026-06-28) | 51 |
| Średnia / odchylenie standardowe | 5 316,27 zł/h / 994,21 zł/h |
| Odchylenie w % średniej | **18,70%** |
| Autokorelacja tydzień do tygodnia | −0,09 |
| **MDE, 12 tygodni** (6 + 6; t, alfa 5%, moc 80%) | **33,6%** ≈ 1 785 zł/h (przybliżenie normalne: 30,2%) |
| **MDE, 16 tygodni** (8 + 8) | **28,2%** ≈ 1 498 zł/h (przybliżenie normalne: 26,2%) |
| **Tygodnie potrzebne dla +15%** (797 zł/h) | **52** (26 + 26), gdyby cały efekt trafiał do tygodnia podpisania |
| Część prawdziwego efektu widoczna przy zmianie co tydzień (pary) | 0,150 (T2) |
| Tygodnie dla +15% z tym rozmyciem | więcej niż 400 (nie do osiągnięcia) |

MDE to najmniejszy wzrost, który eksperyment wykryje z prawdopodobieństwem 80% przy 5% ryzyku fałszywego alarmu,
w % średniej metryki. Liczymy go z rozkładu t niecentralnego, bo przy 12–16 tygodniach przybliżenie normalne
zaniża MDE.

### T2. Skąd pochodzi wartość umów podpisanych w tygodniu (umowy z zapytań 2025-07-07 – 2026-06-28)

| Tydzień pierwszego kontaktu | Umowy | Udział wartości |
|---|---:|---:|
| ten sam tydzień | 1 039 | 29,5% |
| tydzień wcześniej | 942 | 29,0% |
| 2 tygodnie wcześniej | 540 | 16,4% |
| 3 tygodnie wcześniej | 371 | 12,0% |
| 4 tygodnie wcześniej | 268 | 8,7% |
| 5 tygodni wcześniej | 127 | 3,4% |
| 6 tygodni wcześniej | 35 | 1,0% |

W parach poprzedni tydzień należy w połowie przypadków do drugiego wariantu. Różnica wariantów w tygodniu
podpisania to więc ok. 0,295 − 0,5 × 0,290 ≈ 0,15 prawdziwego efektu. Symulacja 20 000 planów daje 0,150 przy
12 i 16 tygodniach.

### T3. Kandydaci na metrykę główną (MDE w % średniej, alfa 5%, moc 80%)

| Metryka | Zmienność (% średniej) | Część efektu w metryce | MDE 12 tyg. | MDE 16 tyg. | Tygodnie dla +15% |
|---|---:|---:|---:|---:|---:|
| przychód na godzinę, tydzień podpisania (z polecenia) | 18,70% | 0,15 | 33,6% (prawdziwego: 223%) | 28,2% (187%) | ponad 400 |
| jw. z korektą o godziny i napływ zapytań | 14,89% | 0,15 | 27,5% (183%) | 22,7% (151%) | ponad 400 |
| przychód z kontaktów tygodnia na godzinę | 20,54% | 1 | 36,9% | 31,0% | 62 |
| jw., wartość umowy do 95. percentyla (74 529 zł) | 19,58% | 1 | 35,2% | 29,5% | 56 |
| **jw. z korektą o godziny i napływ zapytań (proponowana)** | **17,21%** | 1 | **31,8%** | **26,3%** | **44** |
| umowy z kontaktów tygodnia na godzinę z korektą (bez złotówek) | 14,26% | 1 | 26,4% | 21,8% | 32 |

Zmienność z korektą liczymy z reszt leave-one-out na 51 tygodniach historii, więc nie jest zaniżona dopasowaniem do
tych samych tygodni. Korekta kosztuje 2 stopnie swobody i jest to uwzględnione w MDE. Zmienne korekty (godziny
doradców z grafiku, nowe zapytania w tym i poprzednim tygodniu) nie zależą od wariantu kolejki. Liczba umów waha się
najmniej, ale nie widzi złotówek. Kolejka EV celowo wymienia część umów na umowy wyższej wartości (docs/kolejka_ev.md:
EV ma mniej umów, a więcej wartości niż kolejka według p), więc liczba umów może przegapić efekt.

### T4. Pieniądze: co eksperyment wykryje i ile kosztują tygodnie kontrolne

Złotówki liczone od wartości wyjściowej 2026-Q2 (5 496,56 zł/h) i średnio 389,67 godziny doradców tygodniowo
(51 tygodni). Proponowana metryka. Efekt w % przeliczamy na zł przy założeniu, że rośnie proporcjonalnie.

| Tygodnie (pary) | MDE | MDE, zł/h | MDE, zł wartości umów tygodniowo | Koszt tygodni kontrolnych, jeśli model daje +15% |
|---:|---:|---:|---:|---:|
| 12 (6) | 31,8% | 1 748 | 681 263 | 1 927 642 zł |
| **16 (8)** | **26,3%** | **1 444** | **562 663** | **2 570 190 zł** |
| 20 (10) | 23,0% | 1 263 | 492 032 | 3 212 737 zł |
| 24 (12) | 20,7% | 1 138 | 443 281 | 3 855 285 zł |
| 30 (15) | 18,3% | 1 005 | 391 781 | 4 819 106 zł |
| 44 (22) | 14,9% | 819 | 319 122 | 7 068 022 zł |

+15% = 824 zł/h ≈ 321 274 zł wartości umów tygodniowo. Koszt tygodni kontrolnych = połowa tygodni × 321 274 zł,
czyli wartość umów, które nie powstaną, jeśli model naprawdę daje +15%. Jeśli model nie pomaga, ten koszt jest
zerowy. To wartość umów (czynsz × miesiące), a nie zysk: marży nie ma w danych.

### T5. Metryki pomocnicze

| Metryka | Dane | Wartość | Zmienność | MDE 12 / 16 tyg. |
|---|---|---:|---:|---:|
| Konwersja górnego decyla | 10 pełnych tygodni symulacji wstecz (2026-04-20 – 2026-06-28) | 26,3% (ok. 96 zapytań w decylu tygodniowo) | 20,2% | 36,3% / 30,5% (szacunek z 10 tygodni) |
| Adopcja (pozycje 1–20) | jw. | 7,5%; przy losowym wyborze 6,4% | — | warunek ważności, nie test efektu (reguła 4) |

### T6. Część losowa w kolejce z 2026-11-17 (pokaz)

| | Wartość |
|---|---:|
| Pozycje losowe | 22 z 440 (2 na każdego z 11 doradców) |
| Suma EV kolejek z pozycjami losowymi | 5 048 810 zł |
| Suma EV kolejek bez pozycji losowych (pierwsze 40 × liczba doradców według EV) | 5 100 086 zł |
| Koszt w EV | 51 276 zł (1,0%) |
| EV 22 zapytań wylosowanych | 98 947 zł |
| p_losowania w miastach | 0,0084 (Poznań) – 0,0114 (Wrocław) |

## Decyzje do potwierdzenia

- **Metryka główna** to przychód z kontaktów tygodnia, a nie przychód tygodnia podpisania z polecenia (wnioski 3–4).
  Miara z polecenia zostaje w raporcie eksperymentu jako informacja.
- **Limit 74 529 zł** wartości jednej umowy (95. percentyl umów z 2025-07-07 – 2026-06-28) jest stały w trakcie
  eksperymentu (`vars.limit_wartosci_umowy`). Przycina 5% największych umów, głównie ramowe B2B.
- **+15%** liczę względem średniej metryki (dla miary z polecenia 15% × 5 316,27 = 797 zł/h). W złotówkach w T4
  względem wartości wyjściowej 2026-Q2 (824 zł/h).
- **Losowanie w parach** zamiast dowolnej permutacji tygodni. Przy przypisaniu do tygodnia kontaktu pary nic nie
  kosztują, a równoważą warianty w czasie.
- **5% losowych pozycji** obowiązuje od teraz także poza eksperymentem. Symulacja wstecz używa tego samego losowania,
  więc adopcja przed wdrożeniem w [kolejka_panel.md](kolejka_panel.md) zmieniła się z 7,7% na 7,6%.
- **Wariant przełącza cały zespół naraz.** Losowanie osobne dla miast dało w symulacji A/A tylko niewielki zysk
  (odchylenie różnicy przy 12 tygodniach 11,3% → 10,0% dla przychodu z kontaktów) kosztem trudniejszej organizacji.
  Te liczby pochodzą z analizy eksploracyjnej (4 000 losowań okien z 51 tygodni), nie z modułu.
- **Interferencja:** zapytanie pominięte w tygodniu modelu bywa obsłużone w tygodniu kontrolnym i odwrotnie (wspólna
  pula). To zmniejsza różnicę wariantów, więc wynik jest raczej ostrożny.
- **Plan nie jest jeszcze wylosowany.** Data startu należy do kierownika. Losowanie:
  `zapisz_plan(wylosuj_plan(start=<poniedziałek>, tygodnie=16, ziarno=<liczba>))` tworzy
  `api/api/contexts_boundaries/leasing_bc/eksperyment_plan.yaml`, a zadanie 05:30 samo przełącza warianty.

## SQL i kod

```bash
pypyr baza                                                    # modele dbt: przychod_z_kontaktow, eksperyment_tydzien
cd api && poetry run python -m api.data_platform.eksperyment_kolejki   # T1–T6 -> wyniki/eksperyment_moc.json
poetry run pytest api/tests/test_eksperyment_kolejki.py
# start eksperymentu (data i ziarno do ustalenia):
cd api && poetry run python -c "from datetime import date; from api.contexts_boundaries.leasing_bc.eksperyment import *; \
  zapisz_plan(wylosuj_plan(date(RRRR, MM, DD), 16, ZIARNO))"
```

Kod:
- `api/api/data_platform/eksperyment_kolejki.py`: moc, MDE, tygodnie dla efektu, tłumienie, `analiza`;
- `api/api/contexts_boundaries/leasing_bc/eksperyment.py`: plan, wariant dnia, ziarno, 5%;
- `kolejka_dzienna.ranking_kolejki`: wariant i część losowa; `api/api/adapters/kolejka_historia.py`;
- modele dbt `models/kolejka/przychod_z_kontaktow.sql` i `models/panel/eksperyment_tydzien.sql`, testy
  `tests/singular/{limit_wartosci_nie_zwieksza_przychodu,kolejka_historia_piec_procent_losowych}.sql`.

**Q1. Tygodnie do mocy i porównania metryk** (`SQL_TYGODNIE`):

```sql
SELECT p.poczatek_okresu AS tydzien, p.godziny_doradcow, p.przychod_na_godzine_doradcy,
       k.nowe_zapytania + k.nowe_zapytania_poprzedni_tydzien AS nowe_zapytania_2tyg,
       k.przychod_z_kontaktow_na_godzine, k.przychod_z_kontaktow_bez_limitu_na_godzine,
       k.umowy_z_kontaktow_na_godzine, k.kompletny
FROM metryki.przychod_na_godzine_doradcy AS p
JOIN metryki.przychod_z_kontaktow AS k ON k.tydzien = p.poczatek_okresu
WHERE p.okres = 'tydzien' AND p.pelny_okres AND p.poczatek_okresu BETWEEN DATE '2025-07-07' AND DATE '2026-06-22';
```

**Q2. Opóźnienie kontakt → podpisanie (T2)** (`SQL_OPOZNIENIE`):

```sql
SELECT date_diff('week', cast(date_trunc('week', k.data_kolejki_kontaktu) AS date),
                 cast(date_trunc('week', w.data_podpisania) AS date)) AS opoznienie_tyg,
       count(*) AS umowy, sum(w.wartosc_umowy) AS wartosc
FROM metryki.wartosc_umowy AS w JOIN metryki.pierwszy_kontakt AS k USING (id_leada)
WHERE w.z_zapytania AND NOT k.kontakt_cc
  AND w.data_podpisania BETWEEN DATE '2025-07-07' AND DATE '2026-06-28'
GROUP BY 1 ORDER BY 1;
```

**Q3. MDE i tygodnie** (`moc_testu`, `mde`, `tygodnie_dla`): dwa warianty po n/2 tygodni, statystyka t
z df = n − 2 − k (k = zmienne korekty), parametr niecentralności = efekt / (σ × √(4/n)), moc =
P(|T| > t₀,₉₇₅), MDE = efekt, przy którym moc = 0,80. Zmienność z korektą: `cv_loo` (reszty leave-one-out
regresji metryki na godziny i nowe zapytania). Tłumienie: `tlumienie_podpisan` (20 000 planów w parach, wagi z Q2,
tygodnie przed startem w wariancie model).

**Q4. Limit wartości umowy** (95. percentyl, `vars.limit_wartosci_umowy`):

```sql
SELECT quantile_cont(wartosc_umowy, 0.95), count(*)
FROM metryki.wartosc_umowy
WHERE z_zapytania AND data_podpisania BETWEEN DATE '2025-07-07' AND DATE '2026-06-28';   -- 74 529 zł, 3 412 umów
```

**Q5. Wartość wyjściowa i godziny** (`SQL_WYJSCIOWA`; godziny = średnia `godziny_doradcow` z Q1):

```sql
SELECT przychod_na_godzine_doradcy FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'kwartal' AND poczatek_okresu = DATE '2026-04-01';
```

**Q6. Metryki pomocnicze (T5)** (`SQL_DECYL`):

```sql
SELECT tydzien, zapytania_decyl, konwersja_decyl, adopcja, adopcja_losowa FROM metryki.panel_tydzien
WHERE zrodlo_kolejki = 'symulacja_wstecz' AND dni_kolejki = 7 AND konwersja_decyl IS NOT NULL;
```

**Q7. Koszt części losowej (T6)** (`SQL_KOSZT_LOSOWYCH`): suma `ev_pln` pozycji w kolejkach dnia wobec sumy
`ev_pln` pierwszych (liczba pozycji miasta) zapytań rankingu EV miasta, z `kolejka_ranking` i `kolejka_historia`.

**Q8. Analiza po eksperymencie** (`analiza(tygodnie, "przychod_z_kontaktow_na_godzine")` na):

```sql
SELECT tydzien, wariant, przychod_z_kontaktow_na_godzine, godziny_doradcow, nowe_zapytania_2tyg,
       adopcja, konwersja_decyl, kompletny
FROM metryki.eksperyment_tydzien
WHERE wariant IN ('model', 'od_najnowszego') AND kompletny AND dni_kolejki = 7;
```
