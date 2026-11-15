-- czas_najmu + indeksacja przy ostatnim przedłużeniu najmu (docs/przezycie.md, sekcja „Grupy”).
--
-- Ostatnie przedłużenie = umowa typu 'przedłużenie' z najwyższym nr_okresu i data_od <= 2026-09-30 (przedłużenia
--   podpisane, ale zaczynające się po eksporcie, pomijamy). Najem bez takiej umowy ma grupę 'bez przedłużenia'.
-- grupa_indeksacji: '<= 6%' (indeksacja_pct <= 6, także 6,0) albo '> 6%'.
-- UWAGA: grupa jest znana dopiero po fakcie. Każdy najem z przedłużeniem przetrwał pierwszą umowę, a „ostatnie”
--   przedłużenie wybieramy, znając dalszy los najmu. To opis, nie przyczyna (docs/przezycie.md).
WITH ostatnie AS (
    SELECT
        id_najmu,
        arg_max(indeksacja_pct, nr_okresu) AS indeksacja_ostatnia,
        max(data_od)::DATE AS data_od_ostatniego,
        count(*) AS przedluzenia
    FROM pms_umowy
    WHERE typ = 'przedłużenie'
      AND data_od::DATE <= DATE '2026-09-30'
    GROUP BY id_najmu
)
SELECT
    c.id_najmu,
    c.linia,
    c.miesiace,
    c.zdarzenie,
    c.rok_wprowadzenia,
    o.indeksacja_ostatnia,
    o.data_od_ostatniego,
    coalesce(o.przedluzenia, 0) AS przedluzenia,
    CASE
        WHEN o.indeksacja_ostatnia IS NULL THEN 'bez przedłużenia'
        WHEN o.indeksacja_ostatnia <= 6 THEN '<= 6%'
        ELSE '> 6%'
    END AS grupa_indeksacji
FROM czas_najmu AS c
LEFT JOIN ostatnie AS o USING (id_najmu)
