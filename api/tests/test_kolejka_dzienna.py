"""Dzienna kolejka doradców (leasing_bc/kolejka_dzienna.py), webhook do CRM (adapters/crm_lejek.py), atrapa CRM
(dev/mock_lejek/app.py), funkcja Inngest kolejka-doradcow i GET /leads/next. Testy bez LLM (z_llm=False)."""

import importlib.util
import shutil
from datetime import date, datetime
from pathlib import Path

import httpx
import pandas as pd
import pytest
from api.adapters import kolejka_doradcow
from api.adapters.crm_lejek import KlientLejka, KonfliktIdempotencji, klucz_idempotencji
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polacz
from api.ai.lead_model.base import KOLUMNY_WEJSCIA
from api.contexts_boundaries.leasing_bc import kolejka_dzienna as kd
from fastapi.testclient import TestClient

DZIEN = "2026-11-16"


def _modul_atrapy():
    spec = importlib.util.spec_from_file_location("mock_lejek_app", KATALOG_REPO / "dev" / "mock_lejek" / "app.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def atrapa(tmp_path):
    return TestClient(_modul_atrapy().utworz_aplikacje(tmp_path / "stan.json"))


def _pozycja(id_leada="L1", dzien=DZIEN, **zmiany):
    return {"id_leada": id_leada, "data_kolejki": dzien, "id_doradcy": "D01", "pozycja": 1, "ev_pln": 100.0} | zmiany


# --- logika --------------------------------------------------------------------------------------------------------


def test_stan_danych_to_0530_dnia_kolejki_ale_nie_pozniej_niz_koniec_eksportu():
    assert kd.stan_danych_na(date(2026, 6, 15)).isoformat() == "2026-06-15T05:30:00+02:00"
    assert kd.stan_danych_na(date(2026, 1, 15)).isoformat() == "2026-01-15T05:30:00+01:00"
    assert kd.stan_danych_na(date(2026, 11, 16)) == kd.KONIEC_DANYCH


def test_przydzial_rozdaje_po_kolei_wedlug_ev_bez_powtorzen_i_z_limitem():
    ev = pd.DataFrame(
        {
            "id_leada": [f"W{i:02d}" for i in range(7)] + ["K1", "K2", "X1"],
            "miasto": ["Warszawa"] * 7 + ["Kraków", "Kraków", "Szczecin"],
            "ev": [70, 60, 50, 40, 30, 30, None, 5, 9, 99],
        }
    )
    doradcy = pd.DataFrame({"id_doradcy": ["D02", "D01", "D04"], "miasto": ["Warszawa", "Warszawa", "Kraków"]})
    k = kd.przydziel_kolejki(ev, doradcy, maks=2)
    assert list(k.itertuples(index=False, name=None)) == [
        ("D04", "Kraków", 1, "K2"),
        ("D04", "Kraków", 2, "K1"),
        ("D01", "Warszawa", 1, "W00"),
        ("D02", "Warszawa", 1, "W01"),
        ("D01", "Warszawa", 2, "W02"),
        ("D02", "Warszawa", 2, "W03"),
    ]
    assert k["id_leada"].is_unique  # klucz idempotencji (id_leada, data_kolejki)


def test_remis_ev_rozstrzyga_id_leada():
    ev = pd.DataFrame({"id_leada": ["L2", "L1"], "miasto": ["Łódź", "Łódź"], "ev": [10.0, 10.0]})
    k = kd.przydziel_kolejki(ev, pd.DataFrame({"id_doradcy": ["D11"], "miasto": ["Łódź"]}))
    assert list(k["id_leada"]) == ["L1", "L2"]


@pytest.fixture(scope="module")
def con():
    c = polacz()
    yield c
    c.close()


def test_otwarte_zapytania_na_koniec_eksportu(con):
    o = kd.otwarte_zapytania(con, kd.KONIEC_DANYCH)
    stan = pd.Timestamp(kd.KONIEC_DANYCH)
    assert len(o) == 2360 and o["id_leada"].is_unique
    assert set(o["status_crm"]) == {"otwarty", "w_toku"}
    assert (o["utworzono"] < stan).all() and (o["utworzono"] >= stan - pd.Timedelta(days=45)).all()
    assert set(KOLUMNY_WEJSCIA) <= set(o.columns)  # wejście kontraktu ai/lead_model/base.py


def test_otwarte_zapytania_w_przeszlosci_nie_widza_pozniejszych_zdarzen(con):
    stan = kd.stan_danych_na(date(2026, 6, 15))
    o = kd.otwarte_zapytania(con, stan)
    assert (o["utworzono"] < pd.Timestamp(stan)).all()
    # część z nich później podpisała umowę: wtedy jeszcze była otwarta
    cel = con.execute("SELECT id_leada, data_umowy FROM leady_cel WHERE data_umowy IS NOT NULL").df()
    pozniej = o.merge(cel, on="id_leada")
    assert len(pozniej) > 0 and (pozniej["data_umowy"] >= pd.Timestamp(stan)).all()


def test_aktywni_doradcy_bez_call_center_i_wedlug_dat_zatrudnienia(con):
    teraz = kd.aktywni_doradcy(con, date(2026, 11, 16))
    assert list(teraz["id_doradcy"]) == ["D07", "D04", "D09", "D06", "D01", "D02", "D03", "D08", "D05", "D10", "D11"]
    marzec_2024 = set(kd.aktywni_doradcy(con, date(2024, 3, 1))["id_doradcy"])
    assert "D12" in marzec_2024 and "D08" not in marzec_2024 and "CC" not in marzec_2024


# --- atrapa CRM i adapter ------------------------------------------------------------------------------------------


def test_webhook_powtorzenie_tego_samego_klucza_nie_zmienia_stanu(atrapa):
    klient = KlientLejka(url="http://testserver", http=atrapa)
    assert klient.wyslij_kolejke([_pozycja("L1"), _pozycja("L2", pozycja=2)]) == {"utworzono": 2, "powtorzenia": 0}
    stan = atrapa.get("/stan").json()
    assert klient.wyslij_kolejke([_pozycja("L1"), _pozycja("L2", pozycja=2)]) == {"utworzono": 0, "powtorzenia": 2}
    assert atrapa.get("/stan").json() == stan
    assert set(stan["pozycje"]) == {klucz_idempotencji("L1", DZIEN), klucz_idempotencji("L2", DZIEN)}


def test_webhook_ten_sam_klucz_z_inna_trescia_to_konflikt_i_nic_nie_zapisuje(atrapa):
    klient = KlientLejka(url="http://testserver", http=atrapa)
    klient.wyslij_kolejke([_pozycja("L1")])
    stan = atrapa.get("/stan").json()
    with pytest.raises(KonfliktIdempotencji):
        klient.wyslij_kolejke([_pozycja("L3"), _pozycja("L1", ev_pln=999.0)])
    assert atrapa.get("/stan").json() == stan  # L3 też nie wszedł: paczka jest odrzucana w całości


def test_ten_sam_lead_innego_dnia_to_nowy_klucz(atrapa):
    klient = KlientLejka(url="http://testserver", http=atrapa)
    klient.wyslij_kolejke([_pozycja("L1")])
    assert klient.wyslij_kolejke([_pozycja("L1", dzien="2026-11-17")])["utworzono"] == 1


def test_atrapa_odrzuca_klucz_niezgodny_z_id_leada_i_data(atrapa):
    odp = atrapa.post("/webhook/kolejka-doradcy", json={"pozycje": [_pozycja() | {"klucz_idempotencji": "zly"}]})
    assert odp.status_code == 422


# --- funkcja Inngest -----------------------------------------------------------------------------------------------


def test_funkcja_inngest_kolejki_ma_harmonogram_0530_w_czasie_warszawskim_i_zdarzenie_reczne():
    from api import inngest_app

    [fn] = [f for f in inngest_app.FUNKCJE if f.local_id == "kolejka-doradcow"]
    cfg = fn.get_config("http://app:8101/api/inngest").main
    wyzwalacze = [t.model_dump(exclude_none=True) for t in cfg.triggers]
    assert {"cron": "TZ=Europe/Warsaw 30 5 * * *"} in wyzwalacze
    assert {"event": "domilo/kolejka.doradcow"} in wyzwalacze
    assert inngest_app.data_kolejki_ze_zdarzenia({"data_kolejki": "2026-11-16"}) == "2026-11-16"
    assert inngest_app.data_kolejki_ze_zdarzenia({"cron": "TZ=Europe/Warsaw 30 5 * * *"}) is None


# --- cały przebieg na kopii bazy ------------------------------------------------------------------------------------


class InngestNaNiby:
    """Zapamiętuje wynik udanego kroku jak Inngest: ponowny przebieg wykonuje tylko kroki bez zapamiętanego wyniku."""

    def __init__(self):
        self.pamiec: dict[str, object] = {}
        self.wykonania: list[str] = []

    def krok(self, id_kroku, handler, *args):
        if id_kroku in self.pamiec:
            return self.pamiec[id_kroku]
        self.wykonania.append(id_kroku)
        wynik = handler(*args)
        self.pamiec[id_kroku] = wynik
        return wynik


def _wprost(id_kroku, handler, *args):
    return handler(*args)


@pytest.fixture(scope="module")
def baza_kopia(tmp_path_factory):
    sciezka = tmp_path_factory.mktemp("kolejka") / "baza.duckdb"
    shutil.copyfile(SCIEZKA_BAZY, sciezka)
    return sciezka


@pytest.fixture(scope="module")
def dwa_przebiegi(baza_kopia, tmp_path_factory):
    """Dwa pełne przebiegi dla tego samego dnia (różne id przebiegu) do tej samej atrapy CRM."""
    katalog = tmp_path_factory.mktemp("przebiegi")
    atrapa = TestClient(_modul_atrapy().utworz_aplikacje(katalog / "stan.json"))
    klient = KlientLejka(url="http://testserver", http=atrapa)
    wyniki, stany = [], []
    for n in (1, 2):
        wyniki.append(
            kd.wykonaj_kolejke_doradcow(
                _wprost,
                f"test-{n}",
                DZIEN,
                sciezka=baza_kopia,
                katalog_bazowy=katalog,
                klient_lejka=klient,
                z_llm=False,
            )
        )
        stany.append(atrapa.get("/stan").json())
    return wyniki, stany, atrapa


def test_dwa_przebiegi_tego_samego_dnia_daja_identyczny_stan_atrapy(dwa_przebiegi):
    wyniki, stany, atrapa = dwa_przebiegi
    assert stany[0]["liczba"] == 440
    assert stany[0] == stany[1]
    assert all(w == {"pozycje": 40, "utworzono": 40, "powtorzenia": 0} for w in wyniki[0]["webhook"].values())
    assert all(w == {"pozycje": 40, "utworzono": 0, "powtorzenia": 40} for w in wyniki[1]["webhook"].values())
    assert atrapa.get("/statystyki").json()["konflikty"] == 0


def test_kolejka_doradcy_ma_maks_40_pozycji_z_jego_miasta_wedlug_ev(dwa_przebiegi, baza_kopia):
    _, stany, _ = dwa_przebiegi
    pozycje = pd.DataFrame(stany[0]["pozycje"].values())
    con = polacz(baza_kopia)
    miasta = con.execute("SELECT id_doradcy, miasto FROM crm_doradcy").df().set_index("id_doradcy")["miasto"]
    leady = con.execute("SELECT id_leada, miasto FROM crm_leady").df().set_index("id_leada")["miasto"]
    losowe = set(
        con.execute("SELECT id_leada FROM kolejka_historia WHERE data_kolejki = ? AND losowa", [DZIEN]).df()["id_leada"]
    )
    con.close()
    assert (pozycje["id_doradcy"].map(miasta) == pozycje["miasto"]).all()
    assert (pozycje["id_leada"].map(leady) == pozycje["miasto"]).all()
    for _, g in pozycje.groupby("id_doradcy"):
        g = g.sort_values("pozycja")
        assert list(g["pozycja"]) == list(range(1, len(g) + 1)) and len(g) <= 40
        # 5% pozycji losowych (40 -> 2); pozostałe według EV malejąco
        assert g["id_leada"].isin(losowe).sum() == 2
        assert g.loc[~g["id_leada"].isin(losowe), "ev_pln"].is_monotonic_decreasing
    assert pozycje["uzasadnienie"].str.len().between(1, 140).all()


def test_get_leads_next_zwraca_te_sama_kolejke_co_webhook(dwa_przebiegi, baza_kopia):
    from api.main import app, baza

    _, stany, _ = dwa_przebiegi

    def baza_testowa():
        c = polacz(baza_kopia)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[baza] = baza_testowa
    try:
        klient = TestClient(app)
        odp = klient.get("/leads/next", params={"doradca": "D01", "data": DZIEN})
        najnowsza = klient.get("/leads/next", params={"doradca": "D01"})
        brak = klient.get("/leads/next", params={"doradca": "D99"})
        bez_parametru = klient.get("/leads/next")
        inny_dzien = klient.get("/leads/next", params={"doradca": "D01", "data": "2030-01-01"})
    finally:
        app.dependency_overrides.clear()
    assert odp.status_code == 200
    k = odp.json()
    assert (k["id_doradcy"], k["miasto"], k["data_kolejki"], k["wersja_modelu"]) == (
        "D01",
        "Warszawa",
        DZIEN,
        "v3_ev_kalibracja",
    )
    w_crm = sorted((p for p in stany[0]["pozycje"].values() if p["id_doradcy"] == "D01"), key=lambda p: p["pozycja"])
    pola = ("pozycja", "id_leada", "p", "ev_pln", "uzasadnienie", "status_crm")
    assert [{f: p[f] for f in pola} for p in k["pozycje"]] == [{f: p[f] for f in pola} for p in w_crm]
    assert datetime.fromisoformat(k["stan_danych_na"]) == kd.KONIEC_DANYCH
    assert (brak.status_code, bez_parametru.status_code, inny_dzien.status_code) == (404, 422, 404)
    # bez daty: najnowsza kolejka doradcy w bazie (nie wcześniejsza niż DZIEN)
    assert najnowsza.status_code == 200 and najnowsza.json()["data_kolejki"] >= DZIEN


def test_po_awarii_webhooka_ponawia_sie_tylko_krok_ktory_padl(baza_kopia, tmp_path):
    atrapa = TestClient(_modul_atrapy().utworz_aplikacje(tmp_path / "stan.json"))

    class ZawodnaSiec:
        """Pierwsze wysłanie kolejki D04 kończy się błędem sieci; potem działa."""

        def __init__(self):
            self.padlo = False

        def post(self, url, **kwargs):
            if not self.padlo and kwargs["json"]["pozycje"][0]["id_doradcy"] == "D04":
                self.padlo = True
                raise httpx.ConnectError("CRM niedostępny")
            return atrapa.post(url, **kwargs)

    klient = KlientLejka(url="http://testserver", http=ZawodnaSiec())
    inngest = InngestNaNiby()
    argumenty = dict(sciezka=baza_kopia, katalog_bazowy=tmp_path, klient_lejka=klient, z_llm=False)
    with pytest.raises(httpx.ConnectError):
        kd.wykonaj_kolejke_doradcow(inngest.krok, "awaria", DZIEN, **argumenty)
    pierwsze = list(inngest.wykonania)
    assert pierwsze[-1] == "webhook-crm-D04" and "webhook-crm-D05" not in pierwsze
    wynik = kd.wykonaj_kolejke_doradcow(inngest.krok, "awaria", DZIEN, **argumenty)
    ponowione = inngest.wykonania[len(pierwsze) :]
    pozniejsi = ("D05", "D06", "D07", "D08", "D09", "D10", "D11")
    assert ponowione == ["webhook-crm-D04"] + [f"webhook-crm-{d}" for d in pozniejsi]
    assert wynik["webhook"]["D04"] == {"pozycje": 40, "utworzono": 40, "powtorzenia": 0}
    assert atrapa.get("/stan").json()["liczba"] == 440


def test_zapis_kolejki_zastepuje_caly_dzien(baza_kopia, dwa_przebiegi):
    con = polacz(baza_kopia)
    n = con.execute(f"SELECT count(*) FROM {kolejka_doradcow.TABELA} WHERE data_kolejki = ?", [DZIEN]).fetchone()[0]
    przebiegi = con.execute(
        f"SELECT DISTINCT id_przebiegu FROM {kolejka_doradcow.TABELA} WHERE data_kolejki = ?", [DZIEN]
    ).fetchall()
    con.close()
    assert n == 440 and len(przebiegi) == 1  # ostatni przebieg dnia zastąpił poprzedni
    assert Path(baza_kopia).exists()
