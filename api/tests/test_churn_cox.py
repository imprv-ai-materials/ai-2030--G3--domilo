import duckdb
import numpy as np
import pandas as pd
import pytest
from api.ai.churn_model.versions.v2_przezycie_cox.model import CECHY, ModelCox
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from api.ai.features.najemcy.cechy_okresow import okresy_umow

# --- okresy_umow.sql: czas i zdarzenie w okresie, ucięcie obserwacji ---------------------------------------------

# (id_najmu, id_lokalu, id_najemcy, linia, data_wprowadzenia, data_wyprowadzenia)
NAJMY = [
    ("N_odchodzi", "L1", "T1", "B2C", "2023-05-01", "2025-04-30"),  # przedłużył raz, odszedł na koniec 2. okresu
    ("N_wczesniej", "L2", "T2", "B2B", "2024-03-01", "2024-08-15"),  # zerwał w trakcie 1. okresu
    ("N_mid", "L3", "T3", "MID", "2024-01-01", "2024-06-30"),
]
# (id_umowy, id_najmu, nr_okresu, typ, data_od, data_do)
UMOWY = [
    ("U1", "N_odchodzi", 1, "pierwsza", "2023-05-01", "2024-04-30"),
    ("U2", "N_odchodzi", 2, "przedłużenie", "2024-05-01", "2025-04-30"),
    ("U3", "N_wczesniej", 1, "pierwsza", "2024-03-01", "2025-08-31"),
    ("U4", "N_mid", 1, "średnioterminowa", "2024-01-01", "2024-06-30"),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    najmy = pd.DataFrame(
        NAJMY, columns=["id_najmu", "id_lokalu", "id_najemcy", "linia", "data_wprowadzenia", "data_wyprowadzenia"]
    )
    umowy = pd.DataFrame(UMOWY, columns=["id_umowy", "id_najmu", "nr_okresu", "typ", "data_od", "data_do"])
    for df, kolumny in ((najmy, ("data_wprowadzenia", "data_wyprowadzenia")), (umowy, ("data_od", "data_do"))):
        for k in kolumny:
            df[k] = pd.to_datetime(df[k])
    con.register("n_df", najmy)
    con.register("u_df", umowy)
    con.execute("CREATE TABLE pms_najmy AS SELECT * FROM n_df")
    con.execute("CREATE TABLE pms_umowy AS SELECT * FROM u_df")
    yield con
    con.close()


def test_okresy_pelna_obserwacja(con):
    o = okresy_umow(con, "2026-09-30").set_index("id_umowy")
    assert set(o.index) == {"U1", "U2", "U3"}
    assert (o.loc["U1", "czas"], o.loc["U1", "zdarzenie"]) == (pytest.approx(12.0), 0)  # przedłużony
    assert (o.loc["U2", "czas"], o.loc["U2", "zdarzenie"]) == (pytest.approx(12.0), 1)  # koniec na data_do
    assert o.loc["U3", "zdarzenie"] == 1
    assert o.loc["U3", "czas"] == pytest.approx(5 + 15 / 31)
    assert o.loc["U3", "miesiecy_umowy"] == 18
    assert str(o.loc["U2", "data_migawki"])[:10] == "2024-05-01"


def test_okresy_uciete_na_koncu_obserwacji(con):
    o = okresy_umow(con, "2024-06-30").set_index("id_umowy")
    assert set(o.index) == {"U1", "U2", "U3"}
    assert (o.loc["U2", "czas"], o.loc["U2", "zdarzenie"]) == (pytest.approx(2.0), 0)  # 2024-05-01 – 06-30
    assert (o.loc["U3", "czas"], o.loc["U3", "zdarzenie"]) == (pytest.approx(4.0), 0)  # wyprowadzka po ucięciu
    assert len(okresy_umow(con, "2024-04-30")) == 2  # U2 zaczyna się po końcu obserwacji


# --- ModelCox na danych syntetycznych ------------------------------------------------------------------------------


def _okresy(n: int = 1500, ziarno: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(ziarno)
    df = pd.DataFrame({k: rng.normal(size=n) for k in KOLUMNY_CECH if k not in ("linia",)})
    df["linia"] = np.where(rng.random(n) < 0.3, "B2B", "B2C")
    df["miesiecy_umowy"] = np.where((df["linia"] == "B2B") & (rng.random(n) < 0.4), 18.0, 12.0)
    df["indeksacja_ostatnia_pct"] = np.where(rng.random(n) < 0.5, np.nan, rng.uniform(0, 12, n))
    df["czynsz_do_podobnych"] = np.where(rng.random(n) < 0.05, np.nan, df["czynsz_do_podobnych"])
    lp = 0.8 * (df["linia"] == "B2B") + 0.4 * (df["indeksacja_ostatnia_pct"].fillna(0) > 6)
    t = rng.exponential(20 / np.exp(lp))
    df["czas"] = np.minimum(t, df["miesiecy_umowy"])
    df["zdarzenie"] = (t <= df["miesiecy_umowy"]).astype(int)
    df["id_najemcy"] = [f"T{i % 900}" for i in range(n)]
    return df


def test_ryzyko_bez_interakcji_jak_lifelines():
    okresy = _okresy()
    m = ModelCox(interakcje_czasu={}).fit(okresy)
    X = m.macierz(okresy)
    # przy warstwach lifelines grupuje kolumny wyniku według warstwy, więc wyrównujemy po indeksie
    oczekiwane = 1 - m.cph_.predict_survival_function(X, times=[12.0])[X.index].to_numpy()[0]
    np.testing.assert_allclose(m.ryzyko(okresy), oczekiwane, rtol=1e-6)


def test_ryzyko_bez_warstw_jak_lifelines():
    okresy = _okresy()
    m = ModelCox(warstwy=(), interakcje_czasu={}).fit(okresy)
    X = m.macierz(okresy)
    # przy warstwach lifelines grupuje kolumny wyniku według warstwy, więc wyrównujemy po indeksie
    oczekiwane = 1 - m.cph_.predict_survival_function(X, times=[12.0])[X.index].to_numpy()[0]
    np.testing.assert_allclose(m.ryzyko(okresy), oczekiwane, rtol=1e-6)


def test_hr_odzyskane_i_interakcja_bliska_zeru():
    okresy = _okresy(n=6000, ziarno=1)
    m = ModelCox().fit(okresy)
    hr = m.hazard_ratio()
    assert hr.loc["b2b", "hr"] == pytest.approx(np.exp(0.8), rel=0.15)
    assert hr.loc["indeksacja_powyzej_6", "hr"] == pytest.approx(np.exp(0.4), rel=0.15)
    assert hr.loc["czynsz_m2_po_11.5", "hr_95_od"] < 1 < hr.loc["czynsz_m2_po_11.5", "hr_95_do"]
    r = m.ryzyko(okresy)
    assert ((r > 0) & (r < 1)).all()


def test_podzial_wierszy_przy_interakcji():
    okresy = _okresy(n=200)
    m = ModelCox(interakcje_czasu={"czynsz_m2": 11.5})
    m.mediany_ = pd.Series(0.0, index=list(CECHY))
    ramka = m._ramka(okresy)
    dluzsze = int((okresy["czas"] > 11.5).sum())
    assert len(ramka) == len(okresy) + dluzsze
    assert ramka["zdarzenie"].sum() == okresy["zdarzenie"].sum()
    pierwsze = ramka[ramka["start"] == 0]
    assert (pierwsze["czynsz_m2_po_11.5"] == 0).all() and (pierwsze["czas"] <= 11.5).all()


def test_cechy_bez_kolumn_zakazanych():
    with pytest.raises(ValueError):
        ModelCox(cechy=(*CECHY, "odejdzie"))
    assert "nr_okresu" not in CECHY and "windy_awarie_90d_na_winde" not in CECHY
