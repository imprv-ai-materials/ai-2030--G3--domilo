import numpy as np
import pandas as pd
import pytest
from api.ai.churn_model.evals.eksperyment_rabatu_2025 import (
    balans_cechy,
    cechy_balansu,
    efekt,
    efekt_stratyfikowany,
    gorne_35,
    roznica_efektow,
    laczny_test_balansu,
)


def test_efekt_roznica_odsetkow_z_przedzialem_walda():
    # oferta: 60/100 przedłużeń, kontrola: 50/100
    y = np.r_[np.ones(60), np.zeros(40), np.ones(50), np.zeros(50)]
    oferta = np.r_[np.ones(100, dtype=bool), np.zeros(100, dtype=bool)]
    e = efekt(y, oferta)
    assert e["n_oferta"] == 100 and e["n_kontrola"] == 100
    assert e["odsetek_oferta"] == pytest.approx(0.6)
    assert e["odsetek_kontrola"] == pytest.approx(0.5)
    assert e["ate"] == pytest.approx(0.1)
    se = np.sqrt(0.6 * 0.4 / 100 + 0.5 * 0.5 / 100)
    assert e["se"] == pytest.approx(se)
    assert e["ci95"] == pytest.approx([0.1 - 1.959964 * se, 0.1 + 1.959964 * se], abs=1e-6)


def test_efekt_stratyfikowany_wazy_warstwy_udzialem():
    # warstwa A (połowa umów): 0,8 vs 0,6; warstwa B: 0,3 vs 0,3 -> ATE = 0,5 * 0,2 + 0,5 * 0 = 0,1
    y = np.r_[np.ones(8), np.zeros(2), np.ones(6), np.zeros(4), np.ones(3), np.zeros(7), np.ones(3), np.zeros(7)]
    oferta = np.r_[np.ones(10), np.zeros(10), np.ones(10), np.zeros(10)].astype(bool)
    warstwa = np.r_[np.repeat("A", 20), np.repeat("B", 20)]
    e = efekt_stratyfikowany(y, oferta, warstwa)
    assert e["ate"] == pytest.approx(0.1)
    se_a = np.sqrt(0.8 * 0.2 / 10 + 0.6 * 0.4 / 10)
    se_b = np.sqrt(0.3 * 0.7 / 10 + 0.3 * 0.7 / 10)
    assert e["se"] == pytest.approx(np.sqrt(0.25 * se_a**2 + 0.25 * se_b**2))


def test_roznica_efektow_segmentow_niezaleznych():
    a = {"ate": 0.10, "se": 0.03}
    b = {"ate": 0.02, "se": 0.04}
    r = roznica_efektow(a, b)
    assert r["roznica"] == pytest.approx(0.08)
    assert r["se"] == pytest.approx(0.05)
    assert r["ci95"][0] == pytest.approx(0.08 - 1.959964 * 0.05, abs=1e-6)


def test_gorne_35_procent_wedlug_progu_kwantyla():
    score = pd.Series(np.arange(100, dtype=float))
    gora = gorne_35(score)
    assert gora.sum() == 35
    assert gora[score >= 65].all() and not gora[score < 65].any()


def test_balans_cechy_liczbowej_smd_i_braki():
    x = pd.Series([1.0, 3.0, np.nan, 2.0, 4.0, np.nan, np.nan])
    oferta = np.array([True, True, True, False, False, False, False])
    w = balans_cechy(x, oferta, "x")
    assert w["oferta"] == pytest.approx(2.0)
    assert w["kontrola"] == pytest.approx(3.0)
    sd = np.sqrt((np.var([1, 3], ddof=1) + np.var([2, 4], ddof=1)) / 2)
    assert w["smd"] == pytest.approx(-1.0 / sd)
    assert w["braki_oferta"] == pytest.approx(1 / 3)
    assert w["braki_kontrola"] == pytest.approx(2 / 4)


def test_balans_cechy_kategorii_jako_udzial_b2b():
    x = pd.Series(["B2B", "B2C", "B2B", "B2C"])
    oferta = np.array([True, True, False, False])
    w = balans_cechy(x, oferta, "linia")
    assert w["cecha"] == "linia (udział B2B)"
    assert w["oferta"] == pytest.approx(0.5) and w["kontrola"] == pytest.approx(0.5)
    assert w["smd"] == pytest.approx(0.0)


def test_test_laczny_bez_zwiazku_daje_wysokie_p():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {"a": rng.normal(size=2000), "b": rng.normal(size=2000), "linia": rng.choice(["B2B", "B2C"], 2000)}
    )
    df.loc[:200, "a"] = np.nan
    oferta = rng.random(2000) < 0.5
    w = laczny_test_balansu(df, oferta, ["a", "b", "linia"])
    assert w["stopnie_swobody"] == 4  # a, brak_a, b, linia
    assert w["p"] > 0.01


def test_test_laczny_jeden_wskaznik_na_wspolny_wzor_brakow():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"a": rng.normal(size=500), "b": rng.normal(size=500)})
    df.loc[:100, ["a", "b"]] = np.nan  # jak ankieta_ostatni_wynik i ankieta_dni_od_odpowiedzi
    w = laczny_test_balansu(df, rng.random(500) < 0.5, ["a", "b"])
    assert w["stopnie_swobody"] == 3  # a, b, wspólny wskaźnik braku


def test_test_laczny_wykrywa_przydzial_zalezny_od_cechy():
    rng = np.random.default_rng(1)
    a = rng.normal(size=2000)
    df = pd.DataFrame({"a": a})
    oferta = rng.random(2000) < 1 / (1 + np.exp(-a))
    assert laczny_test_balansu(df, oferta, ["a"])["p"] < 1e-6


def test_cechy_balansu_to_10_najwazniejszych_cech_v1():
    cechy = cechy_balansu()
    assert len(cechy) == 10
    assert cechy[0] == "linia"
