-- Rodzina `drzwi`: sygnały drzwi kabiny / szybu z 10-minutowych okien telemetrii (opis: docs/b4_cechy.md).
--
-- Kontrakt rodziny (cechy.py): id_windy, ts_utc (koniec okna) i kolumny sygnałów; dla każdego sygnału cechy.py
-- liczy średnią i maksimum z 24 h / 3 / 7 dni, normę (mediana średnich dobowych z dni 15–44), stosunek do normy
-- i nachylenie z 7 dni. `telemetria` = telemetra_windy bez okien z tryb = 'serwis' (widok tymczasowy z cechy.py).
-- czas_zamykania_* jest pusty w oknach bez jazdy; średnia liczy się tylko z okien z wartością.
-- Uwaga: po aktualizacji firmware Liftar do LF-5 (2025-11-17) błędy drzwi są raportowane parami kodów E07|E17,
-- więc drzwi_bledy rośnie bez wzrostu awarii (docs/b4_cechy.md, F1); kontekst: sterownik_firmware.sql.
SELECT
    id_windy,
    ts_utc,
    ponowne_otwarcia AS drzwi_ponowne_otwarcia,
    czas_zamykania_drzwi_sr_s AS drzwi_czas_zamykania_sr,
    czas_zamykania_drzwi_max_s AS drzwi_czas_zamykania_max,
    bledy_drzwi AS drzwi_bledy
FROM telemetria
