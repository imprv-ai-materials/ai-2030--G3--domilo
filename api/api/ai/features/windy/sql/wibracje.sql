-- Rodzina `wibracje`: drgania kabiny z czujnika montowanego od serwis_windy.czujnik_wibracji_od
-- (opis: docs/b4_cechy.md; kontrakt: drzwi.sql).
--
-- Przed montażem czujnika wartości nie uzupełniamy: zostaje NULL (wymuszone także tu, gdyby źródło miało wartość
-- sprzed montażu), więc cechy z okresu bez czujnika są NULL. Flagę ma_czujnik_wibracji liczy wibracje_czujnik.sql.
-- czujnik_wibracji_od to czas lokalny (TIMESTAMP) -> moment przez timezone('Europe/Warsaw', ...).
-- Po montażu wartość jest tylko w oknach z jazdą (kursy > 0).
SELECT
    t.id_windy,
    t.ts_utc,
    CASE
        WHEN t.ts_utc >= timezone('Europe/Warsaw', w.czujnik_wibracji_od) THEN t.wibracje_rms_mg
    END AS wibracje_rms
FROM telemetria AS t
JOIN serwis_windy AS w USING (id_windy)
