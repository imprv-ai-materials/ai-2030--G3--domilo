import base64
import json

import duckdb
import pytest
from api.adapters.llm_client import BrakKluczaAPI, KlientLLM, PromptZmienionyBezNowejWersji, klucz_cache
from api.ai.llm.evals.stabilnosc_cechy_lokalu import losuj_opisy, zgodnosc_przebiegow
from api.ai.llm.prompty import Prompt, wczytaj_prompt
from api.ai.llm.schemas.cechy_lokalu import CechyLokalu
from pomocnicze_llm import CECHY_OK, SerwerOpenAI
from pomocnicze_llm import klient as _klient
from pydantic import ValidationError

# --- schemat ---------------------------------------------------------------------------------------------------


def test_schemat_odrzuca_pole_z_cena_bo_model_ma_nie_zwracac_kwot():
    with pytest.raises(ValidationError):
        CechyLokalu.model_validate({**CECHY_OK, "cena": 650000})


def test_schemat_odrzuca_standard_spoza_skali_1_5():
    with pytest.raises(ValidationError):
        CechyLokalu.model_validate({**CECHY_OK, "standard_1_5": 6})


def test_schemat_przyjmuje_brak_informacji_o_standardzie():
    assert CechyLokalu.model_validate({**CECHY_OK, "standard_1_5": None}).standard_1_5 is None


def test_schemat_odrzuca_widok_spoza_listy():
    with pytest.raises(ValidationError):
        CechyLokalu.model_validate({**CECHY_OK, "widok": "gory"})


# --- prompt ----------------------------------------------------------------------------------------------------


def test_prompt_v1_wczytuje_wersje_i_wstawia_opis_do_wiadomosci():
    p = wczytaj_prompt("cechy_lokalu_v1")
    assert p.wersja == "cechy_lokalu_v1"
    assert "Balkon 8 m²." in p.wiadomosc("Balkon 8 m².")
    assert p.instrukcja.strip()


# --- klient LLM ------------------------------------------------------------------------------------------------


PROMPT = Prompt(wersja="test_v1", instrukcja="Wyciągnij cechy.", szablon="Opis: {opis}")


def test_bez_zmiennej_OPENAI_API_KEY_klient_zglasza_brak_klucza(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(BrakKluczaAPI):
        KlientLLM(katalog_cache=tmp_path)


def test_zapytanie_idzie_do_gpt_6_luna_z_reasoning_none_temperatura_0_i_opisem(tmp_path):
    serwer = SerwerOpenAI()
    wynik = _klient(serwer, tmp_path).zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)

    assert wynik.dane == CECHY_OK
    [zadanie] = serwer.zadania
    assert zadanie["model"] == "gpt-6-luna"
    assert zadanie["reasoning"] == {"effort": "none"}
    assert zadanie["temperature"] == 0
    assert zadanie["instructions"] == "Wyciągnij cechy."
    assert zadanie["input"] == "Opis: Balkon 8 m²."
    assert zadanie["text"]["format"]["type"] == "json_schema"


def test_ten_sam_opis_i_wersja_promptu_drugi_raz_czytane_z_cache_pod_haszem(tmp_path):
    serwer = SerwerOpenAI()
    klient = _klient(serwer, tmp_path)

    pierwszy = klient.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    drugi = klient.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)

    assert len(serwer.zadania) == 1
    assert (pierwszy.z_cache, drugi.z_cache) == (False, True)
    assert drugi.dane == CECHY_OK
    assert [p.name for p in tmp_path.iterdir()] == [f"{klucz_cache('Balkon 8 m².', 'test_v1')}.json"]


def test_klucz_cache_zalezy_od_opisu_i_od_wersji_promptu():
    assert klucz_cache("opis A", "v1") != klucz_cache("opis B", "v1")
    assert klucz_cache("opis A", "v1") != klucz_cache("opis A", "v2")
    assert klucz_cache("opis A", "v1") == klucz_cache("opis A", "v1")


def test_nowa_wersja_promptu_nie_korzysta_z_cache_starej(tmp_path):
    serwer = SerwerOpenAI()
    klient = _klient(serwer, tmp_path)
    klient.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    klient.zapytaj("Balkon 8 m².", Prompt(wersja="test_v2", instrukcja="Inna.", szablon="{opis}"), CechyLokalu)
    assert len(serwer.zadania) == 2


def test_bez_czytania_cache_klient_pyta_api_ponownie(tmp_path):
    serwer = SerwerOpenAI()
    klient = _klient(serwer, tmp_path)
    klient.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    wynik = klient.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu, czytaj_cache=False, zapisuj_cache=False)
    assert len(serwer.zadania) == 2
    assert wynik.z_cache is False


def test_bez_zapisu_cache_nic_nie_trafia_do_katalogu(tmp_path):
    _klient(SerwerOpenAI(), tmp_path).zapytaj("Balkon 8 m².", PROMPT, CechyLokalu, zapisuj_cache=False)
    assert list(tmp_path.iterdir()) == []


def test_zmiana_tresci_promptu_bez_nowej_wersji_nie_zwraca_starej_odpowiedzi_z_cache(tmp_path):
    klient = _klient(SerwerOpenAI(), tmp_path)
    klient.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    zmieniony = Prompt(wersja="test_v1", instrukcja="Inna instrukcja.", szablon="Opis: {opis}")
    with pytest.raises(PromptZmienionyBezNowejWersji):
        klient.zapytaj("Balkon 8 m².", zmieniony, CechyLokalu)


def test_model_bez_temperatury_dostaje_zapytanie_bez_niej_i_cache_to_odnotowuje(tmp_path):
    serwer = SerwerOpenAI(odrzuca_temperature=True)
    wynik = _klient(serwer, tmp_path).zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)

    assert wynik.dane == CECHY_OK
    assert "temperature" not in serwer.zadania[-1]
    [plik] = tmp_path.iterdir()
    assert json.loads(plik.read_text(encoding="utf-8"))["temperatura"] is None


# --- zdjęcia i tokeny ------------------------------------------------------------------------------------------


def _jpg(katalog, nazwa: str, tresc: bytes):
    plik = katalog / nazwa
    plik.write_bytes(tresc)
    return plik


def test_zapytanie_ze_zdjeciami_wysyla_tekst_i_kazde_zdjecie_jako_data_url_w_wysokiej_rozdzielczosci(tmp_path):
    serwer = SerwerOpenAI()
    zdj = [_jpg(tmp_path, "1.jpg", b"\xff\xd8jeden"), _jpg(tmp_path, "2.jpg", b"\xff\xd8dwa")]
    _klient(serwer, tmp_path / "cache").zapytaj("Zdjęcia lokalu.", PROMPT, CechyLokalu, obrazy=zdj)

    [zadanie] = serwer.zadania
    assert zadanie["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Opis: Zdjęcia lokalu."},
                {
                    "type": "input_image",
                    "image_url": "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jeden").decode(),
                    "detail": "high",
                },
                {
                    "type": "input_image",
                    "image_url": "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8dwa").decode(),
                    "detail": "high",
                },
            ],
        }
    ]


def test_klucz_cache_bez_zdjec_jest_taki_jak_dotad_a_ze_zdjeciami_zalezy_od_ich_skrotow():
    assert klucz_cache("opis A", "v1", ()) == klucz_cache("opis A", "v1")
    assert klucz_cache("opis A", "v1", ("aa",)) != klucz_cache("opis A", "v1")
    assert klucz_cache("opis A", "v1", ("aa",)) != klucz_cache("opis A", "v1", ("bb",))


def test_inna_tresc_zdjecia_przy_tym_samym_tekscie_to_nowe_zapytanie_do_api(tmp_path):
    serwer = SerwerOpenAI()
    k = _klient(serwer, tmp_path / "cache")
    zdj = _jpg(tmp_path, "1.jpg", b"\xff\xd8a")
    k.zapytaj("Zdjęcia lokalu.", PROMPT, CechyLokalu, obrazy=[zdj])
    k.zapytaj("Zdjęcia lokalu.", PROMPT, CechyLokalu, obrazy=[zdj])
    zdj.write_bytes(b"\xff\xd8b")
    k.zapytaj("Zdjęcia lokalu.", PROMPT, CechyLokalu, obrazy=[zdj])
    assert len(serwer.zadania) == 2


def test_wynik_i_cache_podaja_tokeny_wejscia_odczytane_z_cache_promptu(tmp_path):
    k = _klient(SerwerOpenAI(tokeny_z_cache=7), tmp_path)
    wynik = k.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    [plik] = tmp_path.iterdir()
    assert wynik.tokeny_wejscia_z_cache == 7
    assert json.loads(plik.read_text(encoding="utf-8"))["tokeny_wejscia_z_cache"] == 7


def test_odczyt_z_cache_oddaje_tokeny_pierwszego_wywolania(tmp_path):
    k = _klient(SerwerOpenAI(tokeny_z_cache=7), tmp_path)
    k.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    z_cache = k.zapytaj("Balkon 8 m².", PROMPT, CechyLokalu)
    assert (z_cache.z_cache, z_cache.tokeny_wejscia, z_cache.tokeny_wyjscia, z_cache.tokeny_wejscia_z_cache) == (
        True,
        10,
        5,
        7,
    )


# --- eksperyment stabilności -----------------------------------------------------------------------------------


def test_losowanie_opisow_jest_powtarzalne_dla_tego_samego_ziarna_i_bez_powtorzen():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE radar_oferty AS SELECT 'O' || lpad(i::VARCHAR, 3, '0') AS id_oferty, 'opis ' || i AS opis "
        "FROM range(50) t(i)"
    )
    a = losuj_opisy(con, n=10, ziarno=7)
    b = losuj_opisy(con, n=10, ziarno=7)
    c = losuj_opisy(con, n=10, ziarno=8)

    assert list(a["id_oferty"]) == list(b["id_oferty"])
    assert list(a["id_oferty"]) != list(c["id_oferty"])
    assert a["id_oferty"].nunique() == 10


def test_zgodnosc_liczy_odsetek_opisow_z_identycznymi_odpowiedziami_we_wszystkich_przebiegach():
    inny_widok = {**CECHY_OK, "widok": "ulica"}
    przebiegi = {
        "O1": [CECHY_OK, CECHY_OK, CECHY_OK],
        "O2": [CECHY_OK, inny_widok, CECHY_OK],
        "O3": [inny_widok, inny_widok, inny_widok],
        "O4": [CECHY_OK, CECHY_OK, CECHY_OK],
    }
    z = zgodnosc_przebiegow(przebiegi)

    assert z["calosc"] == {"identyczne": 3, "opisow": 4, "odsetek": 0.75}
    assert z["widok"] == {"identyczne": 3, "opisow": 4, "odsetek": 0.75}
    assert z["balkon"] == {"identyczne": 4, "opisow": 4, "odsetek": 1.0}
