import json
from datetime import datetime

import duckdb
import pandas as pd
import pytest
from api.adapters.llm_client import klucz_cache
from api.ai.llm.ekstrakcja_awarii import opis_zgloszenia, wyciagnij_awarie, zgloszenia
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.awaria import Awaria
from pomocnicze_llm import SerwerOpenAI
from pomocnicze_llm import klient as _klient
from pydantic import ValidationError

AWARIA_OK = {
    "objaw": "winda stała, uszkodzony falownik",
    "czy_awaria": True,
    "podzespol": "naped",
    "start_wg_notatki": None,
    "czas_naprawy_h": 14.2,
    "pewnosc": 0.9,
}
BEZ_AWARII = {
    "objaw": "kontrola po naprawie, bez usterek",
    "czy_awaria": False,
    "podzespol": "brak",
    "start_wg_notatki": None,
    "czas_naprawy_h": None,
    "pewnosc": 0.95,
}

# --- schemat ---------------------------------------------------------------------------------------------------


def test_schemat_przyjmuje_awarie_i_brak_awarii():
    assert Awaria.model_validate(AWARIA_OK).podzespol == "naped"
    assert Awaria.model_validate(BEZ_AWARII).czy_awaria is False


def test_start_wg_notatki_to_czas_lokalny_minutowy():
    a = Awaria.model_validate({**AWARIA_OK, "start_wg_notatki": "2025-03-12 06:30"})
    assert a.start == datetime(2025, 3, 12, 6, 30)


@pytest.mark.parametrize("start", ["2025-02-30 10:00", "2025-03-12 25:00", "2025-03-12T06:30", "12.03 6:30"])
def test_schemat_odrzuca_nieprawdziwy_albo_zle_zapisany_start(start):
    with pytest.raises(ValidationError):
        Awaria.model_validate({**AWARIA_OK, "start_wg_notatki": start})


@pytest.mark.parametrize(
    "zmiana",
    [
        {"podzespol": "wandalizm"},
        {"pewnosc": 1.1},
        {"pewnosc": -0.1},
        {"czas_naprawy_h": -1},
        {"objaw": "x" * 121},
        {"dodatkowe": 1},
    ],
)
def test_schemat_odrzuca_wartosci_spoza_slownika_zakresu_i_dodatkowe_pola(zmiana):
    with pytest.raises(ValidationError):
        Awaria.model_validate({**AWARIA_OK, **zmiana})


@pytest.mark.parametrize(
    "zmiana", [{"podzespol": "drzwi"}, {"start_wg_notatki": "2025-03-12 06:30"}, {"czas_naprawy_h": 2.0}]
)
def test_bez_awarii_nie_ma_podzespolu_startu_ani_czasu_naprawy(zmiana):
    with pytest.raises(ValidationError, match="czy_awaria = false"):
        Awaria.model_validate({**BEZ_AWARII, **zmiana})


def test_awaria_moze_nie_wskazywac_podzespolu():
    assert Awaria.model_validate({**AWARIA_OK, "podzespol": "brak"}).podzespol == "brak"


def test_schemat_w_api_jest_scisly_ze_slownikiem_podzespolow(tmp_path):
    serwer = SerwerOpenAI(dane=AWARIA_OK)
    _klient(serwer, tmp_path).zapytaj("Treść zgłoszenia: Winda nie jeździ", wczytaj_prompt("awaria_v1"), Awaria)
    zadanie = serwer.zadania[0]
    assert zadanie["model"] == "gpt-6-luna"
    assert zadanie["reasoning"] == {"effort": "none"}
    assert zadanie["temperature"] == 0
    format_ = zadanie["text"]["format"]
    assert format_["strict"] is True
    schemat = format_["schema"]
    assert set(schemat["required"]) == set(AWARIA_OK)
    pod = schemat["properties"]["podzespol"]
    enum = pod.get("enum") or schemat["$defs"][pod["$ref"].split("/")[-1]]["enum"]
    assert sorted(enum) == sorted(["drzwi", "naped", "hamulec_liny", "sterownik", "zewnetrzna", "brak"])


# --- prompt ----------------------------------------------------------------------------------------------------


def test_prompt_v1_ma_wersje_date_i_wstawia_zgloszenie():
    p = wczytaj_prompt("awaria_v1")
    assert p.wersja == "awaria_v1"
    assert p.data == "2026-11-16"
    assert "<zgloszenie>\nTreść zgłoszenia: Winda nie jeździ\n</zgloszenie>" in p.wiadomosc(
        "Treść zgłoszenia: Winda nie jeździ"
    )


def test_prompt_wyjasnia_skroty_konserwatorow():
    instrukcja = wczytaj_prompt("awaria_v1").instrukcja
    for skrot in ("op. drzwi:", "ZK:", "ster.:", "uwolniono N os.:"):
        assert skrot in instrukcja, skrot


def test_prompt_ma_cztery_przyklady_zaprzeczen():
    instrukcja = wczytaj_prompt("awaria_v1").instrukcja
    sekcja = instrukcja.split("Zaprzeczenia:")[1].split("start_wg_notatki:")[0]
    przyklady = [linia for linia in sekcja.splitlines() if linia.strip()[:2] in {"1.", "2.", "3.", "4.", "5."}]
    assert len(przyklady) == 4
    assert "Po awarii z 12.03" in przyklady[0]


# --- wejście ---------------------------------------------------------------------------------------------------


def test_opis_ma_zgloszenie_i_notatki_od_najstarszej_w_jednej_linii():
    opis = opis_zgloszenia(
        datetime(2023, 2, 1, 11, 45),
        "telefon",
        "Winda stoi na 7. piętrze",
        [
            {"data_czas": datetime(2023, 2, 2, 1, 58), "autor": "K09", "tresc": "Naprawa zakończona, winda w ruchu."},
            {"data_czas": datetime(2023, 2, 1, 12, 38), "autor": "KOORD", "tresc": "Wym.\nrolek drzwi."},
        ],
    )
    assert opis.splitlines() == [
        "Zgłoszenie utworzone: 2023-02-01 11:45",
        "Źródło zgłoszenia: telefon",
        "Treść zgłoszenia: Winda stoi na 7. piętrze",
        "Notatki (od najstarszej, czas lokalny):",
        "[2023-02-01 12:38] KOORD (koordynator): Wym. rolek drzwi.",
        "[2023-02-02 01:58] K09 (konserwator): Naprawa zakończona, winda w ruchu.",
    ]


def test_opis_bez_notatek():
    assert opis_zgloszenia(datetime(2023, 2, 1, 11, 45), None, "x", []).endswith("Notatki: brak")


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE serwis_zgloszenia AS SELECT * FROM (VALUES "
        "('Z1', TIMESTAMP '2025-06-01 10:00', 'portal', 'awaria', 'pilny', 'Winda nie jeździ'), "
        "('Z2', TIMESTAMP '2025-06-02 10:00', 'telefon', 'interwencja', 'normalny', 'Drzwi windy skrzypią'), "
        "('Z3', TIMESTAMP '2025-06-03 10:00', 'portal', 'usterka', 'normalny', 'Nie wybrane')) "
        "t(id_zgloszenia, utworzono, zrodlo, kategoria, priorytet, tresc_zgloszenia)"
    )
    con.execute(
        "CREATE TABLE serwis_notatki AS SELECT * FROM (VALUES "
        "('N2', 'Z1', 'K01', TIMESTAMP '2025-06-01 14:00', 'Naprawa zakończona, winda w ruchu.'), "
        "('N1', 'Z1', 'K01', TIMESTAMP '2025-06-01 11:00', 'Uszkodzony falownik, winda stała.')) "
        "t(id_notatki, id_zgloszenia, autor, data_czas, tresc)"
    )
    return con


def test_zgloszenia_z_bazy_bez_kategorii_i_priorytetu(con):
    df = zgloszenia(con, ["Z1", "Z2"])
    assert sorted(df["id_zgloszenia"]) == ["Z1", "Z2"]
    teksty = dict(zip(df["id_zgloszenia"], df["tekst"], strict=True))
    assert teksty["Z1"].splitlines()[-2:] == [
        "[2025-06-01 11:00] K01 (konserwator): Uszkodzony falownik, winda stała.",
        "[2025-06-01 14:00] K01 (konserwator): Naprawa zakończona, winda w ruchu.",
    ]
    assert teksty["Z2"].endswith("Notatki: brak")
    for tekst in teksty.values():
        assert "awaria" not in tekst and "interwencja" not in tekst and "pilny" not in tekst


# --- ekstrakcja i cache ----------------------------------------------------------------------------------------


def test_wyniki_w_cache_pod_kluczem_z_wejscia_i_wersji_promptu(tmp_path):
    serwer = SerwerOpenAI(dane=AWARIA_OK)
    klient = _klient(serwer, tmp_path)
    prompt = wczytaj_prompt("awaria_v1")
    rekordy = pd.DataFrame({"id_zgloszenia": ["Z1"], "tekst": ["Treść zgłoszenia: Winda nie jeździ"]})

    pierwszy = wyciagnij_awarie(klient, rekordy, prompt, watki=1)
    drugi = wyciagnij_awarie(klient, rekordy, prompt, watki=1)

    klucz = klucz_cache("Treść zgłoszenia: Winda nie jeździ", "awaria_v1")
    plik = tmp_path / f"{klucz}.json"
    assert json.loads(plik.read_text(encoding="utf-8"))["wersja_promptu"] == "awaria_v1"
    assert len(serwer.zadania) == 1
    assert pierwszy.loc[0, "klucz_cache"] == klucz
    assert (pierwszy.loc[0, "z_cache"], drugi.loc[0, "z_cache"]) == (False, True)
    assert drugi.loc[0, "podzespol"] == "naped" and drugi.loc[0, "czas_naprawy_h"] == 14.2


def test_blad_jednego_zgloszenia_nie_przerywa_ekstrakcji(tmp_path):
    serwer = SerwerOpenAI(dane=AWARIA_OK, blad_dla="ZEPSUTE")
    rekordy = pd.DataFrame({"id_zgloszenia": ["Z1", "Z2"], "tekst": ["Winda nie jeździ", "ZEPSUTE"]})
    wynik = wyciagnij_awarie(_klient(serwer, tmp_path), rekordy, wczytaj_prompt("awaria_v1"), watki=2)
    assert list(wynik["id_zgloszenia"]) == ["Z1", "Z2"]
    assert pd.isna(wynik.loc[0, "blad"]) and bool(wynik.loc[0, "czy_awaria"]) is True
    assert "InternalServerError" in wynik.loc[1, "blad"] and pd.isna(wynik.loc[1, "czy_awaria"])


def test_niespojna_odpowiedz_modelu_trafia_do_bledu(tmp_path):
    serwer = SerwerOpenAI(dane={**BEZ_AWARII, "podzespol": "drzwi"})
    rekordy = pd.DataFrame({"id_zgloszenia": ["Z1"], "tekst": ["Winda nie jeździ"]})
    wynik = wyciagnij_awarie(_klient(serwer, tmp_path), rekordy, wczytaj_prompt("awaria_v1"), watki=1)
    assert "czy_awaria = false" in wynik.loc[0, "blad"]
    assert list(tmp_path.glob("*.json")) == []
