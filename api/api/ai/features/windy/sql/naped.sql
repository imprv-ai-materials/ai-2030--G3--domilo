-- Rodzina `naped`: silnik, hamulec i poziomowanie (opis: docs/b4_cechy.md; kontrakt: drzwi.sql).
--
-- prad_* i blad_poziomowania są puste w oknach bez jazdy; temperatury są w każdym oknie.
-- temp_maszynowni to tło (otoczenie silnika): pozwala odróżnić grzanie silnika od upału.
SELECT
    id_windy,
    ts_utc,
    prad_silnika_sr_a AS naped_prad_sr,
    prad_silnika_max_a AS naped_prad_max,
    temp_silnika_c AS naped_temp_silnika,
    temp_maszynowni_c AS naped_temp_maszynowni,
    blad_poziomowania_sr_mm AS naped_blad_poziomowania,
    bledy_napedu AS naped_bledy
FROM telemetria
