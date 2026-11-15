import duckdb
import pandas as pd
import pytest
from api.ai.features.najemcy.migawki import TABELA, migawki_najemcy, zbuduj_migawki_najemcy

# (id_najmu, id_lokalu, id_najemcy, linia, data_wprowadzenia, data_wyprowadzenia, powod_odejscia, wypowiedzenie_data)
NAJMY = [
    ("N_przedluza", "L01", "T_przedluza", "B2C", "2024-05-01", None, None, None),
    ("N_odchodzi", "L02", "T_odchodzi", "B2C", "2024-05-01", "2025-04-30", "cena", "2025-03-15"),
    ("N_wczesniej", "L03", "T_wczesniej", "B2C", "2024-05-01", "2025-04-10", "inne", "2025-02-20"),
    ("N_mid", "L04", "T_mid", "MID", "2025-01-01", "2025-04-30", None, "2025-03-30"),
    ("N_granica_od", "L05", "T_granica_od", "B2C", "2022-03-01", "2023-02-28", None, "2023-01-01"),
    ("N_pierwszy_dzien", "L06", "T_pierwszy_dzien", "B2C", "2022-03-02", "2023-03-01", None, "2023-01-20"),
    ("N_ostatni_dzien", "L07", "T_ostatni_dzien", "B2B", "2025-10-01", "2026-09-30", "warunki", "2026-08-01"),
    ("N_granica_do", "L08", "T_granica_do", "B2C", "2025-10-02", None, None, None),
    ("N_b2b_18m", "L09", "T_b2b_18m", "B2B", "2024-01-01", "2025-06-30", None, "2025-05-01"),
    # Przeprowadzka 10 dni po końcu umowy (do innego lokalu Domilo).
    ("N_przeprowadzka", "L10", "T_przeprowadzka", "B2C", "2024-06-01", "2025-05-31", None, "2025-04-10"),
    ("N_przeprowadzka_nowy", "L11", "T_przeprowadzka", "B2C", "2025-06-10", None, None, None),
    # Kolejny najem 31 dni po końcu: za późno, to odejście i powrót.
    ("N_powrot", "L12", "T_powrot", "B2C", "2024-06-01", "2025-05-31", None, "2025-04-01"),
    ("N_powrot_nowy", "L13", "T_powrot", "B2C", "2025-07-01", None, None, None),
    # Nowy najem dokładnie 60 dni przed końcem (dzień migawki): przeprowadzka.
    ("N_wczesna_przepr", "L14", "T_wczesna_przepr", "B2C", "2024-06-01", "2025-05-31", None, "2025-03-01"),
    ("N_wczesna_przepr_nowy", "L15", "T_wczesna_przepr", "B2C", "2025-04-01", None, None, None),
    # Drugi lokal najęty 61 dni przed końcem: równoległy najem, nie przeprowadzka.
    ("N_rownolegly", "L16", "T_rownolegly", "B2C", "2024-06-01", "2025-05-31", None, "2025-03-31"),
    ("N_rownolegly_drugi", "L17", "T_rownolegly", "B2C", "2025-03-31", None, None, None),
    # Najemca, który przedłuża, ma też krótki najem MID w oknie: to nie przeprowadzka.
    ("N_przedluza_mid", "L18", "T_przedluza", "MID", "2025-04-15", "2025-07-14", None, "2025-06-01"),
]

# (id_umowy, id_najmu, nr_okresu, typ, data_od, data_do, id_umowy_ramowej)
UMOWY = [
    ("U_przedluza_1", "N_przedluza", 1, "pierwsza", "2024-05-01", "2025-04-30", None),
    ("U_przedluza_2", "N_przedluza", 2, "przedłużenie", "2025-05-01", "2026-04-30", None),
    ("U_przedluza_3", "N_przedluza", 3, "przedłużenie", "2026-05-01", "2027-04-30", None),
    ("U_odchodzi", "N_odchodzi", 1, "pierwsza", "2024-05-01", "2025-04-30", None),
    ("U_wczesniej", "N_wczesniej", 1, "pierwsza", "2024-05-01", "2025-04-30", None),
    ("U_mid", "N_mid", 1, "średnioterminowa", "2025-01-01", "2025-04-30", None),
    ("U_granica_od", "N_granica_od", 1, "pierwsza", "2022-03-01", "2023-02-28", None),
    ("U_pierwszy_dzien", "N_pierwszy_dzien", 1, "pierwsza", "2022-03-02", "2023-03-01", None),
    ("U_ostatni_dzien", "N_ostatni_dzien", 1, "pierwsza", "2025-10-01", "2026-09-30", "UR-1"),
    ("U_granica_do", "N_granica_do", 1, "pierwsza", "2025-10-02", "2026-10-01", None),
    ("U_b2b_18m", "N_b2b_18m", 1, "pierwsza", "2024-01-01", "2025-06-30", None),
    ("U_przeprowadzka", "N_przeprowadzka", 1, "pierwsza", "2024-06-01", "2025-05-31", None),
    ("U_przeprowadzka_nowy", "N_przeprowadzka_nowy", 1, "pierwsza", "2025-06-10", "2026-06-09", None),
    ("U_powrot", "N_powrot", 1, "pierwsza", "2024-06-01", "2025-05-31", None),
    ("U_powrot_nowy", "N_powrot_nowy", 1, "pierwsza", "2025-07-01", "2026-06-30", None),
    ("U_wczesna_przepr", "N_wczesna_przepr", 1, "pierwsza", "2024-06-01", "2025-05-31", None),
    ("U_wczesna_przepr_nowy", "N_wczesna_przepr_nowy", 1, "pierwsza", "2025-04-01", "2026-03-31", None),
    ("U_rownolegly", "N_rownolegly", 1, "pierwsza", "2024-06-01", "2025-05-31", None),
    ("U_rownolegly_drugi", "N_rownolegly_drugi", 1, "pierwsza", "2025-03-31", "2026-03-30", None),
    ("U_przedluza_mid", "N_przedluza_mid", 1, "średnioterminowa", "2025-04-15", "2025-07-14", None),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    # Typy jak w Parquecie PMS: daty jako TIMESTAMP_NS.
    con.execute(
        "CREATE TABLE pms_najmy (id_najmu VARCHAR, id_lokalu VARCHAR, id_najemcy VARCHAR, linia VARCHAR, "
        "data_wprowadzenia TIMESTAMP_NS, data_wyprowadzenia TIMESTAMP_NS, powod_odejscia VARCHAR, "
        "wypowiedzenie_data TIMESTAMP_NS)"
    )
    con.executemany("INSERT INTO pms_najmy VALUES (?, ?, ?, ?, ?, ?, ?, ?)", NAJMY)
    con.execute(
        "CREATE TABLE pms_umowy (id_umowy VARCHAR, id_najmu VARCHAR, nr_okresu BIGINT, typ VARCHAR, "
        "data_od TIMESTAMP_NS, data_do TIMESTAMP_NS, data_podpisania TIMESTAMP_NS, czynsz BIGINT, "
        "indeksacja_pct DOUBLE, rabat_mies BIGINT, liczba_lokali BIGINT, id_umowy_ramowej VARCHAR)"
    )
    con.executemany(
        "INSERT INTO pms_umowy VALUES (?, ?, ?, ?, ?, ?, NULL, 2000, NULL, 0, 1, ?)",
        UMOWY,
    )
    return con


@pytest.fixture
def wiersze(con):
    rel = migawki_najemcy(con)
    return {w["id_umowy"]: w for w in rel.df().to_dict("records")}


def test_populacja_umowy_roczne_konczace_sie_w_oknie(wiersze):
    assert set(wiersze) == {
        "U_przedluza_1",  # przedłużona, koniec 2025-04-30
        "U_przedluza_2",  # koniec 2026-04-30
        "U_odchodzi",
        "U_pierwszy_dzien",  # data_do 2023-03-01: pierwszy dzień okna
        "U_ostatni_dzien",  # data_do 2026-09-30: ostatni dzień okna
        "U_b2b_18m",
        "U_przeprowadzka",
        "U_powrot",
        "U_wczesna_przepr",
        "U_rownolegly",
        "U_rownolegly_drugi",  # koniec 2026-03-30, bez kolejnego okresu → odejście (brak wyprowadzki w danych)
        "U_wczesna_przepr_nowy",
        "U_przeprowadzka_nowy",
        "U_powrot_nowy",
    }
    # Pominięte: wcześniejsze rozwiązanie, średnioterminowa, koniec przed 2023-03-01 i po 2026-09-30.
    for pominieta in ("U_wczesniej", "U_mid", "U_granica_od", "U_granica_do", "U_przedluza_3"):
        assert pominieta not in wiersze


def test_odejdzie_przedluzenie_i_odejscie(wiersze):
    assert wiersze["U_przedluza_1"]["odejdzie"] == 0
    assert wiersze["U_przedluza_1"]["id_umowy_nastepnej"] == "U_przedluza_2"
    # Przeprowadzkę liczymy tylko wtedy, gdy najem nie ma kolejnego okresu.
    assert not wiersze["U_przedluza_1"]["przeprowadzka"]
    assert pd.isna(wiersze["U_przedluza_1"]["id_najmu_przeprowadzki"])
    assert wiersze["U_odchodzi"]["odejdzie"] == 1
    assert wiersze["U_odchodzi"]["powod_odejscia"] == "cena"
    assert wiersze["U_ostatni_dzien"]["odejdzie"] == 1


def test_przeprowadzka_do_innego_lokalu_to_przedluzenie(wiersze):
    w = wiersze["U_przeprowadzka"]
    assert (w["odejdzie"], w["przeprowadzka"], w["id_najmu_przeprowadzki"]) == (0, True, "N_przeprowadzka_nowy")
    assert wiersze["U_wczesna_przepr"]["odejdzie"] == 0
    assert wiersze["U_wczesna_przepr"]["przeprowadzka"]
    # Kolejny najem 31 dni po końcu albo zaczęty przed dniem migawki nie jest przeprowadzką.
    assert wiersze["U_powrot"]["odejdzie"] == 1
    assert not wiersze["U_powrot"]["przeprowadzka"]
    assert wiersze["U_rownolegly"]["odejdzie"] == 1


def test_migawka_60_dni_przed_koncem_i_wypowiedzenie(wiersze):
    w = wiersze["U_odchodzi"]
    assert str(w["data_migawki"])[:10] == "2025-03-01"
    assert str(w["miesiac_konca"])[:10] == "2025-04-01"
    # Wypowiedzenie 2025-03-15 jest po dniu migawki (2025-03-01): w migawce go jeszcze nie ma.
    assert not w["wypowiedzenie_przed_migawka"]
    # Wypowiedzenie 2025-03-31 wobec migawki 2025-04-01: już złożone.
    assert wiersze["U_rownolegly"]["wypowiedzenie_przed_migawka"]
    # Wypowiedzenie w dniu migawki (2025-04-01) się nie liczy: migawka to stan na początek tego dnia.
    assert not wiersze["U_powrot"]["wypowiedzenie_przed_migawka"]
    assert not wiersze["U_przedluza_1"]["wypowiedzenie_przed_migawka"]


def test_dlugosc_umowy_w_miesiacach(wiersze):
    assert wiersze["U_odchodzi"]["miesiecy_umowy"] == 12
    assert wiersze["U_b2b_18m"]["miesiecy_umowy"] == 18
    assert wiersze["U_ostatni_dzien"]["id_umowy_ramowej"] == "UR-1"


def test_jeden_wiersz_na_umowe_i_zapis_tabeli(con):
    liczba = zbuduj_migawki_najemcy(con)
    assert liczba == 14
    assert con.execute(f"SELECT count(DISTINCT id_umowy) FROM {TABELA}").fetchone()[0] == liczba
