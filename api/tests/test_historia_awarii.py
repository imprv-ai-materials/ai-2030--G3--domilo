import duckdb
import pytest
from api.ai.failure_model.evals.historia_awarii import _komorka, notatki_obok_siebie, wylosuj_notatki


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE zgloszenia_wind AS SELECT * FROM (VALUES "
        "('Z1', 'awaria', 'Winda nie jeździ'), ('Z2', 'interwencja', 'Winda wyłączona'), ('Z3', 'usterka', 'x')) "
        "t(id_zgloszenia, kategoria, tresc_zgloszenia)"
    )
    con.execute(
        "CREATE TABLE serwis_notatki AS SELECT 'N' || lpad(CAST(i AS VARCHAR), 3, '0') AS id_notatki, "
        "CASE i % 3 WHEN 0 THEN 'Z1' WHEN 1 THEN 'Z2' ELSE 'Z3' END AS id_zgloszenia, 'K01' AS autor, "
        "'notatka ' || i AS tresc FROM range(300) r(i)"
    )
    return con


def test_losowanie_jest_powtarzalne_i_bierze_tylko_dana_kategorie(con):
    pierwsze = wylosuj_notatki(con, "awaria")
    assert len(pierwsze) == 30
    assert pierwsze == wylosuj_notatki(con, "awaria")
    assert {w[1] for w in pierwsze} == {"Z1"}
    assert {w[1] for w in wylosuj_notatki(con, "interwencja")} == {"Z2"}


def test_tabela_obok_siebie_ma_30_wierszy_i_naglowek(con):
    linie = notatki_obok_siebie(con).splitlines()
    assert linie[0].startswith("| # | awaria: zgłoszenie")
    assert len(linie) == 2 + 30


def test_komorka_nie_psuje_tabeli_markdown():
    assert _komorka("Na miejscu.\nWymiana | test") == "Na miejscu.<br>Wymiana \\| test"
    assert _komorka(1234567) == "1 234 567"
    assert _komorka(12.5) == "12,5"
