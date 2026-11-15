"""Przedział wyceny v2_lgbm_geo_cqr: modele kwantylowe LightGBM + kalibracja konformalna CQR (docs/b1_przedzialy.md)."""

import math

import numpy as np
import pandas as pd
import pytest
from api.ai.valuation_model.base import KOLUMNY_CECH, KOLUMNY_PRZEDZIALU, ModelWyceny
from api.ai.valuation_model.versions.v2_lgbm_geo.model import ModelLightGBMGeo
from api.ai.valuation_model.versions.v2_lgbm_geo_cqr.model import (
    ModelPrzedzialuCQR,
    korekta_cqr,
    korekta_cqr_asymetryczna,
    kwantyl_konformalny,
)

# --- kwantyl konformalny i korekta CQR -------------------------------------------------------------------------


def test_kwantyl_konformalny_to_k_ty_najmniejszy_wynik_dla_k_rownego_sufit_n_plus_1_razy_poziom():
    wyniki = np.arange(1.0, 11.0)  # 1..10, n = 10
    # k = ceil(11 · 0,8) = ceil(8,8) = 9 -> 9. najmniejszy = 9
    assert kwantyl_konformalny(wyniki, 0.8) == 9.0
    # k = ceil(11 · 0,5) = 6
    assert kwantyl_konformalny(wyniki[::-1], 0.5) == 6.0


def test_kwantyl_konformalny_przy_za_malym_zbiorze_to_nieskonczonosc():
    assert kwantyl_konformalny(np.array([1.0, 2.0, 3.0]), 0.8) == math.inf  # ceil(4 · 0,8) = 4 > 3


def test_korekta_cqr_to_kwantyl_wyniku_max_dolna_minus_y_y_minus_gorna():
    dolna = np.array([0.0, 0.0, 0.0, 0.0])
    gorna = np.array([1.0, 1.0, 1.0, 1.0])
    y = np.array([0.5, -0.2, 1.3, 0.9])  # wyniki: -0,4 (w środku), 0,2 (pod), 0,3 (nad), -0,1
    # k = ceil(5 · 0,6) = 3 -> posortowane [-0,4, -0,1, 0,2, 0,3] -> 0,2
    assert korekta_cqr(dolna, gorna, y, 0.6) == pytest.approx(0.2)


def test_korekta_cqr_moze_byc_ujemna_gdy_przedzial_jest_za_szeroki():
    dolna = np.full(9, -10.0)
    gorna = np.full(9, 10.0)
    y = np.linspace(-1, 1, 9)
    assert korekta_cqr(dolna, gorna, y, 0.8) < 0


def test_korekta_asymetryczna_liczy_osobno_dol_i_gore_na_poziomie_polowy_ogona():
    dolna = np.zeros(9)
    gorna = np.ones(9)
    y = np.array([-0.5, -0.4, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5])  # dwa pod dolną, żaden nad górną
    kor_dol, kor_gor = korekta_cqr_asymetryczna(dolna, gorna, y, 0.8)
    # poziom każdego ogona = 0,9; k = ceil(10 · 0,9) = 9 -> maksimum
    assert kor_dol == pytest.approx(0.5)  # max(dolna − y) = 0,5
    assert kor_gor == pytest.approx(-0.5)  # max(y − gorna) = −0,5


def test_cqr_na_wymienialnych_danych_daje_pokrycie_okolo_poziomu():
    rng = np.random.default_rng(0)
    n = 20_000
    y = rng.normal(size=2 * n)
    dolna, gorna = np.full(2 * n, -0.5), np.full(2 * n, 0.5)  # zły (za wąski) przedział surowy
    kor = korekta_cqr(dolna[:n], gorna[:n], y[:n], 0.8)
    yt = y[n:]
    pokrycie = np.mean((yt >= dolna[n:] - kor) & (yt <= gorna[n:] + kor))
    assert pokrycie == pytest.approx(0.8, abs=0.01)


# --- model --------------------------------------------------------------------------------------------------------


def _dane(n=1500, seed=0):
    """ln(cena) = 12 + ln(metraz/50) + szum, szum ~ N(0, 0,05) dla dzielnicy a1 i N(0, 0,25) dla a2."""
    rng = np.random.default_rng(seed)
    dzielnica = rng.choice(["a1", "a2"], n)
    X = pd.DataFrame(
        {
            "miasto": "A",
            "dzielnica": dzielnica,
            "metraz": rng.uniform(25, 90, n).round(1),
            "pokoje": rng.integers(1, 5, n),
            "pietro": rng.integers(0, 10, n),
            "rok_budowy": rng.integers(1950, 2025, n),
            "blisko": rng.integers(0, 2, n),
        }
    )
    sigma = np.where(dzielnica == "a1", 0.05, 0.25)
    ln_y = 12 + np.log(X["metraz"] / 50) + rng.normal(size=n) * sigma
    return X, pd.Series(np.exp(ln_y))


def _punktowy(X, y):
    return ModelLightGBMGeo(cechy_liczbowe=("blisko",), max_drzew=100).fit(X, y)


def test_model_przedzialu_spelnia_kontrakt_i_zwraca_p10_p50_p90_z_p50_z_modelu_punktowego():
    X, y = _dane()
    X_kal, y_kal = _dane(seed=1)
    punktowy = _punktowy(X, y)
    model = ModelPrzedzialuCQR(punktowy, max_drzew=100).fit(X, y).kalibruj(X_kal, y_kal)
    assert isinstance(model, ModelWyceny)
    assert model.wersja == "v2_lgbm_geo_cqr"
    p = model.predict_interval(X_kal)
    assert list(p.columns) == list(KOLUMNY_PRZEDZIALU)
    assert p.index.equals(X_kal.index)
    assert np.allclose(p["p50"], punktowy.predict(X_kal))
    assert np.allclose(model.predict(X_kal), punktowy.predict(X_kal))
    assert (p["p10"] <= p["p50"]).all() and (p["p50"] <= p["p90"]).all()


def test_modele_kwantylowe_uzywaja_celu_quantile_z_alfa_0_1_i_0_9_i_tych_samych_cech():
    X, y = _dane()
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=50).fit(X, y)
    assert model.dolny_.parametry["objective"] == "quantile" and model.dolny_.parametry["alpha"] == 0.1
    assert model.gorny_.parametry["objective"] == "quantile" and model.gorny_.parametry["alpha"] == 0.9
    for m in (model.dolny_, model.gorny_):
        assert m.cechy_liczbowe == ("blisko",)
        assert m.najlepsza_iteracja_ == 50


def test_przedzial_jest_wezszy_tam_gdzie_szum_jest_mniejszy():
    X, y = _dane(n=3000)
    X_kal, y_kal = _dane(n=3000, seed=1)
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=200).fit(X, y).kalibruj(X_kal, y_kal)
    p = model.predict_interval(X_kal)
    szer = (p["p90"] - p["p10"]) / p["p50"]
    assert szer[X_kal["dzielnica"] == "a1"].median() < 0.5 * szer[X_kal["dzielnica"] == "a2"].median()


def test_po_kalibracji_pokrycie_na_nowych_danych_jest_bliskie_80_proc():
    X, y = _dane(n=3000)
    X_kal, y_kal = _dane(n=3000, seed=1)
    X_t, y_t = _dane(n=5000, seed=2)
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=200).fit(X, y).kalibruj(X_kal, y_kal)
    p = model.predict_interval(X_t)
    pokrycie = ((y_t >= p["p10"]) & (y_t <= p["p90"])).mean()
    assert pokrycie == pytest.approx(0.8, abs=0.03)
    assert model.n_kalibracji_ == 3000


def test_metody_przedzialu_surowy_cqr_i_asymetryczny():
    X, y = _dane()
    X_kal, y_kal = _dane(seed=1)
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=100).fit(X, y).kalibruj(X_kal, y_kal)
    surowy = model.predict_interval(X_kal, metoda="surowy")
    cqr = model.predict_interval(X_kal, metoda="cqr")
    p50 = surowy["p50"]
    # CQR przesuwa obie granice o ten sam czynnik exp(korekta) w ln (przed uporządkowaniem względem p50)
    lo = np.minimum(np.exp(np.log(model.dolny_.predict(X_kal)) - model.korekta_), p50)
    assert np.allclose(cqr["p10"], lo)
    asym = model.predict_interval(X_kal, metoda="cqr_asymetryczny")
    hi = np.maximum(np.exp(np.log(model.gorny_.predict(X_kal)) + model.korekta_asym_[1]), p50)
    assert np.allclose(asym["p90"], hi)
    with pytest.raises(ValueError, match="metoda"):
        model.predict_interval(X_kal, metoda="inna")


def test_przedzial_bez_kalibracji_to_czytelny_blad_a_surowy_dziala():
    X, y = _dane()
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=50).fit(X, y)
    with pytest.raises(RuntimeError, match="kalibr"):
        model.predict_interval(X)
    assert np.isfinite(model.predict_interval(X, metoda="surowy").to_numpy()).all()


def test_liczba_drzew_kwantylowych_z_wczesnego_zatrzymania_na_odlozonej_czesci_treningu():
    X, y = _dane(n=2000)
    X_odl, y_odl = _dane(n=500, seed=3)
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=3000, stopping_rounds=20).fit(X, y, X_odl, y_odl)
    for m in (model.dolny_, model.gorny_):
        assert 0 < m.najlepsza_iteracja_ < 3000
    assert model.drzewa_ == {"p10": model.dolny_.najlepsza_iteracja_, "p90": model.gorny_.najlepsza_iteracja_}
    # Po wyborze liczby drzew modele uczą się na treningu ∪ części odłożonej, bez wczesnego zatrzymania.
    assert model.dolny_.l2_walidacja_ is None


def test_model_przedzialu_po_zapisie_i_wczytaniu_daje_te_same_przedzialy(tmp_path):
    X, y = _dane()
    X_kal, y_kal = _dane(seed=1)
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=50).fit(X, y).kalibruj(X_kal, y_kal)
    model.zapisz(tmp_path / "model.joblib")
    wczytany = ModelWyceny.wczytaj(tmp_path / "model.joblib")
    assert np.allclose(wczytany.predict_interval(X_kal), model.predict_interval(X_kal))


def test_brak_kolumny_cechy_dodatkowej_to_czytelny_blad():
    X, y = _dane()
    model = ModelPrzedzialuCQR(_punktowy(X, y), max_drzew=50).fit(X, y)
    with pytest.raises(ValueError, match="blisko"):
        model.predict_interval(X[list(KOLUMNY_CECH)], metoda="surowy")
