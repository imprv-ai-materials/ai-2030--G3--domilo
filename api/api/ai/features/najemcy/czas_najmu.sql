-- Czas najmu do analizy przeżycia: jeden wiersz = najem roczny z pms_najmy (opis i liczby: docs/przezycie.md).
--
-- Populacja: pms_najmy z linią B2C albo B2B (pierwsza umowa roczna, dla B2B także 18 / 24 miesiące; linia MID =
--   umowy średnioterminowe pomijamy) i data_wprowadzenia <= dzień eksportu. Najmy z data_wprowadzenia po
--   2026-09-30 to umowy już podpisane, ale najemca się jeszcze nie wprowadził: nie mają żadnego czasu obserwacji.
-- zdarzenie = 1: najem zakończony (data_wyprowadzenia jest wpisana, także przeprowadzka do innego lokalu Domilo);
--   0: najem aktywny w dniu eksportu, czyli obserwacja ucięta (cenzurowana) na 2026-09-30.
-- data_konca = data_wyprowadzenia albo 2026-09-30. data_wyprowadzenia to ostatni dzień najmu (dzień data_do
--   ostatniej umowy), a eksport jest z 2026-09-30 23:59, więc oba końce liczymy włącznie: najem trwa od
--   data_wprowadzenia do data_konca + 1 dzień (wyłącznie).
-- dni = (data_konca + 1) - data_wprowadzenia.
-- miesiace = pełne miesiące kalendarzowe od data_wprowadzenia do data_konca + 1 plus ułamek kolejnego miesiąca
--   (dni / liczba dni tego miesiąca). Umowa 12-miesięczna 2019-09-08 – 2020-09-07 daje dokładnie 12,0.
-- import_pms: data_wprowadzenia < 2023-03-01, czyli rekord z importu do PMS (PMS od 2019-04).
-- Daty PMS (TIMESTAMP bez strefy, północ czasu warszawskiego) rzutujemy na DATE.
WITH parametry AS (
    SELECT
        DATE '2026-09-30' AS dzien_eksportu,
        DATE '2023-03-01' AS poczatek_pms
),
najmy AS (
    SELECT
        n.id_najmu,
        n.id_najemcy,
        n.id_lokalu,
        n.linia,
        n.data_wprowadzenia::DATE AS data_wprowadzenia,
        n.data_wyprowadzenia::DATE AS data_wyprowadzenia,
        n.powod_odejscia,
        coalesce(n.data_wyprowadzenia::DATE, p.dzien_eksportu) AS data_konca,
        CASE WHEN n.data_wyprowadzenia IS NULL THEN 0 ELSE 1 END AS zdarzenie,
        n.data_wprowadzenia::DATE < p.poczatek_pms AS import_pms
    FROM pms_najmy AS n, parametry AS p
    WHERE n.linia IN ('B2C', 'B2B')
      AND n.data_wprowadzenia::DATE <= p.dzien_eksportu
),
miesiace AS (
    SELECT
        *,
        date_sub('month', data_wprowadzenia, data_konca + 1) AS pelne_miesiace
    FROM najmy
),
ulamek AS (
    SELECT
        *,
        (data_wprowadzenia + to_months(pelne_miesiace))::DATE AS poczatek_niepelnego,
        (data_wprowadzenia + to_months(pelne_miesiace + 1))::DATE AS koniec_niepelnego
    FROM miesiace
)
SELECT
    id_najmu,
    id_najemcy,
    id_lokalu,
    linia,
    data_wprowadzenia,
    data_konca,
    (data_konca + 1) - data_wprowadzenia AS dni,
    pelne_miesiace
        + ((data_konca + 1) - poczatek_niepelnego) / (koniec_niepelnego - poczatek_niepelnego) AS miesiace,
    zdarzenie,
    year(data_wprowadzenia) AS rok_wprowadzenia,
    import_pms,
    data_wyprowadzenia,
    powod_odejscia
FROM ulamek
ORDER BY data_wprowadzenia, id_najmu
