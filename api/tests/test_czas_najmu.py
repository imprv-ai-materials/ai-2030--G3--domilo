import duckdb
import pandas as pd
import pytest
from api.ai.churn_model.evals.przezycie import krzywa_km, podsumowanie_przezycia
from api.ai.features.najemcy.czas_najmu import TABELA, zbuduj_czas_najmu

# (id_najmu, id_lokalu, id_najemcy, linia, data_wprowadzenia, data_wyprowadzenia, powod_odejscia)
NAJMY = [
    # Pełna umowa 12-miesięczna (rok przestępny w środku): dokładnie 12 miesięcy, 366 dni.
    ("N_zak", "L01", "T01", "B2C", "2019-09-08", "2020-09-07", "cena"),
    # Aktywny w dniu eksportu: cenzura na 2026-09-30 włącznie (16 dni z 30 dni do 2026-10-15).
    ("N_akt", "L02", "T02", "B2C", "2026-09-15", None, None),
    # Średnioterminowy: poza populacją.
    ("N_mid", "L03", "T03", "MID", "2025-01-01", "2025-04-30", None),
    # Wprowadzenie po dniu eksportu: brak czasu obserwacji, poza populacją.
    ("N_przyszly", "L04", "T04", "B2C", "2026-10-05", None, None),
    # Wprowadzenie w dniu eksportu: 1 dzień z 30 (do 2026-10-30).
    ("N_eksport", "L05", "T05", "B2B", "2026-09-30", None, None),
    # Start 31. dnia miesiąca: umowa do 2024-01-30 to też 12 miesięcy; import PMS (przed 2023-03-01).
    ("N_31", "L06", "T06", "B2C", "2023-01-31", "2024-01-30", None),
    # Rozwiązanie w trakcie umowy: 5 pełnych miesięcy + 15 z 31 dni sierpnia.
    ("N_wczesniej", "L07", "T07", "B2B", "2024-03-01", "2024-08-15", "inne"),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    najmy = pd.DataFrame(
        NAJMY,
        columns=[
            "id_najmu",
            "id_lokalu",
            "id_najemcy",
            "linia",
            "data_wprowadzenia",
            "data_wyprowadzenia",
            "powod_odejscia",
        ],
    )
    for kolumna in ("data_wprowadzenia", "data_wyprowadzenia"):
        najmy[kolumna] = pd.to_datetime(najmy[kolumna])
    con.register("najmy_df", najmy)
    con.execute("CREATE TABLE pms_najmy AS SELECT * FROM najmy_df")
    yield con
    con.close()


@pytest.fixture
def wynik(con):
    zbuduj_czas_najmu(con)
    return con.execute(f"SELECT * FROM {TABELA}").df().set_index("id_najmu")


def test_populacja_tylko_najmy_roczne_rozpoczete_do_dnia_eksportu(wynik):
    assert set(wynik.index) == {"N_zak", "N_akt", "N_eksport", "N_31", "N_wczesniej"}


def test_zdarzenie_i_data_konca(wynik):
    assert wynik.loc["N_zak", "zdarzenie"] == 1
    assert wynik.loc["N_wczesniej", "zdarzenie"] == 1
    assert wynik.loc["N_akt", "zdarzenie"] == 0
    assert str(wynik.loc["N_akt", "data_konca"])[:10] == "2026-09-30"
    assert str(wynik.loc["N_zak", "data_konca"])[:10] == "2020-09-07"


def test_dni_licza_oba_konce_wlacznie(wynik):
    assert wynik.loc["N_zak", "dni"] == 366
    assert wynik.loc["N_akt", "dni"] == 16
    assert wynik.loc["N_eksport", "dni"] == 1


def test_miesiace_kalendarzowe_z_ulamkiem(wynik):
    assert wynik.loc["N_zak", "miesiace"] == pytest.approx(12.0)
    assert wynik.loc["N_31", "miesiace"] == pytest.approx(12.0)
    assert wynik.loc["N_akt", "miesiace"] == pytest.approx(16 / 30)
    assert wynik.loc["N_eksport", "miesiace"] == pytest.approx(1 / 30)
    assert wynik.loc["N_wczesniej", "miesiace"] == pytest.approx(5 + 15 / 31)


def test_import_pms(wynik):
    assert bool(wynik.loc["N_31", "import_pms"]) is True
    assert bool(wynik.loc["N_wczesniej", "import_pms"]) is False


# Ręcznie: S(2) = 5/6, S(4) = 5/6 · 4/5 = 2/3, cenzura w 6, S(8) = 2/3 · 2/3 = 4/9 < 0,5 → mediana 8.
CZASY = pd.DataFrame({"miesiace": [2, 4, 6, 8, 10, 12], "zdarzenie": [1, 1, 0, 1, 0, 0]})


def test_podsumowanie_trzech_liczb():
    p = podsumowanie_przezycia(CZASY)
    assert p["najmy"] == 6
    assert p["cenzurowane"] == 3
    assert p["odsetek_cenzurowanych"] == pytest.approx(0.5)
    assert p["srednia_zakonczone"] == pytest.approx((2 + 4 + 8) / 3)
    assert p["srednia_staz_jako_koniec"] == pytest.approx(42 / 6)
    assert p["mediana_km"] == pytest.approx(8.0)


def test_rmst_i_srednie_ograniczone_do_horyzontu():
    # Pole pod krzywą do 12: 2·1 + 2·5/6 + 4·2/3 + 4·4/9.
    p = podsumowanie_przezycia(CZASY, horyzont_rmst=12)
    assert p["rmst_km"] == pytest.approx(2 + 2 * 5 / 6 + 4 * 2 / 3 + 4 * 4 / 9)
    p = podsumowanie_przezycia(CZASY, horyzont_rmst=5)
    assert p["srednia_zakonczone_do_horyzontu"] == pytest.approx((2 + 4 + 5) / 3)
    assert p["srednia_staz_jako_koniec_do_horyzontu"] == pytest.approx((2 + 4 + 5 * 4) / 6)


def test_przezycie_po_progu_i_tuz_przed():
    p = podsumowanie_przezycia(CZASY)
    assert p["km_trwa_dluzej_niz"]["12"] == pytest.approx(4 / 9)
    assert p["km_tuz_przed"]["12"] == pytest.approx(4 / 9)
    assert p["km_trwa_dluzej_niz"]["24"] is None


def test_krzywa_km_zgodna_z_recznym_liczeniem():
    km = krzywa_km(CZASY)
    s = km.survival_function_.iloc[:, 0]
    assert s.loc[2] == pytest.approx(5 / 6)
    assert s.loc[4] == pytest.approx(2 / 3)
    assert s.loc[8] == pytest.approx(4 / 9)
