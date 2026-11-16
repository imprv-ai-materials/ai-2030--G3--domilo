# Awarie wind: co jest w historii Serwisownika (B4)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-16 (`pypyr baza`).
Źródła: `serwis_zgloszenia`, `serwis_notatki`, `serwis_czesci`, `serwis_windy`, `serwis_zloty_zbior` (wczytane przez
`api/api/adapters/serwisownik.py`), `telemetra_windy` oraz tabele pochodne `zgloszenia_wind` i `awarie_odtworzone`
(R10–R14, odczyt notatek przez LLM `awaria_v1`, ocena: [b4_ekstrakcja.md](b4_ekstrakcja.md)).

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
4. Dla modelu „awaria w ciągu 7 dni” cel budujemy więc z treści zgłoszenia i notatek, a nie z kategorii.
   Odczyt notatek przez LLM na złotym zbiorze ma F1 98,9% wobec 46,4% dla kategorii „awaria”
   ([b4_ekstrakcja.md](b4_ekstrakcja.md)). To samo dotyczy cechy `windy_awarie_90d` w liście retencyjnej, która dziś
   liczy `typ_urzadzenia = 'winda'` i `kategoria = 'awaria'`.
5. Odczyt notatek wszystkich 16 880 zgłoszeń wind dał 1 540 awarii na 140 windach (tabela `awarie_odtworzone`,
   od 22 do 59 miesięcznie). To ponad dwa razy więcej niż 683 zgłoszeń z kategorią „awaria” przy znanej windzie.
   Start awarii z telemetrii (ostatnie 10 minut z jazdą przed postojem) zgadza się ze startem koordynatora co do
   okna w 130 ze 174 sprawdzonych awarii. Od startu do pierwszego zgłoszenia mija w medianie 81 minut, a do
   pierwszej notatki 310 minut (ok. 5 godzin): o tyle Serwisownik spóźnia się wobec telemetrii. Awarie z przyczyną
   zewnętrzną skupiają się w czerwcu–sierpniu (np. 26 w lipcu 2025 i w lipcu 2026), a tych telemetria windy nie
   zapowie.

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

**Awaria odtworzona** (tabela `awarie_odtworzone`, jeden wiersz = jedna awaria; SQL: `api/api/ai/features/windy/
awarie_odtworzone.sql` i `serie_przestoju.sql`, krok `pypyr baza` po `zgloszenia_wind`):

- zgłoszenia z `czy_awaria = true` według LLM (`awaria_v1`, wejście: zgłoszenie z notatkami) tej samej windy,
  gdy każde kolejne powstało najpóźniej 24 h po poprzednim, tworzą jedną awarię. Pierwsze z nich to kotwica;
- do awarii dołączamy też zgłoszenia tej windy bez awarii według LLM, z okna od kotwicy do 24 h po ostatnim
  zgłoszeniu z awarią, poza pracami planowymi (`konserwacja`, `przegląd`). To głównie powtórne zgłoszenia tej samej
  awarii (R11c). Same nie zaczynają awarii i nie przedłużają łańcucha;
- 44 zgłoszenia z awarią przy windzie nieustalonej (R10) pomijamy, bo nie da się sięgnąć do telemetrii;
- `podzespol` = najczęstszy różny od `brak` (remis: z wcześniejszego zgłoszenia);
- `start_awarii` = koniec ostatniego 10-minutowego okna z kursami > 0 przed serią co najmniej 3 okien (30 min)
  z `kursy = 0` albo `tryb = 'wylaczona'`. Seria musi się zacząć nie później niż w oknie kotwicy i nie wcześniej
  niż 24 h przed nią; z kilku takich serii bierzemy najpóźniejszą. Minimum 3 okna to wariant B z R12b, wybrany na
  złotym zbiorze: pojedyncze puste okna są codzienne (2 078 097 serii 1-okiennych w telemetrii);
- czas: telemetria (`ts_utc`, UTC) przeliczona na Europe/Warsaw (`timezone('Europe/Warsaw', ts_utc)`), Serwisownik
  zostaje w czasie lokalnym. Różnice minut liczymy na TIMESTAMPTZ, więc zmiana czasu nie dodaje ani nie odejmuje
  godziny. Kolumny `*_tz` to ten sam moment z przesunięciem;
- `czas_awarii` = `start_awarii`, a bez niego pierwsze zgłoszenie; według niego liczymy miesiące w R14.

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
| awaria | 57 | 55 | 2 | 96,5 |
| inne | 57 | 34 | 23 | 59,6 |
| przegląd | 51 | 0 | 51 | 0,0 |
| RAZEM | 400 | 180 | 220 | 45,0 |

### R8b. Ile faktycznych awarii może kryć się w każdej kategorii (szacunek)

**Założenie:** złoty zbiór jest losowy w obrębie każdej kategorii. Jak go wybrano, tego w danych nie ma. Szacunek =
liczba zgłoszeń kategorii × odsetek awarii w złotym zbiorze tej kategorii. Przy tym założeniu kategoria „awaria”
obejmuje ok. 14% faktycznych awarii wind.

**Aktualizacja (R10b): założenie się nie potwierdziło.** Po odczycie notatek wszystkich zgłoszeń wind odsetek awarii
w kategoriach jest dużo niższy niż w złotym zbiorze (np. „usterka”: 8,9% wobec 47,0%, „inne”: 14,9% wobec 59,6%).
Złoty zbiór nie jest więc losowy w obrębie kategorii, a szacunek poniżej (4 816) jest zawyżony. LLM wskazuje
1 584 zgłoszenia z awarią.

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

### R10. Odczyt notatek przez LLM na wszystkich zgłoszeniach wind

Prompt `awaria_v1`, model `gpt-6-luna`, 16 880 zgłoszeń, 0 błędów; 41 482 621 tokenów wejścia i 1 205 296 wyjścia
(`python -m api.ai.llm.ekstrakcja_awarii --zbior windy`). Kosztu w PLN nie podajemy, bo cennika nie ma w danych.

| zgloszenia_wind | z_odpowiedzia_llm | awaria_llm | awaria_llm_winda_ustalona | awaria_llm_winda_nieustalona | kategoria_awaria | kategoria_awaria_i_llm |
|---|---|---|---|---|---|---|
| 16 880 | 16 880 | 1 584 | 1 540 | 44 | 703 | 506 |

Odsetek zgłoszeń z awarią według kategorii Serwisownika:

| kategoria | zgloszenia | awaria_llm | proc_awarii_llm |
|---|---|---|---|
| konserwacja | 6 136 | 0 | 0,0 |
| usterka | 3 305 | 295 | 8,9 |
| przegląd | 2 939 | 0 | 0,0 |
| inne | 2 136 | 319 | 14,9 |
| interwencja | 1 661 | 464 | 27,9 |
| awaria | 703 | 506 | 72,0 |
| RAZEM | 16 880 | 1 584 | 9,4 |

### R11. Łączenie zgłoszeń w awarie

Żadne dwa zgłoszenia z awarią tej samej windy nie są bliżej niż 24 h: najmniejszy odstęp między kolejnymi awariami
jednej windy to 65,7 h. Łańcuch nic więc nie połączył. Do 500 awarii dołączyliśmy za to 653 zgłoszenia bez awarii.

| awarie | windy | zgl_z_awaria | zgl_dolaczone_bez_awarii | awarie_z_2_i_wiecej_zgl_z_awaria | awarie_z_2_i_wiecej_zgl | max_zgl | min_odstep_miedzy_awariami_windy_h | kolejna_awaria_windy_do_7_dni |
|---|---|---|---|---|---|---|---|---|
| 1 540 | 140 | 1 540 | 653 | 0 | 500 | 5 | 65,7 | 91 |

Pierwsza notatka dołączonych zgłoszeń (10 najczęstszych; cyfry → N). Wśród dołączonych są też drobne sprawy tej
samej windy (lustro, sprzątanie), które z awarią nie mają związku. Liczba awarii się przez to nie zmienia, ale
pierwsza notatka może pochodzić z takiego zgłoszenia.

| pierwsza_notatka | zgloszenia |
|---|---|
| (brak notatek) | 420 |
| Dubel zgłoszenia — połączono z wcześniejszym. | 65 |
| Przekazano do firmy serwisowej. | 64 |
| Zgłoszenie od lokatora, serwis już jedzie. | 64 |
| Lustro w kabinie poluzowane — dokręcono. | 5 |
| Czyszczenie kabiny i progów. | 4 |
| Regulacja domykacza drzwi szybowych na N. p. | 3 |
| Skrzypienie drzwi — smarowanie, OK. | 3 |
| Wymiana przycisku wezwania na N. p. | 3 |
| Wymiana świetlówki w kabinie. | 3 |

### R11b. Skąd start awarii

| zrodlo_startu | awarie | proc | z_trybem_wylaczona | mediana_okien_przestoju | mediana_przestoju_h | mediana_min_start_do_zgloszenia |
|---|---|---|---|---|---|---|
| telemetria | 1 539 | 99,9 | 1 033 | 110,0 | 18,3 | 81,0 |
| brak_serii | 1 | 0,1 | 0 |  |  |  |
| RAZEM | 1 540 | 100,0 | 1 033 | 110,0 | 18,3 | 81,0 |

Jedyna awaria bez serii przestoju to B32-W2/Z012353. Telemetria zaczyna się 2023-01-01 dla 129 wind, a 2024-09-15
dla 11 wind budynków B37 i B38 (`SELECT min(ts_utc), count(*) FROM (SELECT id_windy, min(ts_utc) ... GROUP BY 1)`).
Żadna awaria nie ma statusu `brak_telemetrii`, czyli te 11 wind nie ma awarii sprzed startu telemetrii.

### R12. Start z telemetrii wobec startu koordynatora (złoty zbiór)

Awarie odtworzone, których zgłoszenia (także dołączone) są w złotym zbiorze z `czy_awaria = true`. Brakuje 6 ze 180:
4 pominięte przez LLM ([b4_ekstrakcja.md](b4_ekstrakcja.md)) i 2 przy windzie nieustalonej.

| awarie_zz | w_awariach_odtworzonych | ze_startem_z_telemetrii | start_ten_sam | start_do_30_min | mediana_roznicy_min | p90_abs_roznicy_min | max_abs_roznicy_min |
|---|---|---|---|---|---|---|---|
| 180 | 174 | 174 | 130 | 169 | 0,0 | 10,0 | 130 |

Warianty reguły startu. Kotwica = zgłoszenie złotego zbioru, nie pierwsze zgłoszenie awarii, dlatego liczby
różnią się nieco od R12:

| wariant | awarie_zz | ze_startem | start_ten_sam | start_do_30_min | mediana_roznicy_min | p90_abs_roznicy_min |
|---|---|---|---|---|---|---|
| A: dowolna seria (≥ 1 okno), do 24 h przed | 180 | 178 | 129 | 168 | 0,0 | 20,0 |
| B: seria ≥ 3 okna (30 min), do 24 h przed [wybrany] | 180 | 178 | 132 | 171 | 0,0 | 20,0 |
| C: seria ≥ 6 okien (1 h), do 24 h przed | 180 | 178 | 132 | 171 | 0,0 | 20,0 |
| D: seria trwająca w chwili zgłoszenia | 180 | 174 | 128 | 166 | 0,0 | 20,0 |

### R13. Ile mija od startu awarii (telemetria) do zgłoszenia i notatki

Minuty liczone na TIMESTAMPTZ. „Pierwsza notatka” to najwcześniejsza notatka wszystkich zgłoszeń awarii, także
dołączonych. 4 awarie mają notatkę przed startem z telemetrii (krótka seria 3–8 okien znaleziona po notatce, np.
B32-W2/Z008196); dla nich reguła startu wskazała prawdopodobnie złą serię.

| miara | awarie | mediana_min | p25_min | p75_min | p90_min | ujemne |
|---|---|---|---|---|---|---|
| start -> pierwsza notatka | 1 539 | 310,0 | 189,5 | 547,0 | 872,6 | 4 |
| start -> pierwsza notatka konserwatora | 1 539 | 318,0 | 191,5 | 578,5 | 899,8 | 4 |
| start -> pierwsze zgłoszenie | 1 539 | 81,0 | 42,5 | 179,0 | 337,2 | 0 |

**Mediana różnicy między startem z telemetrii a pierwszą notatką: 310 minut (5 h 10 min).** Do pierwszej notatki
konserwatora: 318 minut.

### R14. Awarie miesięcznie według podzespołu

Miesiąc `czas_awarii`. Ostatnia kolumna dla porównania: zgłoszenia z kategorią „awaria” przy znanej windzie
(miesiąc utworzenia). `zewnetrzna` rośnie co roku w czerwcu–sierpniu (zalania, burze), pozostałe podzespoły są
stabilne.

| miesiac | drzwi | naped | hamulec_liny | sterownik | zewnetrzna | brak | razem | zgl_kategoria_awaria |
|---|---|---|---|---|---|---|---|---|
| 2023-01 | 10 | 6 | 4 | 5 | 3 | 4 | 32 | 14 |
| 2023-02 | 12 | 5 | 2 | 3 | 4 | 2 | 28 | 8 |
| 2023-03 | 12 | 4 | 2 | 3 | 2 | 6 | 29 | 14 |
| 2023-04 | 12 | 6 | 2 | 4 | 6 | 3 | 33 | 11 |
| 2023-05 | 10 | 5 | 3 | 4 | 1 | 3 | 26 | 11 |
| 2023-06 | 13 | 4 | 2 | 4 | 18 | 2 | 43 | 24 |
| 2023-07 | 8 | 4 | 3 | 3 | 14 | 7 | 39 | 15 |
| 2023-08 | 13 | 5 | 3 | 2 | 15 | 6 | 44 | 17 |
| 2023-09 | 13 | 5 | 2 | 4 | 3 | 0 | 27 | 14 |
| 2023-10 | 9 | 4 | 3 | 4 | 3 | 4 | 27 | 18 |
| 2023-11 | 9 | 4 | 3 | 3 | 2 | 1 | 22 | 14 |
| 2023-12 | 15 | 8 | 3 | 4 | 3 | 1 | 34 | 10 |
| 2024-01 | 11 | 6 | 3 | 3 | 5 | 2 | 30 | 14 |
| 2024-02 | 11 | 4 | 1 | 3 | 4 | 1 | 24 | 15 |
| 2024-03 | 11 | 5 | 4 | 5 | 5 | 4 | 34 | 14 |
| 2024-04 | 11 | 3 | 3 | 4 | 4 | 2 | 27 | 7 |
| 2024-05 | 11 | 6 | 3 | 3 | 3 | 3 | 29 | 12 |
| 2024-06 | 13 | 5 | 3 | 5 | 22 | 4 | 52 | 16 |
| 2024-07 | 12 | 5 | 3 | 4 | 17 | 2 | 43 | 27 |
| 2024-08 | 12 | 5 | 2 | 3 | 13 | 4 | 39 | 14 |
| 2024-09 | 12 | 4 | 3 | 4 | 4 | 2 | 29 | 11 |
| 2024-10 | 9 | 6 | 2 | 4 | 4 | 6 | 31 | 9 |
| 2024-11 | 12 | 6 | 3 | 2 | 6 | 4 | 33 | 17 |
| 2024-12 | 12 | 7 | 4 | 2 | 0 | 6 | 31 | 13 |
| 2025-01 | 11 | 5 | 3 | 3 | 5 | 4 | 31 | 16 |
| 2025-02 | 12 | 6 | 3 | 3 | 2 | 2 | 28 | 13 |
| 2025-03 | 11 | 5 | 4 | 4 | 5 | 3 | 32 | 15 |
| 2025-04 | 10 | 6 | 5 | 3 | 5 | 6 | 35 | 13 |
| 2025-05 | 13 | 5 | 3 | 3 | 3 | 4 | 31 | 13 |
| 2025-06 | 13 | 5 | 1 | 4 | 14 | 6 | 43 | 27 |
| 2025-07 | 12 | 5 | 2 | 3 | 26 | 4 | 52 | 24 |
| 2025-08 | 13 | 6 | 3 | 4 | 22 | 4 | 52 | 18 |
| 2025-09 | 9 | 4 | 1 | 2 | 4 | 4 | 24 | 16 |
| 2025-10 | 11 | 7 | 3 | 5 | 5 | 2 | 33 | 15 |
| 2025-11 | 12 | 4 | 3 | 3 | 2 | 2 | 26 | 10 |
| 2025-12 | 15 | 7 | 3 | 4 | 7 | 3 | 39 | 19 |
| 2026-01 | 11 | 6 | 2 | 4 | 4 | 2 | 29 | 14 |
| 2026-02 | 10 | 3 | 2 | 4 | 2 | 7 | 28 | 14 |
| 2026-03 | 12 | 6 | 5 | 2 | 5 | 3 | 33 | 8 |
| 2026-04 | 14 | 5 | 3 | 5 | 4 | 1 | 32 | 14 |
| 2026-05 | 16 | 4 | 6 | 4 | 2 | 2 | 34 | 17 |
| 2026-06 | 13 | 6 | 2 | 5 | 13 | 4 | 43 | 20 |
| 2026-07 | 13 | 4 | 5 | 3 | 26 | 8 | 59 | 27 |
| 2026-08 | 12 | 7 | 3 | 2 | 11 | 6 | 41 | 20 |
| 2026-09 | 12 | 4 | 2 | 4 | 4 | 3 | 29 | 11 |

Według roku (2026: styczeń–wrzesień):

| rok | drzwi | naped | hamulec_liny | sterownik | zewnetrzna | brak | razem |
|---|---|---|---|---|---|---|---|
| 2023 | 136 | 60 | 32 | 43 | 74 | 39 | 384 |
| 2024 | 137 | 62 | 34 | 42 | 87 | 40 | 402 |
| 2025 | 142 | 65 | 34 | 41 | 100 | 44 | 426 |
| 2026 | 113 | 45 | 30 | 33 | 71 | 36 | 328 |
| RAZEM | 528 | 232 | 130 | 159 | 332 | 159 | 1 540 |

## SQL i kod

Powtórzenie (z katalogu głównego repozytorium):

```bash
set -a && . ./.env && set +a                             # klucz API tylko do ekstrakcji (odpowiedzi są w cache)
cd api && poetry run python -m api.ai.llm.ekstrakcja_awarii --zbior windy && cd ..   # -> awarie_llm/awaria_v1_windy.parquet
poetry run pypyr baza                                    # serwis_*, zgloszenia_wind, awarie_odtworzone
cd api && poetry run python -m api.ai.failure_model.evals.historia_awarii   # tabele R1–R14 (Markdown)
```

Kod: `api/api/adapters/serwisownik.py` (wczytanie Serwisownika), `api/api/ai/features/windy/zgloszenia_wind.sql` i `zgloszenia_wind.py` (tabela `zgloszenia_wind`), `api/api/ai/features/windy/awarie_odtworzone.py`, `awarie_odtworzone.sql`, `serie_przestoju.sql` (tabela `awarie_odtworzone`), `api/api/ai/llm/ekstrakcja_awarii.py` (odczyt notatek), `api/api/ai/failure_model/evals/historia_awarii.py` (zapytania R1–R14). Testy: `api/tests/test_serwisownik.py`, `test_zgloszenia_wind.py`, `test_awarie_odtworzone.py`, `test_historia_awarii.py`, `test_duckdb_baza.py`.

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
ORDER BY z.kategoria IS NULL, w_zlotym_zbiorze DESC, z.kategoria
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
ORDER BY kategoria = 'RAZEM', szac_awarii DESC, kategoria
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

### Serie okien bez jazdy (`serie_przestoju.sql`)

```sql
-- Serie okien bez jazdy w telemetra_windy (opis: docs/b4_historia_awarii.md, R10–R14).
--
-- Okno martwe = kursy = 0 albo tryb = 'wylaczona'. Seria = kolejne martwe okna jednej windy (telemetria nie ma luk:
-- wszystkie odstępy to 10 minut). ts_utc to KONIEC 10-minutowego okna.
-- ostatnie_aktywne = koniec ostatniego okna z jazdą (kursy > 0, tryb <> 'wylaczona') przed serią; NULL, gdy seria
-- zaczyna telemetrię windy. Czasy jako TIMESTAMPTZ (dokładny moment); na czas lokalny przelicza awarie_odtworzone.sql.
WITH t AS (
    SELECT id_windy, ts_utc, (kursy = 0 OR tryb = 'wylaczona') AS martwe, tryb = 'wylaczona' AS wylaczona
    FROM telemetra_windy
),
g AS (
    SELECT *, sum(CASE WHEN martwe THEN 0 ELSE 1 END) OVER (PARTITION BY id_windy ORDER BY ts_utc) AS grupa
    FROM t
)
SELECT
    id_windy,
    min(ts_utc) FILTER (NOT martwe) AS ostatnie_aktywne,
    min(ts_utc) FILTER (martwe) AS pierwsze_martwe,
    max(ts_utc) FILTER (martwe) AS ostatnie_martwe,
    count(*) FILTER (martwe) AS okna,
    bool_or(wylaczona) AS wylaczona
FROM g
GROUP BY id_windy, grupa
HAVING count(*) FILTER (martwe) > 0
```

### Tabela `awarie_odtworzone` (`awarie_odtworzone.sql`)

```sql
-- awarie_odtworzone: awarie wind odtworzone z notatek (LLM) i telemetrii (opis i liczby: docs/b4_historia_awarii.md).
--
-- Wejście:
--   awarie_llm        — odpowiedzi ekstrakcji (api.ai.llm.ekstrakcja_awarii, zbiór `windy`): id_zgloszenia,
--                       czy_awaria, podzespol, objaw, pewnosc; rejestruje je awarie_odtworzone.py;
--   zgloszenia_wind   — zgłoszenia wind z ustaloną windą (tylko id_windy IS NOT NULL: przy windzie nieustalonej
--                       nie da się sięgnąć do telemetrii);
--   serie_przestoju   — serie okien bez jazdy (serie_przestoju.sql), tabela tymczasowa;
--   serwis_notatki, telemetra_windy.
--
-- Zdarzenie: zgłoszenia z czy_awaria = true tej samej windy, w których każde kolejne powstało najpóźniej 24 h po
--   poprzednim (łańcuch), są jedną awarią. Kotwica = pierwsze zgłoszenie zdarzenia (zawsze z czy_awaria = true).
--   Do zdarzenia dołączamy też zgłoszenia tej windy bez awarii wg LLM z okna (kotwica, ostatnie zgłoszenie z awarią
--   + 24 h], poza pracami planowymi (kategoria konserwacja / przegląd). To powtórne zgłoszenia tej samej awarii
--   („Dubel zgłoszenia — połączono z wcześniejszym.”, „Zgłoszenie od lokatora, serwis już jedzie.”, bez notatek),
--   których notatki nie potwierdzają postoju. Takie zgłoszenia nie zaczynają zdarzenia i nie przedłużają łańcucha.
-- Start z telemetrii: ostatnie okno z kursami > 0 (koniec okna) przed serią co najmniej 3 martwych okien (30 min;
--   kursy = 0 albo tryb = 'wylaczona'), która zaczęła się nie później niż w oknie kotwicy i nie wcześniej niż 24 h
--   przed nią; z kilku takich serii — najpóźniejsza.
-- Czas: Serwisownik to czas lokalny Europe/Warsaw bez strefy, telemetria to UTC. Różnice liczymy na TIMESTAMPTZ
--   (CAST lokalnego TIMESTAMP przy strefie sesji Europe/Warsaw, ustawia ją polacz()), a czasy w tabeli podajemy
--   jako lokalny TIMESTAMP Europe/Warsaw (kolumny *_tz to ten sam moment z przesunięciem).
--   Godzina 2025-10-26 02:00–03:00 Serwisownika jest niejednoznaczna; DuckDB przypisuje jej jedno przesunięcie.
WITH zgl AS (
    SELECT
        zw.id_zgloszenia, zw.id_windy, zw.id_budynku, zw.utworzono,
        CAST(zw.utworzono AS TIMESTAMPTZ) AS utworzono_tz,
        a.podzespol, a.objaw, a.pewnosc
    FROM zgloszenia_wind AS zw
    JOIN awarie_llm AS a USING (id_zgloszenia)
    WHERE a.czy_awaria AND zw.id_windy IS NOT NULL
),
kolejne AS (
    SELECT
        *,
        CASE
            WHEN lag(utworzono_tz) OVER w IS NULL OR utworzono_tz - lag(utworzono_tz) OVER w > INTERVAL 24 HOUR THEN 1
            ELSE 0
        END AS nowe
    FROM zgl
    WINDOW w AS (PARTITION BY id_windy ORDER BY utworzono_tz, id_zgloszenia)
),
numerowane AS (
    SELECT *, sum(nowe) OVER (PARTITION BY id_windy ORDER BY utworzono_tz, id_zgloszenia) AS nr
    FROM kolejne
),
-- podzespół zdarzenia: najczęstszy różny od 'brak'; remis -> ten z wcześniejszego zgłoszenia; same 'brak' -> 'brak'
podzespol_zdarzenia AS (
    SELECT id_windy, nr, podzespol
    FROM (
        SELECT id_windy, nr, podzespol, count(*) AS n, min(utworzono_tz) AS pierwsze
        FROM numerowane
        WHERE podzespol <> 'brak'
        GROUP BY id_windy, nr, podzespol
    )
    QUALIFY row_number() OVER (PARTITION BY id_windy, nr ORDER BY n DESC, pierwsze, podzespol) = 1
),
zdarzenia AS (
    SELECT
        id_windy,
        nr,
        any_value(id_budynku) AS id_budynku,
        min(utworzono) AS pierwsze_zgloszenie,
        min(utworzono_tz) AS kotwica,
        max(utworzono_tz) AS ostatnie_awaria_tz,
        count(*) AS liczba_zgloszen_awaria,
        list(id_zgloszenia ORDER BY utworzono_tz, id_zgloszenia) AS id_zgloszen_awaria,
        arg_min(objaw, utworzono_tz) AS objaw,
        max(pewnosc) AS pewnosc_max
    FROM numerowane
    GROUP BY id_windy, nr
),
dolaczone AS (
    SELECT z.id_windy, z.nr, zw.id_zgloszenia, zw.utworzono, CAST(zw.utworzono AS TIMESTAMPTZ) AS utworzono_tz
    FROM zdarzenia AS z
    JOIN zgloszenia_wind AS zw
        ON zw.id_windy = z.id_windy
       AND CAST(zw.utworzono AS TIMESTAMPTZ) > z.kotwica
       AND CAST(zw.utworzono AS TIMESTAMPTZ) <= z.ostatnie_awaria_tz + INTERVAL 24 HOUR
       AND zw.kategoria NOT IN ('konserwacja', 'przegląd')
    JOIN awarie_llm AS a ON a.id_zgloszenia = zw.id_zgloszenia AND NOT a.czy_awaria
    QUALIFY row_number() OVER (PARTITION BY zw.id_zgloszenia ORDER BY z.kotwica) = 1
),
wszystkie AS (
    SELECT id_windy, nr, id_zgloszenia, utworzono, utworzono_tz FROM numerowane
    UNION ALL
    SELECT id_windy, nr, id_zgloszenia, utworzono, utworzono_tz FROM dolaczone
),
zgloszenia_zdarzenia AS (
    SELECT
        id_windy, nr,
        count(*) AS liczba_zgloszen,
        list(id_zgloszenia ORDER BY utworzono_tz, id_zgloszenia) AS id_zgloszen,
        max(utworzono) AS ostatnie_zgloszenie
    FROM wszystkie
    GROUP BY id_windy, nr
),
notatki AS (
    SELECT
        w.id_windy, w.nr,
        min(sn.data_czas) AS pierwsza_notatka,
        min(sn.data_czas) FILTER (sn.autor <> 'KOORD') AS pierwsza_notatka_konserwatora
    FROM wszystkie AS w
    JOIN serwis_notatki AS sn USING (id_zgloszenia)
    GROUP BY w.id_windy, w.nr
),
zakres_telemetrii AS (
    SELECT id_windy, min(ts_utc) AS od, max(ts_utc) AS do
    FROM telemetra_windy
    GROUP BY id_windy
),
start AS (
    SELECT
        z.id_windy, z.nr,
        arg_max(s.ostatnie_aktywne, s.pierwsze_martwe) AS start_tz,
        arg_max(s.ostatnie_martwe, s.pierwsze_martwe) AS koniec_tz,
        arg_max(s.okna, s.pierwsze_martwe) AS okna,
        arg_max(s.wylaczona, s.pierwsze_martwe) AS wylaczona
    FROM zdarzenia AS z
    JOIN serie_przestoju AS s
        ON s.id_windy = z.id_windy
       AND s.okna >= 3
       AND s.ostatnie_aktywne IS NOT NULL
       AND s.pierwsze_martwe <= z.kotwica + INTERVAL 10 MINUTE
       AND s.pierwsze_martwe >= z.kotwica - INTERVAL 24 HOUR
    GROUP BY z.id_windy, z.nr
)
SELECT
    z.id_windy || '/' || z.id_zgloszen_awaria[1] AS id_awarii,
    z.id_windy,
    z.id_budynku,
    coalesce(p.podzespol, 'brak') AS podzespol,
    z.objaw,
    z.pewnosc_max,
    zz.liczba_zgloszen,
    z.liczba_zgloszen_awaria,
    zz.id_zgloszen,
    z.id_zgloszen_awaria,
    z.pierwsze_zgloszenie,
    zz.ostatnie_zgloszenie,
    timezone('Europe/Warsaw', st.start_tz) AS start_awarii,
    st.start_tz AS start_awarii_tz,
    timezone('Europe/Warsaw', st.koniec_tz) AS koniec_przestoju,
    st.okna AS okna_przestoju,
    round(epoch(st.koniec_tz - st.start_tz) / 3600, 2) AS przestoj_h,
    st.wylaczona,
    CASE
        WHEN st.start_tz IS NOT NULL THEN 'telemetria'
        WHEN zt.od IS NULL OR z.kotwica < zt.od + INTERVAL 24 HOUR OR z.kotwica > zt.do THEN 'brak_telemetrii'
        ELSE 'brak_serii'
    END AS zrodlo_startu,
    n.pierwsza_notatka,
    n.pierwsza_notatka_konserwatora,
    round(epoch(CAST(n.pierwsza_notatka AS TIMESTAMPTZ) - st.start_tz) / 60) AS minuty_start_do_notatki,
    round(epoch(CAST(n.pierwsza_notatka_konserwatora AS TIMESTAMPTZ) - st.start_tz) / 60)
        AS minuty_start_do_notatki_konserwatora,
    round(epoch(z.kotwica - st.start_tz) / 60) AS minuty_start_do_zgloszenia,
    coalesce(timezone('Europe/Warsaw', st.start_tz), z.pierwsze_zgloszenie) AS czas_awarii
FROM zdarzenia AS z
JOIN zgloszenia_zdarzenia AS zz USING (id_windy, nr)
LEFT JOIN podzespol_zdarzenia AS p USING (id_windy, nr)
LEFT JOIN notatki AS n USING (id_windy, nr)
LEFT JOIN start AS st USING (id_windy, nr)
LEFT JOIN zakres_telemetrii AS zt USING (id_windy)
ORDER BY czas_awarii, id_awarii
```

### R10

```sql
SELECT
    count(*) AS zgloszenia_wind,
    count(a.id_zgloszenia) AS z_odpowiedzia_llm,
    count(*) FILTER (a.czy_awaria) AS awaria_llm,
    count(*) FILTER (a.czy_awaria AND zw.id_windy IS NOT NULL) AS awaria_llm_winda_ustalona,
    count(*) FILTER (a.czy_awaria AND zw.id_windy IS NULL) AS awaria_llm_winda_nieustalona,
    count(*) FILTER (zw.kategoria = 'awaria') AS kategoria_awaria,
    count(*) FILTER (zw.kategoria = 'awaria' AND a.czy_awaria) AS kategoria_awaria_i_llm
FROM zgloszenia_wind AS zw
LEFT JOIN awarie_llm AS a USING (id_zgloszenia)
```

### R10b

```sql
SELECT
    coalesce(zw.kategoria, 'RAZEM') AS kategoria,
    count(*) AS zgloszenia,
    count(*) FILTER (a.czy_awaria) AS awaria_llm,
    round(100.0 * count(*) FILTER (a.czy_awaria) / count(*), 1) AS proc_awarii_llm
FROM zgloszenia_wind AS zw
JOIN awarie_llm AS a USING (id_zgloszenia)
GROUP BY ROLLUP (zw.kategoria)
ORDER BY zw.kategoria IS NULL, zgloszenia DESC
```

### R11

```sql
WITH odstepy AS (
    SELECT epoch(CAST(pierwsze_zgloszenie AS TIMESTAMPTZ) - CAST(lag(ostatnie_zgloszenie) OVER (
               PARTITION BY id_windy ORDER BY pierwsze_zgloszenie) AS TIMESTAMPTZ)) / 3600 AS h
    FROM awarie_odtworzone
)
SELECT
    count(*) AS awarie,
    count(DISTINCT id_windy) AS windy,
    sum(liczba_zgloszen_awaria) AS zgl_z_awaria,
    sum(liczba_zgloszen) - sum(liczba_zgloszen_awaria) AS zgl_dolaczone_bez_awarii,
    count(*) FILTER (liczba_zgloszen_awaria >= 2) AS awarie_z_2_i_wiecej_zgl_z_awaria,
    count(*) FILTER (liczba_zgloszen >= 2) AS awarie_z_2_i_wiecej_zgl,
    max(liczba_zgloszen) AS max_zgl,
    (SELECT round(min(h), 1) FROM odstepy) AS min_odstep_miedzy_awariami_windy_h,
    (SELECT count(*) FILTER (h <= 7 * 24) FROM odstepy) AS kolejna_awaria_windy_do_7_dni
FROM awarie_odtworzone
```

### R11c

```sql
WITH d AS (
    SELECT u.id_zgloszenia
    FROM awarie_odtworzone AS a, unnest(a.id_zgloszen) AS u(id_zgloszenia)
    WHERE NOT list_contains(a.id_zgloszen_awaria, u.id_zgloszenia)
),
n AS (
    SELECT id_zgloszenia, arg_min(tresc, data_czas) AS tresc FROM serwis_notatki GROUP BY id_zgloszenia
)
SELECT
    coalesce(regexp_replace(regexp_replace(n.tresc, '\s+', ' ', 'g'), '[0-9]+', 'N', 'g'), '(brak notatek)')
        AS pierwsza_notatka,
    count(*) AS zgloszenia
FROM d
LEFT JOIN n USING (id_zgloszenia)
GROUP BY 1
ORDER BY zgloszenia DESC, pierwsza_notatka
LIMIT 10
```

### R11b

```sql
SELECT
    coalesce(zrodlo_startu, 'RAZEM') AS zrodlo_startu,
    count(*) AS awarie,
    round(100.0 * count(*) / sum(count(*)) FILTER (zrodlo_startu IS NOT NULL) OVER (), 1) AS proc,
    count(*) FILTER (wylaczona) AS z_trybem_wylaczona,
    median(okna_przestoju) AS mediana_okien_przestoju,
    median(przestoj_h) AS mediana_przestoju_h,
    median(minuty_start_do_zgloszenia) AS mediana_min_start_do_zgloszenia
FROM awarie_odtworzone
GROUP BY ROLLUP (zrodlo_startu)
ORDER BY zrodlo_startu IS NULL, awarie DESC
```

### R12

```sql
WITH z AS (
    SELECT a.id_awarii, a.start_awarii, a.zrodlo_startu, zz.id_zgloszenia, zz.start_awarii AS start_koordynatora
    FROM awarie_odtworzone AS a, unnest(a.id_zgloszen) AS u(id_zgloszenia)
    JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
    WHERE zz.czy_awaria
)
SELECT
    (SELECT count(*) FROM serwis_zloty_zbior WHERE czy_awaria) AS awarie_zz,
    count(*) AS w_awariach_odtworzonych,
    count(start_awarii) AS ze_startem_z_telemetrii,
    count(*) FILTER (start_awarii = start_koordynatora) AS start_ten_sam,
    count(*) FILTER (abs(date_diff('minute', start_koordynatora, start_awarii)) <= 30) AS start_do_30_min,
    median(date_diff('minute', start_koordynatora, start_awarii)) AS mediana_roznicy_min,
    quantile_cont(abs(date_diff('minute', start_koordynatora, start_awarii)), 0.9) AS p90_abs_roznicy_min,
    max(abs(date_diff('minute', start_koordynatora, start_awarii))) AS max_abs_roznicy_min
FROM z
```

### R13

```sql
SELECT miara, count(m) AS awarie, median(m) AS mediana_min, quantile_cont(m, 0.25) AS p25_min,
       quantile_cont(m, 0.75) AS p75_min, quantile_cont(m, 0.9) AS p90_min, count(*) FILTER (m < 0) AS ujemne
FROM (
    SELECT 'start -> pierwsza notatka' AS miara, minuty_start_do_notatki AS m, 1 AS k FROM awarie_odtworzone
    UNION ALL
    SELECT 'start -> pierwsza notatka konserwatora', minuty_start_do_notatki_konserwatora, 2 FROM awarie_odtworzone
    UNION ALL
    SELECT 'start -> pierwsze zgłoszenie', minuty_start_do_zgloszenia, 3 FROM awarie_odtworzone
)
WHERE m IS NOT NULL
GROUP BY miara, k
ORDER BY k
```

### R14

```sql
WITH a AS (SELECT strftime(czas_awarii, '%Y-%m') AS miesiac, podzespol FROM awarie_odtworzone),
p AS (PIVOT a ON podzespol IN ('drzwi', 'naped', 'hamulec_liny', 'sterownik', 'zewnetrzna', 'brak') USING count(*) GROUP BY miesiac),
k AS (
    SELECT strftime(utworzono, '%Y-%m') AS miesiac, count(*) AS zgl_kategoria_awaria
    FROM zgloszenia_wind
    WHERE kategoria = 'awaria' AND id_windy IS NOT NULL
    GROUP BY 1
)
SELECT
    coalesce(p.miesiac, k.miesiac) AS miesiac,
    coalesce(p.drzwi, 0) AS drzwi, coalesce(p.naped, 0) AS naped, coalesce(p.hamulec_liny, 0) AS hamulec_liny,
    coalesce(p.sterownik, 0) AS sterownik, coalesce(p.zewnetrzna, 0) AS zewnetrzna, coalesce(p.brak, 0) AS brak,
    coalesce(p.drzwi + p.naped + p.hamulec_liny + p.sterownik + p.zewnetrzna + p.brak, 0) AS razem,
    coalesce(k.zgl_kategoria_awaria, 0) AS zgl_kategoria_awaria
FROM p
FULL JOIN k USING (miesiac)
ORDER BY miesiac
```

### R14b

```sql
SELECT
    coalesce(CAST(year(czas_awarii) AS VARCHAR), 'RAZEM') AS rok,
    count(*) FILTER (podzespol = 'drzwi') AS drzwi,
    count(*) FILTER (podzespol = 'naped') AS naped,
    count(*) FILTER (podzespol = 'hamulec_liny') AS hamulec_liny,
    count(*) FILTER (podzespol = 'sterownik') AS sterownik,
    count(*) FILTER (podzespol = 'zewnetrzna') AS zewnetrzna,
    count(*) FILTER (podzespol = 'brak') AS brak,
    count(*) AS razem
FROM awarie_odtworzone
GROUP BY ROLLUP (year(czas_awarii))
ORDER BY year(czas_awarii) IS NULL, year(czas_awarii)
```

### R12b — warianty reguły startu

```sql
-- {warunek} i ? (nazwa wariantu) z WARIANTY_STARTU:
--   A: dowolna seria (≥ 1 okno), do 24 h przed: s.pierwsze_martwe >= g.kotwica - INTERVAL 24 HOUR
--   B: seria ≥ 3 okna (30 min), do 24 h przed [wybrany]: s.pierwsze_martwe >= g.kotwica - INTERVAL 24 HOUR AND s.okna >= 3
--   C: seria ≥ 6 okien (1 h), do 24 h przed: s.pierwsze_martwe >= g.kotwica - INTERVAL 24 HOUR AND s.okna >= 6
--   D: seria trwająca w chwili zgłoszenia: s.ostatnie_martwe >= g.kotwica
WITH g AS (
    SELECT zz.id_zgloszenia, zw.id_windy, CAST(zw.utworzono AS TIMESTAMPTZ) AS kotwica, zz.start_awarii
    FROM serwis_zloty_zbior AS zz
    JOIN zgloszenia_wind AS zw USING (id_zgloszenia)
    WHERE zz.czy_awaria
),
k AS (
    SELECT g.id_zgloszenia, g.start_awarii,
           timezone('Europe/Warsaw', arg_max(s.ostatnie_aktywne, s.pierwsze_martwe)) AS start_tel
    FROM g
    LEFT JOIN serie_przestoju AS s
        ON s.id_windy = g.id_windy AND s.ostatnie_aktywne IS NOT NULL
       AND s.pierwsze_martwe <= g.kotwica + INTERVAL 10 MINUTE AND {warunek}
    GROUP BY g.id_zgloszenia, g.start_awarii
)
SELECT
    ? AS wariant,
    count(*) AS awarie_zz,
    count(start_tel) AS ze_startem,
    count(*) FILTER (start_tel = start_awarii) AS start_ten_sam,
    count(*) FILTER (abs(date_diff('minute', start_awarii, start_tel)) <= 30) AS start_do_30_min,
    median(date_diff('minute', start_awarii, start_tel)) AS mediana_roznicy_min,
    quantile_cont(abs(date_diff('minute', start_awarii, start_tel)), 0.9) AS p90_abs_roznicy_min
FROM k
```
