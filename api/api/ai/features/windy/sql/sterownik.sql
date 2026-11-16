-- Rodzina `sterownik`: błędy sterownika (opis: docs/b4_cechy.md; kontrakt: drzwi.sql).
--
-- kody_bledow nie są osobnym sygnałem: kody zależą od producenta (DR31, EC1, E31, VC7 = sterownik) i każdy kod jest
-- już policzony w bledy_drzwi / bledy_napedu / bledy_sterownika. Kontekst firmware (dni od zmiany, zmiana wersji
-- głównej w oknie normy): sterownik_firmware.sql.
SELECT
    id_windy,
    ts_utc,
    bledy_sterownika AS sterownik_bledy
FROM telemetria
