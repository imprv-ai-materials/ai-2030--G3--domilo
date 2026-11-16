"""Cotygodniowa lista retencyjna (retention_bc/lista_retencyjna.py), tabela lista_retencyjna, obecne wersje modeli
listy (churn_model/base.wczytaj_obecny) i funkcja Inngest lista-retencyjna."""

import shutil
from datetime import date

import duckdb
import pandas as pd
import pytest
import yaml
from api.adapters import lista_retencyjna as tabela
from api.adapters.duckdb_baza import SCIEZKA_BAZY, polacz
from api.ai.churn_model.base import SCIEZKA_CURRENT, wczytaj_obecny
from api.contexts_boundaries.retention_bc import lista_retencyjna as lr
from api.contexts_boundaries.retention_bc.ryzyko_najmu import ryzyko_najmu, ryzyko_okresow

DZIEN = "2026-11-16"  # poniedziałek; okno końca umów 2027-01-15 – 2027-01-21

# --- logika --------------------------------------------------------------------------------------------------------


def test_okno_to_60_do_66_dni_a_stan_danych_najpozniej_dzien_eksportu():
    assert lr.okno_konca(date(2026, 11, 16)) == (date(2027, 1, 15), date(2027, 1, 21))
    # kolejny poniedziałek zaczyna się dzień po końcu poprzedniego okna: każdy dzień końca umowy raz
    assert lr.okno_konca(date(2026, 11, 23))[0] == date(2027, 1, 22)
    assert lr.stan_danych_na(date(2026, 11, 16)) == date(2026, 9, 30)
    assert lr.stan_danych_na(date(2026, 3, 2)) == date(2026, 3, 2)


@pytest.mark.parametrize(
    "koniec, kampania",
    [
        (date(2026, 12, 1), "kampania_2026q4"),
        (date(2027, 1, 18), "kampania_2026q4"),
        (date(2027, 2, 28), "kampania_2026q4"),
        (date(2027, 3, 1), "kampania_2027q1"),
        (date(2026, 11, 30), "kampania_2026q3"),
    ],
)
def test_nazwa_kampanii_jak_w_planie_q4(koniec, kampania):
    assert lr.nazwa_kampanii(koniec) == kampania


def test_reszta_hasha_to_md5_number_z_duckdb_jak_w_preregistracji():
    ids = [f"U{i:06d}" for i in range(1, 400, 7)]
    con = duckdb.connect()
    z_duckdb = dict(
        con.execute(
            "SELECT id, (md5_number(id || ':kampania_2026q4') % 100)::INTEGER FROM unnest($ids) AS t(id)", {"ids": ids}
        ).fetchall()
    )
    assert {i: lr.reszta_hasha(i, "kampania_2026q4") for i in ids} == z_duckdb


def test_grupa_zalezy_tylko_od_umowy_i_kampanii_i_daje_okolo_20_procent_kontroli():
    ids = [f"U{i:06d}" for i in range(20_000)]
    grupy = [lr.grupa_kampanii(i, "kampania_2026q4") for i in ids]
    assert grupy == [lr.grupa_kampanii(i, "kampania_2026q4") for i in ids]
    udzial = grupy.count("kontrola") / len(ids)
    assert 0.19 < udzial < 0.21
    inna = [lr.grupa_kampanii(i, "kampania_2027q1") for i in ids]
    assert inna != grupy  # inna kampania = nowe losowanie


# --- obecne wersje (current.yaml) ----------------------------------------------------------------------------------


def test_obecny_to_v2_dla_ryzyka_i_v3_dla_upliftu_z_current_yaml():
    obecny = wczytaj_obecny()
    assert (obecny.wersja_ryzyka, obecny.wersja_upliftu) == ("v2_przezycie_cox", "v3_uplift_tlearner")
    assert type(obecny.ryzyko).__name__ == "ModelCox" and type(obecny.uplift).__name__ == "ModelUpliftT"


def test_pusty_current_albo_zla_klasa_to_blad(tmp_path):
    pusty = tmp_path / "pusty.yaml"
    pusty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="brak części"):
        wczytaj_obecny(pusty)
    current = yaml.safe_load(SCIEZKA_CURRENT.read_text(encoding="utf-8"))
    current["uplift"]["klasa"] = "api.ai.churn_model.versions.v1_ryzyko.model.ModelRyzyko"
    zly = tmp_path / "zly.yaml"
    zly.write_text(yaml.safe_dump(current, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="klasa"):
        wczytaj_obecny(zly)


# --- tabela ---------------------------------------------------------------------------------------------------------


def _wiersz(id_umowy="U1", dzien=date(2026, 11, 16), **zmiany) -> dict:
    return {
        "data_listy": dzien, "id_umowy": id_umowy, "id_najmu": "N1", "id_najemcy": "T1", "linia": "B2C",
        "data_do": date(2027, 1, 15), "dni_do_konca": 60, "stan_danych_na": date(2026, 9, 30),
        "data_decyzji": date(2026, 9, 30), "wypowiedzenie_zlozone": False, "ryzyko": 0.3,
        "ryzyko_12_od_poczatku_okresu": 0.3, "przezycie_12_mies": 0.6, "mediana_do_odejscia_mies": None,
        "rmst60_mies": 30.0, "p_przedluzy_z_oferta": 0.7, "p_przedluzy_bez_oferty": 0.6, "uplift": 0.1,
        "ev_pln": -500.0, "poza_zakresem_modelu": [], "akcja": "bez rabatu", "uzasadnienie": "x.",
        "kampania": "kampania_2026q4", "reszta_hasha": 50, "grupa": "polityka", "wyslac_oferte": False,
        "wersja_modelu_ryzyka": "v2", "wersja_modelu_upliftu": "v3", "id_przebiegu": "p1",
    } | zmiany  # fmt: skip


def test_zapis_zastepuje_caly_dzien_listy_i_pilnuje_oferty_tylko_dla_polityki_z_rabatem(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    d = date(2026, 11, 16)
    assert tabela.zapisz(con, d, pd.DataFrame([_wiersz("U1"), _wiersz("U2")])) == 2
    assert tabela.zapisz(con, d, pd.DataFrame([_wiersz("U3")])) == 1
    assert list(tabela.wczytaj(con, d)["id_umowy"]) == ["U3"]
    with pytest.raises(duckdb.ConstraintException):
        tabela.zapisz(con, d, pd.DataFrame([_wiersz("U4", grupa="kontrola", akcja="rabat", wyslac_oferte=True)]))
    assert list(tabela.wczytaj(con, d)["id_umowy"]) == ["U3"]  # błąd = wycofanie całego dnia


def test_wczytaj_bez_tabeli_zwraca_pusta_liste(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    assert tabela.wczytaj(con, date(2026, 11, 16)).empty


# --- spójność z GET /risk ------------------------------------------------------------------------------------------


def test_ryzyko_wsadowe_to_samo_co_endpoint_risk():
    obecny = wczytaj_obecny()
    with polacz() as con:
        umowy = lr.umowy_w_oknie(con, date.fromisoformat(DZIEN), date(2026, 9, 30))
        wsad = ryzyko_okresow(con, umowy.head(3), obecny.ryzyko, date(2026, 9, 30)).set_index("id_umowy")
        for _, u in umowy.head(3).iterrows():
            odp = ryzyko_najmu(con, u["id_najmu"], obecny.ryzyko, date(2026, 9, 30))
            w = wsad.loc[odp["okres"]["id_umowy"]]
            assert w["ryzyko"] == pytest.approx(odp["p_konca_w_biezacym_okresie"])
            assert w["rmst60_mies"] == pytest.approx(odp["rmst60_mies"])
            assert w["przezycie_12_mies"] == pytest.approx(odp["przezycie_12_mies"])


# --- Inngest ---------------------------------------------------------------------------------------------------------


def test_funkcja_inngest_listy_w_poniedzialek_rano_i_na_zdarzenie():
    from api import inngest_app

    [fn] = [f for f in inngest_app.FUNKCJE if f.local_id == "lista-retencyjna"]
    wyzwalacze = [t.model_dump(exclude_none=True) for t in fn.get_config("http://app:8101/api/inngest").main.triggers]
    assert {"cron": "TZ=Europe/Warsaw 0 7 * * 1"} in wyzwalacze
    assert {"event": "domilo/lista.retencyjna"} in wyzwalacze
    assert inngest_app.parametry_listy_ze_zdarzenia({"data_listy": DZIEN, "kampania": "k"}) == (DZIEN, "k")
    assert inngest_app.parametry_listy_ze_zdarzenia({"cron": "x"}) == (None, None)


# --- dwa pełne przebiegi na kopii bazy -----------------------------------------------------------------------------


def _wprost(id_kroku, handler, *args):
    return handler(*args)


@pytest.fixture(scope="module")
def dwa_przebiegi(tmp_path_factory):
    katalog = tmp_path_factory.mktemp("lista")
    baza = katalog / "baza.duckdb"
    shutil.copyfile(SCIEZKA_BAZY, baza)
    wyniki, tabele = [], []
    for n in (1, 2):
        wyniki.append(
            lr.wykonaj_liste_retencyjna(
                _wprost, f"test-{n}", DZIEN, sciezka=baza, katalog_bazowy=katalog, katalog_panelu=katalog / "panel"
            )
        )
        with polacz(baza) as con:
            tabele.append(tabela.wczytaj(con, date.fromisoformat(DZIEN)))
    return wyniki, tabele


def test_dwa_przebiegi_daja_te_same_grupy_i_te_same_wiersze(dwa_przebiegi):
    wyniki, (t1, t2) = dwa_przebiegi
    assert len(t1) == wyniki[0]["umowy"]["umowy"] > 0
    assert set(t1["id_przebiegu"]) == {"test-1"} and set(t2["id_przebiegu"]) == {"test-2"}
    klucz = ["id_umowy", "kampania", "reszta_hasha", "grupa", "wyslac_oferte"]
    pd.testing.assert_frame_equal(t1[klucz], t2[klucz])
    pd.testing.assert_frame_equal(t1.drop(columns="id_przebiegu"), t2.drop(columns="id_przebiegu"))


def test_lista_ma_okno_60_66_dni_grupy_z_hasha_i_oferte_tylko_w_polityce(dwa_przebiegi):
    _, (t, _) = dwa_przebiegi
    assert t["dni_do_konca"].between(60, 66).all()
    assert set(t["kampania"]) == {"kampania_2026q4"}
    assert all(lr.grupa_kampanii(i, k) == g for i, k, g in zip(t["id_umowy"], t["kampania"], t["grupa"]))
    assert not t.loc[t["grupa"] == "kontrola", "wyslac_oferte"].any()
    assert (t["wyslac_oferte"] == ((t["grupa"] == "polityka") & (t["akcja"] == "rabat"))).all()
    assert t["ryzyko"].between(0, 1).all() and t["rmst60_mies"].between(0, 60).all()


def test_przebieg_odswieza_panel_kampanii_najnowsza_lista(dwa_przebiegi):
    wyniki, (t, _) = dwa_przebiegi
    panel = wyniki[1]["panel"]
    assert panel["wiersze"]["lista_tydzien"] == len(t)
    lista = pd.read_parquet(f"{panel['katalog']}/lista_tydzien.parquet")
    assert sorted(lista["id_umowy"]) == sorted(t["id_umowy"])
