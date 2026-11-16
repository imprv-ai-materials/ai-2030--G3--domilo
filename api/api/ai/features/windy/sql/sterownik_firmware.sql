-- Cechy dodatkowe rodziny `sterownik`: kontekst wersji firmware w chwili odcięcia (kontrakt: wibracje_czujnik.sql).
--
-- Zmiana firmware = okno telemetrii (bez okien serwisowych), w którym `firmware` różni się od poprzedniego okna
-- tej windy. Wersja główna = część przed pierwszą kropką (np. LF-4.1.5 -> LF-4).
-- firmware_dni_od_zmiany: dni od ostatniej zmiany do chwili odcięcia; NULL, gdy od początku telemetrii zmiany nie było.
-- firmware_zmiana_glowna_44d: 1, gdy w ostatnich 44 dniach (okno normy) zmieniła się wersja główna — wtedy norma
--   i stosunek do normy porównują dwie wersje firmware (Liftar LF-5 od 2025-11-17: docs/b4_cechy.md, F1).
WITH okna AS (
    SELECT
        id_windy,
        ts_utc,
        firmware,
        lag(firmware) OVER (PARTITION BY id_windy ORDER BY ts_utc) AS poprzedni
    FROM telemetria
),
zmiany AS (
    SELECT
        id_windy,
        ts_utc,
        split_part(firmware, '.', 1) <> split_part(poprzedni, '.', 1) AS glowna
    FROM okna
    WHERE poprzedni IS NOT NULL AND firmware <> poprzedni
)
SELECT
    k.id_windy,
    k.dzien,
    round((epoch(k.moment_odciecia) - epoch(max(z.ts_utc))) / 86400, 2) AS firmware_dni_od_zmiany,
    CAST(coalesce(bool_or(z.glowna AND z.ts_utc > k.moment_odciecia - INTERVAL 44 DAY), false) AS INTEGER)
        AS firmware_zmiana_glowna_44d
FROM kotwice AS k
LEFT JOIN zmiany AS z
    ON z.id_windy = k.id_windy
   AND z.ts_utc <= k.moment_odciecia
GROUP BY k.id_windy, k.dzien, k.moment_odciecia
