import duckdb
import pandas as pd
import pytest
from api.ai.churn_model.evals.przezycie_grupy import (
    SQL_INDEKSACJA,
    SQL_OKRESY,
    metryki_km,
    roznice_z_zalozeniami,
    sql,
)
from api.ai.features.najemcy.czas_najmu import zbuduj_czas_najmu

# (id_najmu, id_lokalu, id_najemcy, linia, data_wprowadzenia, data_wyprowadzenia, powod_odejscia)
NAJMY = [
    ("N_dwa", "L1", "T1", "B2C", "2022-01-01", "2024-12-31", None),  # dwa przedłużenia: 8% potem 4%
    ("N_szesc", "L2", "T2", "B2B", "2023-03-01", None, None),  # przedłużenie z indeksacją dokładnie 6,0
    ("N_brak", "L3", "T3", "B2C", "2025-05-01", None, None),  # bez przedłużenia
    ("N_pozniej", "L4", "T4", "B2C", "2025-10-15", None, None),  # przedłużenie zaczyna się po eksporcie
    ("N_mid", "L5", "T5", "MID", "2024-01-01", "2024-06-30", None),
]

# (id_umowy, id_najmu, nr_okresu, typ, data_od, data_do, indeksacja_pct)
UMOWY = [
    ("U1", "N_dwa", 1, "pierwsza", "2022-01-01", "2022-12-31", None),
    ("U2", "N_dwa", 2, "przedłużenie", "2023-01-01", "2023-12-31", 8.0),
    ("U3", "N_dwa", 3, "przedłużenie", "2024-01-01", "2024-12-31", 4.0),
    ("U4", "N_szesc", 1, "pierwsza", "2023-03-01", "2024-02-29", None),
    ("U5", "N_szesc", 2, "przedłużenie", "2024-03-01", "2025-02-28", 6.0),
    ("U6", "N_brak", 1, "pierwsza", "2025-05-01", "2026-04-30", None),
    ("U7", "N_pozniej", 1, "pierwsza", "2025-10-15", "2026-10-14", None),
    ("U8", "N_pozniej", 2, "przedłużenie", "2026-10-15", "2027-10-14", 9.0),
    ("U9", "N_mid", 1, "średnioterminowa", "2024-01-01", "2024-06-30", None),
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
    umowy = pd.DataFrame(
        UMOWY, columns=["id_umowy", "id_najmu", "nr_okresu", "typ", "data_od", "data_do", "indeksacja_pct"]
    )
    for df, kolumny in ((najmy, ("data_wprowadzenia", "data_wyprowadzenia")), (umowy, ("data_od", "data_do"))):
        for kolumna in kolumny:
            df[kolumna] = pd.to_datetime(df[kolumna])
    con.register("najmy_df", najmy)
    con.register("umowy_df", umowy)
    con.execute("CREATE TABLE pms_najmy AS SELECT * FROM najmy_df")
    con.execute("CREATE TABLE pms_umowy AS SELECT * FROM umowy_df")
    zbuduj_czas_najmu(con)
    yield con
    con.close()


def test_grupa_z_ostatniego_przedluzenia_do_dnia_eksportu(con):
    wynik = con.execute(sql(SQL_INDEKSACJA)).df().set_index("id_najmu")
    assert wynik.loc["N_dwa", "indeksacja_ostatnia"] == 4.0
    assert wynik.loc["N_dwa", "grupa_indeksacji"] == "<= 6%"
    assert wynik.loc["N_dwa", "przedluzenia"] == 2
    assert wynik.loc["N_szesc", "grupa_indeksacji"] == "<= 6%"
    assert wynik.loc["N_brak", "grupa_indeksacji"] == "bez przedłużenia"
    assert wynik.loc["N_pozniej", "grupa_indeksacji"] == "bez przedłużenia"
    assert "N_mid" not in wynik.index


def test_okresy_przedluzen_czas_od_poczatku_przedluzenia(con):
    wynik = con.execute(sql(SQL_OKRESY)).df().set_index("id_umowy")
    assert set(wynik.index) == {"U2", "U3", "U5"}
    assert wynik.loc["U2", "grupa_indeksacji"] == "> 6%"
    assert wynik.loc["U2", "miesiace"] == pytest.approx(24.0)  # 2023-01-01 – 2024-12-31
    assert wynik.loc["U2", "zdarzenie"] == 1
    assert wynik.loc["U5", "zdarzenie"] == 0  # 2024-03-01 – 2026-09-30 włącznie: dokładnie 31 miesięcy
    assert wynik.loc["U5", "miesiace"] == pytest.approx(31.0)


def test_metryki_km_rmst_do_horyzontu():
    czasy = pd.DataFrame({"miesiace": [2, 4, 6, 8, 10, 12], "zdarzenie": [1, 1, 0, 1, 0, 0]})
    m = metryki_km(czasy, horyzont=12)
    assert m["S_12"] == pytest.approx(4 / 9)
    assert m["S_24"] is None
    assert m["mediana_km"] == pytest.approx(8.0)
    assert m["rmst_km"] == pytest.approx(2 + 2 * 5 / 6 + 4 * 2 / 3 + 4 * 4 / 9)


def test_roznice_z_zalozeniami():
    wynik = roznice_z_zalozeniami({"B2C": {"rmst_km": 30.0}}, {"czas_najmu_mies": {"wartosc": {"B2C": 20.0}}})
    assert wynik["B2C"]["roznica_miesiace"] == pytest.approx(10.0)
    assert wynik["B2C"]["roznica_proc_naiwnej"] == pytest.approx(0.5)
