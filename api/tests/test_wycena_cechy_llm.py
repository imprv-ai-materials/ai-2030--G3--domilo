import math

import pandas as pd
import pytest
from api.ai.features.wycena.cechy_llm import KOLUMNY_LLM, cechy_do_modelu, wyciagnij
from api.ai.features.wycena.ceny_w_opisie import bez_kwot, cena_z_opisu, czynsz_najmu_z_opisu, wzmianki_o_cenie
from api.ai.llm.prompty import Prompt, wczytaj_prompt
from pomocnicze_llm import CECHY_OK, SerwerOpenAI, klient

# --- tekst wysyłany do LLM bez kwot --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opis, oczekiwany",
    [
        ("Mieszkanie 2 pok. Cena: 414 000 zł. Balkon.", "Mieszkanie 2 pok. Balkon."),
        ("Balkon. Cena 1305 tys. Winda.", "Balkon. Winda."),
        ("Balkon. Cena 518 tys. zł. Winda.", "Balkon. Winda."),
        ("Balkon. Cena do negocjacji: 605 000. Winda.", "Balkon. Winda."),
        ("Balkon. Tylko 17 800 zł/m². Winda.", "Balkon. Winda."),
        ("Balkon. Rata od 1 880 zł miesięcznie. Winda.", "Balkon. Winda."),
        ("Balkon. Obniżka z 814 do 761 tys. Winda.", "Balkon. Winda."),
        ("Balkon. Miesięcznie 2 550 zł (plus media wg zużycia).", "Balkon."),
        ("Balkon. Czynsz 3 540 zł + media. Winda.", "Balkon. Winda."),
        ("Balkon. Czynsz: 3 230 zł/mies. + media.", "Balkon."),
        ("Cena: 1 220 000 zł.", ""),
    ],
)
def test_bez_kwot_usuwa_zdania_z_cena_rata_obnizka_i_czynszem(opis, oczekiwany):
    assert bez_kwot(opis) == oczekiwany


@pytest.mark.parametrize(
    "opis",
    [
        "Niski czynsz administracyjny.",
        "Umowa na 12 miesięcy z opcją przedłużenia.",
        "Do remontu — instalacje do wymiany, cena uwzględnia nakłady.",
        "Balkon 8 m². Blok z 1986 roku, zadbana klatka.",
    ],
)
def test_bez_kwot_zostawia_zdania_bez_kwoty(opis):
    assert bez_kwot(opis) == opis


def test_po_usunieciu_kwot_nie_da_sie_odczytac_ceny_ani_czynszu():
    opis = "Cena: 628 000 zł. Rata od 2 300 zł miesięcznie. Czynsz 3 540 zł + media. Tylko 12 000 zł/m²."
    tekst = bez_kwot(opis)
    assert (cena_z_opisu(tekst, metraz=50.0), czynsz_najmu_z_opisu(tekst), wzmianki_o_cenie(tekst)) == (
        None,
        None,
        set(),
    )


# --- ekstrakcja równoległa ------------------------------------------------------------------------------------------

PROMPT = Prompt(wersja="test_v1", instrukcja="Wyciągnij cechy.", szablon="Opis: {opis}")


def test_wyciagnij_zwraca_wiersz_na_rekord_w_kolejnosci_wejscia_a_blad_nie_przerywa_reszty(tmp_path):
    rekordy = pd.DataFrame({"id": ["A", "B", "C"], "tekst": ["Balkon.", "AWARIA tutaj.", "Winda."]})
    wynik = wyciagnij(klient(SerwerOpenAI(blad_dla="AWARIA"), tmp_path), rekordy, PROMPT, watki=2)

    assert list(wynik["id"]) == ["A", "B", "C"]
    assert wynik["widok"].isna().tolist() == [False, True, False]
    assert list(wynik["widok"].dropna()) == ["park", "park"]
    assert wynik["blad"].isna().tolist() == [True, False, True]
    assert list(wynik["tokeny_wejscia"].fillna(-1)) == [10, -1, 10]


def test_wyciagnij_ze_zdjeciami_wysyla_obrazy(tmp_path):
    zdj = tmp_path / "1.jpg"
    zdj.write_bytes(b"\xff\xd8x")
    serwer = SerwerOpenAI()
    rekordy = pd.DataFrame({"id": ["A"], "tekst": ["Zdjęcia."], "obrazy": [[zdj]]})
    wyciagnij(klient(serwer, tmp_path / "cache"), rekordy, PROMPT, watki=1)
    assert [c["type"] for c in serwer.zadania[0]["input"][0]["content"]] == ["input_text", "input_image"]


# --- kolumny modelu -------------------------------------------------------------------------------------------------


def test_cechy_do_modelu_maja_prefiks_llm_standard_liczbowy_i_bez_pewnosci():
    surowe = pd.DataFrame(
        [
            {"id": "A", **CECHY_OK, "blad": None},
            {"id": "B", **{**CECHY_OK, "standard_1_5": None, "widok": "brak_info"}, "blad": None},
        ]
    )
    m = cechy_do_modelu(surowe)

    assert list(m.columns) == ["id", *KOLUMNY_LLM]
    assert m.loc[0, "llm_standard"] == 4.0
    assert math.isnan(m.loc[1, "llm_standard"])
    assert list(m["llm_widok"]) == ["park", "brak_info"]


def test_cechy_do_modelu_pomija_rekordy_z_bledem():
    surowe = pd.DataFrame(
        [{"id": "A", **CECHY_OK, "blad": None}, {"id": "B", **{k: None for k in CECHY_OK}, "blad": "awaria"}]
    )
    assert list(cechy_do_modelu(surowe)["id"]) == ["A"]


# --- prompt do zdjęć -------------------------------------------------------------------------------------------------


def test_prompt_zdjec_ma_wlasna_wersje_i_wiadomosc_bez_opisu_ogloszenia():
    p = wczytaj_prompt("cechy_lokalu_zdjecia_v1")
    assert p.wersja == "cechy_lokalu_zdjecia_v1"
    assert p.instrukcja.strip()
    assert "{opis}" not in p.wiadomosc("4 zdjęcia")
