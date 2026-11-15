-- Rodzina `budzet`: budżet z formularza względem mediany czynszu katalogowego lokali Domilo w mieście zapytania.
-- UWAGA: pms_lokale.czynsz_katalogowy to stan na dzień eksportu (CLAUDE.md), a nie cennik z dnia zapytania.
--   Mediana jest jedna na miasto (bez historii), więc to przybliżenie poziomu cen; zmiany cennika w latach
--   2023–2026 nie są w niej widoczne (brak w danych historii czynszów katalogowych).
-- budzet_do_mediany: NULL, gdy budżetu nie podano.
WITH mediana_miasta AS (
    SELECT b.miasto, median(l.czynsz_katalogowy) AS mediana_czynszu_miasta
    FROM pms_lokale AS l
    JOIN pms_budynki AS b USING (id_budynku)
    GROUP BY b.miasto
)
SELECT
    l.id_leada,
    l.budzet_max,
    m.mediana_czynszu_miasta,
    l.budzet_max / m.mediana_czynszu_miasta AS budzet_do_mediany
FROM crm_leady AS l
LEFT JOIN mediana_miasta AS m USING (miasto)
