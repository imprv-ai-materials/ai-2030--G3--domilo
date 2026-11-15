"""v4_llm_cechy: v3_przedzialy + cechy lokalu z LLM w modelach P50/P10/P90, ten sam CQR i ten sam detektor OOD."""

import numpy as np
import pandas as pd
import pytest
from api.ai.valuation_model.base import KOLUMNY_ODMOWY, KOLUMNY_PRZEDZIALU, ModelWyceny
from api.ai.valuation_model.versions.v3_przedzialy.model import ModelWycenyV3
from api.ai.valuation_model.versions.v3_przedzialy.ood import DetektorOOD
from api.ai.valuation_model.versions.v4_llm_cechy.model import ModelWycenyV4

KOLUMNY_DETEKTORA = ("metraz", "pokoje", "pietro", "rok_budowy", "blisko")
MALE = {"max_drzew": 150}


def _dane(n=2000, seed=0, start="2024-01-01"):
    """ln(cena) = 12 + ln(metraz/50) + 0,15·(standard − 3) + szum; standard znany (z opisu) w 40% wierszy."""
    rng = np.random.default_rng(seed)
    standard = rng.integers(1, 6, n).astype(float)
    znany = rng.random(n) < 0.4
    X = pd.DataFrame(
        {
            "miasto": "A",
            "dzielnica": rng.choice(["a1", "a2"], n),
            "metraz": rng.uniform(25, 90, n).round(1),
            "pokoje": rng.integers(1, 4, n),
            "pietro": rng.integers(0, 10, n),
            "rok_budowy": rng.integers(1950, 2025, n),
            "blisko": rng.integers(0, 2, n),
            "data_aktu": pd.Timestamp(start) + pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
            "llm_standard": np.where(znany, standard, np.nan),
            "llm_widok": np.where(znany, rng.choice(["park", "ulica", "brak_info"], n), None),
        }
    )
    y = np.exp(12 + np.log(X["metraz"] / 50) + 0.15 * (standard - 3) + rng.normal(size=n) * 0.05)
    return X, pd.Series(y)


@pytest.fixture(scope="module")
def uczone():
    X, y = _dane()
    X_wal, y_wal = _dane(seed=1)
    detektor = DetektorOOD(kolumny=KOLUMNY_DETEKTORA, n_drzew=50).fit(X)
    punkt = {"cechy_liczbowe": ("blisko",), **MALE}
    v3 = ModelWycenyV3(
        parametry_punktowe=punkt,
        parametry_przedzialu=MALE,
        parametry_detektora={"kolumny": KOLUMNY_DETEKTORA, "n_drzew": 50},
    ).fit(X, y, X_wal, y_wal)
    v4 = ModelWycenyV4(
        parametry_punktowe={**punkt, "cechy_liczbowe": ("blisko", "llm_standard"), "cechy_kategorii": ("llm_widok",)},
        parametry_przedzialu=MALE,
        detektor=detektor,
    ).fit(X, y, X_wal, y_wal)
    return v3, v4, detektor


def test_v4_jest_modelem_wyceny_z_przedzialem_i_odmowa(uczone):
    _, v4, _ = uczone
    X, _ = _dane(seed=2, n=300)
    p = v4.predict_interval(X)
    assert isinstance(v4, ModelWyceny) and v4.wersja == "v4_llm_cechy"
    assert list(p.columns) == list(KOLUMNY_PRZEDZIALU) + list(KOLUMNY_ODMOWY)


def test_v4_uzywa_tego_samego_detektora_co_v3_bez_ponownego_uczenia(uczone):
    _, v4, detektor = uczone
    assert v4.detektor is detektor


def test_cechy_llm_sa_w_modelu_punktowym_i_kwantylowych(uczone):
    _, v4, _ = uczone
    for m in (v4.przedzial.punktowy, v4.przedzial.dolny_, v4.przedzial.gorny_):
        assert {"llm_standard", "llm_widok"} <= set(m.reg_.booster_.feature_name())


def test_cechy_llm_zmniejszaja_blad_tam_gdzie_standard_jest_znany(uczone):
    v3, v4, _ = uczone
    X, y = _dane(seed=3, n=1000)
    znany = X["llm_standard"].notna()
    mape = {n: np.mean(np.abs(m.przedzial.predict(X[znany]) / y[znany] - 1)) for n, m in (("v3", v3), ("v4", v4))}
    assert mape["v4"] < 0.7 * mape["v3"]


def test_v4_wycenia_lokal_bez_cech_llm(uczone):
    _, v4, _ = uczone
    X, _ = _dane(seed=4, n=50)
    X = X.assign(llm_standard=np.nan, llm_widok=None)
    assert np.isfinite(v4.przedzial.predict_interval(X).to_numpy()).all()


def test_brak_kolumny_llm_to_blad_a_nie_cicha_wycena(uczone):
    _, v4, _ = uczone
    X, _ = _dane(seed=5, n=20)
    with pytest.raises(ValueError, match="llm_standard"):
        v4.predict_interval(X.drop(columns="llm_standard"))
