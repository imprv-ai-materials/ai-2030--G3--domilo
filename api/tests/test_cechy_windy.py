from datetime import date

import duckdb
import pytest
from api.ai.features.windy.cechy import RODZINY, TABELA, nazwy_cech, sygnaly, zbuduj_cechy_windy

# Telemetria syntetyczna, czas lokalny Europe/Warsaw (ts = koniec 10-minutowego okna).
# W1: 2025-01-01 00:10 – 2025-03-05 00:00 (zima, bez zmiany czasu); W2: wokół zmiany czasu 2025-03-30.
# Wartości bazowe: kursy 2, otwarcia 4, błędy 0, wibracje 20 (także przed montażem — test wymuszenia NULL),
# temp_silnika rośnie liniowo o 1 na dobę, firmware LF-4.1.0 -> LF-5.0.0 od 2025-02-01 02:00.
# (id_windy, ts lokalny, kolumna, wartość) — nadpisania wartości bazowych
NADPISANIA = [
    ("W1", "2025-02-20 05:50", "prad_silnika_max_a", 50),  # ostatnie okno przed oceną 02-20 -> liczy się
    ("W1", "2025-02-20 06:00", "prad_silnika_max_a", 100),  # okno kończące się o 06:00 -> dopiero dzień 02-21
    ("W1", "2025-02-17 06:00", "otwarcia_drzwi", 7),  # odcięcie 02-20 − 72 h + 10 min -> w oknie 3 dni
    ("W1", "2025-02-17 05:50", "otwarcia_drzwi", 9),  # dokładnie odcięcie − 72 h -> poza 3 dniami, w 7 dniach
    ("W2", "2025-03-29 05:00", "kursy", 5),  # 23 h 50 min przed 03-30 05:50 CEST -> w 24 h
    ("W2", "2025-03-29 04:50", "kursy", 6),  # dokładnie 24 h przed -> poza 24 h (doba kalendarzowa by to wzięła)
]
SERWIS = [("W1", "2025-02-19 12:00")]  # okno serwisowe z bledy_drzwi = 9 -> wykluczone
DNI = [
    ("W1", "2025-01-20"),
    ("W1", "2025-02-05"),
    ("W1", "2025-02-12"),
    ("W1", "2025-02-20"),
    ("W1", "2025-02-21"),
    ("W2", "2025-03-30"),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute("CREATE TABLE serwis_windy (id_windy VARCHAR, czujnik_wibracji_od TIMESTAMP)")
    con.execute("INSERT INTO serwis_windy VALUES ('W1', '2025-02-10 00:00'), ('W2', NULL)")
    con.execute("""
        CREATE TABLE telemetra_windy AS
        WITH okna AS (
            SELECT 'W1' AS id_windy, ts FROM generate_series(
                TIMESTAMP '2025-01-01 00:10', TIMESTAMP '2025-03-05 00:00', INTERVAL 10 MINUTE) AS g(ts)
            UNION ALL
            SELECT 'W2', ts FROM generate_series(
                TIMESTAMP '2025-03-20 00:10', TIMESTAMP '2025-04-02 00:00', INTERVAL 10 MINUTE) AS g(ts)
        )
        SELECT
            id_windy,
            timezone('Europe/Warsaw', ts) AS ts_utc,
            CAST(2 AS SMALLINT) AS kursy,
            CAST(4 AS SMALLINT) AS otwarcia_drzwi,
            CAST(0 AS SMALLINT) AS ponowne_otwarcia,
            CAST(3.2 AS FLOAT) AS czas_zamykania_drzwi_sr_s,
            CAST(3.4 AS FLOAT) AS czas_zamykania_drzwi_max_s,
            CAST(11.0 AS FLOAT) AS prad_silnika_sr_a,
            CAST(16.0 AS FLOAT) AS prad_silnika_max_a,
            CAST((epoch(timezone('Europe/Warsaw', ts)) - epoch(TIMESTAMPTZ '2025-01-01 00:00+01')) / 86400 AS FLOAT)
                AS temp_silnika_c,
            CAST(23.0 AS FLOAT) AS temp_maszynowni_c,
            CAST(20.0 AS FLOAT) AS wibracje_rms_mg,
            CAST(3.0 AS FLOAT) AS blad_poziomowania_sr_mm,
            CAST(0 AS TINYINT) AS bledy_drzwi,
            CAST(0 AS TINYINT) AS bledy_napedu,
            CAST(0 AS TINYINT) AS bledy_sterownika,
            CAST(NULL AS VARCHAR) AS kody_bledow,
            'normalny' AS tryb,
            CASE WHEN ts < TIMESTAMP '2025-02-01 02:00' THEN 'LF-4.1.0' ELSE 'LF-5.0.0' END AS firmware
        FROM okna
        """)
    con.execute(
        "UPDATE telemetra_windy SET kursy = 4 WHERE id_windy = 'W1' AND ts_utc > TIMESTAMPTZ '2025-02-15 05:50+01'"
    )
    for id_windy, ts, kolumna, wartosc in NADPISANIA:
        con.execute(
            f"UPDATE telemetra_windy SET {kolumna} = ? WHERE id_windy = ? "
            "AND ts_utc = timezone('Europe/Warsaw', CAST(? AS TIMESTAMP))",
            [wartosc, id_windy, ts],
        )
    for id_windy, ts in SERWIS:
        con.execute(
            "UPDATE telemetra_windy SET tryb = 'serwis', bledy_drzwi = 9 WHERE id_windy = ? "
            "AND ts_utc = timezone('Europe/Warsaw', CAST(? AS TIMESTAMP))",
            [id_windy, ts],
        )
    con.execute("CREATE TABLE dni_wind (id_windy VARCHAR, dzien DATE)")
    con.executemany("INSERT INTO dni_wind VALUES (?, CAST(? AS DATE))", DNI)
    zbuduj_cechy_windy(con)
    return con


def _cecha(con, id_windy, dzien, kolumna):
    return con.execute(
        f"SELECT {kolumna} FROM {TABELA} WHERE id_windy = ? AND dzien = ?", [id_windy, date.fromisoformat(dzien)]
    ).fetchone()[0]


def test_wiersz_na_kazdy_dzien_dni_wind(con):
    assert con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0] == len(DNI)


def test_kolumny_wszystkich_rodzin(con):
    kolumny = {r[0] for r in con.execute(f"DESCRIBE {TABELA}").fetchall()}
    for rodzina in RODZINY:
        for s in sygnaly(con, rodzina):
            assert set(nazwy_cech(s)) <= kolumny
    assert {"ma_czujnik_wibracji", "firmware_dni_od_zmiany", "firmware_zmiana_glowna_44d"} <= kolumny
    assert len(nazwy_cech("x")) == 11


def test_odciecie_0550_okno_0600_nie_liczy_sie(con):
    assert _cecha(con, "W1", "2025-02-20", "naped_prad_max_max_24h") == 50
    assert _cecha(con, "W1", "2025-02-21", "naped_prad_max_max_24h") == 100


def test_granice_okna_3_dni(con):
    assert _cecha(con, "W1", "2025-02-20", "uzycie_otwarcia_drzwi_max_3d") == 7
    assert _cecha(con, "W1", "2025-02-20", "uzycie_otwarcia_drzwi_max_7d") == 9


def test_24h_to_24_godziny_przy_zmianie_czasu(con):
    assert _cecha(con, "W2", "2025-03-30", "uzycie_kursy_max_24h") == 5


def test_okna_serwisowe_wykluczone(con):
    assert _cecha(con, "W1", "2025-02-20", "drzwi_bledy_max_24h") == 0


def test_norma_i_stosunek_do_normy(con):
    # kursy 2 w dniach 15–44 przed 02-20 (01-08 … 02-06), od 02-15 05:50 kursy 4
    assert _cecha(con, "W1", "2025-02-20", "uzycie_kursy_norma") == 2
    assert _cecha(con, "W1", "2025-02-20", "uzycie_kursy_do_normy_24h") == 2
    # norma 0 (brak błędów) -> stosunek NULL
    assert _cecha(con, "W1", "2025-02-20", "drzwi_bledy_norma") == 0
    assert _cecha(con, "W1", "2025-02-20", "drzwi_bledy_do_normy_24h") is None
    # 01-20: tylko 6 dni historii przed dniem 15 (kotwice 01-01 … 01-06) -> norma NULL
    assert _cecha(con, "W1", "2025-01-20", "uzycie_kursy_norma") is None


def test_trend_7_dni(con):
    assert _cecha(con, "W1", "2025-02-20", "naped_temp_silnika_trend_7d") == pytest.approx(1.0, rel=1e-3)  # FLOAT
    assert _cecha(con, "W1", "2025-02-12", "uzycie_kursy_trend_7d") == pytest.approx(0.0)


def test_wibracje_przed_montazem_null_i_flaga(con):
    assert _cecha(con, "W1", "2025-02-05", "wibracje_rms_sr_24h") is None
    assert _cecha(con, "W1", "2025-02-05", "ma_czujnik_wibracji") == 0
    assert _cecha(con, "W1", "2025-02-12", "wibracje_rms_sr_24h") == pytest.approx(20.0)
    assert _cecha(con, "W1", "2025-02-12", "ma_czujnik_wibracji") == 1
    assert _cecha(con, "W1", "2025-02-20", "wibracje_rms_norma") is None  # dni 15–44 przed montażem
    assert _cecha(con, "W2", "2025-03-30", "ma_czujnik_wibracji") == 0


def test_kontekst_firmware(con):
    assert _cecha(con, "W1", "2025-01-20", "firmware_dni_od_zmiany") is None
    assert _cecha(con, "W1", "2025-01-20", "firmware_zmiana_glowna_44d") == 0
    # 02-01 02:00 -> 02-20 05:50: 19 dni 3 h 50 min
    assert _cecha(con, "W1", "2025-02-20", "firmware_dni_od_zmiany") == pytest.approx(19.16, abs=0.01)
    assert _cecha(con, "W1", "2025-02-20", "firmware_zmiana_glowna_44d") == 1


def test_brak_przecieku_dane_po_odcieciu_nie_zmieniaja_cech(con):
    przed = con.execute(f"SELECT * FROM {TABELA} WHERE id_windy = 'W1' AND dzien = DATE '2025-02-12'").fetchall()
    con.execute(
        "UPDATE telemetra_windy SET kursy = 99, bledy_drzwi = 99, wibracje_rms_mg = 999, firmware = 'XX-9.0.0' "
        "WHERE id_windy = 'W1' AND ts_utc > TIMESTAMPTZ '2025-02-12 05:50+01'"
    )
    zbuduj_cechy_windy(con)
    po = con.execute(f"SELECT * FROM {TABELA} WHERE id_windy = 'W1' AND dzien = DATE '2025-02-12'").fetchall()
    assert po == przed
