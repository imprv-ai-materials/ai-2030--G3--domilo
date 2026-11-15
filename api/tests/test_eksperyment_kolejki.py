"""Eksperyment switchback kolejki: obliczenia mocy (data_platform/eksperyment_kolejki.py), plan tygodni i część losowa
kolejki (leasing_bc/eksperyment.py, kolejka_dzienna.ranking_kolejki), tabela kolejka_historia."""

import shutil
from datetime import date

import numpy as np
import pandas as pd
import pytest
from api.adapters.duckdb_baza import SCIEZKA_BAZY, polacz
from api.contexts_boundaries.leasing_bc import eksperyment as e
from api.contexts_boundaries.leasing_bc import kolejka_dzienna as kd
from api.data_platform import eksperyment_kolejki as ek

# --- moc i MDE -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("n", [12, 16, 30])
def test_mde_daje_moc_80_procent(n):
    cv = 0.187
    d = ek.mde(cv, n)
    assert ek.moc_testu(d / cv, n) == pytest.approx(0.80, abs=1e-6)


def test_mde_maleje_z_liczba_tygodni_i_jest_wieksze_niz_przyblizenie_normalne():
    m = [ek.mde(0.187, n) for n in (8, 12, 16, 24)]
    assert m == sorted(m, reverse=True)
    assert ek.mde(0.187, 12) > ek.mde_normalne(0.187, 12)  # t z małą liczbą stopni swobody
    assert ek.mde(0.187, 2000) == pytest.approx(ek.mde_normalne(0.187, 2000), rel=0.01)


def test_zmienne_korekty_zabieraja_stopnie_swobody():
    assert ek.mde(0.15, 12, k=2) > ek.mde(0.15, 12, k=0)


def test_tygodnie_dla_efektu_to_najmniejsza_parzysta_liczba_z_moca_80():
    n = ek.tygodnie_dla(0.15, 0.172, k=2)
    assert n % 2 == 0
    assert ek.moc_testu(0.15 / 0.172, n, 2) >= 0.8 > ek.moc_testu(0.15 / 0.172, n - 2, 2)
    # połowa efektu dociera do metryki -> potrzeba więcej tygodni
    assert ek.tygodnie_dla(0.15, 0.172, 2, tlumienie=lambda n: 0.5) > n


def test_cv_loo_nie_zanizane_przez_dopasowanie():
    rng = np.random.default_rng(0)
    x = rng.normal(size=50)
    szum = 100 + rng.normal(size=50)
    assert ek.cv_loo(szum, [x]) >= ek.cv_surowe(szum) * 0.95  # zmienna bez związku nie pomaga
    zalezne = 100 + 5 * x + 0.1 * rng.normal(size=50)
    assert ek.cv_loo(zalezne, [x]) < 0.2 * ek.cv_surowe(zalezne)


def test_tlumienie_podpisan():
    assert ek.tlumienie_podpisan(np.array([1.0]), 12, powtorzen=500) == pytest.approx(1.0)
    # połowa wartości z tego tygodnia, połowa z poprzedniego: w parach poprzedni tydzień to w połowie przypadków drugi
    # wariant, więc mierzymy 0,5 − 0,5 × 0,5 = 0,25 efektu
    assert ek.tlumienie_podpisan(np.array([0.5, 0.5]), 16, powtorzen=4000) == pytest.approx(0.25, abs=0.02)


def test_analiza_odzyskuje_znany_efekt():
    rng = np.random.default_rng(1)
    n = 40
    wariant = np.where(ek.plan_par(n, rng) == 1, "model", "od_najnowszego")
    godziny = rng.normal(390, 50, n)
    zapytania = rng.normal(1700, 100, n)
    y = 1000 + 300 * (wariant == "model") + 5 * godziny + 0.5 * zapytania + rng.normal(0, 50, n)
    df = pd.DataFrame({"wariant": wariant, "y": y, "godziny_doradcow": godziny, "nowe_zapytania_2tyg": zapytania})
    w = ek.analiza(df, "y")
    assert w["przedzial_95"][0] < 300 < w["przedzial_95"][1] and w["p"] < 0.001 and w["tygodnie_model"] == 20


# --- plan tygodni --------------------------------------------------------------------------------------------------


def test_plan_w_parach_z_losowa_kolejnoscia_i_stalym_ziarnem():
    p = e.wylosuj_plan(date(2027, 1, 4), 16, ziarno=7)
    assert len(p["plan"]) == 16
    for para in range(1, 9):
        assert sorted(x["wariant"] for x in p["plan"] if x["para"] == para) == ["model", "od_najnowszego"]
    assert [x["wariant"] for x in p["plan"]] == [x["wariant"] for x in e.wylosuj_plan(date(2027, 1, 4), 16, 7)["plan"]]
    pierwsze = {tuple(x["wariant"] for x in e.wylosuj_plan(date(2027, 1, 4), 16, z)["plan"][:2]) for z in range(20)}
    assert len(pierwsze) == 2  # kolejność w parze naprawdę losowa
    with pytest.raises(ValueError):
        e.wylosuj_plan(date(2027, 1, 5), 16, 7)  # wtorek
    with pytest.raises(ValueError):
        e.wylosuj_plan(date(2027, 1, 4), 15, 7)


def test_wariant_dnia_z_planu_a_poza_planem_model(tmp_path):
    p = e.wylosuj_plan(date(2027, 1, 4), 4, ziarno=3)
    drugi = p["plan"][1]
    assert e.wariant_dnia(date(2027, 1, 13), p) == drugi["wariant"]  # środa drugiego tygodnia
    assert e.wariant_dnia(date(2027, 3, 1), p) == "model"
    assert e.wariant_dnia(date(2027, 1, 13), None) == "model"
    sciezka = tmp_path / "plan.yaml"
    e.zapisz_plan(p, sciezka)
    assert e.wczytaj_plan(sciezka)["plan"] == p["plan"]
    with pytest.raises(FileExistsError):
        e.zapisz_plan(p, sciezka)


# --- część losowa kolejki ------------------------------------------------------------------------------------------


def _miasto(n=200):
    rng = np.random.default_rng(5)
    return pd.DataFrame(
        {
            "id_leada": [f"L{i:04d}" for i in range(n)],
            "miasto": "Kraków",
            "ev": rng.uniform(1000, 50000, n).round(2),
            "utworzono": pd.date_range("2026-09-01", periods=n, freq="h", tz="Europe/Warsaw"),
        }
    )


DORADCY = pd.DataFrame({"id_doradcy": ["D04", "D09"], "miasto": ["Kraków", "Kraków"]})


def test_piec_procent_pozycji_losowych_na_losowych_miejscach_i_stale_ziarno():
    ev = _miasto()
    r = kd.ranking_kolejki(ev, DORADCY, ziarno_dnia="2026-11-17")
    k = r[r["id_doradcy"].notna()]
    assert len(k) == 80 and k.groupby("id_doradcy")["losowa"].sum().tolist() == [2, 2]
    assert r["p_losowania"].unique().tolist() == [4 / 200] and (r["pula_losowania"] == 200).all()
    assert r.equals(kd.ranking_kolejki(ev, DORADCY, ziarno_dnia="2026-11-17"))  # ten sam dzień = ta sama kolejka
    inny = kd.ranking_kolejki(ev, DORADCY, ziarno_dnia="2026-11-18")
    assert set(r.loc[r["losowa"], "id_leada"]) != set(inny.loc[inny["losowa"], "id_leada"])
    # nielosowe pozycje: 76 najlepszych według EV (bez wylosowanych), u każdego doradcy EV maleje z pozycją
    nielosowe = k[~k["losowa"]].merge(ev[["id_leada", "ev"]], on="id_leada")
    porzadek = ev.sort_values("ev", ascending=False)["id_leada"]
    assert set(nielosowe["id_leada"]) == set([x for x in porzadek if x not in set(k.loc[k["losowa"], "id_leada"])][:76])
    for _, g in nielosowe.groupby("id_doradcy"):
        assert g.sort_values("pozycja")["ev"].is_monotonic_decreasing


def test_wariant_od_najnowszego_zmienia_kolejke_ale_nie_range():
    ev = _miasto()
    m = kd.ranking_kolejki(ev, DORADCY, wariant="model", ziarno_dnia="d").set_index("id_leada")
    n = kd.ranking_kolejki(ev, DORADCY, wariant="od_najnowszego", ziarno_dnia="d").set_index("id_leada")
    assert m["ranga"].equals(n.loc[m.index, "ranga"])  # górny decyl ten sam w obu wariantach
    k = n[n["id_doradcy"].notna() & ~n["losowa"]].reset_index()
    pierwsze = k[k["pozycja"] == 1]["id_leada"]
    najnowsze = ev.sort_values("utworzono", ascending=False)["id_leada"].head(4)
    assert set(pierwsze) <= set(najnowsze)
    assert (n["wariant"] == "od_najnowszego").all()
    with pytest.raises(ValueError):
        kd.ranking_kolejki(ev, DORADCY, wariant="losowo")


def test_krotka_kolejka_bez_pozycji_losowych():
    ev = _miasto(10)  # po 5 pozycji na doradcę: 5% × 5 = 0,25 -> 0
    r = kd.ranking_kolejki(ev, DORADCY, ziarno_dnia="d")
    assert not r["losowa"].any() and r["p_losowania"].eq(0).all()


# --- zadanie w wariancie z planu zapisuje kolejka_historia ---------------------------------------------------------


def test_zadanie_zapisuje_historie_z_wariantem_i_pozycjami_losowymi(tmp_path):
    sciezka = tmp_path / "domilo.duckdb"
    shutil.copyfile(SCIEZKA_BAZY, sciezka)
    dzien = "2026-05-20"
    plan = e.wylosuj_plan(e.poniedzialek(date.fromisoformat(dzien)), 2, ziarno=1)
    wariant = e.wariant_dnia(date.fromisoformat(dzien), plan)

    class Lejek:
        def wyslij_kolejke(self, pozycje):
            return {"utworzono": len(list(pozycje)), "powtorzenia": 0}

    w = kd.wykonaj_kolejke_doradcow(
        lambda i, h, *a: h(*a), "t", dzien, sciezka=sciezka, katalog_bazowy=tmp_path, klient_lejka=Lejek(),
        z_llm=False, plan=plan,
    )  # fmt: skip
    assert w["kolejki"]["wariant"] == wariant and w["kolejki"]["pozycje_losowe"] == 22  # 11 doradców × 2
    con = polacz(sciezka)
    h = con.execute("SELECT * FROM kolejka_historia WHERE data_kolejki = ?", [dzien]).df()
    k = con.execute("SELECT id_leada, id_doradcy, pozycja FROM kolejka_doradcow WHERE data_kolejki = ?", [dzien]).df()
    con.close()
    assert len(h) == w["zapis"]["historia"] == len(k) == 440
    assert set(h["wariant"]) == {wariant} and h["losowa"].sum() == 22
    assert (h.groupby("miasto")["p_losowania"].nunique() == 1).all()
    pd.testing.assert_frame_equal(
        h[["id_leada", "id_doradcy", "pozycja"]].sort_values("id_leada").reset_index(drop=True),
        k.sort_values("id_leada").reset_index(drop=True),
        check_dtype=False,
    )
