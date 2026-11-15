"""Usługa wyceny (valuation_bc/wycena.py) i obecny model z current.yaml (valuation_model/obecny.py)."""

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest
import yaml
from api.adapters.duckdb_baza import polacz
from api.ai.valuation_model.obecny import KATALOG_MODELU, wczytaj_obecny
from api.contexts_boundaries.valuation_bc.wycena import (
    OPISY_CECH,
    cechy_punktow,
    czynniki_pln,
    najwazniejsze,
    wycen,
)

# --- obecny model ---------------------------------------------------------------------------------------------------


def test_obecny_model_to_wersja_wskazana_w_current_yaml():
    current = yaml.safe_load((KATALOG_MODELU / "current.yaml").read_text(encoding="utf-8"))
    obecny = wczytaj_obecny()
    assert obecny.wersja == current["wersja"]
    assert type(obecny.model).__name__ == current["klasa"].rsplit(".", 1)[1]


def test_klasa_niezgodna_z_current_yaml_to_blad(tmp_path):
    current = yaml.safe_load((KATALOG_MODELU / "current.yaml").read_text(encoding="utf-8"))
    current["model"] = str(KATALOG_MODELU / current["model"])
    current["klasa"] = "api.ai.valuation_model.versions.v1_liniowa.model.ModelLiniowy"
    plik = tmp_path / "current.yaml"
    plik.write_text(yaml.safe_dump(current), encoding="utf-8")
    with pytest.raises(ValueError, match="klasa"):
        wczytaj_obecny(plik)


# --- czynniki SHAP w PLN --------------------------------------------------------------------------------------------


def test_czynniki_w_pln_sumuja_sie_do_roznicy_wyceny_i_wartosci_bazowej():
    # B = 100 zł, P50 = 100·e ≈ 271,83 zł; L = (P50 − B) / (ln P50 − ln B) = 171,83
    c = czynniki_pln({"metraz": 0.7, "dzielnica": 0.3}, ln_bazowa=math.log(100), p50=100 * math.e)
    assert c["metraz"] == pytest.approx(0.7 * 171.828, abs=0.01)
    assert c["dzielnica"] == pytest.approx(0.3 * 171.828, abs=0.01)
    assert sum(c.values()) == pytest.approx(100 * math.e - 100, abs=1e-6)


def test_czynniki_o_przeciwnych_znakach_zachowuja_znak_i_skale():
    # Σ wkładów = 0,01, a mimo to wkłady w PLN nie rosną do absurdu (każdy × ta sama L ≈ wycena).
    p50 = 500_000 * math.exp(0.01)
    c = czynniki_pln({"metraz": 0.5, "pietro": -0.49}, ln_bazowa=math.log(500_000), p50=p50)
    assert c["metraz"] > 0 > c["pietro"]
    assert c["metraz"] == pytest.approx(0.5 * 502_496, rel=1e-3)


def test_gdy_wycena_rowna_bazowej_wspolczynnik_to_wycena():
    c = czynniki_pln({"metraz": 0.2, "pietro": -0.2}, ln_bazowa=math.log(400_000), p50=400_000)
    assert c == pytest.approx({"metraz": 80_000, "pietro": -80_000})


def test_najwazniejsze_to_trzy_najwieksze_co_do_wartosci_bezwzglednej():
    c = {"a": 10.0, "b": -50.0, "c": 30.0, "d": -5.0, "e": 40.0}
    assert najwazniejsze(c) == [("b", -50.0), ("e", 40.0), ("c", 30.0)]


def test_kazda_cecha_modelu_ma_opis_po_polsku():
    obecny = wczytaj_obecny()
    cechy = obecny.model.przedzial.punktowy.reg_.booster_.feature_name()
    assert set(cechy) <= set(OPISY_CECH)


# --- wycena punktów (prawdziwy model i domilo.duckdb) ---------------------------------------------------------------


def _punkt(**zmiany) -> pd.DataFrame:
    p = {
        "id": "P1",
        "miasto": "Warszawa",
        "dzielnica": "Wola",
        "lat": 52.2341,
        "lon": 20.9664,
        "metraz": 48.0,
        "pokoje": 2,
        "pietro": 3,
        "rok_budowy": 2018,
        "dzien_wyceny": date(2026, 11, 15),
        "llm_standard": np.nan,
        "llm_ekspozycja": np.nan,
        "llm_widok": np.nan,
        "llm_balkon": np.nan,
        "llm_stan_budynku": np.nan,
    }
    p.update(zmiany)
    return pd.DataFrame([p])


@pytest.fixture(scope="module")
def con():
    c = polacz()
    yield c
    c.close()


def test_cechy_punktow_dokladaja_otoczenie_i_sasiedztwo_bez_zmiany_liczby_wierszy(con):
    X = cechy_punktow(con, pd.concat([_punkt(), _punkt(id="P2", lat=52.19, lon=21.02)], ignore_index=True))
    assert len(X) == 2
    assert X["sasiedzi_liczba"].tolist() == [20, 20]
    assert X["odl_centrum_m"].notna().all()


def test_wycena_lokalu_z_warszawy_daje_przedzial_wokol_wartosci_i_czynniki_w_pln(con):
    obecny = wczytaj_obecny()
    w = wycen(obecny.model, cechy_punktow(con, _punkt())).iloc[0]
    assert not w["odmowa"]
    assert w["p10"] < w["p50"] < w["p90"]
    assert sum(w["czynniki"].values()) == pytest.approx(w["p50"] - w["wartosc_bazowa"], rel=1e-6)


def test_lokal_w_miescie_spoza_treningu_jest_poza_zakresem_z_powodem_i_bez_liczb(con):
    obecny = wczytaj_obecny()
    w = wycen(
        obecny.model, cechy_punktow(con, _punkt(miasto="Katowice", dzielnica="Śródmieście", lat=50.26, lon=19.02))
    )
    w = w.iloc[0]
    assert w["odmowa"]
    assert "Katowice" in w["powod"]
    assert math.isnan(w["p50"]) and w["czynniki"] == {}
