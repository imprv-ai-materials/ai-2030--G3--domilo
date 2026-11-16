-- Okresy umów do modelu przeżycia v2_przezycie_cox: jeden wiersz = okres umowy rocznej (B2C / B2B), czas od jego
-- początku do końca najmu w tym okresie albo do końca okresu / końca obserwacji (opis: docs/przezycie_cox.md).
--
-- Parametr $koniec_obserwacji (DATE): ostatni dzień, który model „widzi” (trening: 2024-12-31, ocena: 2026-09-30).
-- Populacja: pms_umowy typu 'pierwsza' albo 'przedłużenie' (linia MID = 'średnioterminowa' pomijamy),
--   data_od <= $koniec_obserwacji.
-- Kolumny dla rodzin cech (features/najemcy/sql/*.sql, jak migawki_najemcy): id_umowy, id_najmu, id_najemcy,
--   id_lokalu, linia, nr_okresu, miesiecy_umowy, data_migawki. data_migawki = data_od: cechy liczymy na początek
--   okresu, tylko ze zdarzeń z datą < data_od (indeksacja bieżącego przedłużenia jest znana, bo podpisano je wcześniej).
-- koniec_w_okresie = najwcześniejszy z: data_wyprowadzenia, data_do, $koniec_obserwacji (ostatni dzień włącznie).
-- zdarzenie = 1: najem skończył się w tym okresie i przed końcem obserwacji (data_wyprowadzenia <= data_do
--   i <= $koniec_obserwacji); 0: najem trwa dalej (kolejny okres) albo obserwację ucięto.
-- czas: miesiące kalendarzowe od data_od do koniec_w_okresie + 1 dzień (pełne miesiące + ułamek, jak czas_najmu.sql).
WITH okresy AS (
    SELECT
        u.id_umowy,
        u.id_najmu,
        n.id_najemcy,
        n.id_lokalu,
        n.linia,
        u.nr_okresu,
        u.typ,
        date_diff('month', u.data_od::DATE, u.data_do::DATE + 1) AS miesiecy_umowy,
        u.data_od::DATE AS data_migawki,
        u.data_od::DATE AS data_od,
        u.data_do::DATE AS data_do,
        n.data_wprowadzenia::DATE AS data_wprowadzenia,
        n.data_wyprowadzenia::DATE AS data_wyprowadzenia,
        least(
            coalesce(n.data_wyprowadzenia::DATE, u.data_do::DATE), u.data_do::DATE, $koniec_obserwacji::DATE
        ) AS koniec_w_okresie,
        CASE
            WHEN n.data_wyprowadzenia::DATE <= u.data_do::DATE
             AND n.data_wyprowadzenia::DATE <= $koniec_obserwacji::DATE THEN 1
            ELSE 0
        END AS zdarzenie
    FROM pms_umowy AS u
    JOIN pms_najmy AS n USING (id_najmu)
    WHERE u.typ IN ('pierwsza', 'przedłużenie')
      AND u.data_od::DATE <= $koniec_obserwacji::DATE
),
miesiace AS (
    SELECT *, date_sub('month', data_od, koniec_w_okresie + 1) AS pelne_miesiace
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
    id_najemcy,
    id_lokalu,
    linia,
    nr_okresu,
    typ,
    miesiecy_umowy,
    data_migawki,
    data_od,
    data_do,
    data_wprowadzenia,
    data_wyprowadzenia,
    koniec_w_okresie,
    pelne_miesiace
        + ((koniec_w_okresie + 1) - poczatek_niepelnego) / (koniec_niepelnego - poczatek_niepelnego) AS czas,
    zdarzenie
FROM ulamek
ORDER BY data_od, id_umowy
