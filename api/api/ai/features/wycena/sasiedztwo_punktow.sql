-- Statystyki sąsiedztwa dla dowolnych punktów wycenianych na dany dzień (oferty, lokale Domilo), w wersji
-- „co wiemy w dniu wyceny” (opis: docs/b1_bledy.md, definicja cech: sasiedztwo.sql).
--
-- Punkt P (id, miasto, lat, lon, dzien_wyceny) dostaje 20 najbliższych (haversine, to samo miasto) transakcji
-- S z rcn_transakcje, dla których:
--   P.dzien_wyceny − 12 miesięcy <= S.data_aktu < P.dzien_wyceny
--   S.data_publikacji_rejestru < P.dzien_wyceny      (transakcja była już opublikowana w dniu wyceny)
--   S.data_publikacji_rejestru < 2026-10-01           (znana w dniu eksportu)
-- Bez out-of-fold: punkty nie są transakcjami treningowymi. Remisy jak w sasiedztwo.sql.
-- Wynik: id_transakcji (= id punktu), sasiedzi_mediana_ceny_m2, sasiedzi_liczba, sasiedzi_id.
-- Źródło punktów wstawia sasiedztwo.py w miejsce znacznika ZRODLO_PUNKTOW (kolumny jak wyżej).
WITH punkty AS (
    SELECT id_transakcji, miasto, lat, lon, dzien_wyceny::DATE AS dzien_wyceny
    FROM (/*ZRODLO_PUNKTOW*/) AS p
),
pula AS (
    SELECT id_transakcji, miasto, lat, lon, data_aktu::DATE AS dzien_aktu, data_publikacji_rejestru, cena_m2
    FROM rcn_transakcje
    WHERE data_publikacji_rejestru < TIMESTAMP '2026-10-01'
),
pary AS (
    SELECT
        p.id_transakcji,
        s.id_transakcji AS id_sasiada,
        s.cena_m2,
        s.dzien_aktu AS dzien_sasiada,
        2 * 6371008.8 * asin(sqrt(
            power(sin(radians(s.lat - p.lat) / 2), 2)
            + cos(radians(p.lat)) * cos(radians(s.lat)) * power(sin(radians(s.lon - p.lon) / 2), 2)
        )) AS odl_m
    FROM punkty AS p
    JOIN pula AS s
      ON s.miasto = p.miasto
     AND s.dzien_aktu < p.dzien_wyceny
     AND s.dzien_aktu >= (p.dzien_wyceny - INTERVAL 12 MONTH)::DATE
     AND s.data_publikacji_rejestru < p.dzien_wyceny
),
najblizsi AS (
    SELECT
        id_transakcji,
        min_by(
            struct_pack(id := id_sasiada, cena_m2 := cena_m2),
            struct_pack(o := odl_m, d := -epoch(dzien_sasiada), i := id_sasiada),
            20
        ) AS sasiedzi
    FROM pary
    GROUP BY id_transakcji
)
SELECT
    p.id_transakcji,
    list_aggregate(list_transform(n.sasiedzi, lambda x: x.cena_m2), 'median') AS sasiedzi_mediana_ceny_m2,
    coalesce(len(n.sasiedzi), 0) AS sasiedzi_liczba,
    coalesce(list_transform(n.sasiedzi, lambda x: x.id), []::VARCHAR[]) AS sasiedzi_id
FROM punkty AS p
LEFT JOIN najblizsi AS n USING (id_transakcji)
