-- Statystyki sąsiedztwa dla każdej transakcji z podziału (opis i wyniki: docs/b4_wycena_v2_lgbm_geo.md).
--
-- Dla transakcji T: 20 najbliższych (haversine, to samo miasto) transakcji S z 12 miesięcy przed dniem aktu T:
--   T.data_aktu − 12 miesięcy <= S.data_aktu < T.data_aktu   (porównanie dni; S nigdy nie jest T ani późniejsza,
--                                                             transakcje z tego samego dnia też odpadają)
-- Pula S = transakcje z podziału (podzial.sql), czyli znane w dniu eksportu.
-- Out-of-fold w zbiorze treningowym: każda transakcja dostaje fold = md5_number(id_transakcji) % 5; dla T z
-- `trening` sąsiadem może być tylko S z innego foldu. Dla T z `walidacja` i `test` pula to wszystkie wcześniejsze
-- transakcje (z treningu, walidacji i testu), bez wykluczania foldu.
-- Wariant „wg publikacji” (zmienna DuckDB `sasiedzi_wg_publikacji` = true, ustawia ją sasiedztwo.py): dodatkowo
-- S.data_publikacji_rejestru < T.data_aktu, czyli tylko transakcje już opublikowane w rejestrze w dniu aktu T.
-- Remisy odległości (ten sam budynek): bliższa, potem nowsza (data_aktu), potem mniejsze id_transakcji.
-- Wynik:
--   sasiedzi_mediana_ceny_m2  mediana cena_m2 wybranych sąsiadów (NULL, gdy brak sąsiadów)
--   sasiedzi_liczba           liczba wybranych sąsiadów (0–20; < 20, gdy w oknie jest mniej transakcji)
--   sasiedzi_id               lista id_transakcji sąsiadów (do kontroli; nie jest cechą modelu)
-- Znacznik podziału w klauzuli JOIN (nazwa w nawiasach klamrowych) zastępuje treścią podzial.sql sasiedztwo.py.
WITH baza AS (
    SELECT
        t.id_transakcji,
        t.miasto,
        t.lat,
        t.lon,
        t.data_aktu::DATE AS dzien_aktu,
        t.data_publikacji_rejestru,
        t.cena_m2,
        p.zbior,
        md5_number(t.id_transakcji) % 5 AS fold
    FROM rcn_transakcje AS t
    JOIN ({podzial}) AS p USING (id_transakcji)
),
pary AS (
    SELECT
        t.id_transakcji,
        s.id_transakcji AS id_sasiada,
        s.cena_m2,
        s.dzien_aktu AS dzien_sasiada,
        2 * 6371008.8 * asin(sqrt(
            power(sin(radians(s.lat - t.lat) / 2), 2)
            + cos(radians(t.lat)) * cos(radians(s.lat)) * power(sin(radians(s.lon - t.lon) / 2), 2)
        )) AS odl_m
    FROM baza AS t
    JOIN baza AS s
      ON s.miasto = t.miasto
     AND s.dzien_aktu < t.dzien_aktu
     AND s.dzien_aktu >= (t.dzien_aktu - INTERVAL 12 MONTH)::DATE
     AND (t.zbior <> 'trening' OR s.fold <> t.fold)
     AND (NOT coalesce(getvariable('sasiedzi_wg_publikacji'), false)
          OR s.data_publikacji_rejestru < t.dzien_aktu)
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
    b.id_transakcji,
    list_aggregate(list_transform(n.sasiedzi, lambda x: x.cena_m2), 'median') AS sasiedzi_mediana_ceny_m2,
    coalesce(len(n.sasiedzi), 0) AS sasiedzi_liczba,
    coalesce(list_transform(n.sasiedzi, lambda x: x.id), []::VARCHAR[]) AS sasiedzi_id
FROM baza AS b
LEFT JOIN najblizsi AS n USING (id_transakcji)
