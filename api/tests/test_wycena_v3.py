"""v3_przedzialy: wycena P50 + przedział P10/P90 (CQR) albo odmowa z powodem (detektor OOD). docs/b1_v3.md."""

import numpy as np
import pandas as pd
import pytest
from api.ai.valuation_model.base import KOLUMNY_ODMOWY, KOLUMNY_PRZEDZIALU, ModelWyceny
from api.ai.valuation_model.versions.v2_lgbm_geo.model import ModelLightGBMGeo
from api.ai.valuation_model.versions.v2_lgbm_geo_cqr.model import ModelPrzedzialuCQR
from api.ai.valuation_model.versions.v3_przedzialy.model import ModelWycenyV3
from api.ai.valuation_model.versions.v3_przedzialy.ood import DetektorOOD

KOLUMNY_DETEKTORA = ("metraz", "pokoje", "pietro", "rok_budowy", "blisko")


def _dane(n=1500, seed=0, start="2024-01-01"):
    """Jak w test_wycena_przedzial: ln(cena) = 12 + ln(metraz/50) + szum (dzielnica a1: 0,05, a2: 0,25)."""
    rng = np.random.default_rng(seed)
    dzielnica = rng.choice(["a1", "a2"], n)
    X = pd.DataFrame(
        {
            "miasto": "A",
            "dzielnica": dzielnica,
            "metraz": rng.uniform(25, 90, n).round(1),
            "pokoje": rng.integers(1, 4, n),
            "pietro": rng.integers(0, 10, n),
            "rok_budowy": rng.integers(1950, 2025, n),
            "blisko": rng.integers(0, 2, n),
            "data_aktu": pd.Timestamp(start) + pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
        }
    )
    sigma = np.where(dzielnica == "a1", 0.05, 0.25)
    return X, pd.Series(np.exp(12 + np.log(X["metraz"] / 50) + rng.normal(size=n) * sigma))


@pytest.fixture(scope="module")
def skladniki():
    X, y = _dane()
    X_kal, y_kal = _dane(seed=1)
    punktowy = ModelLightGBMGeo(cechy_liczbowe=("blisko",), max_drzew=100).fit(X, y)
    przedzial = ModelPrzedzialuCQR(punktowy, max_drzew=100).fit(X, y).kalibruj(X_kal, y_kal)
    detektor = DetektorOOD(kolumny=KOLUMNY_DETEKTORA, n_drzew=50).fit(X)
    return przedzial, detektor, X_kal


def _model(skladniki, **kw):
    przedzial, detektor, _ = skladniki
    return ModelWycenyV3(przedzial=przedzial, detektor=detektor, **kw)


def test_kontrakt_przedzial_ma_p10_p50_p90_i_kolumny_odmowy(skladniki):
    model = _model(skladniki)
    X = skladniki[2]
    assert isinstance(model, ModelWyceny) and model.wersja == "v3_przedzialy"
    p = model.predict_interval(X)
    assert list(p.columns) == list(KOLUMNY_PRZEDZIALU) + list(KOLUMNY_ODMOWY)
    assert p.index.equals(X.index)
    przyjete = ~p["odmowa"]
    assert przyjete.mean() > 0.9
    cqr = skladniki[0].predict_interval(X)
    assert np.allclose(p.loc[przyjete, list(KOLUMNY_PRZEDZIALU)], cqr.loc[przyjete])
    assert (p.loc[przyjete, "powod"] == "").all()


def test_odmowa_ma_puste_p10_p50_p90_i_powod_slowami(skladniki):
    model = _model(skladniki)
    X = skladniki[2].head(3).copy()
    X.loc[X.index[0], "miasto"] = "Katowice"
    p = model.predict_interval(X)
    assert p["odmowa"].tolist() == [True, False, False]
    assert p.loc[X.index[0], list(KOLUMNY_PRZEDZIALU)].isna().all()
    assert "Miasto Katowice" in p.loc[X.index[0], "powod"]
    pred = model.predict(X)
    assert np.isnan(pred[0]) and np.isfinite(pred[1:]).all()


def test_odmowa_przy_zbyt_szerokim_przedziale_gdy_ustawiony_prog(skladniki):
    X = skladniki[2]
    bez = _model(skladniki).predict_interval(X)
    z = _model(skladniki, max_szerokosc=0.0).predict_interval(X)
    assert z["odmowa"].all()
    nowe = z["odmowa"] & ~bez["odmowa"]
    assert nowe.any()
    assert z.loc[nowe, "powod"].str.contains("Przedział za szeroki").all()


def test_wlasne_progi_detektora_przekazane_do_ocen(skladniki):
    X = skladniki[2]
    luzny = _model(skladniki, prog_knn=np.inf, prog_if=np.inf).predict_interval(X)
    domyslny = _model(skladniki).predict_interval(X)
    assert luzny["odmowa"].sum() <= domyslny["odmowa"].sum()


def test_explain_ma_wklady_i_decyzje(skladniki):
    wyj = _model(skladniki).explain(skladniki[2].head(5))
    assert {"wklad_metraz", "p10", "p90", "odmowa", "powod"} <= set(wyj.columns)


def test_fit_uczy_wszystkie_skladniki_z_podzialem_czasowym():
    X, y = _dane(n=2000)
    X_wal, y_wal = _dane(n=800, seed=1, start="2025-01-01")
    model = ModelWycenyV3(
        parametry_punktowe={"cechy_liczbowe": ("blisko",), "max_drzew": 300, "stopping_rounds": 20},
        parametry_przedzialu={"max_drzew": 300, "stopping_rounds": 20},
        parametry_detektora={"kolumny": KOLUMNY_DETEKTORA, "n_drzew": 50},
    ).fit(X, y, X_wal, y_wal, poczatek_odlozonej=pd.Timestamp("2024-10-01"))
    # P50: wczesne zatrzymanie na walidacji; P10/P90: drzewa z części odłożonej treningu; CQR na walidacji
    assert 0 < model.przedzial.punktowy.najlepsza_iteracja_ < 300
    assert model.przedzial.n_kalibracji_ == 800
    assert model.detektor.n_treningu_ == 2000
    p = model.predict_interval(X_wal)
    pokrycie = ((y_wal >= p["p10"]) & (y_wal <= p["p90"]))[~p["odmowa"]].mean()
    assert pokrycie == pytest.approx(0.8, abs=0.06)


def test_v3_po_zapisie_i_wczytaniu_daje_to_samo(skladniki, tmp_path):
    model = _model(skladniki, max_szerokosc=0.5)
    X = skladniki[2]
    model.zapisz(tmp_path / "model.joblib")
    wczytany = ModelWyceny.wczytaj(tmp_path / "model.joblib")
    pd.testing.assert_frame_equal(wczytany.predict_interval(X), model.predict_interval(X))
