from datetime import datetime

import duckdb
import pandas as pd
import pytest
from api.ai.features.windy.awarie_odtworzone import BledyEkstrakcji, wczytaj_llm, zbuduj_awarie_odtworzone

# (id_zgloszenia, id_windy, id_budynku, utworzono — czas lokalny Europe/Warsaw bez strefy, kategoria)
ZGLOSZENIA = [
    ("Z1", "W1", "B1", "2025-06-01 11:15", "awaria"),  # w trakcie przestoju (CEST: 09:15 UTC)
    ("Z2", "W1", "B1", "2025-06-01 20:00", "usterka"),  # 8 h 45 min po Z1 -> ta sama awaria
    ("Z3", "W1", "B1", "2025-06-02 22:00", "awaria"),  # 26 h po Z2 -> nowa awaria, bez serii przestoju w 24 h
    ("Z4", "W1", "B1", "2025-06-01 12:00", "konserwacja"),  # bez awarii wg LLM, praca planowa -> nie dołączamy
    ("Z8", "W1", "B1", "2025-06-01 13:00", "interwencja"),  # bez awarii wg LLM (dubel) -> dołączone do W1/Z1
    ("Z9", "W1", "B1", "2025-06-02 21:00", "inne"),  # bez awarii, 25 h po Z2 -> nie dołączamy (nie zaczyna awarii)
    ("Z5", "W2", "B2", "2025-01-15 12:00", "awaria"),  # zima (CET: 11:00 UTC)
    ("Z6", "W3", "B3", "2025-06-01 12:00", "awaria"),  # winda bez telemetrii
    ("Z7", None, "B4", "2025-06-01 12:00", "awaria"),  # winda nieustalona
]
# (id_zgloszenia, czy_awaria, podzespol)
LLM = [
    ("Z1", True, "brak"),
    ("Z2", True, "naped"),
    ("Z3", True, "drzwi"),
    ("Z4", False, "brak"),
    ("Z5", True, "sterownik"),
    ("Z6", True, "drzwi"),
    ("Z7", True, "drzwi"),
    ("Z8", False, "brak"),
    ("Z9", False, "brak"),
]
NOTATKI = [
    ("Z1", "K01", "2025-06-01 12:30"),
    ("Z8", "KOORD", "2025-06-01 13:05"),
    ("Z2", "K01", "2025-06-01 20:30"),
    ("Z4", "K02", "2025-06-01 11:20"),  # praca planowa, nie liczy się do pierwszej notatki
]


def _telemetria(con, id_windy, od_utc, do_utc, martwe=(), wylaczona=()):
    """Okna co 10 min (ts = koniec okna, UTC); kursy = 1, poza zakresami `martwe` (kursy = 0)."""
    warunek = " OR ".join(f"ts BETWEEN TIMESTAMPTZ '{a}+00' AND TIMESTAMPTZ '{b}+00'" for a, b in martwe) or "false"
    wyl = " OR ".join(f"ts BETWEEN TIMESTAMPTZ '{a}+00' AND TIMESTAMPTZ '{b}+00'" for a, b in wylaczona) or "false"
    con.execute(f"""
        INSERT INTO telemetra_windy
        SELECT '{id_windy}', ts, CASE WHEN {warunek} OR {wyl} THEN 0 ELSE 1 END,
               CASE WHEN {wyl} THEN 'wylaczona' ELSE 'normalny' END
        FROM generate_series(TIMESTAMPTZ '{od_utc}+00', TIMESTAMPTZ '{do_utc}+00', INTERVAL 10 MINUTE) t(ts)
        """)


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute(
        "CREATE TABLE zgloszenia_wind (id_zgloszenia VARCHAR, id_windy VARCHAR, id_budynku VARCHAR, "
        "utworzono TIMESTAMP, kategoria VARCHAR)"
    )
    con.executemany("INSERT INTO zgloszenia_wind VALUES (?, ?, ?, ?, ?)", ZGLOSZENIA)
    con.execute("CREATE TABLE serwis_notatki (id_zgloszenia VARCHAR, autor VARCHAR, data_czas TIMESTAMP)")
    con.executemany("INSERT INTO serwis_notatki VALUES (?, ?, ?)", NOTATKI)
    con.execute("CREATE TABLE telemetra_windy (id_windy VARCHAR, ts_utc TIMESTAMPTZ, kursy INTEGER, tryb VARCHAR)")
    # W1: krótka przerwa (2 okna) rano i przestój od 08:40 UTC (ostatnie okno z jazdą 08:30 UTC = 10:30 lokalnie)
    _telemetria(
        con,
        "W1",
        "2025-06-01 00:10",
        "2025-06-03 00:00",
        martwe=[("2025-06-01 07:10", "2025-06-01 07:20"), ("2025-06-01 08:40", "2025-06-01 08:50")],
        wylaczona=[("2025-06-01 09:00", "2025-06-01 12:00")],
    )
    # W2 (zima): ostatnie okno z jazdą 10:00 UTC = 11:00 lokalnie
    _telemetria(con, "W2", "2025-01-14 00:10", "2025-01-16 00:00", martwe=[("2025-01-15 10:10", "2025-01-15 12:00")])
    return con


def _llm():
    df = pd.DataFrame(LLM, columns=["id_zgloszenia", "czy_awaria", "podzespol"])
    return df.assign(objaw="x", pewnosc=0.9)


def _awarie(con):
    zbuduj_awarie_odtworzone(con, _llm())
    return con.execute("SELECT * FROM awarie_odtworzone").df().set_index("id_awarii")


def test_zgloszenia_tej_samej_windy_w_24h_to_jedna_awaria(con):
    a = _awarie(con)
    assert sorted(a.index) == ["W1/Z1", "W1/Z3", "W2/Z5", "W3/Z6"]
    assert list(a.loc["W1/Z1", "id_zgloszen_awaria"]) == ["Z1", "Z2"]
    assert a.loc["W1/Z1", "liczba_zgloszen_awaria"] == 2


def test_dubel_bez_awarii_dolaczony_a_praca_planowa_i_zgloszenie_poza_oknem_nie(con):
    a = _awarie(con)
    assert list(a.loc["W1/Z1", "id_zgloszen"]) == ["Z1", "Z8", "Z2"]
    assert a.loc["W1/Z1", "liczba_zgloszen"] == 3
    assert list(a.loc["W1/Z3", "id_zgloszen"]) == ["Z3"]


def test_podzespol_awarii_to_najczestszy_rozny_od_brak(con):
    a = _awarie(con)
    assert a.loc["W1/Z1", "podzespol"] == "naped"


def test_start_z_telemetrii_w_czasie_lokalnym_latem_i_zima(con):
    a = _awarie(con)
    assert a.loc["W1/Z1", "start_awarii"] == datetime(2025, 6, 1, 10, 30)
    assert a.loc["W1/Z1", "koniec_przestoju"] == datetime(2025, 6, 1, 14, 0)
    assert a.loc["W1/Z1", "przestoj_h"] == pytest.approx(3.5)
    assert bool(a.loc["W1/Z1", "wylaczona"]) is True
    assert a.loc["W2/Z5", "start_awarii"] == datetime(2025, 1, 15, 11, 0)
    assert a.loc["W1/Z1", "zrodlo_startu"] == "telemetria"


def test_krotka_przerwa_nie_jest_seria_a_brak_serii_i_telemetrii_ma_osobny_status(con):
    a = _awarie(con)
    assert a.loc["W1/Z3", "zrodlo_startu"] == "brak_serii" and pd.isna(a.loc["W1/Z3", "start_awarii"])
    assert a.loc["W3/Z6", "zrodlo_startu"] == "brak_telemetrii"
    assert a.loc["W1/Z3", "czas_awarii"] == datetime(2025, 6, 2, 22, 0)


def test_minuty_od_startu_do_pierwszej_notatki(con):
    a = _awarie(con)
    assert a.loc["W1/Z1", "minuty_start_do_notatki"] == 120
    assert a.loc["W1/Z1", "minuty_start_do_notatki_konserwatora"] == 120
    assert a.loc["W1/Z1", "minuty_start_do_zgloszenia"] == 45


def test_bledy_ekstrakcji_przerywaja_budowe(tmp_path):
    plik = tmp_path / "x.parquet"
    _llm().assign(blad=["InternalServerError"] + [None] * (len(LLM) - 1)).to_parquet(plik)
    with pytest.raises(BledyEkstrakcji):
        wczytaj_llm(plik)
