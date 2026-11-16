import numpy as np
import pandas as pd
import pytest
from api.ai.churn_model.evals.metryki_uplift import auuc, bootstrap_miar, krzywa_qini, qini_w, uplift_w_czolowce
from api.ai.churn_model.versions.v3_uplift_tlearner.model import ModelUpliftT, macierz
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from api.ai.features.najemcy.zbior import czesc_uplift, podziel_uplift

# --- podział 70/30 według id_umowy -----------------------------------------------------------------------------


def test_czesc_uplift_zalezy_tylko_od_id_umowy():
    ids = pd.Series([f"U{i:07d}" for i in range(20_000)])
    czesc = czesc_uplift(ids)
    assert set(czesc) == {"trening", "test"}
    assert (czesc == "trening").mean() == pytest.approx(0.70, abs=0.01)
    # ta sama umowa zawsze w tej samej części, niezależnie od kolejności i reszty zbioru
    odwrocone = czesc_uplift(ids[::-1].reset_index(drop=True))
    assert (odwrocone[::-1].to_numpy() == czesc.to_numpy()).all()
    assert czesc_uplift(ids[:5]).tolist() == czesc[:5].tolist()


def test_podziel_uplift_bierze_tylko_test_2025():
    df = pd.DataFrame(
        {"id_umowy": [f"U{i}" for i in range(400)], "okres": ["test_2025"] * 300 + ["polityka_2024"] * 100}
    )
    z = podziel_uplift(df)
    assert len(z["trening"]) + len(z["test"]) == 300
    assert set(z["trening"]["okres"]) == {"test_2025"}
    assert not set(z["trening"]["id_umowy"]) & set(z["test"]["id_umowy"])


# --- krzywa Qini, AUUC, uplift w czołówce ----------------------------------------------------------------------


def test_krzywa_qini_konczy_sie_na_ate_i_zaczyna_od_zera():
    y = np.array([1, 0, 1, 0, 0, 1, 0, 0])
    w = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    k = krzywa_qini(y, w, np.arange(8)[::-1].astype(float))
    assert k["frakcja"].iloc[0] == 0 and k["qini"].iloc[0] == 0
    assert k["frakcja"].iloc[-1] == pytest.approx(1.0)
    assert k["qini"].iloc[-1] == pytest.approx(2 / 4 - 1 / 4)


def test_krzywa_qini_remis_daje_prosta_od_zera_do_ate():
    y = np.array([1, 0, 1, 0, 0, 1, 0, 0])
    w = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    k = krzywa_qini(y, w, np.zeros(8))
    assert len(k) == 2  # tylko 0 i koniec grupy remisu
    assert auuc(k) == pytest.approx(0.25 / 2)
    assert qini_w(k, 0.4) == pytest.approx(0.4 * 0.25)


def test_krzywa_qini_kolejnosc_wedlug_wyniku():
    # oferta przedłuża tylko u osób z wysokim wynikiem; kontrola nie przedłuża nigdzie
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0])
    w = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    wynik = np.array([4, 3, 1, 0, 4, 3, 1, 0], dtype=float)
    k = krzywa_qini(y, w, wynik)
    # remisy (4,4), (3,3), (1,1), (0,0): punkty po 2, 4, 6, 8 umowach
    assert k["frakcja"].tolist() == pytest.approx([0, 0.25, 0.5, 0.75, 1.0])
    assert k["qini"].tolist() == pytest.approx([0, 0.25, 0.5, 0.5, 0.5])
    assert auuc(k) == pytest.approx(0.25 * (0.125 + 0.375 + 0.5 + 0.5))


def test_uplift_w_czolowce_z_ulamkowym_remisem():
    y = np.array([1, 1, 0, 0, 1, 0, 0, 0])
    w = np.array([1, 1, 0, 0, 1, 1, 0, 0])
    wynik = np.array([9, 9, 9, 9, 1, 1, 1, 1], dtype=float)
    # górne 25% = 2 z 4 remisujących na górze -> wartość oczekiwana = uplift górnej grupy: 1 - 0 = 1
    assert uplift_w_czolowce(y, w, wynik, 0.25)["uplift"] == pytest.approx(1.0)
    # stały wynik -> uplift całej populacji
    stale = uplift_w_czolowce(y, w, np.zeros(8), 0.2)
    assert stale["uplift"] == pytest.approx(3 / 4 - 0 / 4)


def test_bootstrap_roznica_rankingu_z_samym_soba_jest_zerowa():
    rng = np.random.default_rng(3)
    y, w, s = rng.integers(0, 2, 300), rng.integers(0, 2, 300), rng.random(300)
    b = bootstrap_miar(y, w, {"a": s, "b": s.copy(), "c": -s}, pary=[("a", "b"), ("b", "c")], n_prob=50)
    assert set(b["roznice"]) == {"a_minus_b", "b_minus_c"}
    assert b["roznice"]["a_minus_b"]["auuc"] == [0.0, 0.0]
    lo, hi = b["przedzialy"]["a"]["auuc"]
    assert lo <= auuc(krzywa_qini(y, w, s)) <= hi


# --- T-learner -------------------------------------------------------------------------------------------------


def _dane(n: int, ziarno: int) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(ziarno)
    df = pd.DataFrame({k: rng.normal(size=n) for k in KOLUMNY_CECH if k != "linia"})
    df["linia"] = rng.choice(["B2C", "B2B"], n)
    w = rng.random(n) < 0.5
    # oferta pomaga tylko przy wysokim czynsz_m2
    p = 0.4 + 0.3 * w * (df["czynsz_m2"].to_numpy() > 0)
    y = (rng.random(n) < p).astype(int)
    return df, w, y


def test_macierz_zamienia_linie_na_b2b():
    df = pd.DataFrame({k: [1.0, 2.0] for k in KOLUMNY_CECH if k != "linia"} | {"linia": ["B2B", "B2C"]})
    X = macierz(df)
    assert "b2b" in X.columns and "linia" not in X.columns
    assert X["b2b"].tolist() == [1.0, 0.0]
    assert all(X.dtypes == "float64")


def test_t_learner_znajduje_segment_z_efektem():
    df, w, y = _dane(6000, 0)
    model = ModelUpliftT().fit(df, w, y)
    test, _, _ = _dane(2000, 1)
    uplift = model.predict(test)
    wysoki = test["czynsz_m2"].to_numpy() > 0
    assert uplift[wysoki].mean() - uplift[~wysoki].mean() > 0.15
    p_o, p_k = model.predict_skladowe(test)
    assert np.allclose(uplift, p_o - p_k)


def test_t_learner_odrzuca_cechy_zakazane():
    with pytest.raises(ValueError, match="zakazane"):
        ModelUpliftT(cechy=("czynsz_m2", "score_polityki"))
