# Awarie wind: co jest w historii Serwisownika (B4)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-16 (`pypyr baza`).
Źródła: `serwis_zgloszenia`, `serwis_notatki`, `serwis_czesci`, `serwis_windy`, `serwis_zloty_zbior` (wczytane przez
`api/api/adapters/serwisownik.py`) oraz tabela pochodna `zgloszenia_wind`.

## Wnioski

1. Z 24 736 zgłoszeń w Serwisowniku 16 880 dotyczy wind. Przy 15 771 z nich wiemy, której windy (15 760 ma numer windy,
   11 pochodzi z budynku B12, który ma jedną windę). Przy 1 109 zgłoszeniach (6,6%) znamy tylko budynek, bo poza B12
   każdy budynek ma od 2 do 6 wind.
2. Kategorii „awaria” nie da się użyć jako listy awarii wind. Ma ją 703 zgłoszeń wind (4,2%). Zgłoszenia o tej samej
   treści („Winda nie jeździ”, „Ktoś utknął w windzie”, „Winda zatrzymała się między piętrami”) trafiają podobnie często
   do kategorii „interwencja”, „usterka” i „inne”. Koordynator ręcznie sprawdził 400 zgłoszeń wind (złoty zbiór).
   Spośród 180 faktycznych awarii, które w nich znalazł, tylko 55 miało kategorię „awaria”.
3. Notatki konserwatorów to potwierdzają. Przy „awarii” zdarzają się zapisy „Test przycisku alarmowego, sprawny. Winda
   bez usterek.” i wymiana oświetlenia w windzie, która cały czas jeździła. Przy „interwencji” są uwolnienia uwięzionych
   osób i wymiana falownika, ale też smarowanie drzwi, sprzątanie kabiny i zgłoszenia nieuzasadnione. Część awarii ma
   przyczynę zewnętrzną (zalanie szybu, brak prądu, wandalizm), a takich zdarzeń czujniki windy nie zapowiedzą.
4. Dla modelu „awaria w ciągu 7 dni” cel trzeba więc zbudować z treści zgłoszenia i notatek (winda wyłączona albo
   stojąca, uwolnienie osób, wymiana podzespołu napędu, drzwi lub sterownika), a nie z kategorii. Taką definicję
   sprawdzamy na złotym zbiorze. To samo dotyczy cechy `windy_awarie_90d` w liście retencyjnej, która dziś liczy
   `typ_urzadzenia = 'winda'` i `kategoria = 'awaria'`.

## Definicje

**Zgłoszenie dotyczy windy** (tabela `zgloszenia_wind`, jeden wiersz = jedno zgłoszenie), gdy:

- `id_urzadzenia` wskazuje windę z `serwis_windy`. Wtedy `typ_urzadzenia` się nie liczy, bo bywa błędny: 481 takich
  zgłoszeń ma typ „inne”, „domofon” albo „węzeł” (R2), najczęściej z treścią „Konserwacja okresowa” (174) i
  „Przegląd dodatkowy” (54), ale są wśród nich też „Winda nie jeździ” (14) i „Ktoś utknął w windzie” (14);
  `SELECT tresc_zgloszenia, count(*) FROM zgloszenia_wind WHERE typ_urzadzenia <> 'winda' GROUP BY 1 ORDER BY 2 DESC`;
- albo `id_urzadzenia` jest puste, a `typ_urzadzenia = 'winda'`.

14 zgłoszeń z typem „winda” i numerem pompy albo węzła ciepła (treść np. „Zimne kaloryfery”) nie dotyczy wind.

**Ustalenie windy** (`ustalenie_windy`, `id_windy`):

| `ustalenie_windy` | Kiedy | `id_windy` |
|---|---|---|
| `id_urzadzenia` | `id_urzadzenia` jest windą | `id_urzadzenia` |
| `jedyna_winda_budynku` | `id_urzadzenia` puste, budynek ma w `serwis_windy` dokładnie jedną windę | ta winda |
| `nieustalona` | `id_urzadzenia` puste, budynek ma kilka wind albo żadnej | NULL |

Numer windy przy zgłoszeniu zawsze należy do budynku zgłoszenia (15 760 z 15 760, sprawdzone zapytaniem
`serwis_zgloszenia JOIN serwis_windy ON id_windy = id_urzadzenia WHERE w.id_budynku <> z.id_budynku` → 0).

**Wczytanie Serwisownika** (`adapters/serwisownik.py`, wywoływane przez `zbuduj_baze()`): wszystkie 6 plików z
`data/serwis/`; czas lokalny bez strefy jako TIMESTAMP z tą samą godziną (w Parquecie TIMESTAMP_NS, dane mają
dokładność do minuty); `koszt_netto` z tekstu `1 234,50` na DECIMAL(12,2). Tekst w innym formacie przerywa budowę
bazy, zamiast dać cicho NULL. Godziny 2025-10-26 02:00–03:00 baza nie rozstrzyga (9 zgłoszeń, R1).

## Tabele

### R1. Serwisownik ogółem

| zgloszenia | notatki | zgloszenia_z_notatka | pozycje_czesci | zgloszenia_z_czesciami | koszt_czesci_netto | pierwsze | ostatnie | zgl_w_podwojnej_godzinie |
|---|---|---|---|---|---|---|---|---|
| 24 736 | 28 885 | 21 200 | 2 758 | 2 267 | 1 734 396,90 | 2023-01-01 09:57 | 2026-09-30 20:06 | 9 |

### R2. Które zgłoszenia dotyczą wind (`typ_urzadzenia` × zawartość `id_urzadzenia`)

`id_to_winda` = numer windy z `serwis_windy`; `id_inne_urzadzenie` = numer pompy, węzła itp.; `dotyczy_windy` według
definicji powyżej. Ostatni wiersz (pusty typ) to suma.

| typ_urzadzenia | zgloszenia | id_to_winda | id_inne_urzadzenie | id_puste | dotyczy_windy |
|---|---|---|---|---|---|
| winda | 16 413 | 15 279 | 14 | 1 120 | 16 399 |
| inne | 3 641 | 175 | 20 | 3 446 | 175 |
| domofon | 2 484 | 165 | 13 | 2 306 | 165 |
| węzeł | 1 114 | 141 | 862 | 111 | 141 |
| pompa | 1 084 | 0 | 1 042 | 42 | 0 |
|  | 24 736 | 15 760 | 1 951 | 7 025 | 16 880 |

### R3. Ustalenie windy w zgłoszeniach wind

| ustalenie_windy | zgloszenia | proc | budynki | liczba_wind_w_budynku |
|---|---|---|---|---|
| id_urzadzenia | 15 760 | 93,4 | 38 | 1, 2, 3, 4, 5, 6 |
| nieustalona | 1 109 | 6,6 | 37 | 2, 3, 4, 5, 6 |
| jedyna_winda_budynku | 11 | 0,1 | 1 | 1 |

Budynki według liczby wind (`serwis_windy`):

| liczba_wind | budynki | id_budynkow |
|---|---|---|
| 1 | 1 | B12 |
| 2 | 1 | B36 |
| 3 | 10 | B09, B10, B15, B20, B22, B24, B27, B28, B34, B35 |
| 4 | 24 | B01, B02, B03, B04, B05, B06, B07, B08, B11, B13, B14, B16, B17, B18, B19, B21, B23, B25, B26, B29, B30, B31, B32, B33 |
| 5 | 1 | B37 |
| 6 | 1 | B38 |

### R4. Kontrola `typ_urzadzenia` przy pustym `id_urzadzenia`

Słownik treści zbudowany z wierszy, w których numer urządzenia jest znany: treść „windowa” pojawia się tylko przy
windach, „inna” tylko przy innych urządzeniach albo nigdy z numerem. Według tego słownika definicja włącza 54 zgłoszenia
o treści niewindowej (np. „Cieknie z sufitu” z typem „winda”) i pomija 32 zgłoszenia o treści windowej z innym typem.
Razem (54 + 32) / 16 880 = 0,5% zgłoszeń wind. Zostawiamy prostą definicję i nie poprawiamy typu na
podstawie treści (do decyzji).

| typ_urzadzenia | zgl_bez_id | tresc_windowa | tresc_inna | tresc_mieszana |
|---|---|---|---|---|
| winda | 1 120 | 1 066 | 54 | 0 |
| inny typ | 5 905 | 32 | 5 873 | 0 |

### R5. Kategorie zgłoszeń wind

`proc_z_czesciami` = zgłoszenia z co najmniej jedną pozycją w `serwis_czesci`; `koszt_czesci_netto` w PLN;
`mediana_godz_do_zamkniecia` = `zamknieto − utworzono` (stan na eksport; zgłoszeń wszystkich urządzeń ze statusem `w_realizacji` jest 26:
`SELECT count(*) FROM serwis_zgloszenia WHERE status = 'w_realizacji'`).

| kategoria | zgloszenia | proc | proc_pilnych | proc_z_notatka | proc_z_czesciami | koszt_czesci_netto | mediana_godz_do_zamkniecia |
|---|---|---|---|---|---|---|---|
| konserwacja | 6 136 | 36,4 | 0,0 | 92,2 | 14,7 | 235 972,30 | 1,1 |
| usterka | 3 305 | 19,6 | 11,1 | 75,1 | 5,7 | 209 160,31 | 34,3 |
| przegląd | 2 939 | 17,4 | 0,0 | 92,9 | 12,2 | 99 626,11 | 1,6 |
| inne | 2 136 | 12,7 | 18,4 | 77,8 | 9,4 | 302 101,36 | 27,8 |
| interwencja | 1 661 | 9,8 | 34,5 | 79,3 | 17,5 | 435 487,55 | 21,9 |
| awaria | 703 | 4,2 | 72,1 | 90,5 | 45,9 | 448 851,61 | 15,6 |
| RAZEM | 16 880 | 100,0 | 10,9 | 85,8 | 13,4 | 1 731 199,24 | 1,9 |

### R6. Kategoria „awaria” według roku

`awaria_windy` = zgłoszenia z `zgloszenia_wind`; `awaria_winda_ustalona` = z ustaloną windą; `awaria_typ_winda` = sam
filtr `typ_urzadzenia = 'winda'` (tak liczy dziś cecha `windy_awarie_90d` listy retencyjnej). Rok 2026 to dziewięć
miesięcy.

| rok | awaria_wszystkie_urzadzenia | awaria_windy | awaria_winda_ustalona | awaria_typ_winda |
|---|---|---|---|---|
| 2023 | 278 | 176 | 170 | 173 |
| 2024 | 289 | 175 | 169 | 170 |
| 2025 | 337 | 203 | 199 | 198 |
| 2026 | 245 | 149 | 145 | 146 |
| RAZEM | 1 149 | 703 | 683 | 687 |

### R7. Treść zgłoszenia windy × kategoria

Numer piętra zastąpiony przez N. Zgłoszenia o zatrzymaniu windy rozkładają się na cztery kategorie. W „awarii” jest też
62 zgłoszeń o treściach zaczynających się od „Awaria …” (przycisk alarmowy, domofon, oświetlenie, przycisk na piętrze),
których nie ma w żadnej innej kategorii.

| tresc_zgloszenia | awaria | interwencja | usterka | inne | przegląd | konserwacja |
|---|---|---|---|---|---|---|
| Winda nie przyjeżdża na wezwanie | 90 | 82 | 49 | 59 | 0 | 0 |
| Winda wyłączona | 89 | 94 | 53 | 50 | 0 | 0 |
| Winda nie jeździ | 85 | 103 | 64 | 64 | 0 | 0 |
| Winda zatrzymała się między piętrami | 77 | 87 | 71 | 62 | 0 | 0 |
| Ktoś utknął w windzie | 77 | 81 | 62 | 64 | 0 | 0 |
| Winda stoi na N. piętrze | 76 | 80 | 53 | 80 | 0 | 0 |
| Winda szarpie i hałasuje | 73 | 90 | 57 | 67 | 0 | 0 |
| Drzwi windy się nie zamykają | 73 | 89 | 59 | 56 | 0 | 0 |
| Awaria — nie działa przycisk alarmowy (test) | 19 | 0 | 0 | 0 | 0 | 0 |
| Awaria domofonu w windzie | 17 | 0 | 0 | 0 | 0 | 0 |
| Awaria oświetlenia kabiny | 13 | 0 | 0 | 0 | 0 | 0 |
| Awaria przycisku na piętrze N | 13 | 0 | 0 | 0 | 0 | 0 |
| Cieknie z sufitu | 1 | 0 | 6 | 5 | 0 | 0 |
| Kontrola po naprawie | 0 | 220 | 0 | 151 | 447 | 0 |
| Dziwne dźwięki w szybie windy | 0 | 129 | 456 | 263 | 0 | 0 |
| Nie świeci światło w windzie | 0 | 129 | 506 | 237 | 0 | 0 |
| Wyświetlacz piętra w windzie nie działa | 0 | 129 | 455 | 234 | 0 | 0 |
| Drzwi windy skrzypią | 0 | 117 | 438 | 250 | 0 | 0 |
| Przycisk w windzie nie działa | 0 | 116 | 467 | 250 | 0 | 0 |
| Brudna kabina windy | 0 | 110 | 486 | 230 | 0 | 0 |
| Nie świeci światło na klatce | 0 | 2 | 3 | 3 | 0 | 0 |
| Zepsuty zamek w drzwiach wejściowych | 0 | 2 | 5 | 3 | 0 | 0 |
| Zapchany pion kanalizacyjny | 0 | 1 | 2 | 0 | 0 | 0 |
| Badanie UDT | 0 | 0 | 0 | 0 | 494 | 0 |
| Brama garażowa nie otwiera się | 0 | 0 | 5 | 4 | 0 | 0 |
| Konserwacja okresowa | 0 | 0 | 0 | 0 | 0 | 6 136 |
| Nie działa domofon | 0 | 0 | 7 | 4 | 0 | 0 |
| Przegląd dodatkowy | 0 | 0 | 0 | 0 | 1 998 | 0 |
| Za niska temperatura w mieszkaniu | 0 | 0 | 1 | 0 | 0 | 0 |

### R8. Złoty zbiór koordynatora (`serwis_zloty_zbior.czy_awaria`) według kategorii

Wszystkie 400 zgłoszeń złotego zbioru dotyczy wind. Zbiór nie jest próbą proporcjonalną: „awaria” to w nim 57 z 400
zgłoszeń, a wśród wszystkich zgłoszeń wind 703 z 16 880 (R5).

| kategoria | w_zlotym_zbiorze | czy_awaria_tak | czy_awaria_nie | proc_awarii |
|---|---|---|---|---|
| konserwacja | 93 | 0 | 93 | 0,0 |
| interwencja | 76 | 60 | 16 | 78,9 |
| usterka | 66 | 31 | 35 | 47,0 |
| inne | 57 | 34 | 23 | 59,6 |
| awaria | 57 | 55 | 2 | 96,5 |
| przegląd | 51 | 0 | 51 | 0,0 |
| RAZEM | 400 | 180 | 220 | 45,0 |

### R8b. Ile faktycznych awarii może kryć się w każdej kategorii (szacunek)

**Założenie:** złoty zbiór jest losowy w obrębie każdej kategorii. Jak go wybrano, tego w danych nie ma. Szacunek =
liczba zgłoszeń kategorii × odsetek awarii w złotym zbiorze tej kategorii. Przy tym założeniu kategoria „awaria”
obejmuje ok. 14% faktycznych awarii wind.

| kategoria | zgloszenia | w_zlotym_zbiorze | proc_awarii_zz | szac_awarii | proc_szac_awarii |
|---|---|---|---|---|---|
| usterka | 3 305 | 66 | 47,0 | 1 552 | 32,2 |
| interwencja | 1 661 | 76 | 78,9 | 1 311 | 27,2 |
| inne | 2 136 | 57 | 59,6 | 1 274 | 26,5 |
| awaria | 703 | 57 | 96,5 | 678 | 14,1 |
| konserwacja | 6 136 | 93 | 0,0 | 0 | 0,0 |
| przegląd | 2 939 | 51 | 0,0 | 0 | 0,0 |
| RAZEM | 16 880 | 400 |  | 4 816 | 100,0 |

### R9. 30 notatek ze zgłoszeń „awaria” obok 30 ze zgłoszeń „interwencja”

Pula: notatki zgłoszeń wind z daną kategorią. Losowanie jest powtarzalne: notatki ułożone według
`md5(id_notatki || ':b4_historia_awarii')`, pierwsze 30 z każdej kategorii. Wiersz to para notatek bez związku
między sobą. W kolumnie „zgłoszenie” są numer, treść zgłoszenia i autor notatki (KOORD = koordynator, K01–K19 =
konserwatorzy). Jedno zgłoszenie może dać dwie notatki (Z016194 w wierszach 5 i 29).

| kategoria | notatki | zgloszenia |
|---|---|---|
| awaria | 897 | 636 |
| interwencja | 1 745 | 1 317 |

| # | awaria: zgłoszenie | awaria: notatka | interwencja: zgłoszenie | interwencja: notatka |
|---|---|---|---|---|
| 1 | Z009033 „Winda stoi na 5. piętrze” (K07) | Przyjazd 19:11, uwolniono 3 os. Uszkodzony falownik, napęd nie rusza. Wymiana modułu, winda stała do naprawy. | Z000314 „Dziwne dźwięki w szybie windy” (K02) | Skrzypienie drzwi — smarowanie, OK. |
| 2 | Z005239 „Winda szarpie i hałasuje” (K18) | Nadużycie: drzwi blokowane wózkiem, uszkodzony mechanizm, winda wyłączona. | Z011713 „Dziwne dźwięki w szybie windy” (K09) | Regulacja domykacza drzwi szybowych na 3.<br>p. |
| 3 | Z000084 „Awaria oświetlenia kabiny” (K18) | Test przycisku alarmowego, sprawny. Winda bez usterek. | Z003939 „Dziwne dźwięki w szybie windy” (K14) | Lustro w kabinie poluzowane — dokręcono. |
| 4 | Z011444 „Winda nie przyjeżdża na wezwanie” (K05) | Przyjazd 18:50, winda stoi na 1. piętrze. Winda wyłączona z ruchu, naprawa na miejscu, test OK. | Z004020 „Zepsuty zamek w drzwiach wejściowych” (KOORD) | Wymiana żarówek na klatce. |
| 5 | Z018019 „Awaria domofonu w windzie” (K10) | Test przycisku alarmowego, sprawny. Winda bez usterek. | Z016194 „Winda nie przyjeżdża na wezwanie” (K18) | Uruchomiono, jazdy próbne OK. |
| 6 | Z005198 „Ktoś utknął w windzie” (K10) | Naprawa zakończona, winda w ruchu. | Z007592 „Ktoś utknął w windzie” (KOORD) | Zgłoszenie od lokatora, serwis już jedzie. |
| 7 | Z015333 „Ktoś utknął w windzie” (K13) | Dojazd 19:04, zabezpieczenie szybu. Liny nośne do wymiany, drgania kabiny, winda wyłączona do czasu wymiany lin. | Z002357 „Drzwi windy skrzypią” (K17) | Czyszczenie kabiny i progów. |
| 8 | Z008576 „Winda zatrzymała się między piętrami” (K14) | Na miejscu o 23:01.<br>Uszkodzony operator drzwi (op. drzwi), drzwi szyowe nie zamykają. Winda wyłączona do nprawy. | Z011372 „Kontrola po naprawie” (K01) | Brak awarii — winda zablokowana przez mieszkańca przy przeprowadzce, odblokowano. |
| 9 | Z021691 „Awaria przycisku na piętrze 7” (K09) | Wymiana oświetlenia kabiny (świetlówka), winda w ruchu cały czas. | Z008120 „Winda stoi na 5. piętrze” (K17) | Nadużycie: drzwi blokowane wózkiem, uszkodzony mechanizm, winda wyłączona. |
| 10 | Z009605 „Awaria oświetlenia kabiny” (K18) | Test przycisku alarmowego, sprawny. Winda bez usterek. | Z008489 „Drzwi windy skrzypią” (K03) | Regulacja domykacza drzwi szybowych na 4. p. |
| 11 | Z016870 „Winda szarpie i hałasuje” (K13) | Przyjazd 19:21, winda stoi na 0. piętrze. Wymiana kurtyny świetlnej, czyszczenie progu, po naprawie jazdy próbne OK. | Z008738 „Ktoś utknął w windzie” (K11) | Przyjazd 01:37, uwolniono 3 os. Reset falownika nie pomógł, wymiana enkodera i wentylatora silnika. |
| 12 | Z016183 „Winda nie jeździ” (K16) | Zalanie szybu (awaria instalacji wodnej), winda wyłączona do osuszenia. | Z017039 „Winda nie jeździ” (K15) | Przyjazd 15:03, uwolniono 2 os. Regulacja hamulca, wymiana okładzin, smarowanie prowadnic, poziomowanie OK. |
| 13 | Z023323 „Winda szarpie i hałasuje” (K06) | Reset falownika nie pomógł, wymiana enkodera i wentylatora silnika. | Z014599 „Nie świeci światło w windzie” (K16) | Zgłoszenie 'awaria' nieuzasadnione — winda sprawna, lokator nie domknął drzwi szybowych. |
| 14 | Z009384 „Awaria — nie działa przycisk alarmowy (test)” (K04) | Awaria przycisku na 3. piętrze — wymiana przycisku, winda jeździła normalnie. | Z014185 „Winda nie przyjeżdża na wezwanie” (K15) | Na miejscu o 09:44.<br>Prowadnice i hamulec: duże wibracje, kabina szarpie. Zablokowana przez ogr. prędk. |
| 15 | Z017917 „Winda zatrzymała się między piętrami” (K11) | Uszkodzony operator drzwi (op. drzwi), drzwi szybowe nie zamykają. Winda wyłączona do naprawy. | Z016964 „Winda nie jeździ” (K14) | Uszkodzony operator drzwi (op. drzwi), drzwi szybowe nie zamykają. Winda wyłączona do naprawy. |
| 16 | Z021815 „Winda nie przyjeżdża na wezwanie” (K02) | Po naprawie test OK, przekazano do eksploatacji. | Z023680 „Brudna kabina windy” (K17) | Lustro w kabinie poluzowane — dokręcono. |
| 17 | Z005738 „Winda wyłączona” (K12) | Awaria drzwi kabinowych, op. drzwi nie domyka, winda stała. Wym. rolek i regulacja. | Z009627 „Nie świeci światło w windzie” (K13) | Wymiana wyświetlacza piętra w kabinie. |
| 18 | Z007631 „Winda nie jeździ” (K09) | Uruchomiono, jazdy próbne OK. | Z019899 „Ktoś utknął w windzie” (K12) | Uruchomiono, jazdy próbne OK. |
| 19 | Z023573 „Winda wyłączona” (K02) | Uruchomiono, jazdy próbne OK. | Z016726 „Ktoś utknął w windzie” (K03) | Dojazd 17:53, zabezpieczenie szybu. Po powrocie prądu reset ster. i jazdy próbne, praca normalna. |
| 20 | Z006898 „Ktoś utknął w windzie” (K02) | Po naprawie test OK, przekazano do eksploatacji. | Z022753 „Drzwi windy się nie zamykają” (K06) | Po naprawie test OK, przekazano do eksploatacji. |
| 21 | Z009860 „Winda nie jeździ” (K17) | Naprawa zakończona, winda w ruchu. | Z003164 „Winda nie jeździ” (K10) | Naprawa zakończona, winda w ruchu. |
| 22 | Z021170 „Winda stoi na 5. piętrze” (K17) | Naprawa zakończona, winda w ruchu. | Z021738 „Winda szarpie i hałasuje” (KOORD) | Zgłoszenie od lokatora, serwis już jedzie. |
| 23 | Z003717 „Winda nie jeździ” (K01) | Drzwi kabiny blokują się w połowie, ZK nie łapie.<br>Naprawa operatora drzwi, test OK. | Z006891 „Winda nie jeździ” (K14) | Wym. rolek i paska napędu drzwi, regulacja ZK, winda uruchomiona. |
| 24 | Z018253 „Winda stoi na 3. piętrze” (K08) | Na miejscu o 07:08. Akt wandalizmu — zniszczona kaseta wezwań, zwarcie, winda stała całą noc. | Z009054 „Winda szarpie i hałasuje” (K06) | Na miejscu o 19:20. Uszkodzony falownik, napęd nie rusza. Wymiana modułu, winda stała do naprawy. |
| 25 | Z000870 „Winda nie jeździ” (K05) | Awaria drzwi — kurtyna świetlna uszkodzona, drzwi się nie zamykają, winda stoi. | Z001947 „Winda zatrzymała się między piętrami” (K12) | Przyjazd 18:23, widna stoi an 1. piętrze. Sterownik zawiesza się, winda staje między piętrami. Uwolniono 2 os. Wymiana modułu ster. |
| 26 | Z023373 „Winda zatrzymała się między piętrami” (K01) | Zanik zasilania w budynku po burzy — wszystkie windy stały. Po powrocie prądu reset i jazdy próbne. | Z001158 „Dziwne dźwięki w szybie windy” (K14) | Zgłoszenie hałasu w szybie — kontrola, nic nie stwierdzono. |
| 27 | Z022743 „Winda nie przyjeżdża na wezwanie” (K15) | Awaria hamulca — winda nie zatrzymuje się równo, błąd poziomowania 3 cm. Wyłączona. | Z022220 „Nie świeci światło w windzie” (K08) | Czyszczenie kabiny i progów. |
| 28 | Z010599 „Winda nie przyjeżdża na wezwanie” (K04) | Wymiana karty I/O i aktualizacja konfiguracji, reset ster., test OK. | Z009192 „Ktoś utknął w windzie” (K19) | Dojazd 19:51, zabezpieczenie szybu. Wym. rolek i paska napędu drzwi, regulacja ZK, winda uruchomiona. |
| 29 | Z015447 „Winda szarpie i hałasuje” (K18) | Dojazd 17:29, zabezpieczenie szybu.<br>Wym. rolek i paska napędu drzwi, regulacja ZK, winda uruchomiona. | Z016194 „Winda nie przyjeżdża na wezwanie” (K18) | Zalanie szybu (awaria instalacji wodnej), winda wyłączona do osuszenia. |
| 30 | Z016725 „Winda stoi na 3. piętrze” (K11) | Uruchomiono, jazdy próbne OK. | Z019159 „Winda szarpie i hałasuje” (K06) | Uruchomiono, jazdy próbne OK. |

Co widać w próbce:

- **„awaria”**: większość notatek opisuje postój windy i naprawę (falownik, operator drzwi, liny, hamulec, uwolnienie
  osób; wiersze 1, 4, 7, 8, 15, 17, 25, 27). Są jednak notatki bez awarii: „Test przycisku alarmowego, sprawny. Winda
  bez usterek.” (3, 5, 10), „winda w ruchu cały czas” (9), „winda jeździła normalnie” (14). Są też przyczyny
  zewnętrzne: nadużycie (2), zalanie szybu (12), wandalizm (24), zanik zasilania (26).
- **„interwencja”**: obok prawdziwych postojów (11, 12, 14, 15, 24, 25: uwolnienie osób, falownik, sterownik, hamulec)
  są drobne prace i fałszywe alarmy: smarowanie drzwi (1), dokręcenie lustra (3, 16), czyszczenie kabiny (7, 27),
  „Zgłoszenie 'awaria' nieuzasadnione” (13), „nic nie stwierdzono” (26), wymiana żarówek na klatce (4).
- Część notatek nie mówi nic o przyczynie („Uruchomiono, jazdy próbne OK.”, „Naprawa zakończona, winda w ruchu.”,
  „Zgłoszenie od lokatora, serwis już jedzie.”). Etykietę trzeba więc nadawać zgłoszeniu na podstawie wszystkich jego
  notatek, a nie pojedynczej notatce.
- W notatkach są literówki i skróty („szyowe”, „nprawy”, „widna stoi an”, „op. drzwi”, „ZK”, „ster.”), więc proste
  szukanie słów kluczowych trzeba sprawdzić na złotym zbiorze.

## SQL i kod

Powtórzenie (z katalogu głównego repozytorium):

```bash
poetry run pypyr baza                                    # serwis_* przez adapters/serwisownik.py, tabela zgloszenia_wind
cd api && poetry run python -m api.ai.failure_model.evals.historia_awarii   # tabele R1–R9 (Markdown)
```

Kod: `api/api/adapters/serwisownik.py` (wczytanie Serwisownika), `api/api/ai/features/windy/zgloszenia_wind.sql` i `zgloszenia_wind.py` (tabela `zgloszenia_wind`), `api/api/ai/failure_model/evals/historia_awarii.py` (zapytania R1–R9). Testy: `api/tests/test_serwisownik.py`, `test_zgloszenia_wind.py`, `test_historia_awarii.py`, `test_duckdb_baza.py`.

### Wczytanie Serwisownika (`adapters/serwisownik.py`)

Dla każdej tabeli `serwis_*` (zgłoszenia, notatki, części, windy, harmonogram, złoty zbiór) adapter wykonuje `CREATE OR REPLACE TABLE <nazwa> AS SELECT * REPLACE (...) FROM read_parquet(...)`, gdzie kolumny czasu idą przez `CAST(... AS TIMESTAMP)` (godzina lokalna bez zmian), a koszt części tak:

```sql
-- przed wczytaniem: ValueError, jeśli którykolwiek niepusty tekst nie pasuje do wzorca ^-?[0-9]{1,3}( [0-9]{3})*,[0-9]{2}$
CAST(replace(replace(koszt_netto, ' ', ''), ',', '.') AS DECIMAL(12, 2)) AS koszt_netto
```

### Tabela `zgloszenia_wind`

```sql
-- Zgłoszenia Serwisownika dotyczące wind, z ustaloną windą (opis i liczby: docs/b4_historia_awarii.md).
--
-- Zgłoszenie dotyczy windy, gdy:
--   a) id_urzadzenia jest windą z serwis_windy (wtedy typ_urzadzenia nie ma znaczenia: bywa błędny, np. „domofon”
--      przy konserwacji windy), albo
--   b) id_urzadzenia jest puste, a typ_urzadzenia = 'winda'.
-- Zgłoszenie z typ_urzadzenia = 'winda', ale id_urzadzenia innego urządzenia (pompa / węzeł ciepła), nie dotyczy windy.
--
-- id_windy / ustalenie_windy:
--   'id_urzadzenia'        — winda z id_urzadzenia;
--   'jedyna_winda_budynku' — id_urzadzenia puste, budynek ma w serwis_windy dokładnie jedną windę;
--   'nieustalona'          — id_urzadzenia puste, budynek ma kilka wind albo żadnej (id_windy = NULL).
-- status i zamknieto to stan na dzień eksportu (nie są cechami na moment predykcji).
WITH windy_budynku AS (
    SELECT id_budynku, count(*) AS liczba_wind, min(id_windy) AS pierwsza_winda
    FROM serwis_windy
    GROUP BY id_budynku
),
z AS (
    SELECT z.*, w.id_windy AS winda_z_id
    FROM serwis_zgloszenia AS z
    LEFT JOIN serwis_windy AS w ON w.id_windy = z.id_urzadzenia
    WHERE w.id_windy IS NOT NULL
       OR (z.id_urzadzenia IS NULL AND z.typ_urzadzenia = 'winda')
)
SELECT
    z.id_zgloszenia,
    z.utworzono,
    z.id_budynku,
    CASE
        WHEN z.winda_z_id IS NOT NULL THEN z.winda_z_id
        WHEN wb.liczba_wind = 1 THEN wb.pierwsza_winda
    END AS id_windy,
    CASE
        WHEN z.winda_z_id IS NOT NULL THEN 'id_urzadzenia'
        WHEN wb.liczba_wind = 1 THEN 'jedyna_winda_budynku'
        ELSE 'nieustalona'
    END AS ustalenie_windy,
    coalesce(wb.liczba_wind, 0) AS liczba_wind_budynku,
    z.id_urzadzenia,
    z.typ_urzadzenia,
    z.zrodlo,
    z.kategoria,
    z.priorytet,
    z.tresc_zgloszenia,
    z.firma_serwisowa,
    z.status,
    z.zamknieto
FROM z
LEFT JOIN windy_budynku AS wb USING (id_budynku)
ORDER BY z.utworzono, z.id_zgloszenia
```

### R1

```sql
SELECT
    (SELECT count(*) FROM serwis_zgloszenia) AS zgloszenia,
    (SELECT count(*) FROM serwis_notatki) AS notatki,
    (SELECT count(DISTINCT id_zgloszenia) FROM serwis_notatki) AS zgloszenia_z_notatka,
    (SELECT count(*) FROM serwis_czesci) AS pozycje_czesci,
    (SELECT count(DISTINCT id_zgloszenia) FROM serwis_czesci) AS zgloszenia_z_czesciami,
    (SELECT sum(koszt_netto) FROM serwis_czesci) AS koszt_czesci_netto,
    (SELECT strftime(min(utworzono), '%Y-%m-%d %H:%M') FROM serwis_zgloszenia) AS pierwsze,
    (SELECT strftime(max(utworzono), '%Y-%m-%d %H:%M') FROM serwis_zgloszenia) AS ostatnie,
    (SELECT count(*) FROM serwis_zgloszenia
      WHERE utworzono >= '2025-10-26 02:00' AND utworzono < '2025-10-26 03:00') AS zgl_w_podwojnej_godzinie
```

### R2

```sql
SELECT
    z.typ_urzadzenia,
    count(*) AS zgloszenia,
    count(*) FILTER (w.id_windy IS NOT NULL) AS id_to_winda,
    count(*) FILTER (z.id_urzadzenia IS NOT NULL AND w.id_windy IS NULL) AS id_inne_urzadzenie,
    count(*) FILTER (z.id_urzadzenia IS NULL) AS id_puste,
    count(*) FILTER (w.id_windy IS NOT NULL OR (z.id_urzadzenia IS NULL AND z.typ_urzadzenia = 'winda'))
        AS dotyczy_windy
FROM serwis_zgloszenia AS z
LEFT JOIN serwis_windy AS w ON w.id_windy = z.id_urzadzenia
GROUP BY ROLLUP (z.typ_urzadzenia)
ORDER BY z.typ_urzadzenia IS NULL, zgloszenia DESC
```

### R3

```sql
SELECT
    ustalenie_windy,
    count(*) AS zgloszenia,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS proc,
    count(DISTINCT id_budynku) AS budynki,
    list(DISTINCT liczba_wind_budynku ORDER BY liczba_wind_budynku) AS liczba_wind_w_budynku
FROM zgloszenia_wind
GROUP BY ustalenie_windy
ORDER BY zgloszenia DESC
```

### R3b

```sql
SELECT liczba_wind, count(*) AS budynki, list(id_budynku ORDER BY id_budynku) AS id_budynkow
FROM (SELECT id_budynku, count(*) AS liczba_wind FROM serwis_windy GROUP BY id_budynku)
GROUP BY liczba_wind
ORDER BY liczba_wind
```

### R4

```sql
WITH slownik AS (
    SELECT
        z.tresc_zgloszenia,
        CASE
            WHEN count(*) FILTER (w.id_windy IS NOT NULL) > 0
             AND count(*) FILTER (z.id_urzadzenia IS NOT NULL AND w.id_windy IS NULL) = 0 THEN 'windowa'
            WHEN count(*) FILTER (w.id_windy IS NOT NULL) = 0 THEN 'inna'
            ELSE 'mieszana'
        END AS rodzaj_tresci
    FROM serwis_zgloszenia AS z
    LEFT JOIN serwis_windy AS w ON w.id_windy = z.id_urzadzenia
    GROUP BY z.tresc_zgloszenia
)
SELECT
    CASE WHEN z.typ_urzadzenia = 'winda' THEN 'winda' ELSE 'inny typ' END AS typ_urzadzenia,
    count(*) AS zgl_bez_id,
    count(*) FILTER (s.rodzaj_tresci = 'windowa') AS tresc_windowa,
    count(*) FILTER (s.rodzaj_tresci = 'inna') AS tresc_inna,
    count(*) FILTER (s.rodzaj_tresci = 'mieszana') AS tresc_mieszana
FROM serwis_zgloszenia AS z
JOIN slownik AS s USING (tresc_zgloszenia)
WHERE z.id_urzadzenia IS NULL
GROUP BY ALL
ORDER BY 1 DESC
```

### R5

```sql
WITH cz AS (
    SELECT id_zgloszenia, sum(koszt_netto) AS koszt FROM serwis_czesci GROUP BY id_zgloszenia
),
nt AS (
    SELECT id_zgloszenia, count(*) AS notatki FROM serwis_notatki GROUP BY id_zgloszenia
)
SELECT
    coalesce(z.kategoria, 'RAZEM') AS kategoria,
    count(*) AS zgloszenia,
    round(100.0 * count(*) / (SELECT count(*) FROM zgloszenia_wind), 1) AS proc,
    round(100.0 * count(*) FILTER (z.priorytet = 'pilny') / count(*), 1) AS proc_pilnych,
    round(100.0 * count(nt.id_zgloszenia) / count(*), 1) AS proc_z_notatka,
    round(100.0 * count(cz.id_zgloszenia) / count(*), 1) AS proc_z_czesciami,
    sum(cz.koszt) AS koszt_czesci_netto,
    round(median(date_diff('minute', z.utworzono, z.zamknieto)) / 60.0, 1) AS mediana_godz_do_zamkniecia
FROM zgloszenia_wind AS z
LEFT JOIN cz USING (id_zgloszenia)
LEFT JOIN nt USING (id_zgloszenia)
GROUP BY ROLLUP (z.kategoria)
ORDER BY z.kategoria IS NULL, zgloszenia DESC
```

### R6

```sql
SELECT
    coalesce(CAST(year(utworzono) AS VARCHAR), 'RAZEM') AS rok,
    count(*) FILTER (kategoria = 'awaria') AS awaria_wszystkie_urzadzenia,
    count(*) FILTER (kategoria = 'awaria' AND id_zgloszenia IN (SELECT id_zgloszenia FROM zgloszenia_wind))
        AS awaria_windy,
    count(*) FILTER (kategoria = 'awaria' AND id_zgloszenia IN (
        SELECT id_zgloszenia FROM zgloszenia_wind WHERE ustalenie_windy <> 'nieustalona')) AS awaria_winda_ustalona,
    count(*) FILTER (kategoria = 'awaria' AND typ_urzadzenia = 'winda') AS awaria_typ_winda
FROM serwis_zgloszenia
GROUP BY ROLLUP (year(utworzono))
ORDER BY year(utworzono) IS NULL, year(utworzono)
```

### R7

```sql
PIVOT (
    SELECT regexp_replace(tresc_zgloszenia, '[0-9]+', 'N', 'g') AS tresc_zgloszenia, kategoria
    FROM zgloszenia_wind
)
ON kategoria IN ('awaria', 'interwencja', 'usterka', 'inne', 'przegląd', 'konserwacja')
USING count(*)
GROUP BY tresc_zgloszenia
ORDER BY awaria DESC, interwencja DESC, tresc_zgloszenia
```

### R8

```sql
SELECT
    coalesce(z.kategoria, 'RAZEM') AS kategoria,
    count(*) AS w_zlotym_zbiorze,
    count(*) FILTER (zz.czy_awaria) AS czy_awaria_tak,
    count(*) FILTER (NOT zz.czy_awaria) AS czy_awaria_nie,
    round(100.0 * count(*) FILTER (zz.czy_awaria) / count(*), 1) AS proc_awarii
FROM zgloszenia_wind AS z
JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
GROUP BY ROLLUP (z.kategoria)
ORDER BY z.kategoria IS NULL, w_zlotym_zbiorze DESC
```

### R8b

```sql
WITH zz AS (
    SELECT z.kategoria, count(*) AS w_zlotym_zbiorze, avg(CAST(zz.czy_awaria AS INTEGER)) AS odsetek_awarii
    FROM zgloszenia_wind AS z
    JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
    GROUP BY z.kategoria
),
wszystkie AS (
    SELECT kategoria, count(*) AS zgloszenia FROM zgloszenia_wind GROUP BY kategoria
),
szac AS (
    SELECT w.kategoria, w.zgloszenia, zz.w_zlotym_zbiorze, zz.odsetek_awarii, w.zgloszenia * zz.odsetek_awarii AS awarie
    FROM wszystkie AS w
    JOIN zz USING (kategoria)
)
SELECT kategoria, zgloszenia, w_zlotym_zbiorze, round(100 * odsetek_awarii, 1) AS proc_awarii_zz,
    CAST(round(awarie) AS BIGINT) AS szac_awarii, round(100 * awarie / sum(awarie) OVER (), 1) AS proc_szac_awarii
FROM szac
UNION ALL
SELECT 'RAZEM', sum(zgloszenia), sum(w_zlotym_zbiorze), NULL, CAST(round(sum(awarie)) AS BIGINT), 100.0
FROM szac
ORDER BY kategoria = 'RAZEM', szac_awarii DESC
```

### R9 — pula i losowanie notatek

```sql
SELECT z.kategoria, count(*) AS notatki, count(DISTINCT n.id_zgloszenia) AS zgloszenia
FROM serwis_notatki AS n
JOIN zgloszenia_wind AS z USING (id_zgloszenia)
WHERE z.kategoria IN ('awaria', 'interwencja')
GROUP BY z.kategoria
ORDER BY z.kategoria

-- losowanie: ? = kategoria ('awaria' / 'interwencja'), ziarno, liczba notatek
-- wywołanie: wylosuj_notatki(con, kategoria) z ZIARNO = 'b4_historia_awarii', n = 30
SELECT
    n.id_notatki,
    n.id_zgloszenia,
    z.tresc_zgloszenia,
    n.autor,
    n.tresc AS notatka
FROM serwis_notatki AS n
JOIN zgloszenia_wind AS z USING (id_zgloszenia)
WHERE z.kategoria = ?
ORDER BY md5(n.id_notatki || ':' || ?)
LIMIT ?
```
