"""Model listy retencyjnej: kontrakt (base.py), v1_ryzyko, metryki górnego decyla i podział w czasie."""

import numpy as np
import pandas as pd
import pytest
from api.ai.churn_model.base import KOLUMNY_WEJSCIA, KOLUMNY_ZAKAZANE, ModelNajemcow
from api.ai.churn_model.evals.metryki import metryki_rankingu, precision_at, recall_at
from api.ai.churn_model.versions.v1_ryzyko.model import ModelRyzyko
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from api.ai.features.najemcy.zbior import podziel


def _migawki(n: int = 1200, ziarno: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    """Syntetyczne migawki z sygnałem w `plat_spoznione_90d` i linii; reszta cech to szum."""
    rng = np.random.default_rng(ziarno)
    df = pd.DataFrame({k: rng.normal(size=n) for k in KOLUMNY_CECH if k != "linia"})
    df["linia"] = rng.choice(["B2C", "B2B"], size=n)
    df["plat_spoznione_90d"] = rng.integers(0, 4, size=n).astype(float)
    df.loc[rng.random(n) < 0.1, "ankieta_ostatni_wynik"] = np.nan
    df["id_umowy"] = [f"U{i}" for i in range(n)]
    df["data_migawki"] = pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, 1000, size=n), unit="D")
    logit = -1 + 0.9 * df["plat_spoznione_90d"] + 1.0 * (df["linia"] == "B2B")
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df, y


# --- kontrakt ----------------------------------------------------------------------------------------------------


def test_wejscie_to_id_dzien_migawki_i_cechy_z_features():
    assert KOLUMNY_WEJSCIA[:2] == ("id_umowy", "data_migawki")
    assert set(KOLUMNY_CECH) <= set(KOLUMNY_WEJSCIA)
    assert not set(KOLUMNY_WEJSCIA) & KOLUMNY_ZAKAZANE


@pytest.mark.parametrize(
    "kolumna", ["odejdzie", "wypowiedzenie_przed_migawka", "score_polityki", "grupa", "rok_urodzenia", "jezyk_kontaktu"]
)
def test_model_odrzuca_zakazana_ceche(kolumna):
    with pytest.raises(ValueError, match="zakazane"):
        ModelRyzyko(cechy=("staz_dni", kolumna))


def test_brak_wymaganej_kolumny():
    df, y = _migawki()
    with pytest.raises(ValueError, match="Brak kolumn"):
        ModelNajemcow.sprawdz_kolumny(df.drop(columns=["data_migawki"]))


# --- v1_ryzyko ---------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def nauczony():
    df, y = _migawki()
    return ModelRyzyko().fit(df, y), df, y


def test_v1_uczy_sie_sygnalu_i_zwraca_ryzyko_0_1(nauczony):
    model, df, y = nauczony
    nowe, y_nowe = _migawki(ziarno=1)
    ryzyko = model.predict(nowe)
    assert ryzyko.shape == (len(nowe),)
    assert ((ryzyko >= 0) & (ryzyko <= 1)).all()
    assert metryki_rankingu(y_nowe, ryzyko)["auc"] > 0.65
    assert model.liczba_drzew_ >= 1


def test_v1_nie_zalezy_od_kolumn_poza_cechami(nauczony):
    model, df, y = nauczony
    z_wynikiem = df.assign(odejdzie=1 - y, score_polityki=0.99, wypowiedzenie_przed_migawka=True)
    np.testing.assert_array_equal(model.predict(z_wynikiem), model.predict(df))


def test_v1_explain_sumuje_sie_do_log_szansy(nauczony):
    model, df, _ = nauczony
    wyj = model.explain(df.head(20))
    log_szansa = wyj.filter(like="wklad_").sum(axis=1)
    np.testing.assert_allclose(1 / (1 + np.exp(-log_szansa)), wyj["wynik"], rtol=1e-6)
    assert model.waznosc_cech().iloc[0]["cecha"] in {"plat_spoznione_90d", "linia"}


def test_v1_zapis_i_odczyt(nauczony, tmp_path):
    model, df, _ = nauczony
    model.zapisz(tmp_path / "v1" / "model.joblib")
    wczytany = ModelNajemcow.wczytaj(tmp_path / "v1" / "model.joblib")
    assert wczytany.wersja == "v1_ryzyko"
    np.testing.assert_array_equal(wczytany.predict(df), model.predict(df))


# --- metryki -----------------------------------------------------------------------------------------------------


def test_recall_i_precyzja_w_gornym_decylu():
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 1] * 2)  # 20 umów, 6 odejść; decyl = 2 umowy
    wynik = np.linspace(1, 0, 20)  # pierwsze dwie (oba odejścia) na górze
    assert precision_at(y, wynik) == 1.0
    assert recall_at(y, wynik) == pytest.approx(2 / 6)


def test_remis_na_granicy_decyla_liczy_wartosc_oczekiwana():
    y = np.array([1, 0, 1, 0] + [0] * 16)  # decyl = 2; cztery pierwsze w remisie, połowa odchodzi
    wynik = np.array([1.0] * 4 + [0.0] * 16)
    assert precision_at(y, wynik) == pytest.approx(0.5)
    assert recall_at(y, wynik) == pytest.approx(0.5)


# --- podział -----------------------------------------------------------------------------------------------------


def test_podzial_trening_do_2025_12_test_2026_04_09_bez_przerwy():
    miesiace = pd.to_datetime(["2023-03-01", "2025-12-01", "2026-01-01", "2026-03-01", "2026-04-01", "2026-09-01"])
    zb = podziel(pd.DataFrame({"miesiac_konca": miesiace, "id_umowy": list("abcdef")}))
    assert list(zb["trening"]["id_umowy"]) == ["a", "b"]
    assert list(zb["test"]["id_umowy"]) == ["e", "f"]
