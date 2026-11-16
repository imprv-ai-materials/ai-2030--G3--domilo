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
