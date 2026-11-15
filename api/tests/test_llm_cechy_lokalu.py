import json

import duckdb
import httpx
import openai
import pytest
from api.adapters.llm_client import BrakKluczaAPI, KlientLLM, PromptZmienionyBezNowejWersji, klucz_cache
from api.ai.llm.evals.stabilnosc_cechy_lokalu import losuj_opisy, zgodnosc_przebiegow
from api.ai.llm.prompty import Prompt, wczytaj_prompt
from api.ai.llm.schemas.cechy_lokalu import CechyLokalu
from pydantic import ValidationError

CECHY_OK = {
    "standard_1_5": 4,
    "ekspozycja": "poludnie",
    "widok": "park",
    "balkon": "tak",
    "stan_budynku": "zadbany",
    "pewnosc": "wysoka",
}


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


def _odpowiedz_api(dane: dict) -> dict:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-6-luna",
        "status": "completed",
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(dane), "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


class SerwerOpenAI:
    """Udaje endpoint /v1/responses; zapisuje każde żądanie. Opcjonalnie odrzuca parametr temperature."""

    def __init__(self, dane: dict = CECHY_OK, odrzuca_temperature: bool = False):
        self.dane = dane
        self.odrzuca_temperature = odrzuca_temperature
        self.zadania: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        tresc = json.loads(request.content)
        self.zadania.append(tresc)
        if self.odrzuca_temperature and "temperature" in tresc:
            blad = {
                "error": {
                    "message": "Unsupported parameter: 'temperature' is not supported with this model.",
                    "type": "invalid_request_error",
                    "param": "temperature",
                    "code": "unsupported_parameter",
                }
            }
            return httpx.Response(400, json=blad)
        return httpx.Response(200, json=_odpowiedz_api(self.dane))


def _klient(serwer: SerwerOpenAI, katalog_cache) -> KlientLLM:
    openai_klient = openai.OpenAI(
        api_key="test", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(serwer))
    )
    return KlientLLM(katalog_cache=katalog_cache, klient_openai=openai_klient)


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
