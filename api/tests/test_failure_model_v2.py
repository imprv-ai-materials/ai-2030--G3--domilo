import numpy as np
import pandas as pd
import pytest
from api.ai.failure_model.base import KOLUMNY_ZAKAZANE, ModelWind
from api.ai.failure_model.evals.ewaluacja_v2 import (
    KATALOG_WERSJI,
    WIND_POZA,
    podzial_czas_winda,
    podzial_losowy,
    windy_poza_treningiem,
)
from api.ai.failure_model.versions.v2_lgbm_losowy.model import ModelLGBMWind
from api.ai.failure_model.versions.v2b_lgbm_czas_winda.model import ModelLGBMCzasWinda


def _dni(n_wind=140, od="2023-03-01", do="2026-09-22"):
    dni = pd.date_range(od, do, freq="D")
    windy = [f"B{i // 4:02d}-W{i % 4 + 1}" for i in range(n_wind)]
    return pd.DataFrame([(w, d) for w in windy for d in dni], columns=["id_windy", "dzien"])


def test_zakazane_cechy_przerywaja_uczenie():
    for k in ("awaria_7d", "id_awarii", "id_windy", "dzien", "godziny_do_startu"):
        assert k in KOLUMNY_ZAKAZANE
        with pytest.raises(ValueError, match="zakazane"):
            ModelLGBMWind(["drzwi_bledy_sr_24h", k])


def test_podzial_losowy_80_20_rozlaczny():
    df = _dni(n_wind=20)
    m = podzial_losowy(df)
    suma = m["trening"].astype(int) + m["walidacja"].astype(int) + m["test"].astype(int)
    assert (suma == 1).all()
    assert m["test"].mean() == pytest.approx(0.2, abs=0.01)
    assert (m["trening"] | m["walidacja"]).mean() == pytest.approx(0.8, abs=0.01)


def test_podzial_czas_winda_okresy_i_windy_poza():
    df = _dni()
    m, poza = podzial_czas_winda(df)
    assert len(poza) == WIND_POZA == 28
    assert poza == windy_poza_treningiem(df["id_windy"])  # powtarzalnie
    for nazwa, (od, do) in {
        "trening": ("2023-03-01", "2025-06-30"),
        "walidacja": ("2025-07-01", "2025-12-31"),
        "test": ("2026-01-01", "2026-09-22"),
    }.items():
        d = df.loc[m[nazwa], "dzien"]
        assert d.min() == pd.Timestamp(od) and d.max() == pd.Timestamp(do)
    uczace = df.loc[m["trening"] | m["walidacja"], "id_windy"]
    assert not uczace.isin(poza).any()
    assert set(df.loc[m["test_windy_niewidziane"], "id_windy"]) == set(poza)
    assert (m["test_windy_widziane"] | m["test_windy_niewidziane"] == m["test"]).all()


def test_fit_predict_explain_na_malych_danych():
    rng = np.random.default_rng(0)
    n = 3000
    df = pd.DataFrame({"id_windy": "W1", "dzien": pd.Timestamp("2025-01-01"), "x": rng.normal(size=n)})
    df["awaria_7d"] = (df["x"] + rng.normal(scale=0.5, size=n) > 1.5).astype(int)
    model = ModelLGBMCzasWinda(["x"], parametry={"min_child_samples": 20}).fit(
        df[:2000], df["awaria_7d"][:2000], df[2000:], df["awaria_7d"][2000:]
    )
    p = model.predict(df[2000:])
    assert p.shape == (1000,) and ((p >= 0) & (p <= 1)).all()
    wyj = model.explain(df[2000:2005])
    assert list(wyj.columns) == ["wynik", "wklad_x", "wklad_staly"]
    with pytest.raises(ValueError, match="Brak kolumn"):
        model.predict(df[["id_windy", "dzien"]])


@pytest.mark.parametrize("wersja", ["v2_lgbm_losowy", "v2b_lgbm_czas_winda"])
def test_zapisane_wersje(wersja):
    sciezka = KATALOG_WERSJI / wersja / "model.joblib"
    if not sciezka.exists():
        pytest.skip("model nie jest zbudowany (python -m api.ai.failure_model.evals.ewaluacja_v2)")
    model = ModelWind.wczytaj(sciezka)
    assert model.wersja == wersja
    assert not set(model.cechy) & KOLUMNY_ZAKAZANE
    assert (KATALOG_WERSJI / wersja / "metryki.json").exists()
