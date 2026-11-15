import duckdb
import pytest
from api.adapters.duckdb_baza import (
    KATALOG_REPO,
    KOLUMNY_CZASU_CRM,
    WIDOKI_TELEMETRII,
    _tabele_trwale,
    pliki_tabel,
    polacz,
    zbuduj_baze,
)


@pytest.fixture(scope="module")
def baza(tmp_path_factory):
    sciezka = tmp_path_factory.mktemp("baza") / "domilo.duckdb"
    liczby = zbuduj_baze(sciezka)
    con = polacz(sciezka)
    yield con, liczby
    con.close()


def test_kazdy_plik_parquet_poza_telemetria_ma_tabele_o_tej_samej_nazwie_i_liczbie_wierszy(baza):
    con, _ = baza
    tabele = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    pliki = pliki_tabel()
    # + tabele trwałe aplikacji (puste w nowej bazie, potrzebne jako źródła modeli dbt)
    assert tabele == set(pliki) | set(_tabele_trwale())
    zrodlo = duckdb.connect()
    for nazwa, plik in pliki.items():
        assert (
            con.execute(f"SELECT count(*) FROM {nazwa}").fetchone()
            == zrodlo.execute(f"SELECT count(*) FROM read_parquet('{plik}')").fetchone()
        ), nazwa


def test_partycje_telemetrii_sa_widokami_a_nie_tabelami(baza):
    con, liczby = baza
    widoki = {r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    assert widoki == set(WIDOKI_TELEMETRII)
    for nazwa in WIDOKI_TELEMETRII:
        assert liczby[nazwa] > 0
        assert all(nazwa not in p.parts for p in pliki_tabel().values())


def test_czas_crm_jest_timestamptz_i_wskazuje_ten_sam_moment_co_tekst_zrodlowy(baza):
    con, _ = baza
    for tabela, kolumny in KOLUMNY_CZASU_CRM.items():
        for kol in kolumny:
            typ = con.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
                [tabela, kol],
            ).fetchone()[0]
            assert typ == "TIMESTAMP WITH TIME ZONE", (tabela, kol)
    roznice = con.execute(
        "SELECT count(*) FROM crm_leady b JOIN read_parquet('data/crm/crm_leady.parquet') s USING (id_leada) "
        "WHERE b.utworzono <> CAST(s.utworzono AS TIMESTAMPTZ) "
        "OR epoch(b.utworzono) <> epoch(strptime(s.utworzono, '%Y-%m-%dT%H:%M:%S%z'))"
    ).fetchone()[0]
    assert roznice == 0


def test_serwisownik_zostaje_czasem_lokalnym_bez_strefy_a_telemetria_w_utc(baza):
    con, _ = baza

    def typ(tabela, kol):
        return con.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = ? AND column_name = ?", [tabela, kol]
        ).fetchone()[0]

    assert typ("serwis_zgloszenia", "utworzono").startswith("TIMESTAMP") and "ZONE" not in typ(
        "serwis_zgloszenia", "utworzono"
    )
    assert typ("telemetra_windy", "ts_utc") == "TIMESTAMP WITH TIME ZONE"
    assert typ("telemetra_cieplo", "ts_utc") == "TIMESTAMP WITH TIME ZONE"


def test_koszt_netto_czesci_jest_liczba_zgodna_z_tekstem_zrodlowym(baza):
    con, _ = baza
    assert (
        con.execute("SELECT sum(koszt_netto), count(koszt_netto) FROM serwis_czesci").fetchone()
        == con.execute(
            "SELECT sum(CAST(replace(replace(koszt_netto, ' ', ''), ',', '.') AS DECIMAL(12, 2))), count(koszt_netto) "
            "FROM read_parquet('data/serwis/serwis_czesci.parquet')"
        ).fetchone()
    )


def test_widoki_dzialaja_niezaleznie_od_katalogu_roboczego(baza, monkeypatch, tmp_path):
    con, liczby = baza
    monkeypatch.chdir(tmp_path)
    assert con.execute("SELECT count(*) FROM telemetra_windy").fetchone()[0] == liczby["telemetra_windy"]


def test_budowa_nie_zapisuje_niczego_w_data(baza):
    zmienione = [p for p in (KATALOG_REPO / "data").rglob("*") if p.suffix in {".duckdb", ".tmp", ".wal"}]
    assert zmienione == []
