import math

import duckdb
import pytest
from api.ai.features.wycena.geo import KOLUMNY_GEO, cechy_geo

R = 6371008.8
M_NA_STOPIEN = R * math.pi / 180  # metry na 1° szerokości geograficznej (ten sam południk)


def _na_polnoc(lat: float, metry: float) -> float:
    return lat + metry / M_NA_STOPIEN


# Transakcje: (id, miasto, dzielnica, lat, lon)
TRANSAKCJE = [
    ("T_waw", "Warszawa", "D1", 52.0, 21.0),
    ("T_krk", "Kraków", "K1", 50.0, 20.0),
    ("T_gh", "Warszawa", "D1", 57.64911, 10.40744),  # znany geohash: u4pruydqqvj
]
# POI: (id, miasto, typ, lat, lon, powierzchnia_ha) — wszystkie na północ od transakcji, na tym samym południku.
POI = [
    ("P1", "Warszawa", "metro", _na_polnoc(52.0, 690), 21.0, None),
    ("P2", "Warszawa", "kolej", _na_polnoc(52.0, 500), 21.0, None),
    ("P3", "Warszawa", "tramwaj", _na_polnoc(52.0, 301), 21.0, None),
    ("P4", "Warszawa", "park", _na_polnoc(52.0, 100), 21.0, 1.9),  # < 2 ha — pomijany
    ("P5", "Warszawa", "park", _na_polnoc(52.0, 399), 21.0, 2.0),
    ("P6", "Warszawa", "uczelnia", _na_polnoc(52.0, 1000), 21.0, None),
    ("P7", "Warszawa", "autobus", _na_polnoc(52.0, 5), 21.0, None),  # typ bez cechy
    ("P8", "Kraków", "tramwaj", _na_polnoc(52.0, 10), 21.0, None),  # inne miasto — pomijany dla T_waw
    ("P9", "Kraków", "tramwaj", _na_polnoc(50.0, 250), 20.0, None),
    ("P10", "Kraków", "kolej", _na_polnoc(50.0, 3000), 20.0, None),
]
# Dzielnice: (miasto, dzielnica, gestosc, dochod, lat_centrum, lon_centrum)
DZIELNICE = [
    ("Warszawa", "D1", 12000, 118, _na_polnoc(52.0, 2000), 21.0),
    ("Kraków", "K1", 8000, 104, 50.0, 20.0),
]


@pytest.fixture
def wynik():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE rcn_transakcje (id_transakcji VARCHAR, miasto VARCHAR, dzielnica VARCHAR, lat DOUBLE, lon DOUBLE)"
    )
    con.executemany("INSERT INTO rcn_transakcje VALUES (?, ?, ?, ?, ?)", TRANSAKCJE)
    con.execute(
        "CREATE TABLE geo_poi (id_poi VARCHAR, miasto VARCHAR, typ VARCHAR, lat DOUBLE, lon DOUBLE, "
        "powierzchnia_ha DOUBLE)"
    )
    con.executemany("INSERT INTO geo_poi VALUES (?, ?, ?, ?, ?, ?)", POI)
    con.execute(
        "CREATE TABLE gus_dzielnice (miasto VARCHAR, dzielnica VARCHAR, gestosc_os_km2 BIGINT, "
        "wskaznik_dochodu BIGINT, lat_centrum_miasta DOUBLE, lon_centrum_miasta DOUBLE)"
    )
    con.executemany("INSERT INTO gus_dzielnice VALUES (?, ?, ?, ?, ?, ?)", DZIELNICE)
    df = cechy_geo(con).set_index("id_transakcji")
    con.close()
    return df


def test_jeden_wiersz_na_transakcje_z_wszystkimi_kolumnami(wynik):
    assert sorted(wynik.index) == sorted(t[0] for t in TRANSAKCJE)
    assert list(wynik.columns) == list(KOLUMNY_GEO)


def test_odleglosci_haversine_do_najblizszego_punktu_w_tym_samym_miescie(wynik):
    w = wynik.loc["T_waw"]
    assert w["odl_centrum_m"] == pytest.approx(2000, abs=0.01)
    assert w["odl_stacja_m"] == pytest.approx(500, abs=0.01)  # kolej bliżej niż metro
    assert w["odl_metro_m"] == pytest.approx(690, abs=0.01)
    assert w["odl_tramwaj_m"] == pytest.approx(301, abs=0.01)  # tramwaj z Krakowa (10 m) pominięty
    assert w["odl_park_m"] == pytest.approx(399, abs=0.01)  # park 1,9 ha (100 m) pominięty
    assert w["odl_uczelnia_m"] == pytest.approx(1000, abs=0.01)


def test_haversine_na_rownolezniku_uwzglednia_cosinus_szerokosci():
    con = duckdb.connect()
    con.execute("CREATE TABLE rcn_transakcje AS SELECT 'T' id_transakcji, 'A' miasto, 'a' dzielnica, 60.0 lat, 0.0 lon")
    con.execute(
        "CREATE TABLE geo_poi AS SELECT 'P' id_poi, 'A' miasto, 'uczelnia' typ, 60.0 lat, 0.01 lon, "
        "NULL::DOUBLE powierzchnia_ha"
    )
    con.execute(
        "CREATE TABLE gus_dzielnice AS SELECT 'A' miasto, 'a' dzielnica, 1 gestosc_os_km2, 100 wskaznik_dochodu, "
        "60.0 lat_centrum_miasta, 0.0 lon_centrum_miasta"
    )
    odl = cechy_geo(con).loc[0, "odl_uczelnia_m"]
    phi = math.radians(60.0)
    oczekiwana = 2 * R * math.asin(math.cos(phi) * math.sin(math.radians(0.01) / 2))
    assert odl == pytest.approx(oczekiwana, rel=1e-9)


def test_flagi_progow_odleglosci(wynik):
    w = wynik.loc["T_waw"]
    assert (w["metro_do_700m"], w["tramwaj_do_300m"], w["park_do_400m"]) == (1, 0, 1)
    k = wynik.loc["T_krk"]
    assert k["tramwaj_do_300m"] == 1


def test_brak_punktu_danego_typu_w_miescie_daje_null_i_flage_zero(wynik):
    k = wynik.loc["T_krk"]
    assert k["odl_metro_m"] != k["odl_metro_m"]  # NaN: w Krakowie nie ma metra
    assert k["odl_park_m"] != k["odl_park_m"]
    assert (k["metro_do_700m"], k["park_do_400m"]) == (0, 0)
    assert k["odl_stacja_m"] == pytest.approx(3000, abs=0.01)


def test_dane_dzielnicy_z_gus(wynik):
    assert (wynik.loc["T_waw", "gestosc_os_km2"], wynik.loc["T_waw", "wskaznik_dochodu"]) == (12000, 118)
    assert (wynik.loc["T_krk", "gestosc_os_km2"], wynik.loc["T_krk", "wskaznik_dochodu"]) == (8000, 104)


def test_geohash6_zgodny_z_wartoscia_referencyjna(wynik):
    assert wynik.loc["T_gh", "geohash6"] == "u4pruy"
    assert wynik["geohash6"].str.len().eq(6).all()
