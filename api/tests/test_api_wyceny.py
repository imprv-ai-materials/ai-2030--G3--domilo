"""API wyceny (main.py): POST /valuation i odczyty dla panelu rzeczoznawcy. Prawdziwy model i domilo.duckdb."""

from datetime import date, datetime, timezone

import pandas as pd
import pytest
import yaml
from api.adapters import wyceny_historia as h
from api.adapters.llm_client import BrakKluczaAPI
from api.ai.valuation_model.obecny import SCIEZKA_CURRENT
from api.main import app, baza, ekstraktor_cech_opisu
from fastapi.testclient import TestClient

LOKAL = {
    "miasto": "Warszawa",
    "dzielnica": "Wola",
    "lat": 52.2341,
    "lon": 20.9664,
    "metraz": 48.0,
    "pokoje": 2,
    "pietro": 3,
    "rok_budowy": 2018,
    "dzien_wyceny": "2026-11-15",
}
CECHY_Z_OPISU = {
    "llm_standard": 4.0,
    "llm_ekspozycja": "poludnie",
    "llm_widok": "brak_info",
    "llm_balkon": "tak",
    "llm_stan_budynku": "brak_info",
}


class Ekstraktor:
    def __init__(self, wynik=CECHY_Z_OPISU, blad: Exception | None = None):
        self.wynik, self.blad, self.opisy = wynik, blad, []

    def __call__(self, opis: str) -> dict:
        self.opisy.append(opis)
        if self.blad:
            raise self.blad
        return self.wynik


@pytest.fixture
def klient():
    ekstraktor = Ekstraktor()
    app.dependency_overrides[ekstraktor_cech_opisu] = lambda: ekstraktor
    yield TestClient(app), ekstraktor
    app.dependency_overrides.clear()


# --- walidacja wejścia ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "zmiana",
    [
        {"metraz": -5},
        {"pokoje": 0},
        {"lat": 10.0},
        {"lon": 99.0},
        {"miasto": ""},
        {"cena": 650_000},  # nieznane pole: wycena nie przyjmuje ceny
        {"dzien_wyceny": "2999-01-01"},  # dzień w przyszłości
    ],
)
def test_bledne_wejscie_to_422(klient, zmiana):
    c, _ = klient
    assert c.post("/valuation", json={**LOKAL, **zmiana}).status_code == 422


def test_brak_wymaganego_pola_to_422(klient):
    c, _ = klient
    assert c.post("/valuation", json={k: v for k, v in LOKAL.items() if k != "metraz"}).status_code == 422


# --- wycena ----------------------------------------------------------------------------------------------------------


def test_wycena_ma_wartosc_w_przedziale_trzy_czynniki_w_pln_i_wersje_z_current_yaml(klient):
    c, ekstraktor = klient
    r = c.post("/valuation", json=LOKAL)
    assert r.status_code == 200
    w = r.json()
    assert w["p10"] < w["wartosc"] < w["p90"]
    assert w["poza_zakresem"] == {"czy": False, "powod": None}
    assert len(w["czynniki"]) == 3
    assert all(isinstance(cz["wplyw_pln"], int) and cz["opis"] for cz in w["czynniki"])
    wplywy = [abs(cz["wplyw_pln"]) for cz in w["czynniki"]]
    assert wplywy == sorted(wplywy, reverse=True)
    assert w["wersja_modelu"] == yaml.safe_load(SCIEZKA_CURRENT.read_text(encoding="utf-8"))["wersja"]
    assert w["cechy_z_opisu"] is False and ekstraktor.opisy == []


def test_lokal_spoza_zakresu_ma_powod_i_brak_liczb(klient):
    c, _ = klient
    r = c.post(
        "/valuation", json={**LOKAL, "miasto": "Katowice", "dzielnica": "Śródmieście", "lat": 50.26, "lon": 19.02}
    )
    w = r.json()
    assert r.status_code == 200
    assert w["poza_zakresem"]["czy"] is True and "Katowice" in w["poza_zakresem"]["powod"]
    assert (w["wartosc"], w["p10"], w["p90"], w["czynniki"]) == (None, None, None, [])


def test_opis_trafia_do_ekstraktora_bez_kwot_i_zmienia_wycene(klient):
    c, ekstraktor = klient
    bez = c.post("/valuation", json=LOKAL).json()
    z = c.post("/valuation", json={**LOKAL, "opis": "Balkon. Cena: 650 000 zł. Wykończone w wysokim standardzie."})
    assert z.status_code == 200
    assert ekstraktor.opisy == ["Balkon. Wykończone w wysokim standardzie."]
    assert z.json()["cechy_z_opisu"] is True
    assert z.json()["wartosc"] != bez["wartosc"]


def test_brak_klucza_llm_przy_opisie_to_503(klient):
    c, _ = klient
    app.dependency_overrides[ekstraktor_cech_opisu] = lambda: Ekstraktor(blad=BrakKluczaAPI("brak klucza"))
    r = c.post("/valuation", json={**LOKAL, "opis": "Balkon."})
    assert r.status_code == 503
    assert "opis" in r.json()["detail"]


# --- odczyty dla panelu ----------------------------------------------------------------------------------------------


@pytest.fixture
def klient_z_historia(tmp_path, klient):
    import duckdb

    sciezka = tmp_path / "h.duckdb"
    con = duckdb.connect(str(sciezka))
    czas = datetime(2026, 11, 15, 1, tzinfo=timezone.utc)
    wiersz = {
        "miasto": "Warszawa", "dzielnica": "Wola", "metraz": 48.0, "dzien_wyceny": date(2026, 11, 15),
        "p10": 450_000.0, "p50": 500_000.0, "p90": 560_000.0, "odmowa": False, "powod": "",
        "cena_ofertowa": None, "wartosc_bazowa": 520_000.0, "czynniki": {"metraz": -30_000.0, "dzielnica": 10_000.0},
    }  # fmt: skip
    lokale = pd.DataFrame([{**wiersz, "id_obiektu": "B01-0001"}, {**wiersz, "id_obiektu": "B01-0002", "odmowa": True,
                           "powod": "Metraż 9 m²", "p10": None, "p50": None, "p90": None, "czynniki": {}}])  # fmt: skip
    oferty = pd.DataFrame([{**wiersz, "id_obiektu": "O1", "cena_ofertowa": 400_000.0}])
    h.zapisz(con, "run-1", czas, "v4_llm_cechy", "lokal", lokale)
    h.zapisz(con, "run-1", czas, "v4_llm_cechy", "oferta", oferty)
    con.close()

    import duckdb as d

    def baza_testowa():
        c = d.connect(str(sciezka), read_only=True)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[baza] = baza_testowa
    return klient[0]


def test_kolejka_nie_wiem(klient_z_historia):
    r = klient_z_historia.get("/valuation/kolejka-nie-wiem")
    assert r.status_code == 200
    assert [(o["rodzaj"], o["id_obiektu"], o["powod"]) for o in r.json()] == [("lokal", "B01-0002", "Metraż 9 m²")]


def test_oferty_ponizej_p10(klient_z_historia):
    r = klient_z_historia.get("/valuation/oferty-ponizej-p10")
    assert [(o["id_obiektu"], o["cena_ofertowa"], o["p10"]) for o in r.json()] == [("O1", 400_000.0, 450_000.0)]


def test_karta_wyceny_ma_wszystkie_czynniki_posortowane_i_historie(klient_z_historia):
    r = klient_z_historia.get("/valuation/karta/lokal/B01-0001")
    k = r.json()
    assert r.status_code == 200
    assert [c["cecha"] for c in k["czynniki"]] == ["metraz", "dzielnica"]
    assert k["czynniki"][0]["opis"] == "metraż"
    assert [p["p50"] for p in k["historia"]] == [500_000.0]


def test_karta_nieznanego_obiektu_to_404(klient_z_historia):
    assert klient_z_historia.get("/valuation/karta/lokal/NIE-MA").status_code == 404
