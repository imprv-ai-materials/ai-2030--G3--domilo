-- dni_wind: target modelu „awaria windy w ciągu 7 dni” (opis, przypadki brzegowe i liczby: docs/b4_target.md).
--
-- Jeden wiersz = winda × dzień t (2023-03-01 – 2026-09-22). Model ocenia windę codziennie o 06:00 czasu
-- Europe/Warsaw (moment_predykcji) i odpowiada, czy w oknie (06:00 dnia t; 06:00 dnia t+7] zacznie się awaria.
--
-- awaria_7d = 1, gdy start awarii z awarie_odtworzone tej windy wypada w oknie: po moment_predykcji (start dokładnie
--   o 06:00 dnia t należy do okna dnia t−1) i najpóźniej w koniec_okna (start o 06:00 dnia t+7 należy do okna).
--   Start = start_awarii_tz (telemetria); bez serii przestoju (zrodlo_startu = 'brak_serii') pierwsze zgłoszenie,
--   tak jak czas_awarii w awarie_odtworzone.
-- Pomijamy dzień t, gdy o 06:00 winda stoi z powodu awarii: moment_predykcji w (start_awarii_tz; koniec przestoju],
--   gdzie koniec przestoju = koniec ostatniego martwego okna = start_awarii_tz + okna_przestoju × 10 min (telemetria
--   nie ma luk; to ten sam moment co koniec_przestoju, ale bez niejednoznacznej godziny przy zmianie czasu).
--   Awaria bez serii przestoju nie pomija żadnego dnia (nie znamy jej przestoju).
-- Zakres windy: dni, w których o 06:00 jest już telemetria windy (pierwsze okno <= moment_predykcji), a całe okno
--   mieści się w telemetrii (koniec_okna <= ostatnie okno). Start awarii pochodzi z telemetrii, więc poza nią target
--   byłby zawsze 0. (Windy B37 i B38 mają telemetrię od 2024-09-15.)
-- Czas: dzień + 06:00 to czas lokalny; timezone('Europe/Warsaw', ...) zamienia go na moment niezależnie od strefy
--   sesji, więc okno ze zmianą czasu ma 167 h albo 169 h, a 06:00 zawsze istnieje (zmiana czasu jest o 02:00–03:00).
-- id_awarii, podzespol, liczba_awarii_7d, godziny_do_startu opisują przyszłość: do analizy targetu, NIE jako cechy.
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
    d.id_windy,
    d.id_budynku,
    d.producent,
    d.dzien,
    d.moment_predykcji,
    d.koniec_okna,
    CAST(a.id_windy IS NOT NULL AS INTEGER) AS awaria_7d,
    coalesce(a.liczba_awarii_7d, 0) AS liczba_awarii_7d,
    a.id_awarii,
    a.podzespol,
    a.godziny_do_startu
FROM dni_bez_postoju AS d
LEFT JOIN awarie_w_oknie AS a USING (id_windy, dzien)
ORDER BY d.dzien, d.id_windy
