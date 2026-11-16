# Cechy modelu „awaria windy w ciągu 7 dni” (B4): tabela `cechy_windy`

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw. Tabela `cechy_windy` zbudowana 2026-11-16 w `domilo.duckdb`
(`python -m api.ai.features.windy.cechy`, krok `pypyr baza` po `dni_wind`) z Parquetu
`data/telemetra/telemetra_windy/` (widok `telemetra_windy`, DuckDB). Jeden wiersz = jeden wiersz `dni_wind`
(winda × dzień oceny, target: [b4_target.md](b4_target.md)).

## Wnioski

1. Każdy z 174 622 dni oceny ma 168 cech z telemetrii. Liczymy je wyłącznie z okien 10-minutowych zakończonych
   najpóźniej o 05:50 dnia oceny i bez okien serwisowych, więc model o 06:00 widzi dokładnie to, co jest już
   w Telemetrze (test: zmiana danych po 05:50 nie zmienia cech).
2. Pojedynczo najwięcej mówią sygnały drzwi: wzrost ponownych otwarć i czasu zamykania drzwi wobec normy windy.
   Ich AUC wobec awarii w 7 dni to ok. 0,63 (C7). To opis pojedynczych cech, nie wynik modelu — model i porównanie
   z punktem odniesienia są dopiero przed nami.
3. **Pułapka firmware:** 2025-11-17 wszystkie windy Liftar dostały firmware LF-5.0.0. Od tego dnia raportują
   prawie trzy razy więcej błędów drzwi (1,29 → 3,73 na 1 000 okien) i dwa razy więcej błędów napędu i sterownika,
   choć awarii przybyło niewiele (9,28 → 10,10 na 1 000 dni pracy windy). W cechach widać to jako fałszywy alarm:
   udział dni Liftar z błędami drzwi ponad 2 × norma wzrósł z 9,1% do 35,4%. Dodaliśmy cechy kontekstu firmware,
   ale samą korektę zostawiamy do decyzji.
4. Dla rzadkich zdarzeń (błędy drzwi, napędu, sterownika, wyłączenie windy) norma liczona jako mediana z 30 dni
   wynosi prawie zawsze 0, więc „stosunek do normy” jest pusty w 90–100% wierszy. Dla tych sygnałów lepiej
   sprawdzi się inna miara (do decyzji).
5. Wibracje mamy dopiero od montażu czujników (2024-05-06, 2024-09-15 i 2025-01-13): 36,4% wierszy nie ma czujnika,
   cechy wibracji są tam puste, a flaga `ma_czujnik_wibracji` = 0.

## Definicje

**Chwila odcięcia** = 05:50 Europe/Warsaw dnia oceny `t` (ocena o 06:00; okno kończące się o 06:00 ma koniec równy
chwili oceny i nie wchodzi). **Okna:** okna 10-min z `ts_utc` w (odcięcie − 24 h; odcięcie], (odcięcie − 72 h;
odcięcie] i (odcięcie − 168 h; odcięcie], liczone w godzinach rzeczywistych, także przy zmianie czasu (tydzień
z marcową zmianą czasu ma nadal 168 h danych). Okna z `tryb = 'serwis'` są wykluczone przed liczeniem; okna
`wylaczona` zostają (np. `kursy = 0`).

Dla każdego sygnału `<s>` (11 cech):

| Cecha | Definicja |
|---|---|
| `<s>_sr_24h`, `_sr_3d`, `_sr_7d` | średnia z okien z wartością (NULL w oknie się nie liczy) |
| `<s>_max_24h`, `_max_3d`, `_max_7d` | maksimum z okien |
| `<s>_norma` | mediana średnich dobowych `<s>_sr_24h` z dni 15–44 przed oceną (doba 1 = 24 h przed odcięciem dnia `t`, czyli kotwice `t−43 … t−14`); NULL, gdy wartość ma mniej niż 20 z 30 dni |
| `<s>_do_normy_24h`, `_3d`, `_7d` | `<s>_sr_<okno> / <s>_norma`; NULL, gdy norma = 0 albo NULL |
| `<s>_trend_7d` | nachylenie prostej (`regr_slope`) średnich dobowych z dni `t−6 … t`, w jednostkach sygnału na dobę; NULL, gdy mniej niż 5 dni z wartością |

Norma i trend korzystają z dni, w których winda stała (dni pominięte w `dni_wind`): to część historii widocznej
o 06:00. Kotwice zaczynają się od pierwszego dnia telemetrii (2023-01-01; B37 i B38: 2024-09-15), więc norma dla
2023-03-01 sięga do 2023-01-17. Windy B37 i B38 mają w pierwszym tygodniu niepełne okna, a norma jest pusta przez
pierwsze 33 dni.

**Rodziny i sygnały** (`api/api/ai/features/windy/sql/<rodzina>.sql`):

| Rodzina | Sygnał (kolumna źródłowa) | Uwagi |
|---|---|---|
| drzwi | `drzwi_ponowne_otwarcia` (`ponowne_otwarcia`), `drzwi_czas_zamykania_sr` (`czas_zamykania_drzwi_sr_s`), `drzwi_czas_zamykania_max` (`czas_zamykania_drzwi_max_s`), `drzwi_bledy` (`bledy_drzwi`) | czas zamykania pusty w oknach bez jazdy |
| naped | `naped_prad_sr`, `naped_prad_max`, `naped_temp_silnika`, `naped_temp_maszynowni`, `naped_blad_poziomowania`, `naped_bledy` | prąd i poziomowanie tylko w oknach z jazdą; temperatura maszynowni jako tło |
| wibracje | `wibracje_rms` (`wibracje_rms_mg`) + `ma_czujnik_wibracji` | przed `serwis_windy.czujnik_wibracji_od` NULL (wymuszone w SQL); flaga = czujnik zamontowany przed odcięciem |
| sterownik | `sterownik_bledy` (`bledy_sterownika`) + `firmware_dni_od_zmiany`, `firmware_zmiana_glowna_44d` | kody błędów nie są osobnym sygnałem (C8) |
| uzycie | `uzycie_kursy`, `uzycie_otwarcia_drzwi`, `uzycie_wylaczona` (1 w oknie `tryb = 'wylaczona'`) | średnia `uzycie_wylaczona` = udział okien z windą wyłączoną |

15 sygnałów × 11 cech = 165 kolumn + 3 cechy dodatkowe = 168 (C1).

**Cechy dodatkowe** (`sql/wibracje_czujnik.sql`, `sql/sterownik_firmware.sql`): `firmware_dni_od_zmiany` = dni od
ostatniej zmiany `firmware` w telemetrii do odcięcia (NULL, gdy zmiany nie było od początku telemetrii);
`firmware_zmiana_glowna_44d` = 1, gdy w ostatnich 44 dniach zmieniła się wersja główna (część przed pierwszą kropką,
np. LF-4 → LF-5), czyli norma i okno pochodzą z różnych wersji firmware.

### Decyzje podjęte bez użytkownika

- Norma = mediana **średnich dobowych** (nie mediana surowych okien 10-min): okno 24 h porównujemy z typową dobą.
- Trend = nachylenie **średnich dobowych** z 7 dni (dobowy rytm jazd zakłóciłby nachylenie z okien 10-min).
- Progi kompletności: norma z ≥ 20 z 30 dni, trend z ≥ 5 z 7 dni (inaczej NULL).
- Stosunek do normy NULL przy normie 0 (bez sztucznego ε).
- Błędy LF-5 bez korekty: dodane cechy kontekstu firmware, korekta do decyzji (C4–C6).
- `kody_bledow` pominięte: są zależne od producenta i każdy kod jest już policzony w `bledy_*` (C8).

## Tabele

### C1. Kształt tabeli

| wiersze | windy | pierwszy_dzien | ostatni_dzien | wiersze_dni_wind | kolumny_cech |
|---|---|---|---|---|---|
| 174 622 | 140 | 2023-03-01 | 2026-09-22 | 174 622 | 168 |

### C2. Odsetek NULL według sygnału (%)

`sr_24h`, `sr_7d`, `norma`, `do_normy_24h`, `trend_7d` — odsetek wierszy z NULL.

| rodzina | sygnal | sr_24h | sr_7d | norma | do_normy_24h | trend_7d |
|---|---|---|---|---|---|---|
| drzwi | drzwi_ponowne_otwarcia | 0,0 | 0,0 | 0,2 | 0,2 | 0,0 |
| drzwi | drzwi_czas_zamykania_sr | 0,0 | 0,0 | 0,2 | 0,2 | 0,1 |
| drzwi | drzwi_czas_zamykania_max | 0,0 | 0,0 | 0,2 | 0,2 | 0,1 |
| drzwi | drzwi_bledy | 0,0 | 0,0 | 0,2 | 90,0 | 0,0 |
| naped | naped_prad_sr | 0,0 | 0,0 | 0,2 | 0,2 | 0,1 |
| naped | naped_prad_max | 0,0 | 0,0 | 0,2 | 0,2 | 0,1 |
| naped | naped_temp_silnika | 0,0 | 0,0 | 0,2 | 0,2 | 0,0 |
| naped | naped_temp_maszynowni | 0,0 | 0,0 | 0,2 | 0,2 | 0,0 |
| naped | naped_blad_poziomowania | 0,0 | 0,0 | 0,2 | 0,2 | 0,1 |
| naped | naped_bledy | 0,0 | 0,0 | 0,2 | 100,0 | 0,0 |
| wibracje | wibracje_rms | 36,4 | 36,4 | 39,0 | 39,0 | 36,8 |
| sterownik | sterownik_bledy | 0,0 | 0,0 | 0,2 | 99,8 | 0,0 |
| uzycie | uzycie_kursy | 0,0 | 0,0 | 0,2 | 0,2 | 0,0 |
| uzycie | uzycie_otwarcia_drzwi | 0,0 | 0,0 | 0,2 | 0,2 | 0,0 |
| uzycie | uzycie_wylaczona | 0,0 | 0,0 | 0,2 | 100,0 | 0,0 |

Norma rzadkich zdarzeń jest dodatnia tylko w części wierszy: `drzwi_bledy_norma > 0` w 17 534, `naped_bledy` w 47,
`sterownik_bledy` w 390, `uzycie_wylaczona` w 10 ze 174 622, choć średnia z 24 h jest dodatnia odpowiednio w
34 176, 9 323, 18 292 i 1 105 wierszach (zapytanie w „Kontrolach”).

### C3. Czujnik wibracji

| ma_czujnik_wibracji | wiersze | z_wibracje_sr_24h | z_norma | z_trendem | od | do |
|---|---|---|---|---|---|---|
| 0 | 63 556 | 0 | 0 | 0 | 2023-03-01 | 2025-01-12 |
| 1 | 111 066 | 111 052 | 106 462 | 110 367 | 2024-05-06 | 2026-09-22 |

Daty montażu w `serwis_windy.czujnik_wibracji_od`: 2024-05-06 (96 wind), 2024-09-15 (11), 2025-01-13 (33).
Wartości przed montażem: 0 okien; po montażu wibracje są tylko w oknach z jazdą (`kursy > 0`).

### C4. Okna 10-min 4 tygodnie przed i po aktualizacji Liftar do LF-5 (2025-11-17 02:00), tylko `tryb = 'normalny'`

Pozostali producenci w tych samych tygodniach to grupa porównawcza.

| producent | okres | okna | bledy_drzwi_na_1000_okien | bledy_napedu_na_1000_okien | bledy_sterownika_na_1000_okien | ponowne_otwarcia_sr | czas_zamykania_sr_s | prad_sr_a | kursy_sr |
|---|---|---|---|---|---|---|---|---|---|
| Dźwigmet | przed | 184 241 | 1,91 | 0,46 | 2,01 | 0,17 | 3,33 | 12,30 | 1,68 |
| Dźwigmet | po | 184 278 | 1,83 | 0,40 | 1,11 | 0,17 | 3,31 | 12,30 | 1,68 |
| Elmont | przed | 88 477 | 1,98 | 0,52 | 0,86 | 0,15 | 3,27 | 10,88 | 1,74 |
| Elmont | po | 88 291 | 2,42 | 0,40 | 0,67 | 0,15 | 3,30 | 10,89 | 1,73 |
| Liftar | przed | 151 581 | 1,29 | 0,40 | 1,09 | 0,17 | 3,21 | 11,59 | 1,74 |
| Liftar | po | 152 079 | 3,73 | 0,79 | 2,37 | 0,25 | 3,31 | 11,58 | 1,73 |
| Vertica | przed | 136 133 | 1,86 | 0,40 | 1,01 | 0,16 | 3,21 | 11,70 | 1,64 |
| Vertica | po | 136 260 | 1,78 | 0,39 | 1,98 | 0,18 | 3,23 | 11,70 | 1,65 |

Po LF-5 błąd drzwi Liftar jest zwykle raportowany parą kodów `E07|E17` (2 339 okien), więc liczy się podwójnie;
wcześniej był to jeden kod `E07` (C8). Ponowne otwarcia Liftar wzrosły o ok. połowę, a kursy się nie zmieniły.
U Vertiki błędy sterownika też wzrosły w tym okresie (1,01 → 1,98) bez zmiany firmware, więc nie każdy skok to
firmware.

### C5. Awarie przed i po LF-5 (na 1 000 dni pracy windy = okna telemetrii / 144)

| producent | okres | awarie | awarie_na_1000_winda_dni | awarie_drzwi_na_1000_winda_dni |
|---|---|---|---|---|
| Dźwigmet | przed | 364 | 7,53 | 2,28 |
| Dźwigmet | po | 113 | 7,73 | 2,94 |
| Elmont | przed | 210 | 9,08 | 3,24 |
| Elmont | po | 57 | 8,15 | 3,15 |
| Liftar | przed | 307 | 9,28 | 3,17 |
| Liftar | po | 122 | 10,10 | 3,48 |
| Vertica | przed | 279 | 7,81 | 2,88 |
| Vertica | po | 87 | 8,05 | 2,50 |

### C6. Skutek w cechach: 44 dni oceny przed i od 2025-11-18 (pierwszy dzień po aktualizacji)

| producent | okres | wiersze | drzwi_bledy_sr_7d_na_1000 | drzwi_bledy_do_normy_7d_sr | proc_do_normy_7d_ponad_2 | ponowne_otwarcia_do_normy_7d_sr | z_flaga_zmiany_glownej |
|---|---|---|---|---|---|---|---|
| Liftar | przed (44 dni) | 1 654 | 1,51 | 1,02 | 9,10 | 1,06 | 38 |
| Liftar | po (44 dni) | 1 656 | 3,35 | 2,10 | 35,40 | 1,31 | 1 619 |
| pozostali | przed (44 dni) | 4 463 | 1,98 | 1,02 | 9,00 | 1,09 | 0 |
| pozostali | po (44 dni) | 4 459 | 1,96 | 1,09 | 8,90 | 1,10 | 0 |

`drzwi_bledy_do_normy_7d_sr` i `proc_do_normy_7d_ponad_2` liczone na wierszach z niepustym stosunkiem (norma > 0).

### C7. AUC pojedynczych cech wobec `awaria_7d` (opis, nie model)

Cała tabela, NULL pominięte, tylko cechy z co najmniej 1 000 wartościami; 15 cech najdalej od 0,5, a pod nimi
najlepsza cecha pozostałych rodzin. AUC < 0,5 = wyższa wartość przy dniach bez awarii.

| cecha | wiersze_bez_null | dodatnie | auc |
|---|---|---|---|
| drzwi_ponowne_otwarcia_do_normy_24h | 174 260 | 10 042 | 0,633 |
| drzwi_czas_zamykania_max_do_normy_24h | 174 230 | 10 041 | 0,633 |
| drzwi_ponowne_otwarcia_do_normy_3d | 174 260 | 10 042 | 0,632 |
| drzwi_ponowne_otwarcia_do_normy_7d | 174 260 | 10 042 | 0,631 |
| drzwi_czas_zamykania_sr_do_normy_24h | 174 230 | 10 041 | 0,631 |
| drzwi_czas_zamykania_max_sr_24h | 174 603 | 10 058 | 0,628 |
| drzwi_czas_zamykania_max_max_24h | 174 603 | 10 058 | 0,628 |
| drzwi_czas_zamykania_max_do_normy_3d | 174 246 | 10 042 | 0,628 |
| drzwi_czas_zamykania_max_max_3d | 174 619 | 10 059 | 0,627 |
| drzwi_czas_zamykania_sr_do_normy_3d | 174 246 | 10 042 | 0,626 |
| drzwi_czas_zamykania_max_max_7d | 174 622 | 10 059 | 0,626 |
| drzwi_czas_zamykania_max_do_normy_7d | 174 249 | 10 042 | 0,626 |
| drzwi_ponowne_otwarcia_sr_24h | 174 622 | 10 059 | 0,625 |
| drzwi_czas_zamykania_sr_max_24h | 174 603 | 10 058 | 0,625 |
| drzwi_czas_zamykania_sr_do_normy_7d | 174 249 | 10 042 | 0,624 |
| naped_temp_silnika_do_normy_24h | 174 260 | 10 042 | 0,585 |
| wibracje_rms_do_normy_3d | 106 459 | 6 221 | 0,535 |
| sterownik_bledy_sr_24h | 174 622 | 10 059 | 0,514 |
| uzycie_otwarcia_drzwi_do_normy_7d | 174 260 | 10 042 | 0,482 |
| ma_czujnik_wibracji | 174 622 | 10 059 | 0,507 |
| firmware_dni_od_zmiany | 129 704 | 7 509 | 0,508 |

### C8. Kody błędów a kolumny `bledy_*` (okna z kodem, grupy z ponad 50 oknami; wybór)

Każdy kod odpowiada jednej kolumnie `bledy_*` (drzwi: DR01, ED2, E07/E17, VD3; napęd: DR21, EN4, E21, VN1;
sterownik: DR31, EC1, E31, VC7). Liczba powtórzeń kodu w oknie = wartość `bledy_*`.

| producent | firmware | kody_bledow | okna | bledy_drzwi | bledy_napedu | bledy_sterownika |
|---|---|---|---|---|---|---|
| Liftar | LF-4 | E07 | 3 173 | 3 173 | 0 | 0 |
| Liftar | LF-5 | E07 | 321 | 321 | 0 | 0 |
| Liftar | LF-5 | E07\|E17 | 2 339 | 4 678 | 0 | 0 |
| Liftar | LF-5 | E17 | 564 | 564 | 0 | 0 |
| Liftar | LF-5 | E21 | 729 | 0 | 729 | 0 |
| Liftar | LF-5 | E31 | 1 320 | 0 | 0 | 1 320 |
| Dźwigmet | DM-4 | DR01 | 11 482 | 11 482 | 0 | 0 |
| Dźwigmet | DM-4 | DR31\|DR31 | 132 | 0 | 0 | 264 |

## SQL i kod

Powtórzenie (z katalogu głównego repozytorium):

```bash
poetry run pypyr baza                                             # ... dni_wind, cechy_windy
cd api && poetry run python -m api.ai.failure_model.evals.cechy   # tabele C1–C7 (Markdown)
poetry run pytest tests/test_cechy_windy.py                       # odcięcie 05:50, okna, serwis, zmiana czasu, przeciek
```

Kod: `api/api/ai/features/windy/cechy.py` (widok `telemetria`, `kotwice`, generowanie SQL statystyk, tabela
`cechy_windy`), rodziny `api/api/ai/features/windy/sql/{drzwi,naped,wibracje,sterownik,uzycie}.sql`, cechy
dodatkowe `sql/wibracje_czujnik.sql`, `sql/sterownik_firmware.sql`; zapytania raportu
`api/api/ai/failure_model/evals/cechy.py`; test `api/tests/test_cechy_windy.py`.

### Widok `telemetria` i kotwice (`cechy.py`, `przygotuj`)

```sql
CREATE OR REPLACE TEMP VIEW telemetria AS
SELECT *
FROM telemetra_windy                                   -- read_parquet('data/telemetra/telemetra_windy/rok=*/miesiac=*/*.parquet')
WHERE tryb IS DISTINCT FROM 'serwis'
  AND ts_utc <= timezone('Europe/Warsaw', TIMESTAMP '2026-09-22 05:50');

CREATE OR REPLACE TEMP TABLE kotwice AS
WITH zakres AS (SELECT id_windy, min(ts_utc) AS od FROM telemetra_windy GROUP BY id_windy)
SELECT
    z.id_windy,
    CAST(d.dzien AS DATE) AS dzien,
    timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50') AS moment_odciecia,
    CAST(epoch(timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50')) AS BIGINT) AS odciecie_s
FROM zakres AS z
CROSS JOIN generate_series(TIMESTAMP '2023-01-01', TIMESTAMP '2026-09-22', INTERVAL 1 DAY) AS d(dzien)
WHERE timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50') >= z.od;
```

### Statystyki rodziny (SQL generowany przez `sql_rodziny`; przykład: `sterownik`, jeden sygnał)

Dla innych rodzin różnią się tylko CTE `sygnaly` (treść pliku rodziny) i lista sygnałów. Pełny SQL dowolnej
rodziny: `python -c "from api.ai.features.windy.cechy import *; ..."` → `sql_rodziny(rodzina, sygnaly(con, rodzina))`.

```sql
WITH sygnaly AS (
    SELECT id_windy, ts_utc, bledy_sterownika AS sterownik_bledy FROM telemetria   -- sql/sterownik.sql
),
godziny AS (
    -- okna 10-min -> godziny kończące się o :50 UTC: ts w (H:50 − 1 h; H:50]
    SELECT
        id_windy,
        CAST(floor((epoch(ts_utc) + 540) / 3600) * 3600 + 3000 AS BIGINT) AS koniec_godziny,
        sum(CAST(sterownik_bledy AS DOUBLE)) AS sterownik_bledy__suma, count(sterownik_bledy) AS sterownik_bledy__n,
        max(CAST(sterownik_bledy AS DOUBLE)) AS sterownik_bledy__max
    FROM sygnaly
    GROUP BY ALL
),
okna AS (
    SELECT
        k.id_windy, k.dzien,
        sum(g.sterownik_bledy__suma) FILTER (g.koniec_godziny > k.odciecie_s - 86400)
            / nullif(sum(g.sterownik_bledy__n) FILTER (g.koniec_godziny > k.odciecie_s - 86400), 0) AS sterownik_bledy_sr_24h,
        max(g.sterownik_bledy__max) FILTER (g.koniec_godziny > k.odciecie_s - 86400) AS sterownik_bledy_max_24h,
        -- ... to samo dla 259200 s (3d) i 604800 s (7d)
    FROM kotwice AS k
    LEFT JOIN godziny AS g
        ON g.id_windy = k.id_windy
       AND g.koniec_godziny > k.odciecie_s - 604800
       AND g.koniec_godziny <= k.odciecie_s
    GROUP BY k.id_windy, k.dzien
),
normy AS (
    SELECT
        *,
        CASE WHEN count(sterownik_bledy_sr_24h) OVER w_norma >= 20
             THEN median(sterownik_bledy_sr_24h) OVER w_norma END AS sterownik_bledy_norma,
        CASE WHEN regr_count(sterownik_bledy_sr_24h, nr_dnia) OVER w_trend >= 5
             THEN regr_slope(sterownik_bledy_sr_24h, nr_dnia) OVER w_trend END AS sterownik_bledy_trend_7d
    FROM (SELECT *, date_diff('day', DATE '2023-01-01', dzien) AS nr_dnia FROM okna)
    WINDOW
        w_norma AS (PARTITION BY id_windy ORDER BY dzien
                    RANGE BETWEEN INTERVAL 43 DAY PRECEDING AND INTERVAL 14 DAY PRECEDING),
        w_trend AS (PARTITION BY id_windy ORDER BY dzien
                    RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW)
)
SELECT
    id_windy, dzien,
    sterownik_bledy_sr_24h, sterownik_bledy_max_24h, sterownik_bledy_sr_3d, sterownik_bledy_max_3d,
    sterownik_bledy_sr_7d, sterownik_bledy_max_7d, sterownik_bledy_norma,
    sterownik_bledy_sr_24h / nullif(sterownik_bledy_norma, 0) AS sterownik_bledy_do_normy_24h,
    sterownik_bledy_sr_3d / nullif(sterownik_bledy_norma, 0) AS sterownik_bledy_do_normy_3d,
    sterownik_bledy_sr_7d / nullif(sterownik_bledy_norma, 0) AS sterownik_bledy_do_normy_7d,
    sterownik_bledy_trend_7d
FROM normy
```

Tabela końcowa: `SELECT d.id_windy, d.dzien, <cechy rodzin i dodatkowe> FROM dni_wind AS d LEFT JOIN cechy_<rodzina>
USING (id_windy, dzien) ...` (kontrola unikalności `(id_windy, dzien)` w `zbuduj_cechy_windy`).

### C1–C6

Zapytania w `api/api/ai/failure_model/evals/cechy.py` (słownik `ZAPYTANIA`; C2 generuje `braki_md`, C7 `auc_md`
— `sklearn.metrics.roc_auc_score` na `cechy_windy JOIN dni_wind`). Najważniejsze:

```sql
-- C4 (różnica w różnicach wokół LF-5)
SELECT w.producent, CASE WHEN t.ts_utc >= TIMESTAMPTZ '2025-11-17 02:00+01' THEN 'po' ELSE 'przed' END AS okres,
    count(*) AS okna, round(1000 * avg(t.bledy_drzwi), 2) AS bledy_drzwi_na_1000_okien, ...
FROM telemetra_windy AS t JOIN serwis_windy AS w USING (id_windy)
WHERE t.tryb = 'normalny'
  AND t.ts_utc >= TIMESTAMPTZ '2025-11-17 02:00+01' - INTERVAL 28 DAY
  AND t.ts_utc <  TIMESTAMPTZ '2025-11-17 02:00+01' + INTERVAL 28 DAY
GROUP BY ALL;

-- C6 (skutek w cechach)
SELECT CASE WHEN w.producent = 'Liftar' THEN 'Liftar' ELSE 'pozostali' END AS producent,
    CASE WHEN c.dzien >= DATE '2025-11-18' THEN 'po (44 dni)' ELSE 'przed (44 dni)' END AS okres,
    count(*) AS wiersze,
    round(avg(c.drzwi_bledy_do_normy_7d), 2) AS drzwi_bledy_do_normy_7d_sr,
    round(100.0 * avg(CAST(c.drzwi_bledy_do_normy_7d > 2 AS INTEGER)), 1) AS proc_do_normy_7d_ponad_2,
    sum(c.firmware_zmiana_glowna_44d) AS z_flaga_zmiany_glownej, ...
FROM cechy_windy AS c JOIN serwis_windy AS w USING (id_windy)
WHERE c.dzien BETWEEN DATE '2025-11-18' - 44 AND DATE '2025-11-18' + 43
GROUP BY ALL;
```

### Kontrole użyte w opisie

```sql
-- aktualizacja LF-5: data i liczba wind (telemetra_firmware; wszystkie zmiany na LF-5.0.0 mają datę 2025-11-17 02:00)
SELECT wersja_na, min(data), max(data), count(DISTINCT id_windy) FROM telemetra_firmware
WHERE wersja_na LIKE 'LF-5%' GROUP BY 1;

-- C8: kody błędów a kolumny bledy_*
SELECT w.producent, split_part(t.firmware, '.', 1) AS firmware, t.kody_bledow, count(*) AS okna,
    sum(t.bledy_drzwi), sum(t.bledy_napedu), sum(t.bledy_sterownika)
FROM telemetra_windy AS t JOIN serwis_windy AS w USING (id_windy)
WHERE t.kody_bledow IS NOT NULL
GROUP BY ALL HAVING count(*) > 50 ORDER BY 1, 2, 3;

-- wibracje przed montażem (wynik: 0) i daty montażu
SELECT count(*) FILTER (t.wibracje_rms_mg IS NOT NULL AND t.ts_utc < timezone('Europe/Warsaw', w.czujnik_wibracji_od))
FROM telemetra_windy AS t JOIN serwis_windy AS w USING (id_windy);
SELECT czujnik_wibracji_od, count(*) FROM serwis_windy GROUP BY 1 ORDER BY 1;

-- norma rzadkich zdarzeń > 0 i średnia 24 h > 0 (C2)
SELECT count(*) FILTER (drzwi_bledy_norma > 0), count(*) FILTER (naped_bledy_norma > 0),
    count(*) FILTER (sterownik_bledy_norma > 0), count(*) FILTER (uzycie_wylaczona_norma > 0),
    count(*) FILTER (drzwi_bledy_sr_24h > 0), count(*) FILTER (naped_bledy_sr_24h > 0),
    count(*) FILTER (sterownik_bledy_sr_24h > 0), count(*) FILTER (uzycie_wylaczona_sr_24h > 0)
FROM cechy_windy;
```
