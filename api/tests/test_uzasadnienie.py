import json

import pandas as pd
import pytest
from api.ai.features.leady.cechy import KOLUMNY_CECH
from api.ai.features.leady.fakty import MAKS_DLUGOSC_FAKTU, Fakt, fakt, fakty_leada, krotka_firma, odmiana
from api.ai.lead_model.evals.ewaluacja import KATALOG_WYNIKOW
from api.ai.lead_model.uzasadnienie import (
    ZDANIE_BEZ_FAKTOW,
    sprawdz_zdanie,
    top_wklady,
    uzasadnij,
    wejscie_llm,
    zdanie_z_szablonu,
)
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.uzasadnienie import MAKS_DLUGOSC_ZDANIA, Uzasadnienie
from pomocnicze_llm import SerwerOpenAI
from pomocnicze_llm import klient as _klient
from pydantic import ValidationError

PLIK_UZASADNIEN = KATALOG_WYNIKOW / "uzasadnienia.parquet"
KONTEKST = {"firma": "Altakom S.A.", "budzet_max": 3500}
TOP = [
    fakt("syg_relokacja", 1, KONTEKST),
    fakt("liczba_lokali", 2, KONTEKST),
    fakt("syg_pilny_termin", 1, KONTEKST),
]
POZOSTALE = [fakt("miasto", "Kraków", KONTEKST), fakt("budzet_do_mediany", 1.5, KONTEKST), fakt("zrodlo", "www", {})]


# --- szablon faktów --------------------------------------------------------------------------------------------


def test_fakt_relokacji_i_lokali_ma_nazwe_firmy_bez_formy_prawnej():
    assert [f.tekst for f in TOP] == ["relokacja: Altakom", "2 lokale: Altakom", "pilny termin"]
    assert "altakom" in TOP[0].kotwice


@pytest.mark.parametrize("n, forma", [(1, "lokal"), (2, "lokale"), (5, "lokali"), (12, "lokali"), (22, "lokale")])
def test_odmiana_liczebnika(n, forma):
    assert odmiana(n, "lokal", "lokale", "lokali") == forma


def test_budzet_jako_kwota_i_procent_mediany():
    assert fakt("budzet_do_mediany", 1.5, KONTEKST).tekst == "budżet 3 500 zł, 150% mediany w mieście"
    assert fakt("budzet_do_mediany", float("nan"), {}).tekst == "budżet nie podany"


def test_kazda_cecha_modelu_ma_fakt_najwyzej_40_znakow():
    wiersz = {c: 1.0 for c in KOLUMNY_CECH} | {"zrodlo": "relokacja_b2b", "miasto": "Wrocław", "linia": "MID"}
    fakty = fakty_leada(wiersz, {"firma": "Bardzo Długa Nazwa Firmy Sp. z o.o.", "budzet_max": 12345}, KOLUMNY_CECH)
    assert set(fakty) == set(KOLUMNY_CECH)
    assert all(len(f.tekst) <= MAKS_DLUGOSC_FAKTU and f.kotwice for f in fakty.values())
    assert krotka_firma("Bardzo Długa Nazwa Firmy Sp. z o.o.") == "Bardzo Długa Nazwa"


# --- top 3 z SHAP ----------------------------------------------------------------------------------------------


def test_top_wklady_biora_najwyzej_3_dodatnie_malejaco_bez_stalej():
    w = pd.Series({"wklad_a": 0.1, "wklad_b": -0.5, "wklad_c": 0.7, "wklad_d": 0.3, "wklad_e": 0.2, "wklad_staly": 9})
    assert [c for c, _ in top_wklady(w)] == ["c", "d", "e"]
    assert top_wklady(pd.Series({"wklad_a": -0.1, "wklad_staly": 1.0})) == []


# --- kontrola zdania -------------------------------------------------------------------------------------------


def test_poprawne_zdanie_z_faktow_top3_przechodzi():
    assert sprawdz_zdanie("Relokacja Altakom: 2 lokale z pilnym terminem.", TOP, POZOSTALE) == []


@pytest.mark.parametrize(
    "zdanie, problem",
    [
        ("x" * 141, "długość"),
        ("Relokacja Altakom, 3 lokale, pilny termin.", "liczby spoza top 3: 3"),
        ("Relokacja Altakom do Krakowa, pilny termin.", "fakt spoza top 3: miasto"),
        ("Pilna relokacja Altakom, budżet bez zarzutu.", "fakt spoza top 3: budzet_do_mediany"),
        ("Relokacja z formularza na stronie www, 2 lokale.", "fakt spoza top 3: zrodlo"),
    ],
)
def test_kontrola_wylapuje_dlugosc_i_fakty_spoza_top3(zdanie, problem):
    assert any(p.startswith(problem) for p in sprawdz_zdanie(zdanie, TOP, POZOSTALE))


def test_kotwica_pasuje_tylko_na_poczatku_slowa():
    pozostale = [fakt("syg_konkretne_pytania", 0, {})]
    assert sprawdz_zdanie("Zapytanie: relokacja Altakom, 2 lokale, pilny termin.", TOP, pozostale) == []
    assert sprawdz_zdanie("Relokacja Altakom, pytania o 2 lokale, pilny termin.", TOP, pozostale) != []


def test_liczby_z_kodow_i_tysiecy_nie_sa_obcymi_liczbami():
    top = [fakt("linia", "B2B", {}), fakt("budzet_do_mediany", 1.5, KONTEKST)]
    assert sprawdz_zdanie("Najem B2B, budżet 3500 zł to 150% mediany.", top, []) == []


def test_zdanie_z_szablonu_miesci_sie_w_limicie():
    dlugie = [Fakt("a", "x" * MAKS_DLUGOSC_FAKTU, ("a",))] * 3
    assert len(zdanie_z_szablonu(dlugie)) <= MAKS_DLUGOSC_ZDANIA
    assert zdanie_z_szablonu([]) == ZDANIE_BEZ_FAKTOW


# --- schemat i wywołanie LLM -----------------------------------------------------------------------------------


def test_schemat_ma_limit_140_znakow_i_nie_przyjmuje_innych_pol():
    Uzasadnienie.model_validate({"zdanie": "x" * 140})
    for zle in ({"zdanie": "x" * 141}, {"zdanie": ""}, {"zdanie": "ok", "ocena": 5}):
        with pytest.raises(ValidationError):
            Uzasadnienie.model_validate(zle)


def test_llm_dostaje_tylko_fakty_top3_z_temperatura_0_i_wynik_trafia_do_cache(tmp_path):
    serwer = SerwerOpenAI(dane={"zdanie": "Relokacja Altakom: 2 lokale, pilny termin."})
    k = _klient(serwer, tmp_path)
    w = uzasadnij(TOP, POZOSTALE, k, wczytaj_prompt("uzasadnienie_v1"))
    assert (w.zrodlo, w.zdanie) == ("llm", "Relokacja Altakom: 2 lokale, pilny termin.")
    zadanie = serwer.zadania[0]
    assert zadanie["temperature"] == 0
    assert zadanie["text"]["format"]["schema"]["properties"]["zdanie"]["maxLength"] == 140
    wejscie = json.dumps(zadanie["input"], ensure_ascii=False)
    assert wejscie_llm(TOP).split("\n")[0] in wejscie and "Kraków" not in wejscie
    assert uzasadnij(TOP, POZOSTALE, k).z_cache is True and len(serwer.zadania) == 1


def test_zdanie_llm_z_faktem_spoza_top3_zastepuje_szablon(tmp_path):
    serwer = SerwerOpenAI(dane={"zdanie": "Relokacja Altakom do Krakowa, pilny termin."})
    w = uzasadnij(TOP, POZOSTALE, _klient(serwer, tmp_path), wczytaj_prompt("uzasadnienie_v1"))
    assert w.zrodlo == "szablon" and w.zdanie == zdanie_z_szablonu(TOP)
    assert any("miasto" in p for p in w.problemy_llm)


def test_blad_api_daje_zdanie_z_szablonu(tmp_path):
    serwer = SerwerOpenAI(dane={"zdanie": "nieistotne"}, blad_dla="relokacja")
    w = uzasadnij(TOP, POZOSTALE, _klient(serwer, tmp_path), wczytaj_prompt("uzasadnienie_v1"))
    assert w.zrodlo == "szablon" and w.zdanie == zdanie_z_szablonu(TOP)


# --- wygenerowane zdania (evals/uzasadnienia.py) ---------------------------------------------------------------


@pytest.mark.skipif(not PLIK_UZASADNIEN.exists(), reason="brak evals/wyniki/uzasadnienia.parquet (uzasadnienia.py)")
def test_kazde_wygenerowane_zdanie_ma_najwyzej_140_znakow_i_tylko_fakty_top3():
    df = pd.read_parquet(PLIK_UZASADNIEN)
    z = df[df["z_llm"]]
    assert len(z) > 0 and z["zdanie"].notna().all()
    for r in z.itertuples():
        top = [Fakt.ze_slownika(f) for f in json.loads(r.fakty_top)]
        pozostale = [Fakt.ze_slownika(f) for f in json.loads(r.fakty_pozostale)]
        assert len(r.zdanie) <= MAKS_DLUGOSC_ZDANIA, (r.id_leada, r.zdanie)
        assert sprawdz_zdanie(r.zdanie, top, pozostale) == [], (r.id_leada, r.zdanie)
        assert len(top) <= 3 and len(top) == len(json.loads(r.top3))
