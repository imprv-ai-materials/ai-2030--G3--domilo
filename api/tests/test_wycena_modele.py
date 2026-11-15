import math

import duckdb
import numpy as np
import pandas as pd
import pytest
from api.ai.features.wycena.zbior import wczytaj_transakcje
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.metryki import metryki
from api.ai.valuation_model.versions.v0_mediana_dzielnicy.model import ModelMedianaDzielnicy
from api.ai.valuation_model.versions.v1_liniowa.model import (
    RESZTA_MIASTA,
    ModelLiniowy,
    przedzial_roku_budowy,
)


def _lokale(wiersze):
    return pd.DataFrame(wiersze, columns=list(KOLUMNY_CECH))


# --- metryki ---------------------------------------------------------------------------------------------------


def test_metryki_licza_mae_rmse_mape_i_mdape_w_pln_i_procentach():
    y = np.array([100.0, 200.0, 400.0])
    p = np.array([110.0, 180.0, 400.0])  # błędy: +10, -20, 0; błędy względne: 10%, 10%, 0%
    m = metryki(y, p)
    assert m["mae"] == pytest.approx(10.0)
    assert m["rmse"] == pytest.approx(math.sqrt((100 + 400 + 0) / 3))
    assert m["mape"] == pytest.approx(100 * (0.1 + 0.1 + 0) / 3)
    assert m["mdape"] == pytest.approx(10.0)
    assert m["n"] == 3


# --- kontrakt --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("klasa", [ModelMedianaDzielnicy, ModelLiniowy])
def test_kazda_wersja_spelnia_kontrakt_a_przedzial_nie_jest_jeszcze_gotowy(klasa):
    model = klasa()
    assert isinstance(model, ModelWyceny)
    assert model.wersja
    X = _lokale([("A", "a1", 50.0, 2, 1, 2000)] * 40)
    model.fit(X, pd.Series([500_000.0] * 40))
    with pytest.raises(NotImplementedError):
        model.predict_interval(X)


def test_brak_wymaganej_kolumny_to_czytelny_blad():
    X = _lokale([("A", "a1", 50.0, 2, 1, 2000)]).drop(columns=["metraz"])
    with pytest.raises(ValueError, match="metraz"):
        ModelMedianaDzielnicy().fit(X, pd.Series([1.0]))


# --- v0: mediana ceny m² dzielnicy × metraż ---------------------------------------------------------------------


def test_baseline_mnozy_mediane_ceny_m2_dzielnicy_z_treningu_przez_metraz():
    X = _lokale(
        [
            ("A", "a1", 10.0, 1, 0, 2000),  # 10 000 zł/m²
            ("A", "a1", 20.0, 1, 0, 2000),  # 12 000 zł/m²
            ("A", "a1", 10.0, 1, 0, 2000),  # 14 000 zł/m²  -> mediana a1 = 12 000
            ("A", "a2", 10.0, 1, 0, 2000),  # 20 000 zł/m²  -> mediana a2 = 20 000; miasto A = 13 000
        ]
    )
    y = pd.Series([100_000.0, 240_000.0, 140_000.0, 200_000.0])
    model = ModelMedianaDzielnicy().fit(X, y)
    nowe = _lokale([("A", "a1", 50.0, 3, 2, 1990), ("A", "nowa", 50.0, 3, 2, 1990)])
    assert model.predict(nowe) == pytest.approx([600_000.0, 650_000.0])
    wyj = model.explain(nowe)
    assert list(wyj["zrodlo_mediany"]) == ["dzielnica", "miasto"]
    assert list(wyj["mediana_ceny_m2"]) == pytest.approx([12_000.0, 13_000.0])


def test_baseline_rozroznia_dzielnice_o_tej_samej_nazwie_w_roznych_miastach():
    X = _lokale([("A", "Śródmieście", 10.0, 1, 0, 2000), ("B", "Śródmieście", 10.0, 1, 0, 2000)])
    model = ModelMedianaDzielnicy().fit(X, pd.Series([100_000.0, 50_000.0]))
    assert model.predict(X) == pytest.approx([100_000.0, 50_000.0])


# --- v1: regresja liniowa na ln(ceny) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rok, przedzial",
    [(1880, "do 1944"), (1944, "do 1944"), (1945, "1945–1969"), (1970, "1970–1989"), (1990, "1990–2009"),
     (2010, "2010–2019"), (2019, "2010–2019"), (2020, "od 2020"), (2026, "od 2020")],
)  # fmt: skip
def test_przedzialy_roku_budowy(rok, przedzial):
    assert przedzial_roku_budowy(pd.Series([rok])).iloc[0] == przedzial


def _syntetyczne(n_duza=200, n_mala=10, seed=0):
    """ln(cena) = 9 + ln(metraz) + 0.2·[dzielnica a1] + 0.05·pietro — dokładnie liniowe w cechach."""
    rng = np.random.default_rng(seed)
    dzielnice = ["a1"] * n_duza + ["a2"] * n_duza + ["a3"] * n_mala
    n = len(dzielnice)
    X = _lokale(
        {
            "miasto": ["A"] * n,
            "dzielnica": dzielnice,
            "metraz": rng.uniform(25, 90, n).round(1),
            "pokoje": rng.integers(1, 5, n),
            "pietro": rng.integers(0, 10, n),
            "rok_budowy": rng.integers(1950, 2025, n),
        }
    )
    ln_cena = 9 + np.log(X["metraz"]) + 0.2 * (X["dzielnica"] == "a1") + 0.05 * X["pietro"]
    return X, pd.Series(np.exp(ln_cena))


def test_liniowa_laczy_dzielnice_z_mniej_niz_30_transakcjami_w_reszte_miasta():
    X, y = _syntetyczne(n_mala=29)
    model = ModelLiniowy().fit(X, y)
    assert model.dzielnice_polaczone_ == {("A", "a3"): 29}
    wyj = model.explain(X)
    assert set(wyj.loc[X["dzielnica"] == "a3", "dzielnica_w_modelu"]) == {f"A | {RESZTA_MIASTA}"}
    assert set(wyj.loc[X["dzielnica"] == "a1", "dzielnica_w_modelu"]) == {"A | a1"}


def test_liniowa_dzielnica_z_30_transakcjami_zostaje_osobna():
    X, y = _syntetyczne(n_mala=30)
    assert ModelLiniowy().fit(X, y).dzielnice_polaczone_ == {}


def test_liniowa_odtwarza_cene_gdy_ln_ceny_jest_liniowy_a_explain_sumuje_sie_do_ln_wyceny():
    X, y = _syntetyczne()
    model = ModelLiniowy(metraz_log=True).fit(X, y)
    pred = model.predict(X)
    assert np.max(np.abs(pred / y - 1)) < 1e-6
    wyj = model.explain(X)
    skladowe = [k for k in wyj.columns if k.startswith("wklad_")]
    assert np.allclose(wyj[skladowe].sum(axis=1), np.log(pred))


def test_liniowa_nieznana_dzielnica_dostaje_reszte_miasta():
    X, y = _syntetyczne()
    model = ModelLiniowy().fit(X, y)
    nowy = _lokale([("A", "nieznana", 50.0, 2, 1, 2000)])
    assert model.explain(nowy)["dzielnica_w_modelu"].iloc[0] == f"A | {RESZTA_MIASTA}"
    assert model.predict(nowy)[0] > 0


def test_liniowa_nieznana_dzielnica_w_miescie_bez_reszty_dostaje_srednia_wazona_dzielnic():
    X, y = _syntetyczne(n_duza=200, n_mala=100)  # a1, a2: 200, a3: 100 -> żadnej „reszty miasta”
    model = ModelLiniowy().fit(X, y)
    w = model.wspolczynniki_
    oczekiwany = (200 * w["dzielnica=A | a1"] + 200 * w["dzielnica=A | a2"] + 100 * w["dzielnica=A | a3"]) / 500
    wyj = model.explain(_lokale([("A", "nieznana", 50.0, 2, 1, 2000)]))
    assert wyj["dzielnica_w_modelu"].iloc[0] == "A | średnia miasta"
    assert wyj["wklad_dzielnica"].iloc[0] == pytest.approx(oczekiwany)


def test_liniowa_nieznane_miasto_to_blad():
    X, y = _syntetyczne()
    with pytest.raises(ValueError, match="Miasto nieznane"):
        ModelLiniowy().fit(X, y).predict(_lokale([("B", "b1", 50.0, 2, 1, 2000)]))


def test_model_po_zapisie_i_wczytaniu_daje_te_same_wyceny(tmp_path):
    X, y = _syntetyczne()
    model = ModelLiniowy().fit(X, y)
    model.zapisz(tmp_path / "model.joblib")
    assert np.allclose(ModelWyceny.wczytaj(tmp_path / "model.joblib").predict(X), model.predict(X))


# --- zbiór: transakcje RCN z podziałem -------------------------------------------------------------------------


def test_wczytaj_transakcje_daje_cechy_target_i_zbior_tylko_dla_transakcji_z_podzialu():
    con = duckdb.connect()
    con.execute("""CREATE TABLE rcn_transakcje AS SELECT * FROM (VALUES
           ('T1', TIMESTAMP '2024-01-10', TIMESTAMP '2024-04-01', 'A', 'a1', 40.0, 2, 1, 1990, 'wtorny', 400000, 10000),
           ('T2', TIMESTAMP '2026-06-30', TIMESTAMP '2026-10-02', 'A', 'a1', 40.0, 2, 1, 1990, 'wtorny', 400000, 10000))
           t(id_transakcji, data_aktu, data_publikacji_rejestru, miasto, dzielnica, metraz, pokoje, pietro,
             rok_budowy, rynek, cena_pln, cena_m2)""")
    df = wczytaj_transakcje(con)
    assert list(df["id_transakcji"]) == ["T1"]
    assert list(df["zbior"]) == ["trening"]
    assert set(KOLUMNY_CECH) <= set(df.columns)
    assert {"cena_pln", "cena_m2", "rynek", "data_aktu"} <= set(df.columns)


# --- v1: efekty w procentach ceny ------------------------------------------------------------------------------


def test_efekty_procentowe_dzielnic_sa_wzgledem_sredniej_wazonej_miasta_a_ciagle_na_jednostke():
    X, y = _syntetyczne(n_duza=200, n_mala=10)  # a1: +0,2 ln vs a2; a3 (10) -> reszta miasta (poziom jak a2)
    model = ModelLiniowy().fit(X, y)
    ef = model.efekty_procentowe().set_index("cecha")
    srednia = (200 * 0.2 + 200 * 0 + 10 * 0) / 410
    assert ef.loc["dzielnica: A | a1", "b"] == pytest.approx(0.2 - srednia, abs=1e-6)
    assert ef.loc["dzielnica: A | a1", "efekt_proc"] == pytest.approx(100 * (math.exp(0.2 - srednia) - 1), abs=1e-4)
    assert ef.loc["dzielnica: A | a1", "transakcje_trening"] == 200
    assert ef.loc["piętro (+1)", "efekt_proc"] == pytest.approx(100 * (math.exp(0.05) - 1), abs=1e-4)
    assert ef.loc["rok budowy: od 2020", "odniesienie"] == "1970–1989"
    # ln(metraż): efekt dla +10% metrażu, nie e^b − 1
    assert ef.loc["metraż (+10%)", "efekt_proc"] == pytest.approx(100 * (1.1**1.0 - 1), abs=1e-4)
    assert {"typ", "odniesienie", "efekt_proc", "b"} <= set(ef.columns)
