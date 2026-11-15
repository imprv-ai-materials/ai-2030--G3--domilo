import duckdb
import pandas as pd
import pytest
from api.ai.features.wycena.ceny_w_opisie import (
    cena_z_opisu,
    czynsz_najmu_z_opisu,
    szablon_ceny,
    wzmianki_o_cenie,
)
from api.ai.features.wycena.grupy_lokali import bez_grup_z_wczesniejszych_zbiorow, grupy_ofert

# --- wzmianki o cenie w opisie ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opis, typy",
    [
        ("Mieszkanie 2 pok. Cena: 414 000 zł. Polecam!", {"kwota"}),
        ("Cena 1305 tys. Blisko tramwaju.", {"kwota"}),
        ("Cena 518 tys. zł. Polecam!", {"kwota"}),
        ("Cena do negocjacji: 605 000. Budynek z windą.", {"kwota"}),
        ("Tylko 17 800 zł/m². Balkon.", {"zl_m2"}),
        ("Rata od 1 880 zł miesięcznie. Balkon.", {"rata"}),
        ("Obniżka z 814 do 761 tys. Balkon.", {"obnizka"}),
        ("Cena: 628 000 zł. Rata od 2 300 zł miesięcznie.", {"kwota", "rata"}),
        ("Do remontu — instalacje do wymiany, cena uwzględnia nakłady. Niski czynsz administracyjny.", set()),
        ("Blok z 1986 roku, zadbana klatka. Balkon 8 m².", set()),
    ],
)
def test_wzmianki_o_cenie_rozpoznaja_kwote_cene_za_m2_rate_i_obnizke(opis, typy):
    assert wzmianki_o_cenie(opis) == typy


def test_spacja_nierozdzielajaca_w_kwocie_tez_jest_kwota():
    assert cena_z_opisu("Cena: 1 220 000 zł.", metraz=50.0) == 1_220_000


@pytest.mark.parametrize(
    "opis, metraz, cena",
    [
        ("Cena: 1 220 000 zł.", 50.0, 1_220_000),
        ("Cena 1305 tys.", 50.0, 1_305_000),
        ("Cena 518 tys. zł.", 50.0, 518_000),
        ("Cena do negocjacji: 397 000.", 50.0, 397_000),
        ("Obniżka z 814 do 761 tys.", 50.0, 761_000),  # cena po obniżce, czyli aktualna
        ("Tylko 17 800 zł/m².", 40.0, 712_000),  # cena za m² × metraż
        ("Rata od 1 880 zł miesięcznie.", 40.0, None),  # z raty nie da się odtworzyć ceny
        ("Balkon 8 m². Niski czynsz administracyjny.", 40.0, None),
    ],
)
def test_cena_z_opisu_w_pln(opis, metraz, cena):
    assert cena_z_opisu(opis, metraz=metraz) == cena


@pytest.mark.parametrize(
    "opis, szablon",
    [
        ("Cena: 414 000 zł.", "cena_zl"),
        ("Cena do negocjacji: 605 000.", "cena_negocjacje"),
        ("Cena 1305 tys.", "cena_tys"),
        ("Obniżka z 814 do 761 tys.", "obnizka"),
        ("Tylko 17 800 zł/m².", "zl_m2"),
        ("Rata od 1 880 zł miesięcznie.", None),
        ("Tylko 10 000 zł/m². Cena: 450 000 zł.", "cena_zl"),
    ],
)
def test_szablon_ceny_wskazuje_zrodlo_ceny_uzytej_przez_cena_z_opisu(opis, szablon):
    assert szablon_ceny(opis) == szablon


def test_kwota_calkowita_ma_pierwszenstwo_przed_cena_za_m2():
    assert cena_z_opisu("Tylko 10 000 zł/m². Cena: 450 000 zł.", metraz=40.0) == 450_000


def test_opis_najmu_domilo_nie_ma_ceny_sprzedazy_tylko_czynsz():
    opis = (
        "Zamieszkaj w Domilo Tarchomin: 2-pokojowe mieszkanie, 37,3 m². Miesięcznie 2 550 zł (plus media wg zużycia)."
    )
    assert cena_z_opisu(opis, metraz=37.3) is None
    assert wzmianki_o_cenie(opis) == set()
    assert czynsz_najmu_z_opisu(opis) == 2_550


@pytest.mark.parametrize(
    "opis, czynsz",
    [
        ("Czynsz 3 540 zł + media.", 3_540),
        ("Czynsz: 3 230 zł/mies. + media.", 3_230),
        ("Miesięcznie 1 850 zł (plus media wg zużycia).", 1_850),
        ("Bez prowizji i bez pośredników.", None),
    ],
)
def test_czynsz_najmu_z_opisu_domilo(opis, czynsz):
    assert czynsz_najmu_z_opisu(opis) == czynsz


# --- grupy ofert (ten sam lokal na kilku portalach) ----------------------------------------------------------------


def _oferty(wiersze: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    df = pd.DataFrame(
        wiersze, columns=["id_oferty", "portal", "data_publikacji", "lat", "lon", "metraz", "pietro"]
    ).assign(data_publikacji=lambda d: pd.to_datetime(d["data_publikacji"]))
    con.register("_oferty", df)
    con.execute("CREATE TABLE radar_oferty AS SELECT * FROM _oferty")
    return con


def _grupy(con) -> dict[str, str]:
    g = grupy_ofert(con)
    return dict(zip(g["id_oferty"], g["id_grupy"]))


def test_ten_sam_lokal_na_dwoch_portalach_w_ciagu_3_dni_to_jedna_grupa():
    g = _grupy(
        _oferty(
            [
                ("A", "lokum24", "2025-03-01 10:00", 52.1, 21.0, 40.0, 2),
                ("B", "domteraz", "2025-03-04 09:00", 52.1, 21.0, 40.0, 2),
            ]
        )
    )
    assert g["A"] == g["B"]


def test_publikacje_rozne_o_wiecej_niz_3_dni_to_osobne_grupy():
    g = _grupy(
        _oferty(
            [
                ("A", "lokum24", "2025-03-01", 52.1, 21.0, 40.0, 2),
                ("B", "domteraz", "2025-03-05", 52.1, 21.0, 40.0, 2),
            ]
        )
    )
    assert g["A"] != g["B"]


@pytest.mark.parametrize("zmiana", [{"metraz": 41.0}, {"pietro": 3}, {"lat": 52.2}, {"lon": 21.1}])
def test_inny_metraz_pietro_lub_wspolrzedne_to_osobne_grupy(zmiana):
    a = dict(id_oferty="A", portal="lokum24", data_publikacji="2025-03-01", lat=52.1, lon=21.0, metraz=40.0, pietro=2)
    b = {**a, "id_oferty": "B", "portal": "domteraz", **zmiana}
    g = _grupy(_oferty([tuple(a.values()), tuple(b.values())]))
    assert g["A"] != g["B"]


def test_kazda_oferta_dostaje_dokladnie_jedna_grupe():
    con = _oferty(
        [
            ("A", "lokum24", "2025-03-01", 52.1, 21.0, 40.0, 2),
            ("B", "domteraz", "2025-03-02", 52.1, 21.0, 40.0, 2),
            ("C", "lokum24", "2025-06-01", 50.0, 19.9, 55.0, 0),
        ]
    )
    g = grupy_ofert(con)
    assert sorted(g["id_oferty"]) == ["A", "B", "C"]
    assert g["id_grupy"].nunique() == 2


# --- rozłączność zbiorów po grupie --------------------------------------------------------------------------------


def test_z_testu_odpada_transakcja_z_grupy_obecnej_w_treningu_lub_walidacji():
    df = pd.DataFrame(
        {
            "id_transakcji": ["T1", "T2", "T3", "T4", "T5"],
            "zbior": ["trening", "walidacja", "test", "test", "test"],
            "id_grupy": ["G1", "G2", "G1", "G2", "G3"],
        }
    )
    wynik = bez_grup_z_wczesniejszych_zbiorow(df)
    assert list(wynik["id_transakcji"]) == ["T1", "T2", "T5"]


def test_z_walidacji_odpada_grupa_z_treningu_a_trening_zostaje_caly():
    df = pd.DataFrame({"id_transakcji": ["T1", "T2"], "zbior": ["trening", "walidacja"], "id_grupy": ["G1", "G1"]})
    assert list(bez_grup_z_wczesniejszych_zbiorow(df)["id_transakcji"]) == ["T1"]
