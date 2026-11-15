"""Detektor danych spoza zakresu dla wyceny (versions/v3_przedzialy/ood.py, docs/b1_ood.md)."""

import numpy as np
import pandas as pd
import pytest
from api.ai.valuation_model.versions.v3_przedzialy.ood import (
    KOD_DZIELNICA,
    KOD_IF,
    KOD_KNN,
    KOD_METRAZ,
    KOD_MIASTO,
    KOD_ROK,
    KOD_TYP,
    DetektorOOD,
)

KOLUMNY = ("a", "b", "c")


def _trening(n=2000, seed=0):
    """Dwa miasta (A: 1 500, B: 400), dzielnica A|rzadka ma 50 transakcji; trzy cechy liczbowe ~ N(0, 1)."""
    rng = np.random.default_rng(seed)
    miasto = np.array(["A"] * 1500 + ["B"] * 400 + ["A"] * 100)
    dzielnica = np.array(["a1"] * 1500 + ["b1"] * 400 + ["rzadka"] * 50 + ["a1"] * 50)
    pokoje = rng.choice([1, 2, 3], n, p=[0.4, 0.4, 0.2])
    metraz = 15 * pokoje + 10 + rng.uniform(0, 10, n)  # 1 pok.: 25–35, 2: 40–50, 3: 55–65 m²
    return pd.DataFrame(
        {
            "miasto": miasto,
            "dzielnica": dzielnica,
            "metraz": metraz,
            "pokoje": pokoje,
            "rok_budowy": rng.integers(1960, 2021, n),
            "a": rng.normal(size=n),
            "b": rng.normal(size=n),
            "c": rng.normal(size=n),
        }
    )


def _lokal(**zmiany):
    wiersz = {"miasto": "A", "dzielnica": "a1", "metraz": 45.0, "pokoje": 2, "rok_budowy": 1990,
              "a": 0.0, "b": 0.0, "c": 0.0}  # fmt: skip
    wiersz.update(zmiany)
    return pd.DataFrame([wiersz])


@pytest.fixture(scope="module")
def detektor():
    return DetektorOOD(kolumny=KOLUMNY, n_drzew=100).fit(_trening())


def test_typowy_lokal_jest_przyjety_bez_powodow(detektor):
    wynik = detektor.ocen(_lokal())
    assert not wynik["odmowa"].iloc[0]
    assert wynik["powody"].iloc[0] == ""
    assert wynik["kody"].iloc[0] == []


def test_nieznane_miasto_to_odmowa_z_powodem_slowami(detektor):
    wynik = detektor.ocen(_lokal(miasto="Katowice", dzielnica="Bogucice"))
    assert wynik["odmowa"].iloc[0]
    assert KOD_MIASTO in wynik["kody"].iloc[0]
    assert "Katowice" in wynik["powody"].iloc[0]
    assert "0 transakcji" in wynik["powody"].iloc[0]
    # dzielnica nieznana też jest powodem, ale miasto wystarcza
    assert KOD_DZIELNICA in wynik["kody"].iloc[0]


def test_dzielnica_z_mniej_niz_80_transakcjami_to_odmowa(detektor):
    wynik = detektor.ocen(_lokal(dzielnica="rzadka"))
    assert wynik["kody"].iloc[0] == [KOD_DZIELNICA]
    assert "50 transakcji" in wynik["powody"].iloc[0]
    assert "rzadka" in wynik["powody"].iloc[0]


def test_dzielnica_jest_rozrozniana_w_ramach_miasta(detektor):
    # b1 istnieje tylko w mieście B; w mieście A to nieznana dzielnica
    assert KOD_DZIELNICA in detektor.ocen(_lokal(dzielnica="b1"))["kody"].iloc[0]
    assert KOD_DZIELNICA not in detektor.ocen(_lokal(miasto="B", dzielnica="b1"))["kody"].iloc[0]


def test_metraz_i_rok_poza_zakresem_p0_5_p99_5(detektor):
    tr = _trening()
    lo, hi = np.quantile(tr["metraz"], [0.005, 0.995])
    assert detektor.zakresy_["metraz"] == pytest.approx((lo, hi))
    wynik = detektor.ocen(_lokal(metraz=hi + 5, pokoje=3))
    assert KOD_METRAZ in wynik["kody"].iloc[0]
    assert "m²" in wynik["powody"].iloc[0]
    wynik = detektor.ocen(_lokal(rok_budowy=1850))
    assert KOD_ROK in wynik["kody"].iloc[0]
    assert "1850" in wynik["powody"].iloc[0]


def test_brak_roku_budowy_to_powod(detektor):
    wynik = detektor.ocen(_lokal(rok_budowy=np.nan))
    assert KOD_ROK in wynik["kody"].iloc[0]
    assert "brak roku budowy" in wynik["powody"].iloc[0].lower()


def test_nietypowy_typ_lokalu_liczba_pokoi_rzadka_albo_metraz_niepasujacy_do_pokoi(detektor):
    # 5 pokoi: 0 transakcji w treningu
    wynik = detektor.ocen(_lokal(pokoje=5))
    assert KOD_TYP in wynik["kody"].iloc[0]
    # 1 pokój i 60 m²: metraż w zakresie ogólnym, ale nie dla 1-pokojowych (25–35 m²)
    wynik = detektor.ocen(_lokal(pokoje=1, metraz=60.0))
    assert wynik["kody"].iloc[0][0] == KOD_TYP or KOD_TYP in wynik["kody"].iloc[0]
    assert KOD_METRAZ not in wynik["kody"].iloc[0]
    assert "1-pokojow" in wynik["powody"].iloc[0]


def test_daleko_w_przestrzeni_cech_to_odmowa_knn_z_nazwa_odstajacej_cechy(detektor):
    wynik = detektor.ocen(_lokal(a=8.0))
    assert KOD_KNN in wynik["kody"].iloc[0]
    assert "a" in wynik["powody"].iloc[0]
    assert wynik["odl_knn"].iloc[0] > detektor.prog_knn_


def test_progi_domyslne_odrzucaja_okolo_1_proc_treningu_w_knn_i_isolation_forest(detektor):
    tr = _trening()
    w = detektor.wyniki(tr, bez_siebie=True)  # punkt treningu nie jest swoim sąsiadem
    assert np.mean(w["odl_knn"] > detektor.prog_knn_) == pytest.approx(0.01, abs=0.003)
    assert np.mean(w["wynik_if"] > detektor.prog_if_) == pytest.approx(0.01, abs=0.003)


def test_isolation_forest_wylapuje_skrajny_punkt(detektor):
    wynik = detektor.ocen(_lokal(a=6.0, b=-6.0, c=6.0))
    assert KOD_IF in wynik["kody"].iloc[0]
    assert "Isolation Forest" in wynik["powody"].iloc[0]


def test_odleglosc_knn_w_treningu_nie_liczy_samego_siebie(detektor):
    tr = _trening()
    assert (detektor.wyniki(tr.head(5), bez_siebie=True)["odl_knn"] > 0).all()


def test_braki_w_cechach_przestrzeni_sa_uzupelniane_wartosciami_z_treningu(detektor):
    wynik = detektor.wyniki(_lokal(a=np.nan))
    assert np.isfinite(wynik["odl_knn"]).all() and np.isfinite(wynik["wynik_if"]).all()


def test_wlasne_progi_zmieniaja_decyzje(detektor):
    lokal = _lokal(a=8.0)
    d = detektor.wyniki(lokal)["odl_knn"].iloc[0]
    assert not detektor.ocen(lokal, prog_knn=d + 1, prog_if=np.inf)["odmowa"].iloc[0]


def test_brak_kolumny_to_czytelny_blad(detektor):
    with pytest.raises(ValueError, match="rok_budowy"):
        detektor.ocen(_lokal().drop(columns=["rok_budowy"]))


def test_wiele_powodow_laczonych_srednikiem(detektor):
    wynik = detektor.ocen(_lokal(miasto="Z", dzielnica="z", rok_budowy=1700, a=9.0))
    powody = wynik["powody"].iloc[0].split("; ")
    assert len(powody) == len(wynik["kody"].iloc[0]) >= 3
