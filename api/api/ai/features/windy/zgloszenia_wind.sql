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
