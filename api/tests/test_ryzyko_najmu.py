from datetime import date

import numpy as np
import pytest
from api.adapters.duckdb_baza import KATALOG_REPO, polacz
from api.ai.churn_model.versions.v2_przezycie_cox.model import ModelCox
from api.contexts_boundaries.retention_bc.ryzyko_najmu import (
    SCIEZKA_MODELU,
    KrzywaNajmu,
    krzywa_pozostala,
    miesiace_kalendarzowe,
)
from tests.test_churn_cox import _okresy

JEST_BAZA = (KATALOG_REPO / "domilo.duckdb").exists() and SCIEZKA_MODELU.exists()


def test_miesiace_kalendarzowe_jak_w_czas_najmu():
    assert miesiace_kalendarzowe(date(2019, 9, 8), date(2020, 9, 8)) == pytest.approx(12.0)
    assert miesiace_kalendarzowe(date(2023, 1, 31), date(2024, 1, 31)) == pytest.approx(12.0)
    assert miesiace_kalendarzowe(date(2024, 3, 1), date(2024, 8, 16)) == pytest.approx(5 + 15 / 31)
    assert miesiace_kalendarzowe(date(2026, 9, 15), date(2026, 10, 1)) == pytest.approx(16 / 30)


def test_mediana_i_rmst_krzywej_schodkowej():
    u = np.arange(0, 60 + 1e-9, 0.5)
    S = np.where(u < 12, 1.0, np.where(u < 24, 0.6, 0.3))
    k = KrzywaNajmu(czasy=u, przezycie=S, p_konca_biezacego_okresu=0.4)
    assert k.mediana() == pytest.approx(24.0)
    assert k.rmst(60) == pytest.approx(12 * 1.0 + 12 * 0.6 + 36 * 0.3)
    assert k.przezycie_po(12) == pytest.approx(0.6)


@pytest.fixture(scope="module")
def model():
    return ModelCox().fit(_okresy(n=3000, ziarno=7))


def test_krzywa_od_dnia_oceny_maleje_i_zaczyna_od_jedynki(model):
    okresy = _okresy(n=5, ziarno=8)
    X0 = model.macierz(okresy).iloc[[0]]
    k = krzywa_pozostala(model, X0, miesiecy_umowy=12, minelo=4.0)
    assert k.przezycie[0] == pytest.approx(1.0)
    assert np.all(np.diff(k.przezycie) <= 1e-12)
    assert 0 < k.rmst() <= 60
    # koniec bieżącego okresu po 8 mies. od dnia oceny: S tuż po nim = 1 - p_konca
    assert k.przezycie_po(8.0) == pytest.approx(1 - k.p_konca_biezacego_okresu, abs=1e-9)


def test_okres_po_dniu_oceny_to_pewne_przezycie_do_jego_poczatku(model):
    X0 = model.macierz(_okresy(n=5, ziarno=9)).iloc[[0]]
    k = krzywa_pozostala(model, X0, miesiecy_umowy=12, minelo=0.0, opoznienie=1.0)
    assert np.all(k.przezycie[k.czasy < 1.0] == 1.0)


@pytest.fixture(scope="module")
def klient():
    from api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb (pypyr baza) albo model.joblib v2")
def test_endpoint_ryzyka(klient):
    con = polacz()
    aktywny, zakonczony, mid = con.execute("""
        SELECT
            (SELECT id_najmu FROM pms_najmy WHERE linia = 'B2C' AND data_wyprowadzenia IS NULL
                AND data_wprowadzenia < DATE '2026-01-01' ORDER BY id_najmu LIMIT 1),
            (SELECT id_najmu FROM pms_najmy WHERE linia = 'B2B' AND data_wyprowadzenia IS NOT NULL ORDER BY id_najmu LIMIT 1),
            (SELECT id_najmu FROM pms_najmy WHERE linia = 'MID' ORDER BY id_najmu LIMIT 1)
        """).fetchone()
    con.close()
    r = klient.get(f"/risk/{aktywny}")
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["wersja_modelu"] == "v2_przezycie_cox" and w["linia"] == "B2C"
    assert 0 < w["rmst60_mies"] <= 60
    assert w["mediana_powyzej_horyzontu"] == (w["mediana_do_odejscia_mies"] is None)
    assert 0 <= w["przezycie_24_mies"] <= w["przezycie_12_mies"] <= 1
    assert klient.get(f"/risk/{zakonczony}").status_code == 409
    assert klient.get(f"/risk/{mid}").status_code == 422
    assert klient.get("/risk/N_NIE_MA").status_code == 404
