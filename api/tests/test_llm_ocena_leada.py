import datetime as dt

import duckdb
import pytest
from api.ai.features.leady.ocena_llm import losuj_leady, opis_leada
from api.ai.llm.evals.stabilnosc_ocena_leada import zgodnosc_dwoch_przebiegow
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.ocena_leada import OcenaLeada
from pomocnicze_llm import SerwerOpenAI
from pomocnicze_llm import klient as _klient
from pydantic import ValidationError

OCENA_OK = {"ocena": 7, "uzasadnienie": "Konkretne pytania o termin i umowę.", "sygnaly": ["konkretne_pytania"]}

# --- schemat ---------------------------------------------------------------------------------------------------


def test_schemat_przyjmuje_poprawna_ocene():
    assert OcenaLeada.model_validate(OCENA_OK).ocena == 7


@pytest.mark.parametrize("ocena", [0, 11])
def test_schemat_odrzuca_ocene_spoza_skali_1_10(ocena):
    with pytest.raises(ValidationError):
        OcenaLeada.model_validate({**OCENA_OK, "ocena": ocena})


def test_uzasadnienie_ma_najwyzej_140_znakow():
    assert OcenaLeada.model_validate({**OCENA_OK, "uzasadnienie": "x" * 140})
    with pytest.raises(ValidationError):
        OcenaLeada.model_validate({**OCENA_OK, "uzasadnienie": "x" * 141})


def test_schemat_odrzuca_sygnal_spoza_slownika():
    with pytest.raises(ValidationError):
        OcenaLeada.model_validate({**OCENA_OK, "sygnaly": ["bogaty_klient"]})


def test_schemat_odrzuca_dodatkowe_pole():
    with pytest.raises(ValidationError):
        OcenaLeada.model_validate({**OCENA_OK, "prawdopodobienstwo": 0.4})


def test_sygnaly_to_zbior_w_stalej_kolejnosci_slownika():
    ocena = OcenaLeada.model_validate({**OCENA_OK, "sygnaly": ["relokacja", "pilny_termin", "relokacja"]})
    assert ocena.model_dump(mode="json")["sygnaly"] == ["pilny_termin", "relokacja"]


def test_schemat_w_api_ma_zamkniety_slownik_sygnalow_i_limit_uzasadnienia(tmp_path):
    serwer = SerwerOpenAI(dane=OCENA_OK)
    prompt = wczytaj_prompt("ocena_leada_v1")
    _klient(serwer, tmp_path).zapytaj("źródło: www", prompt, OcenaLeada)

    schemat = serwer.zadania[0]["text"]["format"]["schema"]
    assert serwer.zadania[0]["text"]["format"]["strict"] is True
    assert schemat["properties"]["uzasadnienie"]["maxLength"] == 140
    sygnal = schemat["properties"]["sygnaly"]["items"]
    enum = sygnal.get("enum") or schemat["$defs"][sygnal["$ref"].split("/")[-1]]["enum"]
    assert sorted(enum) == sorted(
        [
            "konkretne_pytania",
            "niedopasowanie_oferty",
            "pilny_termin",
            "relokacja",
            "budzet_niski",
            "brak_informacji",
        ]
    )


# --- prompt ----------------------------------------------------------------------------------------------------


def test_prompt_v1_ma_wersje_date_i_wstawia_opis_leada():
    p = wczytaj_prompt("ocena_leada_v1")
    assert p.wersja == "ocena_leada_v1"
    assert p.data == "2026-11-15"
    assert "miasto: Gdańsk" in p.wiadomosc("miasto: Gdańsk")


# --- wejście: tylko to, co znane w chwili utworzenia zapytania -------------------------------------------------

LEAD = {
    "zrodlo": "lokum24",
    "miasto": "Gdańsk",
    "linia_pref": "B2C",
    "budzet_max": 2400,
    "liczba_osob": 2,
    "termin_wprowadzenia": dt.datetime(2023, 2, 27),
    "zwierze": None,
    "liczba_lokali": None,
    "wiadomosc": "Szukamy mieszkania od marca. Pozdrawiam, Przemysław",
    "imie": "Przemysław",
    "utworzono": dt.datetime(2023, 1, 1, 0, 52, tzinfo=dt.timezone(dt.timedelta(hours=1))),
}


def test_opis_leada_zawiera_pola_znane_przy_utworzeniu():
    opis = opis_leada(LEAD)
    for fragment in ["źródło: lokum24", "miasto: Gdańsk", "linia: B2C", "budżet maks.: 2400 zł", "liczba osób: 2"]:
        assert fragment in opis
    assert "Szukamy mieszkania od marca." in opis


def test_termin_podany_w_dniach_od_zapytania_a_nie_jako_data():
    opis = opis_leada(LEAD)
    assert "termin wprowadzenia: 57 dni po zapytaniu" in opis
    assert "2023" not in opis


def test_imie_jest_usuniete_takze_z_tresci_wiadomosci():
    opis = opis_leada(LEAD)
    assert "Przemysław" not in opis
    assert "Pozdrawiam, [imię]" in opis


def test_braki_sa_opisane_jawnie():
    opis = opis_leada({**LEAD, "budzet_max": None, "termin_wprowadzenia": None, "wiadomosc": None})
    assert "budżet maks.: brak" in opis
    assert "termin wprowadzenia: brak" in opis
    assert "zwierzę: brak" in opis
    assert "treść zapytania: brak" in opis


def test_zwierze_tak_nie():
    assert "zwierzę: tak" in opis_leada({**LEAD, "zwierze": True})
    assert "zwierzę: nie" in opis_leada({**LEAD, "zwierze": False})


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute(
        "CREATE TABLE crm_leady AS SELECT 'L' || lpad(i::VARCHAR, 3, '0') AS id_leada, "
        "TIMESTAMPTZ '2025-01-01 10:00:00+01' AS utworzono, 'www' AS zrodlo, 'Łódź' AS miasto, "
        "'B2C' AS linia_pref, 2000 AS budzet_max, 1 AS liczba_osob, TIMESTAMP '2025-02-01' AS termin_wprowadzenia, "
        "NULL::BOOLEAN AS zwierze, NULL::BIGINT AS liczba_lokali, 'pl' AS jezyk, 'Ala' AS imie, 'Dzień dobry' "
        "AS wiadomosc, 30 AS metraz_min, 'utracony' AS status FROM range(50) t(i)"
    )
    yield con
    con.close()


def test_losowanie_jest_powtarzalne_i_bez_powtorzen(con):
    a = losuj_leady(con, n=10, ziarno=1)
    b = losuj_leady(con, n=10, ziarno=1)
    assert list(a["id_leada"]) == list(b["id_leada"])
    assert a["id_leada"].is_unique and len(a) == 10


def test_losowanie_nie_czyta_jezyka_ani_stanu_na_eksport(con):
    kolumny = set(losuj_leady(con, n=5, ziarno=1).columns)
    assert not kolumny & {"jezyk", "status", "metraz_min"}


# --- zgodność dwóch przebiegów --------------------------------------------------------------------------------


def test_zgodnosc_liczy_identyczne_oceny_i_traktuje_blad_jako_niezgodnosc():
    a = {"ocena": 7, "uzasadnienie": "x", "sygnaly": []}
    przebieg_1 = {"L1": a, "L2": a, "L3": a, "L4": a}
    przebieg_2 = {"L1": a, "L2": {**a, "ocena": 8}, "L3": {**a, "uzasadnienie": "y"}, "L4": None}

    z = zgodnosc_dwoch_przebiegow(przebieg_1, przebieg_2)

    assert z["ocena"] == {"identyczne": 2, "leadow": 4, "odsetek": 0.5}
    assert z["ocena_roznica_do_1"]["identyczne"] == 3
    assert z["calosc"]["identyczne"] == 1
