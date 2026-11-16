from datetime import date, datetime, timedelta, timezone

import duckdb
import pytest
from api.ai.features.windy.dni_wind import TABELA, zbuduj_dni_wind

UTC = timezone.utc

WINDY = [("W1", "B1", "Alfa"), ("W2", "B2", "Beta")]
# (id_windy, pierwsze okno, ostatnie okno) — czas lokalny Europe/Warsaw; SQL bierze tylko min / max ts_utc
TELEMETRIA = [
    ("W1", "2025-03-20 00:10", "2025-04-20 00:00"),
    ("W2", "2025-03-28 07:00", "2025-04-12 00:00"),  # telemetria od 07:00 -> 2025-03-28 bez wiersza
]
# (id_awarii, id_windy, podzespol, start_awarii (lokalny), okna_przestoju, pierwsze_zgloszenie (lokalny))
AWARIE = [
    ("A1", "W1", "drzwi", "2025-04-01 06:00", 6, "2025-04-01 07:00"),  # start dokładnie o 06:00 (koniec okna 03-25)
    ("A2", "W1", "naped", "2025-04-05 05:00", 18, "2025-04-05 06:30"),  # o 06:00 winda stoi -> 04-05 pominięty
    ("A3", "W1", "brak", None, None, "2025-04-08 12:00"),  # brak serii przestoju: start = pierwsze zgłoszenie
    ("A4", "W1", "sterownik", "2025-04-09 20:00", 60, "2025-04-09 21:00"),  # przestój do 04-10 06:00 włącznie
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute("CREATE TABLE serwis_windy (id_windy VARCHAR, id_budynku VARCHAR, producent VARCHAR)")
    con.executemany("INSERT INTO serwis_windy VALUES (?, ?, ?)", WINDY)
    con.execute("CREATE TABLE telemetra_windy (id_windy VARCHAR, ts_utc TIMESTAMPTZ)")
    for id_windy, od, do in TELEMETRIA:
        con.execute(
            "INSERT INTO telemetra_windy VALUES (?, timezone('Europe/Warsaw', CAST(? AS TIMESTAMP))), "
            "(?, timezone('Europe/Warsaw', CAST(? AS TIMESTAMP)))",
            [id_windy, od, id_windy, do],
        )
    con.execute(
        "CREATE TABLE awarie_odtworzone (id_awarii VARCHAR, id_windy VARCHAR, podzespol VARCHAR, "
        "start_awarii_tz TIMESTAMPTZ, okna_przestoju BIGINT, pierwsze_zgloszenie TIMESTAMP)"
    )
    for id_awarii, id_windy, podzespol, start, okna, pierwsze in AWARIE:
        con.execute(
            "INSERT INTO awarie_odtworzone VALUES (?, ?, ?, timezone('Europe/Warsaw', CAST(? AS TIMESTAMP)), ?, ?)",
            [id_awarii, id_windy, podzespol, start, okna, pierwsze],
        )
    zbuduj_dni_wind(con)
    return con


def _dni(con, id_windy):
    wiersze = con.execute(
        f"SELECT dzien, awaria_7d, id_awarii, liczba_awarii_7d FROM {TABELA} WHERE id_windy = ? ORDER BY dzien",
        [id_windy],
    ).fetchall()
    return {r[0]: r[1:] for r in wiersze}


def _d(tekst):
    return date.fromisoformat(tekst)


def test_zakres_dni_wedlug_telemetrii(con):
    w1, w2 = _dni(con, "W1"), _dni(con, "W2")
    # W1: od pierwszego dnia telemetrii; ostatni dzień, którego okno (do 06:00 t+7) mieści się w telemetrii: 04-12
    assert min(w1) == _d("2025-03-20") and max(w1) == _d("2025-04-12")
    # W2: 2025-03-28 06:00 jest przed pierwszym oknem (07:00); 04-04 + 7 dni 06:00 = 04-11 06:00 <= 04-12 00:00
    assert min(w2) == _d("2025-03-29") and max(w2) == _d("2025-04-04")
    assert all(v[0] == 0 for v in w2.values())


def test_jeden_wiersz_na_winde_i_dzien(con):
    n, n_unikalnych = con.execute(f"SELECT count(*), count(DISTINCT (id_windy, dzien)) FROM {TABELA}").fetchone()
    assert n == n_unikalnych


def test_okno_lewostronnie_otwarte_prawostronnie_domkniete(con):
    w1 = _dni(con, "W1")
    # A1 startuje 2025-04-01 06:00: należy do okna dnia 03-25 (koniec okna włącznie), nie do okna dnia 04-01
    assert w1[_d("2025-03-24")][0] == 0
    assert w1[_d("2025-03-25")] == (1, "A1", 1)
    assert w1[_d("2025-03-31")][0] == 1
    # dzień 04-01: start A1 = chwila predykcji, winda jeszcze jeździła (przestój od 06:00 wyłącznie) -> wiersz jest
    assert _d("2025-04-01") in w1


def test_kilka_awarii_w_oknie_pierwsza_wedlug_startu(con):
    # 03-29: w oknie (03-29 06:00; 04-05 06:00] są A1 (04-01 06:00) i A2 (04-05 05:00)
    assert _dni(con, "W1")[_d("2025-03-29")] == (1, "A1", 2)


def test_pomija_dni_gdy_winda_stoi_o_6(con):
    w1 = _dni(con, "W1")
    assert _d("2025-04-05") not in w1  # A2: przestój 05:00–08:00
    assert _d("2025-04-10") not in w1  # A4: przestój do 06:00 włącznie (koniec ostatniego martwego okna)
    assert _d("2025-04-09") in w1  # A4 startuje o 20:00, o 06:00 winda jeździ
    assert w1[_d("2025-04-09")] == (1, "A4", 1)


def test_awaria_bez_serii_przestoju_ma_start_z_pierwszego_zgloszenia(con):
    w1 = _dni(con, "W1")
    assert w1[_d("2025-04-08")][1] == "A3"  # 04-08 12:00 w oknie dnia 04-08
    assert w1[_d("2025-04-01")][1] == "A2"  # A2 przed A3
    assert w1[_d("2025-04-06")] == (1, "A3", 2)  # A3 i A4; bez przestoju A3 żaden dzień nie jest pominięty


def test_chwila_predykcji_06_lokalnie_przy_zmianie_czasu(con):
    wiersze = dict(
        con.execute(f"SELECT dzien, (moment_predykcji, koniec_okna) FROM {TABELA} WHERE id_windy = 'W1'").fetchall()
    )
    m29, _ = wiersze[_d("2025-03-29")]
    m31, _ = wiersze[_d("2025-03-31")]
    assert m29.astimezone(UTC) == datetime(2025, 3, 29, 5, 0, tzinfo=UTC)  # CET
    assert m31.astimezone(UTC) == datetime(2025, 3, 31, 4, 0, tzinfo=UTC)  # CEST
    m25, k25 = wiersze[_d("2025-03-25")]
    assert k25 - m25 == timedelta(hours=167)  # tydzień ze zmianą czasu na letni
    # godziny do startu A1 (04-01 06:00 CEST) od 03-25 06:00 CET: 167 h, nie 168 h (odejmowanie TIMESTAMPTZ w DuckDB
    # daje „7 days”, które epoch() liczy jako 168 h)
    godziny = con.execute(
        f"SELECT godziny_do_startu FROM {TABELA} WHERE id_windy = 'W1' AND dzien = DATE '2025-03-25'"
    ).fetchone()[0]
    assert godziny == 167.0
