"""Panel kierownika zespołu najmu: ranking kolejki (kolejka_dzienna.ranking_kolejki), ranking wstecz (kolejka_wstecz),
pominięcia z CRM (atrapa dev/mock_lejek -> POST /leads/skips -> kolejka_pominiecia), modele dbt panelu
(schemat metryki) i GET /team/dashboard. Testy bez LLM."""

import importlib.util
import shutil
import typing
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from api.adapters import kolejka_pominiecia, kolejka_ranking
from api.adapters.crm_lejek import KlientLejka
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polacz
from api.contexts_boundaries.leasing_bc import kolejka_dzienna as kd
from api.contexts_boundaries.leasing_bc import kolejka_wstecz as kw
from api.contexts_boundaries.leasing_bc.pominiecia import POWODY_POMINIECIA
from api.contexts_boundaries.leasing_bc.schematy import KodPowodu
from fastapi.testclient import TestClient

DZIEN = "2026-05-20"


def _modul_atrapy():
    spec = importlib.util.spec_from_file_location("mock_lejek_app", KATALOG_REPO / "dev" / "mock_lejek" / "app.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _wprost(id_kroku, handler, *args):
    return handler(*args)


# --- słownik powodów -----------------------------------------------------------------------------------------------


def test_slownik_powodow_jest_ten_sam_w_domilo_api_i_atrapie_crm():
    assert list(POWODY_POMINIECIA) == ["znam_klienta", "brak_lokalu", "duplikat", "inne"]
    assert set(typing.get_args(KodPowodu)) == set(POWODY_POMINIECIA)
    assert _modul_atrapy().POWODY_POMINIECIA == POWODY_POMINIECIA


def test_tabela_pominiec_odrzuca_kod_spoza_slownika(tmp_path):
    con = polacz(tmp_path / "x.duckdb", tylko_odczyt=False)
    kolejka_pominiecia.utworz(con)
    with pytest.raises(Exception, match="CHECK|Constraint"):
        con.execute(
            "INSERT INTO kolejka_pominiecia VALUES (DATE '2026-05-20', 'L1', 'D01', 1, 'nie_chce', NULL, now(), now())"
        )
    con.close()


# --- ranking -------------------------------------------------------------------------------------------------------


def test_ranking_obejmuje_wszystkie_otwarte_zapytania_z_ranga_w_miescie():
    ev = pd.DataFrame(
        {
            "id_leada": ["W1", "W2", "W3", "K1", "S1", "S2", "X"],
            "miasto": ["Warszawa", "Warszawa", "Warszawa", "Kraków", "Szczecin", "Szczecin", "Kraków"],
            "ev": [30.0, 20.0, 10.0, 5.0, 7.0, 9.0, None],
        }
    )
    doradcy = pd.DataFrame({"id_doradcy": ["D01", "D02", "D04"], "miasto": ["Warszawa", "Warszawa", "Kraków"]})
    r = kd.ranking_kolejki(ev, doradcy, maks=1).set_index("id_leada")
    assert "X" not in r.index  # bez EV: poza rankingiem
    assert r.loc[["W1", "W2", "W3"], "ranga"].tolist() == [1, 2, 3]
    assert r.loc["W1", "otwarte_w_miescie"] == 3
    assert r.loc[["W1", "W2"], "id_doradcy"].tolist() == ["D01", "D02"]
    assert pd.isna(r.loc["W3", "id_doradcy"]) and pd.isna(r.loc["W3", "pozycja"])  # poza 1 × 2 pozycjami
    assert r.loc[["S2", "S1"], "ranga"].tolist() == [1, 2] and r.loc[["S1", "S2"], "id_doradcy"].isna().all()
    assert kd.przydziel_kolejki(ev, doradcy, maks=1)["id_leada"].tolist() == ["K1", "W1", "W2"]


# --- kopia bazy z kolejką z zadania dla 2026-05-20 ------------------------------------------------------------------


@pytest.fixture(scope="module")
def srodowisko(tmp_path_factory):
    """Kopia bazy, dzienne zadanie (bez LLM, sygnały z cache) dla DZIEN do atrapy CRM; API Domilo na kopii."""
    from api.adapters.duckdb_baza import polaczenie
    from api.main import app, baza, baza_zapis

    katalog = tmp_path_factory.mktemp("panel")
    sciezka = katalog / "domilo.duckdb"
    shutil.copyfile(SCIEZKA_BAZY, sciezka)

    def baza_kopia():
        with polaczenie(sciezka=sciezka) as c:
            yield c

    def baza_zapis_kopia():
        with polaczenie(tylko_odczyt=False, sciezka=sciezka) as c:
            yield c

    app.dependency_overrides[baza] = baza_kopia
    app.dependency_overrides[baza_zapis] = baza_zapis_kopia
    api = TestClient(app)
    atrapa = TestClient(_modul_atrapy().utworz_aplikacje(katalog / "stan.json", api_domilo=api, url_domilo=""))
    wynik = kd.wykonaj_kolejke_doradcow(
        _wprost,
        "test-panel",
        DZIEN,
        sciezka=sciezka,
        katalog_bazowy=katalog,
        klient_lejka=KlientLejka(url="http://testserver", http=atrapa),
        z_llm=False,
    )
    yield {"sciezka": sciezka, "api": api, "atrapa": atrapa, "wynik": wynik}
    app.dependency_overrides.clear()


def test_zadanie_zapisuje_pelny_ranking_dnia_a_kolejki_sa_jego_czescia(srodowisko):
    con = polacz(srodowisko["sciezka"])
    r = con.execute("SELECT * FROM kolejka_ranking WHERE data_kolejki = ?", [DZIEN]).df()
    k = con.execute("SELECT id_leada, id_doradcy, pozycja FROM kolejka_doradcow WHERE data_kolejki = ?", [DZIEN]).df()
    con.close()
    assert len(r) == srodowisko["wynik"]["otwarte"]["zapytania"] and set(r["zrodlo_kolejki"]) == {"zadanie"}
    z_kolejka = r[r["id_doradcy"].notna()][["id_leada", "id_doradcy", "pozycja"]]
    pd.testing.assert_frame_equal(
        z_kolejka.sort_values("id_leada").reset_index(drop=True).astype({"pozycja": int}),
        k.sort_values("id_leada").reset_index(drop=True).astype({"pozycja": int}),
    )


def test_symulacja_wstecz_daje_ten_sam_ranking_co_zadanie(srodowisko):
    con = polacz(srodowisko["sciezka"])
    zadanie = con.execute("SELECT * FROM kolejka_ranking WHERE data_kolejki = ?", [DZIEN]).df()
    wstecz = kw.ranking_wstecz(con, date(2026, 5, 20), date(2026, 5, 20), "test")
    con.close()
    kolumny = ["id_leada", "miasto", "ranga", "otwarte_w_miescie", "id_doradcy", "pozycja", "p", "ev_pln"]

    def norm(df):  # brak doradcy: NaN z bazy, None z pandas
        df = df[kolumny].sort_values("id_leada").reset_index(drop=True)
        return df.assign(id_doradcy=df["id_doradcy"].astype(object).where(df["id_doradcy"].notna(), "")).astype(
            {"pozycja": "Int64", "id_doradcy": str}
        )

    pd.testing.assert_frame_equal(norm(zadanie), norm(wstecz), check_dtype=False)


def test_symulacja_wstecz_nie_nadpisuje_dni_z_zadania(srodowisko):
    w = kw.policz_wstecz(date(2026, 5, 19), date(2026, 5, 21), sciezka=srodowisko["sciezka"])
    assert w["pominiete_dni_zadania"] == [DZIEN] and w["dni"] == 2
    con = polacz(srodowisko["sciezka"])
    zrodla = dict(
        con.execute(
            "SELECT data_kolejki, any_value(zrodlo_kolejki) FROM kolejka_ranking "
            "WHERE data_kolejki BETWEEN DATE '2026-05-19' AND DATE '2026-05-21' GROUP BY 1"
        ).fetchall()
    )
    con.close()
    assert zrodla == {
        date(2026, 5, 19): "symulacja_wstecz",
        date(2026, 5, 20): "zadanie",
        date(2026, 5, 21): "symulacja_wstecz",
    }


# --- pominięcia: atrapa CRM -> POST /leads/skips -> kolejka_pominiecia -> dbt -----------------------------------------


def _klucz(srodowisko, doradca="D01", pozycja=1):
    stan = srodowisko["atrapa"].get("/stan").json()["pozycje"]
    return next(k for k, p in stan.items() if p["id_doradcy"] == doradca and p["pozycja"] == pozycja)


def test_pominiecie_z_crm_trafia_do_tabeli_i_powtorzenie_nic_nie_zmienia(srodowisko):
    atrapa, klucz = srodowisko["atrapa"], _klucz(srodowisko, "D01", 1)
    odp = atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": klucz, "powod": "brak_lokalu"})
    assert odp.status_code == 200 and odp.json()["wynik"] == "utworzono"
    odp2 = atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": klucz, "powod": "brak_lokalu"})
    assert odp2.json()["wynik"] == "powtorzenie"
    con = polacz(srodowisko["sciezka"])
    w = con.execute("SELECT * FROM kolejka_pominiecia WHERE id_leada = ?", [klucz.split(":")[0]]).df()
    con.close()
    assert len(w) == 1 and w["powod"].iat[0] == "brak_lokalu" and w["id_doradcy"].iat[0] == "D01"
    assert w["pozycja"].iat[0] == 1 and w["zgloszono"].iat[0] == w["zmieniono"].iat[0]
    assert klucz in atrapa.get("/pominiecia").json()


def test_zmiana_powodu_to_poprawka(srodowisko):
    atrapa, klucz = srodowisko["atrapa"], _klucz(srodowisko, "D02", 1)
    atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": klucz, "powod": "znam_klienta"})
    odp = atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": klucz, "powod": "duplikat"})
    assert odp.json()["wynik"] == "zmieniono"
    con = polacz(srodowisko["sciezka"])
    powod = con.execute("SELECT powod FROM kolejka_pominiecia WHERE id_leada = ?", [klucz.split(":")[0]]).fetchone()
    con.close()
    assert powod == ("duplikat",)


def test_bledne_pominiecia_sa_odrzucane_i_nie_zapisane(srodowisko):
    atrapa, api, klucz = srodowisko["atrapa"], srodowisko["api"], _klucz(srodowisko, "D03", 1)
    assert (
        atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": klucz, "powod": "nie_chce"}).status_code == 422
    )
    inne = atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": klucz, "powod": "inne"})
    assert inne.status_code == 422  # „inne” wymaga komentarza (walidacja w API Domilo)
    assert (
        atrapa.post("/kolejka/pominiecie", json={"klucz_idempotencji": "L0:2026-05-20", "powod": "inne"}).status_code
        == 404
    )
    # pozycja D03, ale zgłoszona jako D01: spoza kolejki doradcy
    id_leada = klucz.split(":")[0]
    zly_doradca = {"data_kolejki": DZIEN, "id_leada": id_leada, "id_doradcy": "D01", "powod": "duplikat",
                   "zgloszono": datetime.now(timezone.utc).isoformat()}  # fmt: skip
    assert api.post("/leads/skips", json=zly_doradca).status_code == 404
    bez_strefy = zly_doradca | {"id_doradcy": "D03", "zgloszono": "2026-05-20T10:00:00"}
    assert api.post("/leads/skips", json=bez_strefy).status_code == 422
    assert klucz not in atrapa.get("/pominiecia").json()
    con = polacz(srodowisko["sciezka"])
    n = con.execute("SELECT count(*) FROM kolejka_pominiecia WHERE id_leada = ?", [id_leada]).fetchone()[0]
    con.close()
    assert n == 0


def test_gdy_domilo_niedostepne_atrapa_zwraca_502_i_nie_zapamietuje(srodowisko, tmp_path):
    import httpx

    class Niedostepne:
        def post(self, *a, **k):
            raise httpx.ConnectError("brak połączenia")

    stan = tmp_path / "stan.json"
    shutil.copyfile(srodowisko["atrapa"].app.state.magazyn.sciezka, stan)
    atrapa = TestClient(_modul_atrapy().utworz_aplikacje(stan, api_domilo=Niedostepne()))
    odp = atrapa.post(
        "/kolejka/pominiecie", json={"klucz_idempotencji": _klucz(srodowisko, "D05", 1), "powod": "duplikat"}
    )
    assert odp.status_code == 502 and atrapa.get("/pominiecia").json() == {}


def test_strona_doradcy_w_atrapie_ma_pole_powodu_pominiecia(srodowisko):
    tekst = srodowisko["atrapa"].get("/doradca/D01").text
    assert "powód pominięcia" in tekst and all(f'value="{k}"' in tekst for k in POWODY_POMINIECIA)
    assert tekst.count("<button") == 40


def test_panel_widzi_pominiecia_bez_przebudowy_modeli_dbt(srodowisko):
    _klucz(srodowisko)  # pominięcia z poprzednich testów: D01 brak_lokalu, D02 duplikat
    d = srodowisko["api"].get("/team/dashboard").json()
    powody = {p["powod"]: p["pominiecia"] for p in d["pominiecia"]["powody"]}
    assert powody["brak_lokalu"] >= 1 and powody["duplikat"] >= 1
    assert {p["powod"] for p in d["pominiecia"]["ostatnie"]} >= {"brak_lokalu", "duplikat"}


# --- modele dbt i API na prawdziwej bazie -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def con():
    c = polacz()
    yield c
    c.close()


def test_kontakt_przed_0530_nalezy_do_kolejki_z_poprzedniego_dnia(con):
    df = con.execute("""SELECT timezone('Europe/Warsaw', pierwszy_kontakt) AS lokalny, data_kolejki_kontaktu
           FROM metryki.pierwszy_kontakt
           WHERE hour(timezone('Europe/Warsaw', pierwszy_kontakt)) = 5""").df()
    przed = df["lokalny"].dt.minute < 30
    assert przed.any() and (~przed).any()
    assert (df.loc[przed, "data_kolejki_kontaktu"] == (df.loc[przed, "lokalny"] - pd.Timedelta(days=1)).dt.date).all()
    assert (df.loc[~przed, "data_kolejki_kontaktu"] == df.loc[~przed, "lokalny"].dt.date).all()


def test_panel_kierownika_z_modeli_dbt(con):
    from api.main import app, baza

    def baza_prawdziwa():
        yield con

    app.dependency_overrides[baza] = baza_prawdziwa
    try:
        d = TestClient(app).get("/team/dashboard").json()
    finally:
        app.dependency_overrides.clear()
    kwartal = con.execute(
        "SELECT przychod_na_godzine_doradcy FROM metryki.przychod_na_godzine_doradcy "
        "WHERE okres = 'kwartal' AND poczatek_okresu = DATE '2026-04-01'"
    ).fetchone()[0]
    assert d["przychod"]["wartosc_wyjsciowa"]["przychod_na_godzine_doradcy"] == pytest.approx(kwartal)
    assert d["przychod"]["tygodnie"][0]["tydzien"] >= "2025-07-01"
    for okres in d["okresy"]["adopcja"]:
        if okres["adopcja"] is not None:
            assert 0 <= okres["adopcja"] <= 1 and okres["z_top"] <= okres["pierwsze_kontakty"]
    assert {p["powod"] for p in d["pominiecia"]["powody"]} == set(POWODY_POMINIECIA)
    assert kolejka_ranking.ZRODLA == ("zadanie", "symulacja_wstecz")
