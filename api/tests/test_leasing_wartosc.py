import numpy as np
import pandas as pd
import pytest
from api.adapters.duckdb_baza import KATALOG_REPO, polacz
from api.contexts_boundaries.leasing_bc.wartosc import czynsz_i_czas, wartosc_oczekiwana, wartosc_umow
from api.contexts_boundaries.leasing_bc.zalozenia import wczytaj_zalozenia
from api.contexts_boundaries.leasing_bc.zalozenia_z_danych import policz

ZALOZENIA = {
    "czas_najmu_mies": {"wartosc": {"B2B": 10.0, "B2C": 20.0, "MID": 4.0}},
    "czynsz_mediana_pln": {
        "wartosc": {
            "Łódź": {"B2B": 2000, "B2C": 1500, "MID": None},
            "Warszawa": {"B2B": 3000, "B2C": 2500, "MID": 4000},
        },
        "zastepstwo": {"Łódź/MID": "B2C"},
    },
}


def test_ev_to_p_razy_czynsz_razy_czas_razy_lokale_a_brak_liczby_lokali_to_jeden():
    leady = pd.DataFrame(
        {
            "miasto": ["Warszawa", "Warszawa", "Warszawa"],
            "linia_pref": ["B2B", "B2C", "MID"],
            "liczba_lokali": [3, None, None],
        }
    )
    ev = wartosc_oczekiwana([0.1, 0.2, 0.5], leady, ZALOZENIA)
    np.testing.assert_allclose(ev, [0.1 * 3000 * 10 * 3, 0.2 * 2500 * 20, 0.5 * 4000 * 4])


def test_para_bez_lokali_linii_bierze_czynsz_i_czas_linii_zastepczej():
    leady = pd.DataFrame({"miasto": ["Łódź"], "linia_pref": ["MID"], "liczba_lokali": [None]})
    s = czynsz_i_czas(leady, ZALOZENIA)
    assert (s["linia_wyceny"].iloc[0], s["czynsz"].iloc[0], s["czas_najmu_mies"].iloc[0]) == ("B2C", 1500, 20.0)


def test_brak_czynszu_bez_zastepstwa_to_blad_a_nie_cicha_zero():
    z = {**ZALOZENIA, "czynsz_mediana_pln": {**ZALOZENIA["czynsz_mediana_pln"], "zastepstwo": {}}}
    with pytest.raises(ValueError, match="Łódź/MID"):
        czynsz_i_czas(pd.DataFrame({"miasto": ["Łódź"], "linia_pref": ["MID"], "liczba_lokali": [None]}), z)


def test_wartosc_umow_sumuje_umowy_ramowe_z_czasem_linii_najmu():
    umowy = pd.DataFrame(
        {"id_leada": ["L1", "L1", "L2"], "id_umowy": ["U1", "U2", "U3"], "czynsz": [3000, 2000, 4000],
         "linia": ["B2B", "B2B", "MID"]}  # fmt: skip
    )
    w = wartosc_umow(umowy, ZALOZENIA).set_index("id_leada")
    assert w.loc["L1", "umowy"] == 2 and w.loc["L1", "wartosc_umow"] == (3000 + 2000) * 10
    assert w.loc["L2", "wartosc_umow"] == 4000 * 4


def test_kazde_zalozenie_ma_zrodlo_i_pole_odpowiedzialny():
    for nazwa, pozycja in wczytaj_zalozenia().items():
        assert {"wartosc", "opis", "zrodlo", "odpowiedzialny"} <= set(pozycja), nazwa
    assert wczytaj_zalozenia()["czas_najmu_mies"]["odpowiedzialny"] == "Natalia"


@pytest.mark.skipif(not (KATALOG_REPO / "domilo.duckdb").exists(), reason="brak domilo.duckdb (pypyr baza)")
def test_zalozenia_w_yaml_zgadzaja_sie_z_danymi():
    z = wczytaj_zalozenia()
    dane = policz(polacz())
    assert z["czas_najmu_mies"]["wartosc"] == dane["czas_najmu_mies"]
    assert z["czynsz_mediana_pln"]["wartosc"] == dane["czynsz_mediana_pln"]
    g, gd = z["godziny_doradcow"]["wartosc"], dane["godziny_doradcow"]
    assert (g["okres"], g["dni_pracy"], g["doradcy"]) == (gd["okres"], gd["dni_pracy"], gd["doradcy"])
    assert g["godziny_na_dzien_pracy"] == gd["godziny_na_dzien_pracy"]
