-- Rodzina `budynek`: awarie wind w budynku najemcy w 90 dniach przed migawką (opis: docs/przecieki_najemcy.md).
--
-- Zgłoszenia z serwis_zgloszenia: typ_urzadzenia = 'winda' i kategoria = 'awaria', budynek lokalu,
--   utworzono w [data_migawki - 90 dni, data_migawki). Serwisownik zapisuje czas lokalny bez strefy, a migawka to
--   północ czasu warszawskiego, więc porównujemy wprost (podwójna godzina 2025-10-26 02:00–03:00 nie ma znaczenia
--   przy granicy dnia).
-- Nie czytamy serwis_zgloszenia.status ani zamknieto (stan na eksport / zdarzenia po migawce).
-- liczba_wind: windy budynku z serwis_windy (atrybut stały); windy_awarie_90d_na_winde = NULL, gdy budynek nie
--   ma wind.
WITH m AS (
    SELECT mg.id_umowy, mg.data_migawki, l.id_budynku
    FROM migawki_najemcy AS mg
    JOIN pms_lokale AS l USING (id_lokalu)
),
windy AS (
    SELECT id_budynku, count(*) AS liczba_wind
    FROM serwis_windy
    GROUP BY id_budynku
),
awarie AS (
    SELECT m.id_umowy, count(*) AS windy_awarie_90d
    FROM m
    JOIN serwis_zgloszenia AS z
        ON z.id_budynku = m.id_budynku
       AND z.typ_urzadzenia = 'winda'
       AND z.kategoria = 'awaria'
       AND z.utworzono >= (m.data_migawki - 90)::TIMESTAMP
       AND z.utworzono < m.data_migawki::TIMESTAMP
    GROUP BY m.id_umowy
)
SELECT
    m.id_umowy,
    coalesce(w.liczba_wind, 0) AS liczba_wind,
    coalesce(a.windy_awarie_90d, 0) AS windy_awarie_90d,
    coalesce(a.windy_awarie_90d, 0) / nullif(w.liczba_wind, 0) AS windy_awarie_90d_na_winde
FROM m
LEFT JOIN windy AS w USING (id_budynku)
LEFT JOIN awarie AS a USING (id_umowy)
