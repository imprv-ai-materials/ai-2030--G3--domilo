"""Historia wycen w domilo.duckdb (adapters/wyceny_historia.py) i jej przetrwanie przy przebudowie bazy."""

import math
from datetime import date, datetime, timezone

import duckdb
import pandas as pd
import pytest
from api.adapters import wyceny_historia as h
from api.adapters.duckdb_baza import polacz, zbuduj_baze

CZAS_1 = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
CZAS_2 = datetime(2026, 11, 15, 1, 0, tzinfo=timezone.utc)


def _wyceny(**zmiany) -> pd.DataFrame:
    w = {
        "id_obiektu": "B01-0001",
        "miasto": "Warszawa",
        "dzielnica": "Wola",
        "metraz": 48.0,
        "dzien_wyceny": date(2026, 11, 15),
        "p10": 450_000.0,
        "p50": 500_000.0,
        "p90": 560_000.0,
        "odmowa": False,
        "powod": "",
        "cena_ofertowa": None,
        "wartosc_bazowa": 520_000.0,
        "czynniki": {"metraz": -30_000.0, "dzielnica": 10_000.0},
    }
    w.update(zmiany)
    return pd.DataFrame([w])


@pytest.fixture
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "h.duckdb"))
    yield c
    c.close()


def test_bez_tabeli_odczyty_sa_puste_a_nie_bledem(con):
    assert h.ostatnie(con).empty
    assert h.odmowy(con).empty
    assert h.karta(con, "lokal", "B01-0001") is None


def test_zapis_i_odczyt_ostatniej_wyceny_z_czynnikami(con):
    h.zapisz(con, "run-1", CZAS_1, "v4_llm_cechy", "lokal", _wyceny())
    w = h.ostatnie(con, "lokal").iloc[0]
    assert (w["id_obiektu"], w["p50"], w["wersja_modelu"]) == ("B01-0001", 500_000.0, "v4_llm_cechy")
    assert w["czynniki"] == {"metraz": -30_000.0, "dzielnica": 10_000.0}


def test_ponowny_zapis_tego_samego_przebiegu_nie_dubluje_wierszy(con):
    h.zapisz(con, "run-1", CZAS_1, "v4", "lokal", _wyceny(p50=1.0))
    h.zapisz(con, "run-1", CZAS_1, "v4", "lokal", _wyceny(p50=2.0))
    assert con.execute("SELECT count(*), max(p50) FROM wyceny_historia").fetchone() == (1, 2.0)


def test_ostatnie_bierze_najnowszy_przebieg_dla_kazdego_obiektu(con):
    h.zapisz(con, "run-1", CZAS_1, "v4", "lokal", _wyceny(p50=1.0))
    h.zapisz(con, "run-2", CZAS_2, "v4", "lokal", _wyceny(p50=2.0))
    assert h.ostatnie(con)["p50"].tolist() == [2.0]


def test_odmowy_to_obiekty_z_odmowa_w_ostatniej_wycenie(con):
    h.zapisz(con, "run-1", CZAS_1, "v4", "lokal", _wyceny(id_obiektu="A", odmowa=True, powod="Miasto Katowice"))
    run_2 = pd.concat([_wyceny(id_obiektu="A"), _wyceny(id_obiektu="B", odmowa=True, powod="Metraż 9 m²")])
    h.zapisz(con, "run-2", CZAS_2, "v4", "lokal", run_2)
    o = h.odmowy(con)
    assert o["id_obiektu"].tolist() == ["B"] and o["powod"].tolist() == ["Metraż 9 m²"]


def test_oferty_ponizej_p10_bez_odmow_posortowane_od_najwiekszego_rabatu(con):
    oferty = pd.concat(
        [
            _wyceny(id_obiektu="O1", cena_ofertowa=440_000.0),  # 0,978 × P10
            _wyceny(id_obiektu="O2", cena_ofertowa=400_000.0),  # 0,889 × P10
            _wyceny(id_obiektu="O3", cena_ofertowa=460_000.0),  # powyżej P10
            _wyceny(id_obiektu="O4", cena_ofertowa=100_000.0, odmowa=True, p10=math.nan),
        ],
        ignore_index=True,
    )
    h.zapisz(con, "run-1", CZAS_1, "v4", "oferta", oferty)
    assert h.oferty_ponizej_p10(con)["id_obiektu"].tolist() == ["O2", "O1"]


def test_karta_ma_ostatnia_wycene_i_historie_p50(con):
    h.zapisz(con, "run-1", CZAS_1, "v4", "lokal", _wyceny(p50=1.0))
    h.zapisz(con, "run-2", CZAS_2, "v4", "lokal", _wyceny(p50=2.0))
    k = h.karta(con, "lokal", "B01-0001")
    assert k["p50"] == 2.0
    assert [p["p50"] for p in k["historia"]] == [1.0, 2.0]


def test_wycenione_oferty(con):
    h.zapisz(con, "run-1", CZAS_1, "v4", "oferta", _wyceny(id_obiektu="O1", cena_ofertowa=1.0))
    assert h.wycenione(con, "oferta") == {"O1"}


def test_historia_przetrwa_przebudowe_bazy(tmp_path):
    baza = tmp_path / "domilo.duckdb"
    zbuduj_baze(baza)
    c = polacz(baza, tylko_odczyt=False)
    h.zapisz(c, "run-1", CZAS_1, "v4", "lokal", _wyceny())
    c.close()

    zbuduj_baze(baza)

    c = polacz(baza)
    assert c.execute("SELECT count(*) FROM wyceny_historia").fetchone() == (1,)
    assert h.ostatnie(c)["czynniki"].iloc[0] == {"metraz": -30_000.0, "dzielnica": 10_000.0}
    c.close()


def test_wycenione_poza_biezacym_przebiegiem_pozwalaja_ponowic_krok_bez_utraty_ofert(con):
    # Ponowiony krok tego samego przebiegu musi znowu zobaczyć swoje oferty jako nowe, inaczej zapis by je skasował.
    h.zapisz(con, "run-1", CZAS_1, "v4", "oferta", _wyceny(id_obiektu="O1", cena_ofertowa=1.0))
    h.zapisz(con, "run-2", CZAS_2, "v4", "oferta", _wyceny(id_obiektu="O2", cena_ofertowa=1.0))
    assert h.wycenione(con, "oferta", poza_przebiegiem="run-2") == {"O1"}
