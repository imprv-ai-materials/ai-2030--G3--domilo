-- Rodzina `firma_b2b`: czy firma zapytania (crm_leady.id_firmy_b2b) miała umowę ramową W CHWILI zapytania.
-- crm_firmy_b2b.umowa_ramowa to stan na dzień eksportu; obowiązuje od data_umowy_ramowej (początek dnia, czas
-- warszawski). Zapytania sprzed tej daty i bez firmy dostają 0.
SELECT
    l.id_leada,
    CAST(coalesce(f.umowa_ramowa AND CAST(CAST(f.data_umowy_ramowej AS TIMESTAMP) AS TIMESTAMPTZ) <= l.utworzono, FALSE) AS INTEGER) AS umowa_ramowa
FROM crm_leady AS l
LEFT JOIN crm_firmy_b2b AS f ON f.id_firmy = l.id_firmy_b2b
