-- Kontrola dla grup indeksacji (docs/przezycie.md): jeden wiersz = przedłużenie umowy rocznej (B2C / B2B),
-- czas od jego data_od do końca najmu albo do 2026-09-30. Grupa = indeksacja tego przedłużenia, znana w chwili
-- jego podpisania, więc nie zależy od dalszego losu najmu (w odróżnieniu od „ostatniego przedłużenia”).
--
-- Populacja: pms_umowy.typ = 'przedłużenie', data_od <= 2026-09-30. Ten sam najem może mieć kilka wierszy
--   (każde przedłużenie osobno), więc przedziały ufności KM są dla tej tabeli za wąskie.
-- miesiace: jak w czas_najmu.sql (pełne miesiące kalendarzowe + ułamek), początek = data_od przedłużenia.
-- zdarzenie = 1: najem się skończył (data_wyprowadzenia), 0: trwa w dniu eksportu.
WITH parametry AS (
    SELECT DATE '2026-09-30' AS dzien_eksportu
),
okresy AS (
    SELECT
        u.id_umowy,
        u.id_najmu,
        n.linia,
        u.nr_okresu,
        u.indeksacja_pct,
        u.data_od::DATE AS data_od,
        coalesce(n.data_wyprowadzenia::DATE, p.dzien_eksportu) AS data_konca,
        CASE WHEN n.data_wyprowadzenia IS NULL THEN 0 ELSE 1 END AS zdarzenie
    FROM pms_umowy AS u
    JOIN pms_najmy AS n USING (id_najmu)
    CROSS JOIN parametry AS p
    WHERE u.typ = 'przedłużenie'
      AND u.data_od::DATE <= p.dzien_eksportu
      AND n.linia IN ('B2C', 'B2B')
),
miesiace AS (
    SELECT *, date_sub('month', data_od, data_konca + 1) AS pelne_miesiace
    FROM okresy
),
ulamek AS (
    SELECT
        *,
        (data_od + to_months(pelne_miesiace))::DATE AS poczatek_niepelnego,
        (data_od + to_months(pelne_miesiace + 1))::DATE AS koniec_niepelnego
    FROM miesiace
)
SELECT
    id_umowy,
    id_najmu,
    linia,
    nr_okresu,
    indeksacja_pct,
    CASE WHEN indeksacja_pct <= 6 THEN '<= 6%' ELSE '> 6%' END AS grupa_indeksacji,
    data_od,
    year(data_od) AS rok_przedluzenia,
    data_konca,
    pelne_miesiace
        + ((data_konca + 1) - poczatek_niepelnego) / (koniec_niepelnego - poczatek_niepelnego) AS miesiace,
    zdarzenie
FROM ulamek
ORDER BY data_od, id_umowy
