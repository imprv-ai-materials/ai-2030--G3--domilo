from decimal import Decimal

import duckdb
import pytest
from api.adapters.serwisownik import KOLUMNY_CZASU, wczytaj


def _zapisz_parquet(con, sciezka, select):
    con.execute(f"COPY ({select}) TO '{sciezka.as_posix()}' (FORMAT parquet)")
    return sciezka


@pytest.fixture
def pliki(tmp_path):
    zrodlo = duckdb.connect()
    return {
        "serwis_czesci": _zapisz_parquet(
            zrodlo,
            tmp_path / "serwis_czesci.parquet",
            "SELECT * FROM (VALUES ('Z1', '1 234,50'), ('Z2', '88,39'), ('Z3', NULL), ('Z4', '12 345 678,05'))"
            " t(id_zgloszenia, koszt_netto)",
        ),
        "serwis_zgloszenia": _zapisz_parquet(
            zrodlo,
            tmp_path / "serwis_zgloszenia.parquet",
            "SELECT 'Z1' AS id_zgloszenia, CAST('2025-10-26 02:30:00' AS TIMESTAMP_NS) AS utworzono, "
            "CAST(NULL AS TIMESTAMP_NS) AS zamknieto",
        ),
    }


def test_koszt_netto_z_przecinkiem_i_spacja_tysiecy_staje_sie_liczba(pliki):
    con = duckdb.connect()
    wczytaj(con, pliki)
    assert con.execute("SELECT id_zgloszenia, koszt_netto FROM serwis_czesci ORDER BY 1").fetchall() == [
        ("Z1", Decimal("1234.50")),
        ("Z2", Decimal("88.39")),
        ("Z3", None),
        ("Z4", Decimal("12345678.05")),
    ]
    typ = con.execute(
        "SELECT data_type FROM information_schema.columns WHERE table_name = 'serwis_czesci' "
        "AND column_name = 'koszt_netto'"
    ).fetchone()[0]
    assert typ == "DECIMAL(12,2)"


@pytest.mark.parametrize("zly", ["12.50", "1,234.50", "12,5", "abc", "1234,50 zł"])
def test_koszt_netto_w_nieznanym_formacie_przerywa_wczytywanie(tmp_path, pliki, zly):
    zrodlo = duckdb.connect()
    pliki["serwis_czesci"] = _zapisz_parquet(
        zrodlo,
        tmp_path / "zle_czesci.parquet",
        f"SELECT * FROM (VALUES ('Z1', '88,39'), ('Z2', '{zly}')) t(id_zgloszenia, koszt_netto)",
    )
    con = duckdb.connect()
    with pytest.raises(ValueError, match="koszt_netto"):
        wczytaj(con, pliki)


def test_czas_serwisownika_jest_timestamp_bez_strefy_z_ta_sama_godzina_lokalna(pliki):
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    wczytaj(con, pliki)
    for kol in KOLUMNY_CZASU["serwis_zgloszenia"]:
        typ = con.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = 'serwis_zgloszenia' "
            "AND column_name = ?",
            [kol],
        ).fetchone()[0]
        assert typ == "TIMESTAMP", kol
    # podwójna godzina zmiany czasu zostaje bez zmian (baza jej nie rozstrzyga)
    assert str(con.execute("SELECT utworzono FROM serwis_zgloszenia").fetchone()[0]) == "2025-10-26 02:30:00"


def test_wczytaj_zwraca_liczby_wierszy_i_pomija_tabele_spoza_serwisownika(pliki, tmp_path):
    zrodlo = duckdb.connect()
    pliki["crm_leady"] = _zapisz_parquet(zrodlo, tmp_path / "crm_leady.parquet", "SELECT 1 AS x")
    con = duckdb.connect()
    assert wczytaj(con, pliki) == {"serwis_czesci": 4, "serwis_zgloszenia": 1}
    assert {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()} == {
        "serwis_czesci",
        "serwis_zgloszenia",
    }
