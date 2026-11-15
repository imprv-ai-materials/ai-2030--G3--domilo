-- Cechy otoczenia dla każdej transakcji RCN (opis i statystyki: docs/b3_wycena_v2_geo.md).
--
-- Jednostka: jedna transakcja (rcn_transakcje, klucz id_transakcji), wszystkie transakcje z tabeli — podział na
-- zbiory robi podzial.sql. Położenie transakcji: rcn_transakcje.lat / lon.
-- Źródła: zewnetrzne/geo_poi (punkty), zewnetrzne/gus_dzielnice (dzielnice i centrum miasta).
-- geo_poi i gus_dzielnice nie mają dat (jeden stan), więc cechy nie zależą od daty transakcji.
--
-- Odległości: wzór haversine na kuli o promieniu 6 371 008,8 m (średni promień Ziemi), wynik w metrach.
-- Szukamy najbliższego punktu tylko w tym samym mieście (geo_poi.miasto = rcn_transakcje.miasto).
--   odl_centrum_m   do centrum miasta (gus_dzielnice.lat_centrum_miasta / lon_centrum_miasta, jedno na miasto)
--   odl_stacja_m    do najbliższej stacji metra lub kolei (typ 'metro' albo 'kolej')
--   odl_metro_m     do najbliższej stacji metra (typ 'metro'; metro jest tylko w Warszawie, gdzie indziej NULL)
--   odl_tramwaj_m   do najbliższego przystanku tramwajowego (typ 'tramwaj')
--   odl_park_m      do najbliższego parku o powierzchni ≥ 2 ha (typ 'park', powierzchnia_ha >= 2)
--   odl_uczelnia_m  do najbliższej uczelni (typ 'uczelnia')
-- Flagi (0/1; brak punktu danego typu w mieście = 0):
--   metro_do_700m   odl_metro_m <= 700
--   tramwaj_do_300m odl_tramwaj_m <= 300
--   park_do_400m    odl_park_m <= 400
-- Dzielnica (gus_dzielnice, złączenie po miasto + dzielnica): gestosc_os_km2, wskaznik_dochodu.
-- geohash6: geohash o długości 6 znaków (30 bitów: 15 bitów długości i 15 szerokości geograficznej, przeplatane
-- od długości; alfabet base32 geohash). Liczony w SQL bez rozszerzenia spatial: bity geohasha to rozwinięcie
-- dwójkowe floor((lon + 180) / 360 · 2^15) i floor((lat + 90) / 180 · 2^15).
-- Zapytanie działa na domilo.duckdb (połączenie przez polacz()).
WITH transakcje AS (
    SELECT id_transakcji, miasto, dzielnica, lat, lon
    FROM rcn_transakcje
),
punkty AS (
    SELECT miasto, typ, lat, lon
    FROM geo_poi
    WHERE typ IN ('metro', 'kolej', 'tramwaj', 'uczelnia')
       OR (typ = 'park' AND powierzchnia_ha >= 2)
    UNION ALL
    SELECT DISTINCT miasto, 'centrum' AS typ, lat_centrum_miasta AS lat, lon_centrum_miasta AS lon
    FROM gus_dzielnice
),
odleglosci AS (
    SELECT
        t.id_transakcji,
        p.typ,
        2 * 6371008.8 * asin(sqrt(
            power(sin(radians(p.lat - t.lat) / 2), 2)
            + cos(radians(t.lat)) * cos(radians(p.lat)) * power(sin(radians(p.lon - t.lon) / 2), 2)
        )) AS odl_m
    FROM transakcje AS t
    JOIN punkty AS p ON p.miasto = t.miasto
),
najblizsze AS (
    SELECT
        id_transakcji,
        min(odl_m) FILTER (WHERE typ = 'centrum') AS odl_centrum_m,
        min(odl_m) FILTER (WHERE typ IN ('metro', 'kolej')) AS odl_stacja_m,
        min(odl_m) FILTER (WHERE typ = 'metro') AS odl_metro_m,
        min(odl_m) FILTER (WHERE typ = 'tramwaj') AS odl_tramwaj_m,
        min(odl_m) FILTER (WHERE typ = 'park') AS odl_park_m,
        min(odl_m) FILTER (WHERE typ = 'uczelnia') AS odl_uczelnia_m
    FROM odleglosci
    GROUP BY id_transakcji
),
siatka AS (
    SELECT
        id_transakcji,
        least(floor((lon + 180) / 360 * 32768), 32767)::BIGINT AS lon_i,
        least(floor((lat + 90) / 180 * 32768), 32767)::BIGINT AS lat_i
    FROM transakcje
)
SELECT
    t.id_transakcji,
    n.odl_centrum_m,
    n.odl_stacja_m,
    n.odl_metro_m,
    n.odl_tramwaj_m,
    n.odl_park_m,
    n.odl_uczelnia_m,
    coalesce(n.odl_metro_m <= 700, false)::INTEGER AS metro_do_700m,
    coalesce(n.odl_tramwaj_m <= 300, false)::INTEGER AS tramwaj_do_300m,
    coalesce(n.odl_park_m <= 400, false)::INTEGER AS park_do_400m,
    g.gestosc_os_km2,
    g.wskaznik_dochodu,
    array_to_string(list_transform(range(6), lambda c: substr(
        '0123456789bcdefghjkmnpqrstuvwxyz',
        1 + list_sum(list_transform(range(5), lambda b:
            (CASE WHEN (5 * c + b) % 2 = 0
                  THEN (s.lon_i >> (14 - (5 * c + b) // 2)) & 1
                  ELSE (s.lat_i >> (14 - (5 * c + b) // 2)) & 1 END) << (4 - b)))::INTEGER,
        1)), '') AS geohash6
FROM transakcje AS t
LEFT JOIN najblizsze AS n USING (id_transakcji)
LEFT JOIN siatka AS s USING (id_transakcji)
LEFT JOIN gus_dzielnice AS g ON g.miasto = t.miasto AND g.dzielnica = t.dzielnica
