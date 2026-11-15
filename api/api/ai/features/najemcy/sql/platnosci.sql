-- Rodzina `platnosci`: opóźnienia płatności z ostatnich 90 dni przed migawką (opis: docs/przecieki_najemcy.md).
--
-- Płatności najmu: pms_platnosci wszystkich umów tego najmu (id_najmu), nie tylko bieżącej.
-- Termin płatności: 10. dzień miesiąca `miesiac` (dla każdej spóźnionej płatności w danych
--   data_platnosci - dni_opoznienia wypada 10. dnia tego miesiąca).
-- Okno: miesiące z terminem płatności w [data_migawki - 90 dni, data_migawki) (zwykle 3; 4, gdy okno
--   obejmuje luty, np. migawka 2023-05-11: terminy 10.02, 10.03, 10.04 i 10.05).
-- Opóźnienie znane w dniu migawki (opoznienie_znane):
--   - zapłacona przed dniem migawki: pms_platnosci.dni_opoznienia;
--   - niezapłacona przed dniem migawki: dni od terminu do migawki (tyle zaległości widać w tym dniu).
--   Końcowe dni_opoznienia płatności zapłaconej w dniu migawki lub później to przyszłość (przeciek).
-- Gdy w oknie nie ma płatności (np. migawki przed 2023-04: pms_platnosci zaczyna się od 2023-01), liczby
--   są 0, a plat_max_opoznienie_90d i plat_srednie_opoznienie_90d są NULL.
WITH m AS (
    SELECT id_umowy, id_najmu, data_migawki
    FROM migawki_najemcy
),
-- Najem × miesiąc: w miesiącu przejścia na kolejny okres najem ma dwie płatności (stara i nowa umowa); miesiąc
-- jest zapłacony, gdy zapłacono obie (ostatnia data), a jego opóźnienie to większe z dwóch.
platnosci AS (
    SELECT
        u.id_najmu,
        strptime(p.miesiac, '%Y-%m')::DATE + 9 AS termin,
        CASE WHEN count(p.data_platnosci) = count(*) THEN max(p.data_platnosci)::DATE END AS data_platnosci,
        max(p.dni_opoznienia) AS dni_opoznienia
    FROM pms_platnosci AS p
    JOIN pms_umowy AS u USING (id_umowy)
    GROUP BY u.id_najmu, p.miesiac
),
okno AS (
    SELECT
        m.id_umowy,
        p.termin,
        p.data_platnosci IS NULL OR p.data_platnosci >= m.data_migawki AS nieoplacona_na_migawke,
        CASE
            WHEN p.data_platnosci < m.data_migawki THEN p.dni_opoznienia
            ELSE date_diff('day', p.termin, m.data_migawki)
        END AS opoznienie_znane
    FROM m
    JOIN platnosci AS p
        ON p.id_najmu = m.id_najmu
       AND p.termin >= m.data_migawki - 90
       AND p.termin < m.data_migawki
)
SELECT
    m.id_umowy,
    count(o.termin) AS plat_liczba_90d,
    count(o.termin) FILTER (WHERE o.opoznienie_znane > 0) AS plat_spoznione_90d,
    count(o.termin) FILTER (WHERE o.nieoplacona_na_migawke) AS plat_zalegle_na_migawke,
    max(o.opoznienie_znane) AS plat_max_opoznienie_90d,
    avg(o.opoznienie_znane) AS plat_srednie_opoznienie_90d
FROM m
LEFT JOIN okno AS o USING (id_umowy)
GROUP BY m.id_umowy
