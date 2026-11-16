-- Rodzina `uzycie`: jak intensywnie winda pracuje (opis: docs/b4_cechy.md; kontrakt: drzwi.sql).
--
-- uzycie_wylaczona = 1 w oknie z tryb = 'wylaczona' (średnia = udział okien z windą wyłączoną; okna serwisowe są
-- wykluczone wcześniej, w widoku `telemetria`).
SELECT
    id_windy,
    ts_utc,
    kursy AS uzycie_kursy,
    otwarcia_drzwi AS uzycie_otwarcia_drzwi,
    CAST(tryb = 'wylaczona' AS INTEGER) AS uzycie_wylaczona
FROM telemetria
