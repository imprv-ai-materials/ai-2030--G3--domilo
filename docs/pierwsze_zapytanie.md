# Pierwsze zapytanie: zakres danych, spójność kluczy, obłożenie i końce umów

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw) przez `pypyr baza`.
Policzono 2026-11-15. Wszystkie liczby pochodzą z zapytań w sekcji [SQL i kod](#sql-i-kod).

## Wnioski

Dane zgadzają się z tym, co wiemy o Domilo (7 200 lokali, 38 budynków, 140 wind), a klucze lokal → budynek,
najem → lokal, umowa → najem, lead „umowa” → umowa w PMS i winda → budynek nie mają ani jednego błędu.
Na koniec 2026-09-30 zajętych jest 6 828 z 7 200 lokali (**94,8%**, od 94,0% w Poznaniu do 96,9% w Gdańsku i Łodzi),
a wynik z historii najmów zgadza się co do lokalu ze statusem w `pms_lokale`. W 2026 kończy się 7 596 okresów umów
(od 533 do 710 miesięcznie), w tym 2 046 w IV kwartale, po dniu eksportu: dla nich lista retencyjna da pierwszą
prognozę, bo `retencja_decyzje` kończy się na umowach z końcem we wrześniu. Najsłabszym źródłem jest Serwisownik:
28,4% zgłoszeń nie ma urządzenia, w tym 1 120 z 16 413 zgłoszeń wind (6,8%), których model awarii nie przypisze do
windy. Do modeli trzeba odfiltrować dane nieznane w dniu eksportu, m.in. 305 transakcji RCN i 16 ofert z datą
publikacji po 2026-09-30.

## Tabele

### 1. Liczba wierszy i zakres dat

Kolumny dat: typy DATE/TIMESTAMP oraz tekstowe kolumny `miesiac` (RRRR-MM). Czas CRM i telemetrii pokazany w strefie
Europe/Warsaw, czas Serwisownika i PMS jak w źródle (lokalny). „> dzień eksportu” = od 2026-10-01 00:00
(dla `miesiac`: po 2026-09).

| Tabela | Typ | Wiersze | Kolumna daty | Min | Max | Puste | < 2023-01-01 | > dzień eksportu |
|---|---|---:|---|---|---|---:|---:|---:|
| ankiety_satysfakcji | tabela | 20 891 | data_wysylki | 2023-01-01 | 2026-09-30 | 0 | 0 | 0 |
| ankiety_satysfakcji | tabela | 20 891 | data_odpowiedzi | 2023-01-02 | 2026-09-30 | 12 164 | 0 | 0 |
| crm_aktywnosci | tabela | 594 459 | data_czas | 2023-01-02 05:03 | 2026-09-30 23:54 | 0 | 0 | 0 |
| crm_doradcy | tabela | 16 | data_od | 2019-05-06 | 2025-09-01 | 0 | 10 | 0 |
| crm_doradcy | tabela | 16 | data_do | 2023-10-31 | 2025-08-29 | 11 | 0 | 0 |
| crm_firmy_b2b | tabela | 420 | data_umowy_ramowej | 2025-06-02 | 2025-06-02 | 417 | 0 | 0 |
| crm_grafik | tabela | 10 806 | data | 2023-01-02 | 2026-09-30 | 0 | 0 | 0 |
| crm_historia_statusow | tabela | 452 911 | data_czas | 2023-01-01 00:22 | 2026-09-30 23:58 | 0 | 0 | 0 |
| crm_leady | tabela | 161 556 | utworzono | 2023-01-01 00:22 | 2026-09-30 22:48 | 0 | 0 | 0 |
| crm_leady | tabela | 161 556 | termin_wprowadzenia | 2023-01-08 | 2027-05-26 | 48 407 | 0 | 4 839 |
| crm_leady | tabela | 161 556 | data_statusu | 2023-01-03 10:33 | 2026-09-30 23:58 | 0 | 0 | 0 |
| fk_koszty_rotacji | tabela | 1 642 | miesiac | 2023-01 | 2026-09 | 0 | 0 | 0 |
| fk_koszty_serwisu | tabela | 10 194 | data | 2023-01-04 | 2026-09-30 | 0 | 0 | 0 |
| fk_rabaty | tabela | 33 987 | miesiac | 2024-02 | 2026-09 | 0 | 0 | 0 |
| geo_poi | tabela | 47 208 | — | | | | | |
| gus_dzielnice | tabela | 109 | — | | | | | |
| lokale_domilo_opisy | tabela | 7 200 | — | | | | | |
| metadane | tabela | 7 600 | — | | | | | |
| operaty | tabela | 21 420 | data_wyceny | 2023-12-15 | 2026-09-28 | 0 | 0 | 0 |
| pms_budynki | tabela | 38 | data_przejecia | 2019-04-01 | 2024-09-15 | 0 | 27 | 0 |
| pms_lokale | tabela | 7 200 | — | | | | | |
| pms_najemcy | tabela | 21 761 | data_rejestracji | 2019-02-12 | 2026-09-25 | 0 | 7 329 | 0 |
| pms_najmy | tabela | 23 289 | data_wprowadzenia | 2019-04-01 | 2026-12-12 | 0 | 7 503 | 350 |
| pms_najmy | tabela | 23 289 | data_wyprowadzenia | 2019-07-22 | 2026-09-30 | 7 178 | 2 815 | 0 |
| pms_najmy | tabela | 23 289 | wypowiedzenie_data | 2019-05-26 | 2026-08-29 | 7 178 | 3 192 | 0 |
| pms_platnosci | tabela | 312 438 | miesiac | 2023-01 | 2026-09 | 0 | 0 | 0 |
| pms_platnosci | tabela | 312 438 | data_platnosci | 2023-01-01 | 2026-09-30 | 164 | 0 | 0 |
| pms_rekompensaty | tabela | 2 956 | data | 2023-01-01 | 2026-09-29 | 0 | 0 | 0 |
| pms_umowy | tabela | 36 974 | data_od | 2019-04-01 | 2026-12-12 | 0 | 9 259 | 358 |
| pms_umowy | tabela | 36 974 | data_do | 2019-07-22 | 2028-11-12 | 0 | 4 508 | 7 334 |
| pms_umowy | tabela | 36 974 | data_podpisania | 2023-01-03 | 2026-09-29 | 9 893 | 0 | 0 |
| portal_logowania_mies | tabela | 288 813 | miesiac | 2023-01 | 2026-09 | 0 | 0 | 0 |
| portal_wiadomosci | tabela | 120 726 | data_czas | 2023-01-01 01:17 | 2026-09-30 20:52 | 0 | 0 | 0 |
| portal_zgloszenia | tabela | 58 521 | utworzono | 2023-01-01 00:24 | 2026-09-30 23:41 | 0 | 0 | 0 |
| portal_zgloszenia | tabela | 58 521 | zamknieto | 2023-01-01 12:36 | 2026-09-29 23:25 | 169 | 0 | 0 |
| radar_dopasowania | tabela | 20 500 | — | | | | | |
| radar_oferty | tabela | 176 859 | data_publikacji | 2023-01-01 | 2026-10-03 | 0 | 0 | 16 |
| radar_oferty | tabela | 176 859 | data_zdjecia | 2023-01-02 | 2026-09-30 | 10 680 | 0 | 0 |
| radar_pakiety | tabela | 60 | data_oferty | 2023-01-02 | 2026-08-12 | 0 | 0 | 0 |
| rcn_transakcje | tabela | 54 000 | data_aktu | 2023-01-01 | 2026-06-30 | 0 | 0 | 0 |
| rcn_transakcje | tabela | 54 000 | data_publikacji_rejestru | 2023-03-03 | 2026-10-28 | 0 | 0 | 305 |
| retencja_decyzje | tabela | 15 206 | data_konca | 2024-02-01 | 2026-09-30 | 0 | 0 | 0 |
| retencja_decyzje | tabela | 15 206 | data_oferty | 2023-12-18 | 2026-08-16 | 9 320 | 0 | 0 |
| serwis_czesci | tabela | 2 758 | — | | | | | |
| serwis_harmonogram | tabela | 8 668 | data_plan | 2023-01-02 | 2026-09-30 | 0 | 0 | 0 |
| serwis_harmonogram | tabela | 8 668 | data_wykonania | 2023-01-01 | 2026-09-27 | 31 | 0 | 0 |
| serwis_notatki | tabela | 28 885 | data_czas | 2023-01-01 11:55 | 2026-09-30 22:52 | 0 | 0 | 0 |
| serwis_windy | tabela | 140 | czujnik_wibracji_od | 2024-05-06 | 2025-01-13 | 0 | 0 | 0 |
| serwis_zgloszenia | tabela | 24 736 | utworzono | 2023-01-01 09:57 | 2026-09-30 20:06 | 0 | 0 | 0 |
| serwis_zgloszenia | tabela | 24 736 | zamknieto | 2023-01-01 12:51 | 2026-09-30 23:58 | 26 | 0 | 0 |
| serwis_zloty_zbior | tabela | 400 | start_awarii | 2023-01-15 12:50 | 2026-09-13 11:30 | 220 | 0 | 0 |
| telemetra_firmware | tabela | 327 | data | 2023-05-01 02:00 | 2026-09-27 02:00 | 0 | 0 | 0 |
| telemetra_urzadzenia_ciepla | tabela | 77 | — | | | | | |
| www_sesje | tabela | 884 109 | data_czas | 2022-09-20 14:33 | 2026-09-30 23:58 | 0 | 382 | 0 |
| telemetra_cieplo | widok | 9 044 720 | ts_utc | 2023-01-01 00:15 | 2026-10-01 00:00 | 0 | 0 | 77 |
| telemetra_windy | widok | 26 611 434 | ts_utc | 2023-01-01 00:10 | 2026-10-01 00:00 | 0 | 0 | 140 |

Porównanie z tym, co wiemy o danych (`data/README.md`):

| Oczekiwanie | Wynik | Ocena |
|---|---|---|
| Dane zdarzeniowe 2023-01-01 – 2026-09-30 | Wszystkie tabele zdarzeń mieszczą się w tym okresie, poza wyjątkami niżej | zgodne |
| PMS od 2019-04, rekordy sprzed 2023-03-01 to import z pustym `data_podpisania` | `pms_najmy`/`pms_umowy` od 2019-04-01; 9 893 umowy bez `data_podpisania`, najstarsza podpisana 2023-01-03 | zgodne |
| RCN do 2026-06-30, publikacja z opóźnieniem 60–120 dni | `data_aktu` do 2026-06-30, ale **305 transakcji opublikowano po dniu eksportu** (do 2026-10-28) | do odfiltrowania |
| Najmy z wprowadzeniem po eksporcie | 350 najmów (358 okresów umów) zaczyna się po 2026-09-30, najpóźniej 2026-12-12 | zgodne |
| Telemetra: `ts_utc` = koniec okna | Ostatnie okno kończy się 2026-10-01 00:00 (czyli obejmuje 30.09 23:50–24:00): po 1 wierszu na każde ze 140 wind i 77 urządzeń ciepła | zgodne |
| — | **16 ofert** w `radar_oferty` ma `data_publikacji` po eksporcie (do 2026-10-03) | do wyjaśnienia |
| — | **382 sesje** w `www_sesje` są sprzed 2023-01-01 (od 2022-09-20) | do wyjaśnienia |
| — | `crm_firmy_b2b.data_umowy_ramowej`: tylko 3 z 420 firm mają datę, wszystkie 2025-06-02 | do wyjaśnienia |

### 2. Spójność kluczy

| Relacja | Wiersze | Bez klucza | Klucz nie istnieje |
|---|---:|---:|---:|
| lokal → budynek | 7 200 | 0 | 0 |
| najem → lokal | 23 289 | 0 | 0 |
| umowa → najem | 36 974 | 0 | 0 |
| lead „umowa” → umowa PMS | 12 111 | 0 | 0 |
| winda → budynek | 140 | 0 | 0 |

Budynki (38): liczba lokali w `pms_lokale` i wind w `serwis_windy` zgadza się z `pms_budynki.liczba_lokali` i
`liczba_wind` w każdym budynku (0 niezgodności). Każdy budynek ma co najmniej jedną windę.

Leady ze statusem „umowa”: każdy wskazuje inną umowę, żadna nie została podpisana przed utworzeniem leada.
Leady z innym statusem nie mają `id_umowy`.

| Typ umowy | Leady | Różne umowy | Umowa podpisana przed leadem |
|---|---:|---:|---:|
| pierwsza | 8 044 | 8 044 | 0 |
| średnioterminowa | 4 067 | 4 067 | 0 |

Zgłoszenia Serwisownika → urządzenie (rejestry: `serwis_windy` dla wind, `telemetra_urzadzenia_ciepla` dla węzłów
i pomp ciepła; domofony i „inne” nie mają rejestru urządzeń):

| Typ zgłoszenia | Zgłoszenia | Bez urządzenia | % bez urządzenia | Urządzenie nie istnieje | Urządzenie innego typu | Urządzenie z innego budynku |
|---|---:|---:|---:|---:|---:|---:|
| **razem** | 24 736 | **7 025** | 28,4 | 0 | 534 | 0 |
| winda | 16 413 | 1 120 | 6,8 | 0 | 14 | 0 |
| inne | 3 641 | 3 446 | 94,6 | 0 | 195 | 0 |
| domofon | 2 484 | 2 306 | 92,8 | 0 | 178 | 0 |
| węzeł | 1 114 | 111 | 10,0 | 0 | 147 | 0 |
| pompa | 1 084 | 42 | 3,9 | 0 | 0 | 0 |

Każdy wpisany identyfikator urządzenia istnieje i leży w tym samym budynku co zgłoszenie. Problemy to brak
identyfikatora (7 025) i niezgodny typ (534, np. zgłoszenie „węzeł” przypisane do windy).

### 3. Obłożenie na 2026-09-30 (koniec dnia)

Lokal zajęty = ma najem z `data_wprowadzenia` ≤ 2026-09-30 i bez `data_wyprowadzenia` albo z wyprowadzeniem po tym dniu.

| Miasto | Lokale | Zajęte (najmy) | Obłożenie % | Zajęte (status PMS) | W remoncie | Lokale z >1 aktywnym najmem |
|---|---:|---:|---:|---:|---:|---:|
| **razem** | 7 200 | 6 828 | **94,8** | 6 828 | 18 | 0 |
| Warszawa | 2 900 | 2 730 | 94,1 | 2 730 | 5 | 0 |
| Kraków | 1 300 | 1 236 | 95,1 | 1 236 | 3 | 0 |
| Wrocław | 1 100 | 1 041 | 94,6 | 1 041 | 3 | 0 |
| Poznań | 700 | 658 | 94,0 | 658 | 3 | 0 |
| Gdańsk | 650 | 630 | 96,9 | 630 | 3 | 0 |
| Łódź | 550 | 533 | 96,9 | 533 | 1 | 0 |

Status w `pms_lokale` a aktywne najmy: zgodność co do lokalu.

| Status PMS | Aktywny najem | Lokale |
|---|---|---:|
| zajęty | tak | 6 828 |
| wolny | nie | 354 |
| remont | nie | 18 |

### 4. Umowy kończące się w 2026 (wg `pms_umowy.data_do`)

`data_do` to planowany koniec okresu umowy. Okresy z października–grudnia kończą się po dniu eksportu: to stan wiedzy
na 2026-09-30.

| Miesiąc | Okresy umów | pierwsza | przedłużenie | średnioterminowa | Po dniu eksportu |
|---|---:|---:|---:|---:|---:|
| 2026-01 | 674 | 248 | 302 | 124 | 0 |
| 2026-02 | 576 | 209 | 243 | 124 | 0 |
| 2026-03 | 647 | 245 | 275 | 127 | 0 |
| 2026-04 | 576 | 203 | 256 | 117 | 0 |
| 2026-05 | 533 | 171 | 249 | 113 | 0 |
| 2026-06 | 559 | 157 | 285 | 117 | 0 |
| 2026-07 | 646 | 213 | 334 | 99 | 0 |
| 2026-08 | 659 | 229 | 304 | 126 | 0 |
| 2026-09 | 680 | 245 | 319 | 116 | 0 |
| 2026-10 | 677 | 236 | 338 | 103 | 677 |
| 2026-11 | 710 | 249 | 339 | 122 | 710 |
| 2026-12 | 659 | 236 | 314 | 109 | 659 |
| **razem** | **7 596** | | | | **2 046** |

Kontrola krzyżowa z `retencja_decyzje` (umowy roczne = „pierwsza” + „przedłużenie”):

| Miesiąc | Roczne w PMS | W retencja_decyzje | Te same umowy (ta sama data końca) |
|---|---:|---:|---:|
| 2026-01 | 550 | 537 | 537 |
| 2026-02 | 452 | 435 | 435 |
| 2026-03 | 520 | 500 | 500 |
| 2026-04 | 459 | 440 | 440 |
| 2026-05 | 420 | 404 | 404 |
| 2026-06 | 442 | 426 | 426 |
| 2026-07 | 547 | 533 | 533 |
| 2026-08 | 533 | 510 | 510 |
| 2026-09 | 564 | 543 | 543 |
| 2026-10 | 574 | — | — |
| 2026-11 | 588 | — | — |
| 2026-12 | 550 | — | — |

Każda umowa z `retencja_decyzje` ma odpowiednik w PMS z tą samą datą końca. Różnica (159 umów w styczniu–wrześniu)
to w całości najmy zakończone wyprowadzką **przed** końcem umowy: takich umów `retencja_decyzje` nie zawiera wcale.

| Typ | Wiele lokali (B2B) | Wyprowadzka przed końcem umowy | Umowy poza retencja_decyzje |
|---|---|---|---:|
| przedłużenie | nie | tak | 81 |
| pierwsza | nie | tak | 51 |
| pierwsza | tak | tak | 27 |

| W retencja_decyzje (I–IX 2026) | Wiele lokali (B2B) | Umowy |
|---|---|---:|
| bez wcześniejszej wyprowadzki | nie | 4 037 |
| bez wcześniejszej wyprowadzki | tak | 291 |

## SQL i kod

Wszystkie zapytania uruchamiane na `domilo.duckdb` przez `api.adapters.duckdb_baza.polacz()` (strefa sesji
Europe/Warsaw, ścieżki względne od katalogu repozytorium). Uruchomienie z katalogu głównego repozytorium.

### Zakres dat (tabela 1)

```python
"""Liczba wierszy i zakres dat każdej tabeli i widoku w domilo.duckdb."""

import sys

sys.path.insert(0, "api")
from api.adapters.duckdb_baza import polacz  # noqa: E402

con = polacz()
obiekty = con.execute(
    "SELECT table_name, table_type FROM information_schema.tables ORDER BY table_type, table_name"
).fetchall()
# Kolumny dat: typy DATE/TIMESTAMP* oraz tekstowe kolumny „miesiac” w formacie RRRR-MM.
kolumny = con.execute(
    """SELECT table_name, column_name, data_type FROM information_schema.columns
       WHERE data_type LIKE 'DATE%' OR data_type LIKE 'TIMESTAMP%'
          OR (column_name = 'miesiac' AND data_type = 'VARCHAR')
       ORDER BY table_name, ordinal_position"""
).fetchall()
print("| Tabela | Typ | Wiersze | Kolumna daty | Min | Max | Puste | < 2023-01-01 | > dzień eksportu |")
print("|---|---|---:|---|---|---|---:|---:|---:|")
for tabela, typ in obiekty:
    n = con.execute(f'SELECT count(*) FROM "{tabela}"').fetchone()[0]
    kol = [(c, t) for tb, c, t in kolumny if tb == tabela]
    if not kol:
        print(f"| {tabela} | {typ} | {n:,} | — | | | | | |".replace(",", " "))
    for c, t in kol:
        if t == "VARCHAR":  # 'RRRR-MM'
            warunek_przed, warunek_po, pokaz = f"{c} < '2023-01'", f"{c} > '2026-09'", c
        else:  # TIMESTAMP = czas lokalny; TIMESTAMPTZ porównywany w strefie sesji Europe/Warsaw
            warunek_przed = f"{c} < TIMESTAMP '2023-01-01'"
            warunek_po = f"{c} >= TIMESTAMP '2026-10-01'"
            pokaz = f"strftime({c}, '%Y-%m-%d %H:%M')"
        mn, mx, puste, p1, p2 = con.execute(
            f"""SELECT min({pokaz}), max({pokaz}), count(*) - count({c}),
                       count(*) FILTER ({warunek_przed}), count(*) FILTER ({warunek_po})
                FROM "{tabela}" """
        ).fetchone()
        mn, mx = (str(x).removesuffix(" 00:00") if x else "" for x in (mn, mx))
        print(f"| {tabela} | {typ} | {n:,} | {c} | {mn} | {mx} | {puste:,} | {p1:,} | {p2:,} |".replace(",", " "))
```

### Spójność kluczy (tabela 2)

```sql
SELECT 'lokal → budynek' AS relacja, count(*) AS wiersze,
       count(*) FILTER (l.id_budynku IS NULL) AS bez_klucza,
       count(*) FILTER (l.id_budynku IS NOT NULL AND b.id_budynku IS NULL) AS klucz_nie_istnieje
FROM pms_lokale l LEFT JOIN pms_budynki b USING (id_budynku)
UNION ALL
SELECT 'najem → lokal', count(*), count(*) FILTER (n.id_lokalu IS NULL),
       count(*) FILTER (n.id_lokalu IS NOT NULL AND l.id_lokalu IS NULL)
FROM pms_najmy n LEFT JOIN pms_lokale l USING (id_lokalu)
UNION ALL
SELECT 'umowa → najem', count(*), count(*) FILTER (u.id_najmu IS NULL),
       count(*) FILTER (u.id_najmu IS NOT NULL AND n.id_najmu IS NULL)
FROM pms_umowy u LEFT JOIN pms_najmy n USING (id_najmu)
UNION ALL
SELECT 'lead „umowa” → umowa PMS', count(*), count(*) FILTER (ld.id_umowy IS NULL),
       count(*) FILTER (ld.id_umowy IS NOT NULL AND u.id_umowy IS NULL)
FROM crm_leady ld LEFT JOIN pms_umowy u USING (id_umowy) WHERE ld.status = 'umowa'
UNION ALL
SELECT 'winda → budynek', count(*), count(*) FILTER (w.id_budynku IS NULL),
       count(*) FILTER (w.id_budynku IS NOT NULL AND b.id_budynku IS NULL)
FROM serwis_windy w LEFT JOIN pms_budynki b USING (id_budynku);
```

```sql
-- Czy liczba lokali i wind w budynku zgadza się z pms_budynki.liczba_lokali / liczba_wind
WITH l AS (SELECT id_budynku, count(*) AS lokale FROM pms_lokale GROUP BY ALL),
     w AS (SELECT id_budynku, count(*) AS windy FROM serwis_windy GROUP BY ALL)
SELECT count(*) AS budynki,
       count(*) FILTER (coalesce(l.lokale, 0) <> b.liczba_lokali) AS niezgodna_liczba_lokali,
       count(*) FILTER (coalesce(w.windy, 0) <> b.liczba_wind) AS niezgodna_liczba_wind,
       count(*) FILTER (b.liczba_wind = 0) AS budynki_bez_wind
FROM pms_budynki b LEFT JOIN l USING (id_budynku) LEFT JOIN w USING (id_budynku);
```

```sql
-- Leady „umowa”: typ powiązanej umowy, unikalność id_umowy, kolejność dat
SELECT u.typ AS typ_umowy, count(*) AS leady, count(DISTINCT ld.id_umowy) AS rozne_umowy,
       count(*) FILTER (u.data_podpisania IS NOT NULL AND u.data_podpisania < CAST(ld.utworzono AS DATE)) AS podpisana_przed_leadem
FROM crm_leady ld JOIN pms_umowy u USING (id_umowy)
WHERE ld.status = 'umowa' GROUP BY ALL ORDER BY leady DESC;

-- Leady z innym statusem a id_umowy
SELECT status, count(*), count(id_umowy) FROM crm_leady GROUP BY ALL;
```

```sql
-- Zgłoszenia Serwisownika → urządzenie (windy z serwis_windy, ciepło z telemetra_urzadzenia_ciepla)
WITH urzadzenia AS (
    SELECT id_windy AS id_urzadzenia, 'winda' AS rodzaj, id_budynku FROM serwis_windy
    UNION ALL
    SELECT id_urzadzenia, CASE typ WHEN 'wezel' THEN 'węzeł' ELSE typ END, id_budynku FROM telemetra_urzadzenia_ciepla
)
SELECT z.typ_urzadzenia, count(*) AS zgloszenia,
       count(*) FILTER (z.id_urzadzenia IS NULL) AS bez_urzadzenia,
       round(100.0 * count(*) FILTER (z.id_urzadzenia IS NULL) / count(*), 1) AS proc_bez_urzadzenia,
       count(*) FILTER (z.id_urzadzenia IS NOT NULL AND u.id_urzadzenia IS NULL) AS urzadzenie_nie_istnieje,
       count(*) FILTER (u.rodzaj IS NOT NULL AND u.rodzaj <> z.typ_urzadzenia) AS urzadzenie_innego_typu,
       count(*) FILTER (u.id_budynku IS NOT NULL AND u.id_budynku <> z.id_budynku) AS urzadzenie_z_innego_budynku
FROM serwis_zgloszenia z LEFT JOIN urzadzenia u USING (id_urzadzenia)
GROUP BY ROLLUP (z.typ_urzadzenia) ORDER BY zgloszenia DESC;
```

### Obłożenie (tabela 3)

```sql
-- Obłożenie na koniec dnia 2026-09-30: lokal zajęty, jeśli ma najem z wprowadzeniem do tego dnia
-- i bez wyprowadzenia albo z wyprowadzeniem po tym dniu.
WITH aktywne AS (
    SELECT id_lokalu, count(*) AS najmy
    FROM pms_najmy
    WHERE data_wprowadzenia <= DATE '2026-09-30'
      AND (data_wyprowadzenia IS NULL OR data_wyprowadzenia > DATE '2026-09-30')
    GROUP BY ALL
)
SELECT coalesce(b.miasto, 'RAZEM') AS miasto,
       count(*) AS lokale,
       count(a.id_lokalu) AS zajete_wg_najmow,
       round(100.0 * count(a.id_lokalu) / count(*), 1) AS oblozenie_proc,
       count(*) FILTER (l.status = 'zajęty') AS zajete_wg_statusu,
       count(*) FILTER (l.status = 'remont') AS w_remoncie,
       count(*) FILTER (a.najmy > 1) AS lokale_z_wieloma_najmami
FROM pms_lokale l JOIN pms_budynki b USING (id_budynku) LEFT JOIN aktywne a USING (id_lokalu)
GROUP BY ROLLUP (b.miasto) ORDER BY lokale DESC;
```

```sql
-- Zgodność pms_lokale.status (stan na eksport) z aktywnymi najmami 2026-09-30
WITH aktywne AS (
    SELECT DISTINCT id_lokalu FROM pms_najmy
    WHERE data_wprowadzenia <= DATE '2026-09-30'
      AND (data_wyprowadzenia IS NULL OR data_wyprowadzenia > DATE '2026-09-30')
)
SELECT l.status, (a.id_lokalu IS NOT NULL) AS aktywny_najem, count(*) AS lokale
FROM pms_lokale l LEFT JOIN aktywne a USING (id_lokalu)
GROUP BY ALL ORDER BY ALL;
```

### Końce umów (tabela 4)

```sql
-- Okresy umów (pms_umowy) z data_do w 2026, po miesiącach i typie
SELECT strftime(data_do, '%Y-%m') AS miesiac,
       count(*) AS umowy,
       count(*) FILTER (typ = 'pierwsza') AS pierwsza,
       count(*) FILTER (typ = 'przedłużenie') AS przedluzenie,
       count(*) FILTER (typ = 'średnioterminowa') AS srednioterminowa,
       count(*) FILTER (data_do > DATE '2026-09-30') AS po_dniu_eksportu
FROM pms_umowy
WHERE data_do >= DATE '2026-01-01' AND data_do < DATE '2027-01-01'
GROUP BY ALL ORDER BY miesiac;

-- Suma roczna i część po dniu eksportu
SELECT count(*), count(*) FILTER (data_do > DATE '2026-09-30') FROM pms_umowy WHERE year(data_do) = 2026;
```

```sql
-- Kontrola krzyżowa: umowy roczne (pierwsza + przedłużenie) kończące się w 2026 vs retencja_decyzje.data_konca
WITH pms AS (
    SELECT strftime(data_do, '%Y-%m') AS miesiac, count(*) AS pms_roczne
    FROM pms_umowy WHERE typ IN ('pierwsza', 'przedłużenie') AND year(data_do) = 2026 GROUP BY ALL
), ret AS (
    SELECT strftime(data_konca, '%Y-%m') AS miesiac, count(*) AS retencja_decyzje
    FROM retencja_decyzje WHERE year(data_konca) = 2026 GROUP BY ALL
), wspolne AS (
    SELECT strftime(u.data_do, '%Y-%m') AS miesiac, count(*) AS te_same_umowy
    FROM retencja_decyzje r JOIN pms_umowy u USING (id_umowy)
    WHERE year(r.data_konca) = 2026 AND u.data_do = r.data_konca GROUP BY ALL
)
SELECT miesiac, pms_roczne, retencja_decyzje, te_same_umowy
FROM pms FULL JOIN ret USING (miesiac) FULL JOIN wspolne USING (miesiac) ORDER BY miesiac;
```

```sql
-- Umowy roczne z PMS kończące się 2026-01..09, których nie ma w retencja_decyzje: czym się różnią
SELECT u.typ,
       (u.liczba_lokali > 1) AS wiele_lokali,
       (n.data_wyprowadzenia IS NOT NULL AND n.data_wyprowadzenia < u.data_do) AS wyprowadzka_przed_koncem,
       count(*) AS umowy,
       min(date_diff('day', u.data_od, u.data_do)) AS min_dni, max(date_diff('day', u.data_od, u.data_do)) AS max_dni
FROM pms_umowy u JOIN pms_najmy n USING (id_najmu)
LEFT JOIN retencja_decyzje r USING (id_umowy)
WHERE u.typ IN ('pierwsza', 'przedłużenie') AND u.data_do BETWEEN DATE '2026-01-01' AND DATE '2026-09-30'
  AND r.id_umowy IS NULL
GROUP BY ALL ORDER BY umowy DESC;

-- To samo dla umów, które są w retencja_decyzje
SELECT (n.data_wyprowadzenia IS NOT NULL AND n.data_wyprowadzenia < u.data_do) AS wyprowadzka_przed_koncem,
       (u.liczba_lokali > 1) AS wiele_lokali, count(*) AS umowy
FROM pms_umowy u JOIN pms_najmy n USING (id_najmu) JOIN retencja_decyzje r USING (id_umowy)
WHERE u.data_do BETWEEN DATE '2026-01-01' AND DATE '2026-09-30' GROUP BY ALL;
```
