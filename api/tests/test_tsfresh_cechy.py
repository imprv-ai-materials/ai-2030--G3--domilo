import duckdb
import numpy as np
import pandas as pd
import pytest
from api.ai.features.windy.tsfresh_cechy import (
    GODZIN,
    MIN_GODZIN,
    dlugi_format,
    nazwy_cech,
    przebiegi,
    przygotuj,
    uzupelnij,
    wybierz_cechy,
    wyciagnij,
)


def _macierz(funkcja, n=1):
    h = np.arange(GODZIN, dtype="float64")
    return np.vstack([funkcja(h) for _ in range(n)])


def test_pasmo_dobowe_i_rms_sinusoidy_24h():
    m = {
        "drzwi_czas_zamykania": _macierz(lambda h: 3 + np.sin(2 * np.pi * h / 24)),
        "naped_prad": _macierz(lambda h: 10 + np.sin(2 * np.pi * h / 6)),  # okres 6 h -> pasmo krótkie (k = 28)
        "wibracje_rms": np.full((1, GODZIN), np.nan),  # bez czujnika -> cechy NULL
    }
    c = wyciagnij(dlugi_format(m, od=0)).iloc[0]
    assert c["ts_drzwi_czas_zamykania_fft_doba"] == pytest.approx(1.0, abs=1e-9)
    assert c["ts_drzwi_czas_zamykania_rms"] == pytest.approx(np.sqrt(9 + 0.5), rel=1e-6)
    assert c["ts_drzwi_czas_zamykania_energia"] == pytest.approx(GODZIN * (9 + 0.5), rel=1e-6)
    assert c["ts_naped_prad_fft_krotkie"] == pytest.approx(1.0, abs=1e-9)
    assert sum(c[f"ts_naped_prad_fft_{p}"] for p in ("dlugie", "doba", "pol_doby", "krotkie")) == pytest.approx(1.0)
    assert np.isnan(c["ts_wibracje_rms_rms"])
    assert list(c.index) == nazwy_cech()


def test_uzupelnij_interpolacja_i_minimum_godzin():
    m = np.vstack([np.arange(GODZIN, dtype="float64"), np.full(GODZIN, np.nan)])
    m[0, 10] = np.nan
    m[1, : MIN_GODZIN - 1] = 1.0  # za mało godzin
    wynik, ok = uzupelnij(m)
    assert ok.tolist() == [True, False]
    assert wynik[0, 10] == pytest.approx(10.0)


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute("CREATE TABLE serwis_windy (id_windy VARCHAR, czujnik_wibracji_od TIMESTAMP)")
    con.execute("INSERT INTO serwis_windy VALUES ('W1', '2025-02-18 00:00')")
    con.execute("""
        CREATE TABLE telemetra_windy AS
        SELECT 'W1' AS id_windy, timezone('Europe/Warsaw', ts) AS ts_utc,
            CAST(3.0 AS FLOAT) AS czas_zamykania_drzwi_sr_s, CAST(11.0 AS FLOAT) AS prad_silnika_sr_a,
            CAST(20.0 AS FLOAT) AS wibracje_rms_mg, 'normalny' AS tryb
        FROM generate_series(TIMESTAMP '2025-02-01 00:10', TIMESTAMP '2025-02-25 00:00', INTERVAL 10 MINUTE) AS g(ts)
        """)
    # okno serwisowe z ogromnym prądem -> wykluczone; okno 06:00 dnia oceny -> poza przebiegiem
    con.execute(
        "UPDATE telemetra_windy SET prad_silnika_sr_a = 999, tryb = 'serwis' "
        "WHERE ts_utc = timezone('Europe/Warsaw', TIMESTAMP '2025-02-15 12:00')"
    )
    con.execute(
        "UPDATE telemetra_windy SET czas_zamykania_drzwi_sr_s = 99 "
        "WHERE ts_utc = timezone('Europe/Warsaw', TIMESTAMP '2025-02-20 06:00')"
    )
    con.execute(
        "UPDATE telemetra_windy SET czas_zamykania_drzwi_sr_s = 5 "
        "WHERE ts_utc = timezone('Europe/Warsaw', TIMESTAMP '2025-02-20 05:50')"
    )
    con.execute("CREATE TABLE dni_wind (id_windy VARCHAR, dzien DATE)")
    con.execute("INSERT INTO dni_wind VALUES ('W1', DATE '2025-02-20')")
    return con


def test_przebieg_168_godzin_do_0550_bez_serwisu(con):
    assert przygotuj(con) == 1
    m = przebiegi(con, 0, 1)
    drzwi, prad, wib = m["drzwi_czas_zamykania"][0], m["naped_prad"][0], m["wibracje_rms"][0]
    assert drzwi.shape == (GODZIN,)
    # ostatnia godzina = okna 04:50 (wył.) … 05:50: 5 okien po 3,0 i jedno 5,0
    assert drzwi[-1] == pytest.approx((5 * 3.0 + 5.0) / 6)
    assert 99 not in drzwi
    assert np.nanmax(prad) == pytest.approx(11.0)
    # wibracje: czujnik od 2025-02-18 00:00 -> godziny wcześniejsze NaN (przebieg zaczyna się 2025-02-13 05:50)
    assert np.isnan(wib[:100]).all() and np.isfinite(wib[-40:]).all()


def test_selekcja_bez_brakow_osobno_dla_wibracji():
    rng = np.random.default_rng(0)
    n = 400
    y = pd.Series(rng.integers(0, 2, n))
    dane = pd.DataFrame({c: rng.normal(size=n) for c in nazwy_cech()})
    dane["ts_naped_prad_rms"] += 2 * y  # jedyna cecha związana z celem
    dane.loc[: n // 2, [c for c in nazwy_cech() if c.startswith("ts_wibracje")]] = np.nan
    tabela = wybierz_cechy(dane, y)
    assert set(tabela.loc[tabela["relevant"], "feature"]) == {"ts_naped_prad_rms"}
    assert tabela.loc[tabela["grupa"] == "wibracje", "wiersze"].iloc[0] == n - n // 2 - 1
