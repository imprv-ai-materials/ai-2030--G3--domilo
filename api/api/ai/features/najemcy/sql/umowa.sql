-- Rodzina `umowa`: cechy bieżącej umowy na dzień migawki (opis: docs/przecieki_najemcy.md).
--
-- Wejście: migawki_najemcy (jedna kończąca się umowa na wiersz; czytamy tylko kolumny znane w dniu migawki).
-- Migawka = stan na początek dnia data_migawki: używamy wyłącznie zdarzeń z datą < data_migawki.
-- staz_dni: dni od wprowadzenia (pms_najmy.data_wprowadzenia) do dnia migawki.
-- indeksacja_ostatnia_pct: pms_umowy.indeksacja_pct bieżącej umowy, czyli ostatniego przedłużenia przed migawką;
--   NULL dla pierwszej umowy (nr_okresu = 1), bo indeksacji jeszcze nie było.
-- czynsz_do_podobnych: czynsz bieżącej umowy / (mediana czynszu za m² nowych umów w podobnych lokalach × metraż).
--   Podobne lokale: ta sama linia najmu i liczba pokoi; najpierw ten sam budynek, a gdy jest tam mniej niż
--   MIN_PODOBNYCH umów, to samo miasto (podobne_poziom). Nowe umowy: typ 'pierwsza', data_od w 365 dniach przed
--   migawką, inny lokal. NIE używamy pms_lokale.czynsz_katalogowy: to stan na dzień eksportu (2026-09-30), a nie
--   cennik z dnia migawki (dryf w docs/przecieki_najemcy.md). Czynsz nowych umów podobnych lokali sprzed migawki
--   pełni rolę czynszu katalogowego z tamtego dnia.
-- Z pms_lokale bierzemy tylko atrybuty stałe (budynek, metraż, pokoje), nie status ani czynsz_katalogowy.
WITH parametry AS (
    SELECT 365 AS dni_okna_podobnych, 5 AS min_podobnych
),
m AS (
    SELECT id_umowy, id_najmu, id_lokalu, linia, nr_okresu, miesiecy_umowy, data_migawki
    FROM migawki_najemcy
),
lokal AS (
    SELECT l.id_lokalu, l.id_budynku, l.pokoje, l.metraz, b.miasto
    FROM pms_lokale AS l
    JOIN pms_budynki AS b USING (id_budynku)
),
biezaca AS (
    SELECT
        m.*,
        u.czynsz,
        u.indeksacja_pct,
        n.data_wprowadzenia::DATE AS data_wprowadzenia,
        l.id_budynku,
        l.pokoje,
        l.metraz,
        l.miasto
    FROM m
    JOIN pms_umowy AS u ON u.id_umowy = m.id_umowy
    JOIN pms_najmy AS n ON n.id_najmu = m.id_najmu
    JOIN lokal AS l ON l.id_lokalu = m.id_lokalu
),
nowe_umowy AS (
    SELECT
        n.id_lokalu,
        n.linia,
        l.id_budynku,
        l.pokoje,
        l.miasto,
        u.data_od::DATE AS data_od,
        u.czynsz / l.metraz AS czynsz_m2
    FROM pms_umowy AS u
    JOIN pms_najmy AS n USING (id_najmu)
    JOIN lokal AS l USING (id_lokalu)
    WHERE u.typ = 'pierwsza'
),
podobne_budynek AS (
    SELECT b.id_umowy, median(nu.czynsz_m2) AS mediana_m2, count(*) AS liczba
    FROM biezaca AS b
    CROSS JOIN parametry AS p
    JOIN nowe_umowy AS nu
        ON nu.id_budynku = b.id_budynku
       AND nu.pokoje = b.pokoje
       AND nu.linia = b.linia
       AND nu.id_lokalu <> b.id_lokalu
       AND nu.data_od >= b.data_migawki - p.dni_okna_podobnych
       AND nu.data_od < b.data_migawki
    GROUP BY b.id_umowy
),
podobne_miasto AS (
    SELECT b.id_umowy, median(nu.czynsz_m2) AS mediana_m2, count(*) AS liczba
    FROM biezaca AS b
    CROSS JOIN parametry AS p
    JOIN nowe_umowy AS nu
        ON nu.miasto = b.miasto
       AND nu.pokoje = b.pokoje
       AND nu.linia = b.linia
       AND nu.id_lokalu <> b.id_lokalu
       AND nu.data_od >= b.data_migawki - p.dni_okna_podobnych
       AND nu.data_od < b.data_migawki
    GROUP BY b.id_umowy
),
porownanie AS (
    SELECT
        b.id_umowy,
        CASE
            WHEN pb.liczba >= p.min_podobnych THEN 'budynek'
            WHEN pm.liczba >= p.min_podobnych THEN 'miasto'
        END AS podobne_poziom,
        CASE
            WHEN pb.liczba >= p.min_podobnych THEN pb.mediana_m2
            WHEN pm.liczba >= p.min_podobnych THEN pm.mediana_m2
        END AS podobne_mediana_m2,
        CASE
            WHEN pb.liczba >= p.min_podobnych THEN pb.liczba
            WHEN pm.liczba >= p.min_podobnych THEN pm.liczba
        END AS podobne_liczba
    FROM biezaca AS b
    CROSS JOIN parametry AS p
    LEFT JOIN podobne_budynek AS pb USING (id_umowy)
    LEFT JOIN podobne_miasto AS pm USING (id_umowy)
)
SELECT
    b.id_umowy,
    b.linia,
    b.miesiecy_umowy,
    b.nr_okresu,
    date_diff('day', b.data_wprowadzenia, b.data_migawki) AS staz_dni,
    CASE WHEN b.nr_okresu > 1 THEN b.indeksacja_pct END AS indeksacja_ostatnia_pct,
    b.czynsz,
    b.czynsz / b.metraz AS czynsz_m2,
    p.podobne_poziom,
    p.podobne_liczba,
    p.podobne_mediana_m2,
    b.czynsz / (p.podobne_mediana_m2 * b.metraz) AS czynsz_do_podobnych
FROM biezaca AS b
JOIN porownanie AS p USING (id_umowy)
