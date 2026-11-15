"""Cechy sąsiedztwa (sasiedztwo.sql): tylko wcześniejsze transakcje, okno 12 miesięcy, out-of-fold w treningu."""

import math

import duckdb
import numpy as np
import pandas as pd
import pytest
from api.adapters.duckdb_baza import polacz, zbuduj_baze
from api.ai.features.wycena.podzial import sql_podzialu
from api.ai.features.wycena.sasiedztwo import LICZBA_FOLDOW, LICZBA_SASIADOW, cechy_sasiedztwa

R = 6371008.8
M_NA_STOPIEN = R * math.pi / 180


def _fold(con, id_):
    return con.execute(f"SELECT md5_number('{id_}') % {LICZBA_FOLDOW}").fetchone()[0]


def _ids_w_foldzie(con, fold, n, prefiks):
    """n identyfikatorów z danym foldem (fold zależy od md5 id)."""
    wynik, i = [], 0
    while len(wynik) < n:
        id_ = f"{prefiks}{i}"
        if _fold(con, id_) == fold:
            wynik.append(id_)
        i += 1
    return wynik


def _con(wiersze):
    """wiersze: (id, data_aktu, data_publikacji, miasto, metry_na_polnoc, cena_m2)."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE rcn_transakcje (id_transakcji VARCHAR, data_aktu TIMESTAMP, data_publikacji_rejestru TIMESTAMP, "
        "miasto VARCHAR, lat DOUBLE, lon DOUBLE, cena_m2 BIGINT)"
    )
    con.executemany(
        "INSERT INTO rcn_transakcje VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(i, a, p, m, 52.0 + metry / M_NA_STOPIEN, 21.0, c) for i, a, p, m, metry, c in wiersze],
    )
    return con


def _wynik(con, **kw):
    return cechy_sasiedztwa(con, z_lista_sasiadow=True, **kw).set_index("id_transakcji")


# --- przypadki syntetyczne --------------------------------------------------------------------------------------


@pytest.fixture
def okno():
    """T w walidacji (2025-09-15); kandydaci wokół granic okna czasu."""
    return _con(
        [
            ("T", "2025-09-15", "2025-12-01", "A", 0, 10000),
            ("S_dzien_wczesniej", "2025-09-14", "2025-11-01", "A", 100, 11000),
            ("S_rowno_12_mies", "2024-09-15", "2024-12-01", "A", 200, 12000),
            ("S_12_mies_i_dzien", "2024-09-14", "2024-12-01", "A", 1, 99000),
            ("S_ten_sam_dzien", "2025-09-15", "2025-12-01", "A", 1, 99000),
            ("S_pozniej", "2025-09-20", "2025-12-01", "A", 1, 99000),
            ("S_inne_miasto", "2025-09-01", "2025-11-01", "B", 0, 99000),
        ]
    )


def test_sasiedzi_tylko_z_12_miesiecy_przed_dniem_aktu_bez_tego_samego_dnia_i_pozniejszych(okno):
    w = _wynik(okno).loc["T"]
    assert sorted(w["sasiedzi_id"]) == ["S_dzien_wczesniej", "S_rowno_12_mies"]
    assert w["sasiedzi_liczba"] == 2
    assert w["sasiedzi_mediana_ceny_m2"] == pytest.approx(11500)


def test_transakcja_bez_wczesniejszych_sasiadow_ma_null_i_liczbe_zero(okno):
    w = _wynik(okno).loc["S_12_mies_i_dzien"]  # najwcześniejsza w mieście A
    assert w["sasiedzi_liczba"] == 0
    assert pd.isna(w["sasiedzi_mediana_ceny_m2"])


def test_wybiera_20_najblizszych_a_remis_rozstrzyga_nowsza_transakcja():
    wiersze = [("T", "2025-10-01", "2025-12-15", "A", 0, 10000)]
    wiersze += [(f"S{i:02d}", "2025-08-01", "2025-10-15", "A", 10 * (i + 1), 10000 + i) for i in range(25)]
    # S18 leży 190 m od T; dwie kolejne transakcje w tej samej odległości: kolejność S00–S17, R_nowsza (09-01),
    # S18 (08-01), R_starsza (07-02) -> 20. miejsce zajmuje S18, R_starsza odpada
    wiersze += [
        ("R_nowsza", "2025-09-01", "2025-11-15", "A", 190, 50000),
        ("R_starsza", "2025-07-02", "2025-09-15", "A", 190, 1),
    ]
    w = _wynik(_con(wiersze)).loc["T"]
    assert w["sasiedzi_liczba"] == LICZBA_SASIADOW
    assert set(w["sasiedzi_id"]) == {f"S{i:02d}" for i in range(19)} | {"R_nowsza"}


def test_out_of_fold_w_treningu_a_pelna_pula_w_walidacji():
    con = duckdb.connect()
    t_tr = _ids_w_foldzie(con, 0, 1, "TR")[0]
    t_wal = _ids_w_foldzie(con, 0, 1, "WAL")[0]
    s_ten_sam = _ids_w_foldzie(con, 0, 1, "S")[0]
    s_inny = _ids_w_foldzie(con, 1, 1, "S")[0]
    con.close()
    con = _con(
        [
            (t_tr, "2025-06-15", "2025-08-15", "A", 0, 10000),  # trening
            (t_wal, "2025-08-01", "2025-10-01", "A", 0, 10000),  # walidacja
            (s_ten_sam, "2025-06-01", "2025-08-01", "A", 10, 11000),
            (s_inny, "2025-07-15", "2025-09-15", "A", 20, 12000),
        ]
    )
    w = _wynik(con)
    assert list(w.loc[t_tr, "sasiedzi_id"]) == []  # jedyny wcześniejszy sąsiad jest z tego samego foldu
    assert w.loc[t_tr, "sasiedzi_liczba"] == 0
    # w walidacji fold nie ma znaczenia: sąsiadami są wszystkie wcześniejsze, także transakcje treningowe
    assert sorted(w.loc[t_wal, "sasiedzi_id"]) == sorted([s_ten_sam, s_inny, t_tr])


def test_wariant_wg_publikacji_pomija_transakcje_nieopublikowane_w_dniu_aktu():
    con = _con(
        [
            ("T", "2025-10-01", "2025-12-15", "A", 0, 10000),
            ("S_opublikowana", "2025-06-01", "2025-08-15", "A", 50, 11000),
            ("S_nieopublikowana", "2025-09-01", "2025-11-15", "A", 10, 12000),
        ]
    )
    assert sorted(_wynik(con).loc["T", "sasiedzi_id"]) == ["S_nieopublikowana", "S_opublikowana"]
    assert list(_wynik(con, wg_publikacji=True).loc["T", "sasiedzi_id"]) == ["S_opublikowana"]
    # zmienna nie zostaje w sesji
    assert list(_wynik(con).loc["T", "sasiedzi_id"]) != ["S_opublikowana"]


# --- prawdziwe dane: 20 losowych transakcji ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def dane(tmp_path_factory):
    sciezka = tmp_path_factory.mktemp("baza") / "domilo.duckdb"
    zbuduj_baze(sciezka)
    con = polacz(sciezka)
    cechy = cechy_sasiedztwa(con, z_lista_sasiadow=True)
    pula = con.execute(
        "SELECT t.id_transakcji, t.miasto, t.lat, t.lon, t.data_aktu::DATE AS dzien, t.cena_m2, p.zbior, "
        f"(md5_number(t.id_transakcji) % {LICZBA_FOLDOW})::INTEGER AS fold "
        "FROM rcn_transakcje t JOIN (" + sql_podzialu() + ") p USING (id_transakcji)"
    ).df()
    con.close()
    return cechy.set_index("id_transakcji"), pula.set_index("id_transakcji")


@pytest.fixture(scope="module")
def losowe(dane):
    cechy, _ = dane
    return cechy.sample(20, random_state=20261115).index


def test_zaden_sasiad_20_losowych_transakcji_nie_ma_daty_rownej_ani_pozniejszej(dane, losowe):
    cechy, pula = dane
    for id_ in losowe:
        sasiedzi = list(cechy.loc[id_, "sasiedzi_id"])
        assert id_ not in sasiedzi
        dzien = pula.loc[id_, "dzien"]
        daty = pula.loc[sasiedzi, "dzien"]
        assert (daty < dzien).all(), f"{id_}: sąsiad z datą >= {dzien}"
        assert (daty >= dzien - pd.DateOffset(months=12)).all()
        if pula.loc[id_, "zbior"] == "trening":
            assert (pula.loc[sasiedzi, "fold"] != pula.loc[id_, "fold"]).all()


def test_sasiedzi_20_losowych_transakcji_to_20_najblizszych_z_dozwolonej_puli(dane, losowe):
    """Niezależne przeliczenie w numpy: ten sam zbiór sąsiadów i ta sama mediana ceny m²."""
    cechy, pula = dane
    for id_ in losowe:
        t = pula.loc[id_]
        kand = pula[
            (pula["miasto"] == t["miasto"])
            & (pula["dzien"] < t["dzien"])
            & (pula["dzien"] >= t["dzien"] - pd.DateOffset(months=12))
        ]
        if t["zbior"] == "trening":
            kand = kand[kand["fold"] != t["fold"]]
        f1, f2 = np.radians(t["lat"]), np.radians(kand["lat"])
        h = np.sin((f2 - f1) / 2) ** 2 + np.cos(f1) * np.cos(f2) * np.sin(np.radians(kand["lon"] - t["lon"]) / 2) ** 2
        kand = kand.assign(odl=2 * R * np.arcsin(np.sqrt(h)), id=kand.index)
        kand = kand.sort_values(["odl", "dzien", "id"], ascending=[True, False, True]).head(LICZBA_SASIADOW)
        assert set(cechy.loc[id_, "sasiedzi_id"]) == set(kand["id"]), id_
        assert cechy.loc[id_, "sasiedzi_liczba"] == len(kand)
        assert cechy.loc[id_, "sasiedzi_mediana_ceny_m2"] == pytest.approx(kand["cena_m2"].median())
