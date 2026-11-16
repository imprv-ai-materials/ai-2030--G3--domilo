import duckdb
import pytest
from api.ai.features.windy.zgloszenia_wind import TABELA, zbuduj_zgloszenia_wind, zgloszenia_wind

WINDY = [("B1-W1", "B1"), ("B3-W1", "B3"), ("B3-W2", "B3"), ("B3-W3", "B3")]

# (id_zgloszenia, id_budynku, id_urzadzenia, typ_urzadzenia, kategoria)
ZGLOSZENIA = [
    ("Z_id_windy", "B3", "B3-W2", "winda", "awaria"),
    ("Z_id_windy_zly_typ", "B3", "B3-W1", "domofon", "konserwacja"),
    ("Z_bez_id_jedna_winda", "B1", None, "winda", "interwencja"),
    ("Z_bez_id_trzy_windy", "B3", None, "winda", "awaria"),
    ("Z_bez_id_budynek_bez_wind", "B9", None, "winda", "usterka"),
    ("Z_typ_winda_id_pompy", "B3", "B3-PC1", "winda", "usterka"),
    ("Z_domofon_bez_id", "B1", None, "domofon", "awaria"),
    ("Z_pompa", "B3", "B3-PC1", "pompa", "awaria"),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("CREATE TABLE serwis_windy (id_windy VARCHAR, id_budynku VARCHAR)")
    con.executemany("INSERT INTO serwis_windy VALUES (?, ?)", WINDY)
    con.execute(
        "CREATE TABLE serwis_zgloszenia (id_zgloszenia VARCHAR, utworzono TIMESTAMP, id_budynku VARCHAR, "
        "id_urzadzenia VARCHAR, typ_urzadzenia VARCHAR, zrodlo VARCHAR, kategoria VARCHAR, priorytet VARCHAR, "
        "tresc_zgloszenia VARCHAR, firma_serwisowa VARCHAR, status VARCHAR, zamknieto TIMESTAMP)"
    )
    con.executemany(
        "INSERT INTO serwis_zgloszenia VALUES (?, '2025-06-01 10:00', ?, ?, ?, 'portal', ?, 'normalny', 't', 'F', "
        "'zamkniete', '2025-06-02 10:00')",
        ZGLOSZENIA,
    )
    return con


def _wiersze(con):
    return {
        r[0]: r[1:]
        for r in zgloszenia_wind(con).select("id_zgloszenia, id_windy, ustalenie_windy, liczba_wind_budynku").fetchall()
    }


def test_zgloszenie_dotyczy_windy_gdy_id_jest_winda_albo_brak_id_i_typ_winda(con):
    assert set(_wiersze(con)) == {
        "Z_id_windy",
        "Z_id_windy_zly_typ",
        "Z_bez_id_jedna_winda",
        "Z_bez_id_trzy_windy",
        "Z_bez_id_budynek_bez_wind",
    }


def test_winda_z_id_urzadzenia_ma_pierwszenstwo_przed_typem(con):
    w = _wiersze(con)
    assert w["Z_id_windy"] == ("B3-W2", "id_urzadzenia", 3)
    assert w["Z_id_windy_zly_typ"] == ("B3-W1", "id_urzadzenia", 3)


def test_bez_id_winda_ustalona_tylko_gdy_budynek_ma_jedna_winde(con):
    w = _wiersze(con)
    assert w["Z_bez_id_jedna_winda"] == ("B1-W1", "jedyna_winda_budynku", 1)
    assert w["Z_bez_id_trzy_windy"] == (None, "nieustalona", 3)
    assert w["Z_bez_id_budynek_bez_wind"] == (None, "nieustalona", 0)


def test_tabela_ma_jeden_wiersz_na_zgloszenie_i_zachowuje_kategorie(con):
    assert zbuduj_zgloszenia_wind(con) == 5
    assert con.execute(f"SELECT count(DISTINCT id_zgloszenia) FROM {TABELA}").fetchone()[0] == 5
    assert con.execute(f"SELECT kategoria FROM {TABELA} WHERE id_zgloszenia = 'Z_bez_id_trzy_windy'").fetchone() == (
        "awaria",
    )
