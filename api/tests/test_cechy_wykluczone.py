import re

import pandas as pd
import pytest
from api.adapters.duckdb_baza import KATALOG_REPO, polacz
from api.ai.features.leady.cechy import KOLUMNY_CECH, zbuduj_cechy
from api.ai.features.leady.fakty import fakt
from api.ai.features.leady.ocena_llm import opis_leada
from api.ai.features.leady.wykluczone import (
    WYKLUCZONE,
    CechaWykluczona,
    sprawdz_brak_wykluczonych,
    wczytaj_wykluczone,
)
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.evals.ewaluacja import KATALOG_MODELU
from api.ai.lead_model.versions.v2_lgbm_naiwny.model import ModelLGBMNaiwny
from api.ai.lead_model.versions.v2b_lgbm_ipw.model import ModelLGBMIPW
from api.ai.lead_model.versions.v3_ev_kalibracja.model import ModelV3EVKalibracja
from api.ai.llm.prompty import KATALOG_PROMPTOW, wczytaj_prompt

CHRONIONE = {"jezyk", "imie", "rok_urodzenia"}
MODELE_ZAPISANE = ("v2_lgbm_naiwny", "v2b_lgbm_ipw", "v3_ev_kalibracja")
BAZA = KATALOG_REPO / "domilo.duckdb"


def _kolumny_z_wykluczona(kolumny) -> list[str]:
    return [k for k in kolumny if any(k == w or k.endswith(f"_{w}") or k.startswith(f"{w}_") for w in CHRONIONE)]


# --- lista --------------------------------------------------------------------------------------------------


def test_lista_wykluczonych_ma_trzy_cechy_chronione_z_uzasadnieniem():
    lista = wczytaj_wykluczone()
    assert set(lista) == CHRONIONE == set(WYKLUCZONE)
    for nazwa, pozycja in lista.items():
        assert {"zrodlo", "uzasadnienie", "dozwolone_uzycie", "ryzyko_posrednie"} <= set(pozycja), nazwa
        assert len(pozycja["uzasadnienie"].strip()) > 20, nazwa


@pytest.mark.parametrize("kolumna", ["jezyk", "imie", "rok_urodzenia", "wklad_jezyk", "imie_dl"])
def test_straznik_odrzuca_wykluczona_kolumne(kolumna):
    with pytest.raises(CechaWykluczona):
        sprawdz_brak_wykluczonych(["zrodlo", kolumna], "test")


def test_straznik_przepuszcza_zwykle_cechy():
    sprawdz_brak_wykluczonych(KOLUMNY_CECH, "test")


# --- macierz cech -------------------------------------------------------------------------------------------


def test_zadna_wykluczona_cecha_nie_jest_w_kolumny_cech():
    assert _kolumny_z_wykluczona(KOLUMNY_CECH) == []


@pytest.mark.parametrize("klasa", [ModelLGBMNaiwny, ModelLGBMIPW, ModelV3EVKalibracja])
@pytest.mark.parametrize("cecha", sorted(CHRONIONE))
def test_model_nie_przyjmie_wykluczonej_cechy(klasa, cecha):
    with pytest.raises(CechaWykluczona):
        klasa(cechy=(*KOLUMNY_CECH, cecha))


@pytest.mark.parametrize("wersja", MODELE_ZAPISANE)
def test_zapisane_modele_nie_maja_wykluczonych_cech_w_macierzy(wersja):
    plik = KATALOG_MODELU / "versions" / wersja / "model.joblib"
    if not plik.exists():
        pytest.skip(f"brak {plik}")
    model = ModelLeadow.wczytaj(plik)
    assert _kolumny_z_wykluczona(model.cechy) == []
    assert _kolumny_z_wykluczona(model.booster_.feature_name()) == []


def test_macierz_v3_pomija_wykluczone_kolumny_obecne_w_wejsciu():
    plik = KATALOG_MODELU / "versions" / "v3_ev_kalibracja" / "model.joblib"
    if not plik.exists():
        pytest.skip(f"brak {plik}")
    v3 = ModelLeadow.wczytaj(plik)
    wiersz = {k: float("nan") for k in KOLUMNY_CECH} | {"zrodlo": "www", "miasto": "Kraków", "linia": "B2C"}
    X = pd.DataFrame([wiersz | {"jezyk": "uk", "imie": "Kamil", "rok_urodzenia": 1990}])
    macierz = v3.model_._macierz(X)
    assert list(macierz.columns) == list(v3.cechy) and _kolumny_z_wykluczona(macierz.columns) == []
    assert 0 <= v3.predict(X)[0] <= 1


@pytest.mark.skipif(not BAZA.exists(), reason="brak domilo.duckdb (pypyr baza)")
def test_zbuduj_cechy_nie_zwraca_wykluczonych_kolumn():
    cechy = zbuduj_cechy(
        polacz(), pd.DataFrame({"id_leada": pd.Series([], dtype="string"), "sygnaly": pd.Series([], dtype="string")})
    )
    assert _kolumny_z_wykluczona(cechy.columns) == []
    assert set(KOLUMNY_CECH) <= set(cechy.columns)


# --- prompty ------------------------------------------------------------------------------------------------


def test_opis_dla_llm_nie_ma_imienia_jezyka_ani_roku_urodzenia():
    lead = {
        "zrodlo": "www", "miasto": "Gdańsk", "linia_pref": "B2C", "budzet_max": 3000,
        "termin_wprowadzenia": None, "liczba_osob": 2, "zwierze": False, "liczba_lokali": None,
        "utworzono": pd.Timestamp("2026-06-15 10:00", tz="Europe/Warsaw"),
        "wiadomosc": "Dzień dobry, szukam mieszkania. Pozdrawiam, Kamil", "imie": "Kamil",
        "jezyk": "uk", "rok_urodzenia": 1987,
    }  # fmt: skip
    opis = opis_leada(lead)
    assert "Kamil" not in opis and "[imię]" in opis
    assert "1987" not in opis
    assert not re.search(r"^(język|jezyk|imię|imie|rok urodzenia|wiek)\s*:", opis, flags=re.I | re.M)


def test_szablony_promptow_maja_tylko_pole_opis():
    for plik in sorted(KATALOG_PROMPTOW.glob("*.yaml")):
        prompt = wczytaj_prompt(plik.stem)
        assert set(re.findall(r"{(\w+)}", prompt.szablon)) == {"opis"}, plik.name
        assert not set(re.findall(r"{(\w+)}", prompt.instrukcja)) & CHRONIONE, plik.name


@pytest.mark.parametrize("cecha", sorted(CHRONIONE))
def test_uzasadnienie_nie_ma_szablonu_faktu_dla_wykluczonej_cechy(cecha):
    with pytest.raises(ValueError):
        fakt(cecha, "x", {})
