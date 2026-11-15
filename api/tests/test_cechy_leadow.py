"""Cechy modelu kolejki liczone na moment utworzenia zapytania (api/ai/features/leady/cechy_*.sql)."""

import duckdb
import numpy as np
import pandas as pd
import pytest
from api.ai.features.leady.cechy import KOLUMNY_CECH, RODZINY, zbuduj_cechy
from api.ai.features.leady.podzial_v2 import podziel

# (id_leada, utworzono, zrodlo, miasto, linia_pref, budzet_max, liczba_osob, termin_wprowadzenia, zwierze,
#  id_firmy_b2b, liczba_lokali, wiadomosc)
LEADY = [
    ("L1", "2025-06-10 23:30:00+02", "www", "Łódź", "B2C", 2000, 2, "2025-06-20", True, None, None, "Dzień dobry"),
    ("L2", "2025-05-01 10:00:00+02", "relokacja_b2b", "Kraków", "B2B", None, 1, None, None, "F1", 3, None),
    ("L3", "2025-06-03 10:00:00+02", "relokacja_b2b", "Kraków", "B2B", 3000, 1, None, False, "F1", 1, ""),
    ("L4", "2025-06-03 10:00:00+02", "lokum24", "Kraków", "MID", 1500, 1, None, None, "F2", 1, "abc"),
]
# Kolumny stanu na dzień eksportu celowo „kłamią”: cechy nie mogą od nich zależeć.
STAN = ("umowa", "2026-09-30 10:00:00+02", "D01")

# (id_sesji, id_leada, data_czas, czy_kalkulator, czy_spacer_3d)
SESJE = [
    ("S1", "L1", "2025-06-01 12:00:00+02", True, False),
    ("S2", "L1", "2025-06-10 23:29:00+02", False, False),
    ("S3", "L1", "2025-06-10 23:31:00+02", False, True),  # po utworzeniu: nie liczymy
    ("S4", "L1", "2025-06-12 12:00:00+02", True, True),  # po utworzeniu: nie liczymy
    ("S5", None, "2025-06-01 12:00:00+02", True, True),  # sesja bez zapytania
]

# (id_firmy, umowa_ramowa, data_umowy_ramowej)
FIRMY = [("F1", True, "2025-06-02"), ("F2", False, None)]

# (id_lokalu, id_budynku, czynsz_katalogowy)
LOKALE = [("A", "B1", 1000), ("B", "B1", 3000), ("C", "B1", 2000), ("D", "B2", 2500)]
BUDYNKI = [("B1", "Łódź"), ("B2", "Kraków")]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute(
        "CREATE TABLE crm_leady (id_leada VARCHAR, utworzono TIMESTAMPTZ, zrodlo VARCHAR, miasto VARCHAR, "
        "linia_pref VARCHAR, budzet_max BIGINT, liczba_osob BIGINT, termin_wprowadzenia TIMESTAMP_NS, "
        "zwierze BOOLEAN, id_firmy_b2b VARCHAR, liczba_lokali BIGINT, wiadomosc VARCHAR, status VARCHAR, "
        "data_statusu TIMESTAMPTZ, id_doradcy VARCHAR)"
    )
    con.executemany("INSERT INTO crm_leady VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [r + STAN for r in LEADY])  # fmt: skip
    con.execute(
        "CREATE TABLE www_sesje (id_sesji VARCHAR, id_leada VARCHAR, data_czas TIMESTAMPTZ, "
        "czy_kalkulator BOOLEAN, czy_spacer_3d BOOLEAN)"
    )
    con.executemany("INSERT INTO www_sesje VALUES (?, ?, ?, ?, ?)", SESJE)
    con.execute("CREATE TABLE crm_firmy_b2b (id_firmy VARCHAR, umowa_ramowa BOOLEAN, data_umowy_ramowej TIMESTAMP_NS)")
    con.executemany("INSERT INTO crm_firmy_b2b VALUES (?, ?, ?)", FIRMY)
    con.execute("CREATE TABLE pms_lokale (id_lokalu VARCHAR, id_budynku VARCHAR, czynsz_katalogowy BIGINT)")
    con.executemany("INSERT INTO pms_lokale VALUES (?, ?, ?)", LOKALE)
    con.execute("CREATE TABLE pms_budynki (id_budynku VARCHAR, miasto VARCHAR)")
    con.executemany("INSERT INTO pms_budynki VALUES (?, ?)", BUDYNKI)
    yield con
    con.close()


SYGNALY = pd.DataFrame(
    {"id_leada": ["L1", "L2", "L3"], "sygnaly": ["konkretne_pytania,pilny_termin", "", None]}
).astype({"sygnaly": "string"})


@pytest.fixture
def cechy(con):
    return zbuduj_cechy(con, SYGNALY).set_index("id_leada")


def test_jeden_wiersz_na_zapytanie_i_wszystkie_rodziny(cechy):
    assert sorted(cechy.index) == ["L1", "L2", "L3", "L4"]
    assert set(RODZINY) == {"zapytanie", "budzet", "www", "firma_b2b", "tekst"}
    assert set(KOLUMNY_CECH) <= set(cechy.columns)


def test_brak_kolumn_stanu_crm_w_cechach(cechy):
    assert not {"status", "data_statusu", "id_doradcy", "id_umowy", "powod_utraty"} & set(cechy.columns)


def test_termin_w_dniach_od_dnia_zapytania_w_czasie_warszawskim(cechy):
    # 2025-06-10 23:30 w Warszawie (21:30 UTC): dzień zapytania 10.06, termin 20.06 -> 10 dni
    assert cechy.loc["L1", "termin_dni"] == 10
    assert pd.isna(cechy.loc["L2", "termin_dni"])


def test_budzet_dzielony_przez_mediane_czynszu_w_miescie(cechy):
    assert cechy.loc["L1", "budzet_do_mediany"] == pytest.approx(2000 / 2000)  # Łódź: mediana 1000, 2000, 3000
    assert cechy.loc["L3", "budzet_do_mediany"] == pytest.approx(3000 / 2500)
    assert pd.isna(cechy.loc["L2", "budzet_do_mediany"])


def test_www_tylko_sesje_sprzed_utworzenia(cechy):
    assert cechy.loc["L1", "www_liczba_sesji"] == 2
    assert cechy.loc["L1", "www_kalkulator"] == 1
    assert cechy.loc["L1", "www_spacer_3d"] == 0  # spacer był dopiero po utworzeniu zapytania
    assert cechy.loc["L2", "www_liczba_sesji"] == 0
    assert cechy.loc["L2", "www_kalkulator"] == 0


@pytest.mark.parametrize("id_leada, oczekiwana", [("L2", 0), ("L3", 1), ("L4", 0), ("L1", 0)])
def test_umowa_ramowa_tylko_gdy_obowiazywala_w_chwili_zapytania(cechy, id_leada, oczekiwana):
    # F1 ma umowę ramową od 2025-06-02: L2 (2025-05-01) jeszcze nie, L3 (2025-06-03) już tak
    assert cechy.loc[id_leada, "umowa_ramowa"] == oczekiwana


def test_dlugosc_wiadomosci_brak_to_zero(cechy):
    assert cechy.loc["L1", "dlugosc_wiadomosci"] == len("Dzień dobry")
    assert cechy.loc["L2", "dlugosc_wiadomosci"] == 0


def test_sygnaly_v1_jako_flagi_a_brak_odpowiedzi_to_nan(cechy):
    assert cechy.loc["L1", "syg_konkretne_pytania"] == 1
    assert cechy.loc["L1", "syg_pilny_termin"] == 1
    assert cechy.loc["L1", "syg_relokacja"] == 0
    assert cechy.loc["L2", "syg_konkretne_pytania"] == 0  # odpowiedź bez sygnałów
    assert np.isnan(float(cechy.loc["L3", "syg_konkretne_pytania"]))  # NULL w cache
    assert np.isnan(float(cechy.loc["L4", "syg_konkretne_pytania"]))  # brak w tabeli sygnałów


# --- podział --------------------------------------------------------------------------------------------------


def test_podzial_trening_tylko_zamkniete_bez_okna_test_i_okno_wszystkie():
    t = lambda s: pd.Timestamp(s, tz="Europe/Warsaw")  # noqa: E731
    zbior = pd.DataFrame(
        {
            "id_leada": ["tr", "tr_otwarty", "tr_okno", "tr_2022", "te", "te_otwarty", "po_tescie", "cenz"],
            "utworzono": [t("2024-01-01"), t("2024-01-02"), t("2025-03-10"), t("2022-12-31"), t("2026-03-01"),
                          t("2026-06-30 23:59"), t("2026-07-01"), t("2026-09-01")],  # fmt: skip
            "umowa_45d": [0, 0, 1, 0, 1, 0, 0, None],
            "cenzurowany": [False] * 7 + [True],
            "zamkniety": [True, False, True, True, True, False, True, True],
            "okno_migracji": [False, False, True, False, False, False, False, False],
        }
    )
    zbiory = podziel(zbior)
    assert list(zbiory["trening"]["id_leada"]) == ["tr"]
    assert list(zbiory["test"]["id_leada"]) == ["te", "te_otwarty"]
    assert list(zbiory["okno_migracji"]["id_leada"]) == ["tr_okno"]
