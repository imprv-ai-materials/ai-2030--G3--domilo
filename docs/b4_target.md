# Target modelu „awaria windy w ciągu 7 dni” (B4): tabela `dni_wind`

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` z tabelą `awarie_odtworzone`
(1 540 awarii, [b4_historia_awarii.md](b4_historia_awarii.md)). Tabela `dni_wind` zbudowana 2026-11-16
(`python -m api.ai.features.windy.dni_wind`, krok `pypyr baza` po `awarie_odtworzone`).

## Wnioski

1. Codzienna ocena każdej windy o 06:00 daje 174 622 dni do nauki modelu (140 wind, 2023-03-01 – 2026-09-22).
   W 10 059 z nich (5,76%) w ciągu następnych 7 dni zaczęła się awaria. Model będzie więc szukał mniej więcej
   jednego dnia alarmowego na 17.
2. Różnice między producentami są niewielkie: od 5,30% dni z awarią w windach Dźwigmet do 6,56% w windach Liftar.
   Między latami odsetek też jest stabilny (5,62–6,00%).
3. Ponad jedna piąta dni z awarią (22,0%) dotyczy awarii z przyczyną zewnętrzną (zalanie, burza, wandalizm).
   Takich awarii czujniki windy nie zapowiedzą, więc nawet dobry model część alarmów przegapi z założenia.
4. Pominęliśmy 1 454 dni, w których o 06:00 winda stała z powodu wcześniejszej awarii. Ostrzeganie o awarii
   windy, która już stoi, nie ma sensu. Dzień, w którym awaria zacznie się dopiero po 06:00, zostaje w danych:
   to najcenniejszy alarm, bo awaria nastąpi w ciągu kilkunastu godzin.
5. Każda z 1 479 awarii, które zaczęły się w zakresie tabeli, ma co najmniej jeden dzień z alarmem, więc żadnej
   awarii nie zgubiliśmy przez pomijanie dni.

## Definicja

**Wiersz** = winda × dzień `t`. **Chwila predykcji** `moment_predykcji` = `t` 06:00 Europe/Warsaw.
**Okno** = (06:00 dnia `t`; 06:00 dnia `t+7`], czyli lewostronnie otwarte i prawostronnie domknięte.

**`awaria_7d` = 1**, gdy w oknie wypada start co najmniej jednej awarii tej windy z `awarie_odtworzone`.
Start = `start_awarii_tz` (koniec ostatniego 10-minutowego okna telemetrii z jazdą przed postojem).
Gdy awaria nie ma serii przestoju (`zrodlo_startu = 'brak_serii'`), start = pierwsze zgłoszenie, tak jak
`czas_awarii` w `awarie_odtworzone`. Dotyczy to jednej awarii: B32-W2/Z012353, 2024-12-18 20:31 (T5).

**Pomijamy dzień** `t`, gdy o 06:00 winda stoi z powodu awarii, czyli `moment_predykcji` wypada w
(`start_awarii_tz`; koniec przestoju]. Koniec przestoju to koniec ostatniego martwego okna, równy
`start_awarii_tz + okna_przestoju × 10 min`. Jest to ten sam moment co `koniec_przestoju`, sprawdzone zapytaniem:
0 różnic na 1 539 awariach.

**Zakres windy:** od 2023-03-01 (albo od dnia, w którym o 06:00 jest już telemetria windy) do 2026-09-22 (albo do
dnia, którego całe okno mieści się w telemetrii). Start awarii pochodzi z telemetrii, więc poza nią target byłby
zawsze 0. W praktyce dotyczy to 11 wind budynków B37 i B38, które mają telemetrię od 2024-09-15.

Kolumny `liczba_awarii_7d`, `id_awarii`, `podzespol` (pierwszej awarii w oknie) i `godziny_do_startu` opisują
przyszłość. Służą do analizy targetu i **nie mogą być cechami modelu**.

### Przypadki brzegowe

| Przypadek | Jak traktujemy | Ile w danych |
|---|---|---|
| Start dokładnie o 06:00 dnia `t` | Należy do okna dnia `t−1` (koniec domknięty), nie do okna dnia `t` (początek otwarty). O 06:00 winda jeszcze jeździła (start = koniec okna z jazdą), więc dzień `t` nie jest pomijany. | 8 awarii (T7) |
| Start dokładnie o 06:00 dnia `t+7` | `awaria_7d = 1` dla dnia `t` | w tych samych 8 |
| Zmiana czasu w tygodniu okna | Oba końce okna to 06:00 czasu lokalnego, więc okno ma 167 h (marzec) albo 169 h (październik). 06:00 zawsze istnieje, bo zmiana czasu jest o 02:00–03:00. | 6 583 wierszy (T7) |
| Winda stoi o 06:00 z powodu awarii | Dzień pominięty | 1 454 dni z 941 awarii |
| Awaria zaczyna się w dniu `t` po 06:00 | Dzień zostaje, `awaria_7d = 1` (wariant „pomiń cały dzień kalendarzowy” usunąłby wszystkie takie dni, T4) | 1 284 dni (`godziny_do_startu < 18`) |
| Przestój kończy się po 06:00, bo po naprawie w nocy nikt nie jeździł | Dzień pominięty, choć winda mogła być już sprawna. Telemetria nie odróżnia naprawionej windy od windy nieużywanej w nocy. | do 97 dni (przestój kończy się do 1 h po 06:00) |
| Kilka awarii w jednym oknie | `awaria_7d = 1`; `id_awarii` i `podzespol` pierwszej według startu, `liczba_awarii_7d` = ile | 152 wiersze (T1) |
| Kolejna awaria tuż po długim przestoju | Dni przestoju poprzedniej awarii są pominięte, więc kolejna awaria ma mniej niż 7 dni z alarmem | 81 awarii (T5) |
| Przestój dłuższy niż 7 dni | Dni postoju pominięte; każda awaria i tak ma co najmniej jeden dzień z alarmem | 6 przestojów, najdłuższy 10,01 dnia (T7) |
| Awaria bez serii przestoju | Start = pierwsze zgłoszenie; dni nie pomijamy, bo przestój nieznany | 1 awaria |
| Postój bez awarii (noc, konserwacja, `tryb = 'serwis'`) | Dzień zostaje; to nie jest awaria | — |
| Koniec danych | Ostatnie okno kończy się 2026-09-29 06:00. Najdłuższy czas od startu awarii do zgłoszenia to 768 min, a Serwisownik sięga do 2026-09-30 23:59, więc awarie z ostatnich okien zdążyły zostać zgłoszone | — |
| Zakres przed 2023-03-01 | Awarie ze startem do 2023-03-01 06:00 nie są targetem, ale ich przestój może pominąć pierwsze dni marca | 60 awarii |
| `pms_budynki.data_przejecia` | Nie używamy. Budynki B26 i B31–B36 mają awarie odtworzone sprzed tej daty (26 awarii), więc Serwisownik i telemetria obejmują je wcześniej | — |

**Uwaga o czasie (DuckDB 2.0):** odejmowanie dwóch `TIMESTAMPTZ` daje interwał w dniach kalendarzowych, a `epoch()`
liczy taki dzień jako 24 h. Różnica 2025-03-25 06:00 → 2025-04-01 06:00 wychodzi więc „7 days” = 168 h zamiast 167 h.
Dlatego `godziny_do_startu` to `epoch(a) − epoch(b)` (pilnuje tego test). To samo dotyczy `przestoj_h` w
`awarie_odtworzone`: 6 z 1 539 awarii ma przestój różny od `okna_przestoju × 10 min` o więcej niż minutę
(zapytanie niżej).

## Tabele

### T1. Ogółem

| wiersze | windy | pierwszy_dzien | ostatni_dzien | dodatnie | proc_dodatnich | wiersze_z_2_i_wiecej_awariami |
|---|---|---|---|---|---|---|
| 174 622 | 140 | 2023-03-01 | 2026-09-22 | 10 059 | 5,76 | 152 |

### T2. Według producenta

| producent | windy | wiersze | dodatnie | proc_dodatnich |
|---|---|---|---|---|
| Dźwigmet | 46 | 59 422 | 3 149 | 5,30 |
| Elmont | 22 | 28 415 | 1 712 | 6,02 |
| Liftar | 38 | 42 871 | 2 813 | 6,56 |
| Vertica | 34 | 43 914 | 2 385 | 5,43 |
| RAZEM | 140 | 174 622 | 10 059 | 5,76 |

### T3. Według roku dnia predykcji (2023 od 1 marca, 2026 do 22 września)

| rok | wiersze | dodatnie | proc_dodatnich |
|---|---|---|---|
| 2023 | 39 154 | 2 199 | 5,62 |
| 2024 | 48 023 | 2 732 | 5,69 |
| 2025 | 50 671 | 2 923 | 5,77 |
| 2026 | 36 774 | 2 205 | 6,00 |
| RAZEM | 174 622 | 10 059 | 5,76 |

### T4. Pominięte dni i odrzucony wariant „cały dzień kalendarzowy”

`dni_z_telemetria` = winda × dzień przed pominięciem postojów. Wariant odrzucony pomijałby każdy dzień, w którego
dobie [00:00; 24:00) winda choć przez chwilę stała z powodu awarii. Usunąłby dodatkowo 1 688 dni, w tym 1 306 z
`awaria_7d = 1`, z czego 1 284 to dni, w których awaria zaczęła się po 06:00 tego samego dnia (`godziny_do_startu < 18`).

| dni_z_telemetria | w_dni_wind | pominiete_winda_stoi_o_6 | dodatkowo_pominiete_w_wariancie_caly_dzien | w_tym_dodatnie | w_tym_dodatnie_ze_startem_tego_dnia |
|---|---|---|---|---|---|
| 176 076 | 174 622 | 1 454 | 1 688 | 1 306 | 1 284 |

Pominięte dni według awarii, która trwa o 06:00: 1 454 dni z 941 awarii; w 97 z nich przestój kończy się
najpóźniej o 07:00, a mediana czasu od 06:00 do końca przestoju to 14,9 h.

### T5. Pokrycie awarii

`start_w_zakresie_dni_wind` = start po pierwszej chwili predykcji windy i najpóźniej w ostatnim końcu okna.
61 awarii spoza zakresu: 60 zaczęło się najpóźniej 2023-03-01 06:00, a 1 po 2026-09-29 06:00 (zapytanie
w „Kontrolach”).

| awarie_odtworzone | start_w_zakresie_dni_wind | z_dniem_dodatnim | bez_dnia_dodatniego | z_mniej_niz_7_dniami_dodatnimi | start_z_pierwszego_zgloszenia |
|---|---|---|---|---|---|
| 1 540 | 1 479 | 1 479 | 0 | 81 | 1 |

### T6. Dni z awarią według podzespołu pierwszej awarii w oknie

| podzespol | dodatnie | proc |
|---|---|---|
| drzwi | 3 407 | 33,90 |
| zewnetrzna | 2 217 | 22,00 |
| naped | 1 508 | 15,00 |
| brak | 1 046 | 10,40 |
| sterownik | 1 027 | 10,20 |
| hamulec_liny | 854 | 8,50 |
| RAZEM | 10 059 | 100,00 |

### T7. Przypadki brzegowe w danych

`okna_ze_zmiana_czasu` = wiersze, których okno nie ma 168 h; `max_min_start_do_zgloszenia` w minutach.

| starty_dokladnie_o_6 | przestoje_ponad_7_dni | najdluzszy_przestoj_dni | okna_ze_zmiana_czasu | max_min_start_do_zgloszenia | ostatni_koniec_okna |
|---|---|---|---|---|---|
| 8 | 6 | 10,01 | 6 583 | 768,00 | 2026-09-29 06:00 +0200 |

## SQL i kod

Powtórzenie (z katalogu głównego repozytorium; `awarie_odtworzone` wymaga pliku ekstrakcji LLM, patrz
[b4_historia_awarii.md](b4_historia_awarii.md)):

```bash
poetry run pypyr baza                                              # ... awarie_odtworzone, dni_wind
cd api && poetry run python -m api.ai.failure_model.evals.target   # tabele T1–T7 (Markdown)
poetry run pytest tests/test_dni_wind.py                           # okno, pominięcia, zmiana czasu
```

Kod: `api/api/ai/features/windy/dni_wind.sql` i `dni_wind.py` (tabela `dni_wind`),
`api/api/ai/failure_model/evals/target.py` (zapytania T1–T7), test `api/tests/test_dni_wind.py`.

### Tabela `dni_wind` (`api/api/ai/features/windy/dni_wind.sql`)

```sql
WITH windy AS (
    SELECT w.id_windy, w.id_budynku, w.producent, min(t.ts_utc) AS pierwsze_okno, max(t.ts_utc) AS ostatnie_okno
    FROM serwis_windy AS w
    JOIN telemetra_windy AS t USING (id_windy)
    GROUP BY w.id_windy, w.id_budynku, w.producent
),
dni AS (
    SELECT
        w.id_windy, w.id_budynku, w.producent,
        CAST(d.dzien AS DATE) AS dzien,
        timezone('Europe/Warsaw', d.dzien + INTERVAL 6 HOUR) AS moment_predykcji,
        timezone('Europe/Warsaw', d.dzien + INTERVAL 7 DAY + INTERVAL 6 HOUR) AS koniec_okna,
        w.pierwsze_okno, w.ostatnie_okno
    FROM windy AS w
    CROSS JOIN generate_series(TIMESTAMP '2023-03-01', TIMESTAMP '2026-09-22', INTERVAL 1 DAY) AS d(dzien)
),
dni_z_telemetria AS (
    SELECT * EXCLUDE (pierwsze_okno, ostatnie_okno)
    FROM dni
    WHERE moment_predykcji >= pierwsze_okno AND koniec_okna <= ostatnie_okno
),
awarie AS (
    SELECT
        id_awarii, id_windy, podzespol,
        coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS start_tz,
        start_awarii_tz + okna_przestoju * INTERVAL 10 MINUTE AS koniec_przestoju_tz,
        start_awarii_tz
    FROM awarie_odtworzone
),
dni_bez_postoju AS (
    SELECT d.*
    FROM dni_z_telemetria AS d
    WHERE NOT EXISTS (
        SELECT 1
        FROM awarie AS a
        WHERE a.id_windy = d.id_windy
          AND d.moment_predykcji > a.start_awarii_tz
          AND d.moment_predykcji <= a.koniec_przestoju_tz
    )
),
awarie_w_oknie AS (
    SELECT
        d.id_windy, d.dzien,
        count(*) AS liczba_awarii_7d,
        arg_min(a.id_awarii, a.start_tz) AS id_awarii,
        arg_min(a.podzespol, a.start_tz) AS podzespol,
        round((epoch(min(a.start_tz)) - epoch(any_value(d.moment_predykcji))) / 3600, 2) AS godziny_do_startu
    FROM dni_bez_postoju AS d
    JOIN awarie AS a
        ON a.id_windy = d.id_windy
       AND a.start_tz > d.moment_predykcji
       AND a.start_tz <= d.koniec_okna
    GROUP BY d.id_windy, d.dzien
)
SELECT
    d.id_windy, d.id_budynku, d.producent, d.dzien, d.moment_predykcji, d.koniec_okna,
    CAST(a.id_windy IS NOT NULL AS INTEGER) AS awaria_7d,
    coalesce(a.liczba_awarii_7d, 0) AS liczba_awarii_7d,
    a.id_awarii, a.podzespol, a.godziny_do_startu
FROM dni_bez_postoju AS d
LEFT JOIN awarie_w_oknie AS a USING (id_windy, dzien)
ORDER BY d.dzien, d.id_windy
```

### T1–T3

```sql
-- T1
SELECT count(*) AS wiersze, count(DISTINCT id_windy) AS windy, min(dzien) AS pierwszy_dzien,
    max(dzien) AS ostatni_dzien, sum(awaria_7d) AS dodatnie, round(100.0 * avg(awaria_7d), 2) AS proc_dodatnich,
    count(*) FILTER (liczba_awarii_7d >= 2) AS wiersze_z_2_i_wiecej_awariami
FROM dni_wind;

-- T2 (T3: year(dzien) zamiast producent)
SELECT coalesce(producent, 'RAZEM') AS producent, count(DISTINCT id_windy) AS windy, count(*) AS wiersze,
    sum(awaria_7d) AS dodatnie, round(100.0 * avg(awaria_7d), 2) AS proc_dodatnich
FROM dni_wind
GROUP BY ROLLUP (producent)
ORDER BY producent IS NULL, producent;
```

### T4–T7

Wspólne CTE (`awarie` i `dni_z_telemetria` jak w `dni_wind.sql`) są w `target.py` (stałe `AWARIE`,
`DNI_Z_TELEMETRIA`).

```sql
-- T4: wariant „cały dzień kalendarzowy”
caly_dzien AS (
    SELECT DISTINCT d.id_windy, d.dzien
    FROM dni_wind AS d
    JOIN awarie AS a
        ON a.id_windy = d.id_windy
       AND a.start_awarii_tz < timezone('Europe/Warsaw', d.dzien + INTERVAL 1 DAY)
       AND a.koniec_przestoju_tz > timezone('Europe/Warsaw', CAST(d.dzien AS TIMESTAMP))
)
SELECT
    (SELECT count(*) FROM dni_z_telemetria) AS dni_z_telemetria,
    (SELECT count(*) FROM dni_wind) AS w_dni_wind,
    (SELECT count(*) FROM dni_z_telemetria) - (SELECT count(*) FROM dni_wind) AS pominiete_winda_stoi_o_6,
    (SELECT count(*) FROM caly_dzien) AS dodatkowo_pominiete_w_wariancie_caly_dzien,
    (SELECT count(*) FROM caly_dzien JOIN dni_wind USING (id_windy, dzien) WHERE awaria_7d = 1) AS w_tym_dodatnie,
    (SELECT count(*) FROM caly_dzien JOIN dni_wind USING (id_windy, dzien)
      WHERE awaria_7d = 1 AND godziny_do_startu < 18) AS w_tym_dodatnie_ze_startem_tego_dnia;

-- T4, pominięte dni według awarii trwającej o 06:00
SELECT count(*), count(*) FILTER (a.koniec_przestoju_tz <= d.moment_predykcji + INTERVAL 1 HOUR),
    count(DISTINCT a.id_awarii), median((epoch(a.koniec_przestoju_tz) - epoch(d.moment_predykcji)) / 3600)
FROM dni_z_telemetria AS d
JOIN awarie AS a
    ON a.id_windy = d.id_windy
   AND d.moment_predykcji > a.start_awarii_tz AND d.moment_predykcji <= a.koniec_przestoju_tz;

-- T5
okno AS (SELECT id_windy, min(moment_predykcji) AS od, max(koniec_okna) AS do FROM dni_wind GROUP BY id_windy),
pokrycie AS (
    SELECT a.*,
        a.start_tz > o.od AND a.start_tz <= o.do AS w_zakresie,
        EXISTS (SELECT 1 FROM dni_wind AS d WHERE d.id_windy = a.id_windy
                  AND a.start_tz > d.moment_predykcji AND a.start_tz <= d.koniec_okna) AS ma_dzien_dodatni,
        (SELECT count(*) FROM dni_wind AS d WHERE d.id_windy = a.id_windy
           AND a.start_tz > d.moment_predykcji AND a.start_tz <= d.koniec_okna) AS dni_dodatnie
    FROM awarie AS a JOIN okno AS o USING (id_windy)
)
SELECT count(*) AS awarie_odtworzone,
    count(*) FILTER (w_zakresie) AS start_w_zakresie_dni_wind,
    count(*) FILTER (w_zakresie AND ma_dzien_dodatni) AS z_dniem_dodatnim,
    count(*) FILTER (w_zakresie AND NOT ma_dzien_dodatni) AS bez_dnia_dodatniego,
    count(*) FILTER (w_zakresie AND dni_dodatnie < 7) AS z_mniej_niz_7_dniami_dodatnimi,
    count(*) FILTER (w_zakresie AND zrodlo_startu <> 'telemetria') AS start_z_pierwszego_zgloszenia
FROM pokrycie;

-- T6
SELECT coalesce(podzespol, 'RAZEM') AS podzespol, count(*) AS dodatnie,
    round(100.0 * count(*) / sum(count(*)) FILTER (podzespol IS NOT NULL) OVER (), 1) AS proc
FROM dni_wind WHERE awaria_7d = 1
GROUP BY ROLLUP (podzespol)
ORDER BY podzespol IS NULL, dodatnie DESC;

-- T7
SELECT
    (SELECT count(*) FROM awarie
      WHERE strftime(timezone('Europe/Warsaw', start_tz), '%H:%M') = '06:00') AS starty_dokladnie_o_6,
    (SELECT count(*) FROM awarie WHERE koniec_przestoju_tz - start_awarii_tz > INTERVAL 7 DAY) AS przestoje_ponad_7_dni,
    (SELECT max(okna_przestoju) / 6.0 / 24 FROM awarie) AS najdluzszy_przestoj_dni,
    (SELECT count(*) FROM dni_wind
      WHERE (epoch(koniec_okna) - epoch(moment_predykcji)) / 3600 <> 168) AS okna_ze_zmiana_czasu,
    (SELECT max(minuty_start_do_zgloszenia) FROM awarie_odtworzone) AS max_min_start_do_zgloszenia,
    (SELECT max(koniec_okna) FROM dni_wind) AS ostatni_koniec_okna;
```

### Kontrole użyte w opisie

```sql
-- koniec przestoju z okien = koniec_przestoju z awarie_odtworzone (wynik: 0)
SELECT count(*) FROM awarie_odtworzone
WHERE start_awarii_tz + okna_przestoju * INTERVAL 10 MINUTE <> timezone('Europe/Warsaw', koniec_przestoju);

-- przestoj_h w awarie_odtworzone przesunięty o zmianę czasu (wynik: 1 539 awarii, 6 z różnicą > 1 min)
SELECT count(*), count(*) FILTER (abs(przestoj_h * 60 - okna_przestoju * 10) > 1)
FROM awarie_odtworzone WHERE okna_przestoju IS NOT NULL;

-- dni ze startem awarii tego samego dnia po 06:00 (wynik: 1 284)
SELECT count(*) FROM dni_wind WHERE godziny_do_startu < 18;

-- awarie spoza zakresu dni_wind (wynik: 60, 1)
SELECT
    count(*) FILTER (coalesce(start_awarii_tz, pierwsze_zgloszenie::TIMESTAMPTZ) <= TIMESTAMPTZ '2023-03-01 06:00+01'),
    count(*) FILTER (coalesce(start_awarii_tz, pierwsze_zgloszenie::TIMESTAMPTZ) > TIMESTAMPTZ '2026-09-29 06:00+02')
FROM awarie_odtworzone;

-- awarie sprzed pms_budynki.data_przejecia (B26: 3, B31: 1, B32: 2, B33: 3, B34: 12, B36: 5; B37, B38: 0)
SELECT b.id_budynku, CAST(b.data_przejecia AS DATE),
    (SELECT count(*) FROM awarie_odtworzone AS a
      WHERE a.id_budynku = b.id_budynku AND a.czas_awarii < b.data_przejecia) AS awarie_przed_przejeciem
FROM pms_budynki AS b WHERE b.data_przejecia >= '2023-01-01' ORDER BY 2;
```
