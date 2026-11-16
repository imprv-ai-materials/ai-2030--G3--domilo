from pathlib import Path

import duckdb
import yaml
from api.ai.features.windy import cechy, tsfresh_cechy

KATALOG = yaml.safe_load(Path(cechy.__file__).with_name("katalog.yaml").read_text(encoding="utf-8"))


def test_katalog_opisuje_wszystkie_sygnaly_reczne():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE telemetra_windy (id_windy VARCHAR, ts_utc TIMESTAMPTZ, kursy SMALLINT, otwarcia_drzwi SMALLINT, "
        "ponowne_otwarcia SMALLINT, czas_zamykania_drzwi_sr_s FLOAT, czas_zamykania_drzwi_max_s FLOAT, "
        "prad_silnika_sr_a FLOAT, prad_silnika_max_a FLOAT, temp_silnika_c FLOAT, temp_maszynowni_c FLOAT, "
        "wibracje_rms_mg FLOAT, blad_poziomowania_sr_mm FLOAT, bledy_drzwi TINYINT, bledy_napedu TINYINT, "
        "bledy_sterownika TINYINT, kody_bledow VARCHAR, tryb VARCHAR, firmware VARCHAR)"
    )
    con.execute("CREATE TABLE serwis_windy (id_windy VARCHAR, czujnik_wibracji_od TIMESTAMP)")
    con.execute("CREATE TEMP VIEW telemetria AS SELECT * FROM telemetra_windy")
    sygnaly = {s for r in cechy.RODZINY for s in cechy.sygnaly(con, r)}
    assert sygnaly == set(KATALOG["cechy_reczne"]["sygnaly"])
    statystyki = {k.removeprefix("x_") for k in cechy.nazwy_cech("x")}
    assert statystyki == set(KATALOG["cechy_reczne"]["statystyki"])


def test_katalog_opisuje_wszystkie_cechy_tsfresh():
    opisane = {
        f"ts_{s}_{c}" for s in KATALOG["cechy_tsfresh"]["sygnaly"] for c in KATALOG["cechy_tsfresh"]["statystyki"]
    }
    assert opisane == set(tsfresh_cechy.nazwy_cech())
    wybrane = yaml.safe_load(tsfresh_cechy.PLIK_WYBRANYCH.read_text(encoding="utf-8"))
    assert set(wybrane["wybrane"]) | set(wybrane["odrzucone"]) == opisane
