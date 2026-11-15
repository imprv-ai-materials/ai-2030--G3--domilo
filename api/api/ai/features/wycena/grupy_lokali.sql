-- Grupy ofert: ten sam lokal opublikowany na kilku portalach (docs/b1_przeciek_opisu.md).
--
-- Ten sam lokal = te same lat, lon, metraz, pietro. Oferty jednego lokalu sortujemy po data_publikacji. Kolejna
-- oferta należy do tej samej grupy, jeśli ukazała się najwyżej 3 dni (INTERVAL 3 DAY) po poprzedniej.
-- Łańcuch może więc trwać dłużej niż 3 dni (A, +2 dni B, +2 dni C); raport podaje, jak często.
-- id_grupy = 'G' + id_oferty pierwszej oferty w grupie (stabilne między uruchomieniami).
WITH uporzadkowane AS (
    SELECT id_oferty, portal, data_publikacji, lat, lon, metraz, pietro,
           CASE WHEN data_publikacji - lag(data_publikacji) OVER w <= INTERVAL 3 DAY THEN 0 ELSE 1 END AS nowa_grupa
    FROM radar_oferty
    WINDOW w AS (PARTITION BY lat, lon, metraz, pietro ORDER BY data_publikacji, id_oferty)
),
numerowane AS (
    SELECT *, sum(nowa_grupa) OVER (PARTITION BY lat, lon, metraz, pietro ORDER BY data_publikacji, id_oferty
                                    ROWS UNBOUNDED PRECEDING) AS nr_grupy
    FROM uporzadkowane
)
SELECT id_oferty,
       'G' || first(id_oferty ORDER BY data_publikacji, id_oferty)
           OVER (PARTITION BY lat, lon, metraz, pietro, nr_grupy) AS id_grupy
FROM numerowane
