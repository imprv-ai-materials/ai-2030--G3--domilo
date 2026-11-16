-- Cecha dodatkowa rodziny `wibracje`: czy w chwili odcięcia (05:50 dnia oceny) czujnik wibracji był już
-- zamontowany (serwis_windy.czujnik_wibracji_od, czas lokalny). Kontrakt cech dodatkowych (cechy.py): wiersz na
-- (id_windy, dzien) z tabeli tymczasowej `kotwice` (moment_odciecia = 05:50 Europe/Warsaw dnia oceny).
SELECT
    k.id_windy,
    k.dzien,
    CAST(
        coalesce(timezone('Europe/Warsaw', w.czujnik_wibracji_od) <= k.moment_odciecia, false) AS INTEGER
    ) AS ma_czujnik_wibracji
FROM kotwice AS k
JOIN serwis_windy AS w USING (id_windy)
