-- Rodzina `zapytanie`: pola formularza z crm_leady znane w chwili utworzenia zapytania.
-- Bez kolumn stanu na dzień eksportu (status, data_statusu, powod_utraty, id_doradcy, id_umowy).
-- termin_dni: dni kalendarzowe od dnia zapytania (czas warszawski: strefa sesji z polacz()) do terminu wprowadzenia;
--   ujemne = termin już minął w chwili zapytania; NULL = pole puste.
SELECT
    id_leada,
    zrodlo,
    miasto,
    linia_pref AS linia,
    datediff('day', CAST(utworzono AS DATE), CAST(termin_wprowadzenia AS DATE)) AS termin_dni,
    liczba_osob,
    CAST(zwierze AS INTEGER) AS zwierze,
    liczba_lokali
FROM crm_leady
