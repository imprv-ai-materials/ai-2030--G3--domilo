from datetime import date

import numpy as np
import pandas as pd
import pytest
from api.adapters.duckdb_baza import KATALOG_REPO
from api.ai.churn_model.versions.v3_uplift_tlearner.model import ModelUpliftT
from api.contexts_boundaries.retention_bc.oferta_najmu import (
    AKCJE,
    PROG_NIE_BUDZIC,
    SCIEZKA_MODELU_UPLIFT,
    data_decyzji,
    miesci_sie_w_budzecie,
    opis_cechy,
    trzy_cechy,
    uzasadnienie,
    zalecana_akcja,
)
from api.contexts_boundaries.retention_bc.polityka_rabatow import KATALOG_WYNIKOW
from tests.test_churn_uplift import _dane

# --- wkłady cech w uplift (model v3) ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def model_syntetyczny():
    df, w, y = _dane(6000, 0)
    return ModelUpliftT().fit(df, w, y)


def test_wklady_sumuja_sie_do_upliftu(model_syntetyczny):
    test, _, _ = _dane(300, 1)
    wklady = model_syntetyczny.wklady_upliftu(test)
    uplift = model_syntetyczny.predict(test)
    assert np.allclose(wklady.drop(columns="wklad_staly").sum(axis=1) + wklady["wklad_staly"], uplift, atol=1e-9)


def test_wklady_wskazuja_ceche_z_efektem(model_syntetyczny):
    test, _, _ = _dane(1000, 2)
    wklady = model_syntetyczny.wklady_upliftu(test).drop(columns="wklad_staly")
    assert wklady.abs().mean().idxmax() == "czynsz_m2"


def test_zakres_cech_z_treningu_i_poza_zakresem(model_syntetyczny):
    test, _, _ = _dane(3, 3)
    test.loc[0, "staz_dni"] = model_syntetyczny.zakres_cech_["staz_dni"]["min"] - 1
    test.loc[1, "czynsz_m2"] = np.nan  # w syntetycznym treningu brak braków
    poza = model_syntetyczny.poza_zakresem(test)
    assert poza[0] == ["staz_dni"]
    assert poza[1] == ["czynsz_m2"]
    assert poza[2] == []


def test_poza_zakresem_daje_bez_rabatu_z_wyjasnieniem():
    from api.contexts_boundaries.retention_bc.oferta_najmu import decyzja

    wklady = pd.Series({"a": 0.30, "b": 0.05, "c": 0.02})
    wartosci = pd.Series({"a": 1.0, "b": 2.0, "c": 3.0})
    d = decyzja(0.35, 400.0, 0.7, wklady, wartosci, ["a"], None, date(2026, 12, 1), date(2026, 9, 30))
    assert d["akcja"] == "bez rabatu"
    assert "2026-12-01" in d["uzasadnienie"] and "a = 1,0" in d["uzasadnienie"]
    assert d["uzasadnienie"].count(".") == 1
    w_zakresie = decyzja(0.35, 400.0, 0.7, wklady, wartosci, [], None, date(2026, 8, 1), date(2026, 9, 30))
    assert w_zakresie["akcja"] == "rabat"


# --- decyzja ---------------------------------------------------------------------------------------------------


def test_data_decyzji_to_migawka_albo_dzien_oceny():
    dzien = date(2026, 9, 30)
    assert data_decyzji(date(2026, 11, 10), dzien) == date(2026, 9, 11)  # migawka już minęła
    assert data_decyzji(date(2027, 3, 31), dzien) == dzien  # migawka w przyszłości: stan na dziś


def test_zalecana_akcja():
    assert zalecana_akcja(uplift=0.30, ev=500.0, w_budzecie=True) == "rabat"
    assert zalecana_akcja(uplift=0.30, ev=500.0, w_budzecie=None) == "rabat"  # budżet nieustalony: bez limitu
    assert zalecana_akcja(uplift=0.30, ev=500.0, w_budzecie=False) == "bez rabatu"
    assert zalecana_akcja(uplift=0.05, ev=-900.0, w_budzecie=True) == "bez rabatu"
    assert zalecana_akcja(uplift=PROG_NIE_BUDZIC, ev=-2000.0, w_budzecie=True) == "nie budzić"
    assert zalecana_akcja(uplift=PROG_NIE_BUDZIC + 1e-6, ev=-2000.0, w_budzecie=True) == "bez rabatu"
    assert set(AKCJE) == {"rabat", "bez rabatu", "nie budzić"}


def test_budzet_kolejnosc_wedlug_ev():
    # EV > 0: B (900), A (500), C (100); koszt rabatu 400 każdy; budżet 800 mieści B i A
    ev = pd.Series({"A": 500.0, "B": 900.0, "C": 100.0, "D": -50.0})
    koszt = pd.Series({"A": 400.0, "B": 400.0, "C": 400.0, "D": 400.0})
    assert miesci_sie_w_budzecie(ev, koszt, "A", 800.0)
    assert miesci_sie_w_budzecie(ev, koszt, "B", 800.0)
    assert not miesci_sie_w_budzecie(ev, koszt, "C", 800.0)
    assert not miesci_sie_w_budzecie(ev, koszt, "D", 800.0)  # EV <= 0 nigdy nie bierze budżetu
    assert miesci_sie_w_budzecie(ev, koszt, "C", None) is None  # budżet nieustalony


def test_prog_nie_budzic_z_danych():
    sciezka = KATALOG_WYNIKOW / "ev_najemcow.parquet"
    if not sciezka.exists():
        pytest.skip("brak wyników polityka_rabatow (python -m api.contexts_boundaries.retention_bc.polityka_rabatow)")
    uplift = pd.read_parquet(sciezka)["uplift"]
    assert PROG_NIE_BUDZIC == pytest.approx(uplift.quantile(0.20), abs=5e-5)


# --- uzasadnienie ----------------------------------------------------------------------------------------------


def test_opis_cechy_z_wartoscia_i_brakiem():
    assert opis_cechy("portal_logowania_3m", 14.0) == "14 logowań do portalu w 3 miesiące"
    assert opis_cechy("b2b", 1.0) == "klient firmowy (B2B)"
    assert opis_cechy("czynsz_do_podobnych", 1.083) == "czynsz o 8% wyższy niż w podobnych lokalach"
    assert opis_cechy("indeksacja_ostatnia_pct", np.nan) == "pierwsza umowa, bez wcześniejszej podwyżki"
    assert opis_cechy("zgl_365d", 0.0) == "brak zgłoszeń w portalu w ciągu roku"
    assert opis_cechy("zgl_365d", 3.0) == "3 zgłoszenia w portalu w ciągu roku"
    assert opis_cechy("plat_max_opoznienie_90d", 0.0) == "płatności bez opóźnień w 90 dniach"
    assert opis_cechy("nieznana_cecha", 2.5) == "nieznana_cecha = 2,5"


def test_trzy_cechy_zgodne_z_kierunkiem_akcji():
    wklady = pd.Series({"a": 0.05, "b": -0.08, "c": 0.02, "d": 0.01, "e": -0.01})
    wartosci = pd.Series({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 5.0})
    assert [c["cecha"] for c in trzy_cechy(wklady, wartosci, "rabat")] == ["a", "c", "d"]
    assert [c["cecha"] for c in trzy_cechy(wklady, wartosci, "nie budzić")] == ["b", "e", "a"]
    assert [c["cecha"] for c in trzy_cechy(wklady, wartosci, "bez rabatu")] == ["b", "a", "c"]


def test_uzasadnienie_to_jedno_zdanie_z_trzema_cechami():
    cechy = [
        {"cecha": "a", "opis": "opis a", "wklad_pp": 3.0},
        {"cecha": "b", "opis": "opis b", "wklad_pp": 2.0},
        {"cecha": "c", "opis": "opis c", "wklad_pp": 1.0},
    ]
    for akcja in AKCJE:
        zdanie = uzasadnienie(akcja, uplift=0.12, ev=-300.0, p_oferta=0.6, cechy=cechy, w_budzecie=True)
        assert zdanie.count(".") == 1 and zdanie.endswith(".")
        assert all(f"opis {x}" in zdanie for x in "abc")


# --- integracja z bazą -----------------------------------------------------------------------------------------

JEST_BAZA = (KATALOG_REPO / "domilo.duckdb").exists() and SCIEZKA_MODELU_UPLIFT.exists()


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb albo modelu v3_uplift_tlearner")
def test_risk_zwraca_oferte():
    from api.adapters.duckdb_baza import polacz
    from api.main import app
    from fastapi.testclient import TestClient

    con = polacz()
    (id_najmu,) = con.execute("""
        SELECT id_najmu FROM pms_najmy WHERE linia = 'B2C' AND data_wyprowadzenia IS NULL
            AND data_wprowadzenia < DATE '2026-01-01' ORDER BY id_najmu LIMIT 1
        """).fetchone()
    con.close()
    with TestClient(app) as klient:
        odp = klient.get(f"/risk/{id_najmu}")
        assert odp.status_code == 200
        o = odp.json()["oferta"]
        assert o["zalecana_akcja"] in AKCJE
        assert len(o["najwazniejsze_cechy"]) == 3
        assert o["ev_pln"] == pytest.approx(
            o["uplift"] * o["zalozenia"]["R"] - o["zalozenia"]["D"] * o["p_przedluzy_z_oferta"] - o["zalozenia"]["k"]
        )
        assert o["uzasadnienie"].endswith(".")
