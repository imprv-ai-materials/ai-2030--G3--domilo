"""Tablica działu technicznego (dev/grafana/, maintenance_bc/panel_techniczny.py) i oceny alertów koordynatora
(adapters/alerty_ocena.py, POST /lifts/alerts/feedback, atrapa Serwisownika /koordynator); docs/b4_panel_techniczny.md.
"""

import json
import re
import sys
from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest
from api.adapters import alerty_ocena, ryzyko_wind
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polacz
from api.contexts_boundaries.maintenance_bc import panel_techniczny as panel

STREFA = "Europe/Warsaw"
KATALOG_GRAFANY = KATALOG_REPO / "dev" / "grafana"


def _moment(tekst: str) -> pd.Timestamp:
    return pd.Timestamp(tekst).tz_localize(STREFA)


# --- wynik alertu i podsumowanie ------------------------------------------------------------------------------------


def test_wynik_alertu_trafny_falszywy_w_toku_i_wyprzedzenie():
    alarmy = pd.DataFrame(
        {
            "dzien": [date(2026, 9, 7), date(2026, 9, 7), date(2026, 9, 7), date(2026, 9, 28), date(2026, 9, 28)],
            "id_windy": ["A", "B", "C", "D", "E"],
        }
    )
    awarie = pd.DataFrame(
        {
            "id_awarii": ["A/1", "B/1", "C/1", "E/1"],
            "id_windy": ["A", "B", "C", "E"],
            "podzespol": ["drzwi", "naped", "drzwi", "sterownik"],
            "start_tz": [
                _moment("2026-09-08 18:00"),  # w oknie: 36 h po alarmie
                _moment("2026-09-07 06:00"),  # dokładnie o 06:00 dnia alarmu: poza oknem (jak dni_wind)
                _moment("2026-09-14 06:00"),  # dokładnie koniec okna: w oknie
                _moment("2026-09-29 10:00"),  # okno otwarte, ale awaria już jest
            ],
        }
    )
    w = panel.wyniki_alertow(alarmy, awarie, stan_danych=_moment("2026-09-30 20:06"))
    assert list(w["wynik"]) == ["trafny", "fałszywy", "trafny", "w toku", "trafny"]
    assert w.loc[0, "wyprzedzenie_h"] == pytest.approx(36.0)
    assert w.loc[2, "wyprzedzenie_h"] == pytest.approx(168.0)
    assert w.loc[4, "podzespol_awarii"] == "sterownik" and np.isnan(w.loc[1, "wyprzedzenie_h"])


def test_podsumowanie_8_tygodni_liczy_precyzje_bez_alarmow_w_toku():
    alerty = pd.DataFrame(
        {
            "dzien": [date(2026, 7, 27), date(2026, 8, 10), date(2026, 8, 10), date(2026, 9, 28), date(2026, 9, 28)],
            "wynik": ["trafny", "trafny", "fałszywy", "trafny", "w toku"],
            "wyprzedzenie_h": [10.0, 20.0, np.nan, 40.0, np.nan],
            "ocena_koordynatora": [None, "trafny", "trafny", None, None],
        }
    )
    p = panel.podsumowanie(alerty).iloc[0]
    assert (p["od_dnia"], p["do_dnia"]) == (date(2026, 8, 4), date(2026, 9, 28))  # 2026-07-27 poza oknem
    assert (p["alarmy"], p["trafne"], p["falszywe"], p["w_toku"]) == (4, 2, 1, 1)
    assert p["precyzja_zamkniete"] == pytest.approx(2 / 3)
    assert p["mediana_wyprzedzenia_h"] == pytest.approx(30.0)
    assert (p["ocenione_przez_koordynatora"], p["ocena_zgodna_z_wynikiem"]) == (2, 1)


def test_windy_budynku_rozstawione_wokol_budynku_a_jedyna_w_jego_punkcie():
    df = pd.DataFrame(
        {
            "id_windy": ["B1-W1", "B1-W2", "B1-W3", "B2-W1"],
            "id_budynku": ["B1"] * 3 + ["B2"],
            "lat": [52.0] * 3 + [50.0],
            "lon": [21.0] * 3 + [19.0],
        }
    )
    r = panel.rozstaw_windy(df).set_index("id_windy")
    assert (r.loc["B2-W1", "lat_windy"], r.loc["B2-W1", "lon_windy"]) == (50.0, 19.0)
    punkty = r.loc[["B1-W1", "B1-W2", "B1-W3"], ["lat_windy", "lon_windy"]].round(7)
    assert len(punkty.drop_duplicates()) == 3
    assert ((punkty["lat_windy"] - 52.0).abs() <= panel.PROMIEN_STOPNIE + 1e-12).all()


# --- oceny koordynatora ---------------------------------------------------------------------------------------------


@pytest.fixture
def baza_alarmow(tmp_path):
    sciezka = tmp_path / "domilo.duckdb"
    con = polacz(sciezka, tylko_odczyt=False)
    ryzyko_wind.utworz(con)
    con.execute(
        f"INSERT INTO {ryzyko_wind.TABELA_ALARMOW} (dzien, pozycja, id_windy, wynik, p_awarii_7d, wersja_modelu, "
        "id_przebiegu, id_zgloszenia, tryb_oceny) "
        "VALUES ('2026-09-21', 1, 'B31-W1', 0.64, 0.67, 'v3', 'p', 'A000025', 'model')"
    )
    con.close()
    return sciezka


def test_ocena_zapis_powtorzenie_poprawka_i_alert_nieznany(baza_alarmow):
    con = polacz(baza_alarmow, tylko_odczyt=False)
    o = alerty_ocena.Ocena(id_windy="B31-W1", dzien=date(2026, 9, 21), ocena="trafny", podzespol="drzwi")
    assert alerty_ocena.zapisz(con, o) == "zapisano"
    assert alerty_ocena.zapisz(con, o) == "powtorzenie"
    zmiana = alerty_ocena.Ocena(id_windy="B31-W1", dzien=date(2026, 9, 21), ocena="falszywy")
    assert alerty_ocena.zapisz(con, zmiana) == "poprawka"
    wiersz = alerty_ocena.oceny(con).iloc[0]
    assert (wiersz["ocena"], wiersz["poprawki"], wiersz["id_zgloszenia"]) == ("falszywy", 1, "A000025")
    with pytest.raises(alerty_ocena.AlertNieznany):
        alerty_ocena.zapisz(con, alerty_ocena.Ocena(id_windy="B01-W1", dzien=date(2026, 9, 21), ocena="trafny"))
    with pytest.raises(ValueError):
        alerty_ocena.zapisz(con, alerty_ocena.Ocena(id_windy="B31-W1", dzien=date(2026, 9, 21), ocena="moze"))
    con.close()
    assert alerty_ocena.rozbij_klucz("B31-W1:2026-09-21") == ("B31-W1", date(2026, 9, 21))
    with pytest.raises(ValueError):
        alerty_ocena.rozbij_klucz("bez-daty")


@pytest.fixture
def serwisownik_z_domilo(tmp_path, baza_alarmow):
    """Atrapa Serwisownika, która przekazuje oceny do api.main (TestClient) z bazą tymczasową."""
    from api.adapters.duckdb_baza import polaczenie
    from fastapi.testclient import TestClient

    from api import main

    def baza_zapis():
        with polaczenie(tylko_odczyt=False, sciezka=baza_alarmow) as con:
            yield con

    main.app.dependency_overrides[main.baza_zapis] = baza_zapis
    sys.path.insert(0, str(KATALOG_REPO / "dev" / "serwisownik_mock"))
    try:
        import app as atrapa
    finally:
        sys.path.pop(0)
        sys.modules.pop("app", None)
    http = TestClient(atrapa.utworz_aplikacje(tmp_path / "stan.json", api_domilo=TestClient(main.app)))
    yield http, atrapa
    main.app.dependency_overrides.clear()


def _zgloszenie(id_windy: str, dzien: str) -> dict:
    return {
        "klucz_idempotencji": f"{id_windy}:{dzien}",
        "id_budynku": id_windy[:3],
        "id_urzadzenia": id_windy,
        "typ_urzadzenia": "winda",
        "kategoria": "przegląd",
        "tresc_zgloszenia": "Drzwi: … Sprawdź operator drzwi i rolki.",
        "alarm": {"id_windy": id_windy, "dzien": dzien, "pozycja": 1, "tryb_oceny": "model"},
    }


def test_koordynator_ocenia_w_serwisowniku_a_ocena_trafia_do_alerty_ocena(serwisownik_z_domilo, baza_alarmow):
    http, atrapa = serwisownik_z_domilo
    assert http.post("/api/zgloszenia", json=_zgloszenie("B31-W1", "2026-09-21")).status_code == 200
    assert http.post("/api/zgloszenia", json=_zgloszenie("B01-W1", "2026-09-21")).status_code == 200
    strona = http.get("/koordynator").text
    assert "B31-W1" in strona and 'name="ocena"' in strona and "fałszywy" in strona
    ocena = {"klucz_idempotencji": "B31-W1:2026-09-21", "ocena": "trafny", "podzespol": "drzwi", "oceniajacy": "K"}
    r = http.post("/api/zgloszenia/ocena", json=ocena)
    assert r.status_code == 200 and r.json()["wynik"] == "zapisano"
    assert http.get("/api/zgloszenia").json()["zgloszenia"]["B31-W1:2026-09-21"]["ocena"]["ocena"] == "trafny"
    # alert, którego Domilo nie zna -> 404 z Domilo, ocena nie zapisana w atrapie
    r = http.post("/api/zgloszenia/ocena", json={**ocena, "klucz_idempotencji": "B01-W1:2026-09-21"})
    assert r.status_code == 404 and "ocena" not in http.get("/api/zgloszenia").json()["zgloszenia"]["B01-W1:2026-09-21"]
    assert http.post("/api/zgloszenia/ocena", json={**ocena, "ocena": "moze"}).status_code == 422
    con = polacz(baza_alarmow)
    wiersz = alerty_ocena.oceny(con).iloc[0]
    con.close()
    assert (wiersz["id_windy"], wiersz["ocena"], wiersz["podzespol"], wiersz["id_zgloszenia"]) == (
        "B31-W1",
        "trafny",
        "drzwi",
        "A000001",  # numer zgłoszenia podaje Serwisownik (atrapa numeruje od A000001)
    )
    assert set(atrapa.PODZESPOLY) == set(alerty_ocena.PODZESPOLY) and set(atrapa.OCENY) == set(alerty_ocena.OCENY)


# --- dane panelu i tablica Grafana -------------------------------------------------------------------------------


def _jest_ryzyko() -> bool:
    if not SCIEZKA_BAZY.exists():
        return False
    con = polacz()
    try:
        return bool(
            con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'ryzyko_wind'").fetchone()[0]
            and con.execute("SELECT count(*) FROM ryzyko_wind").fetchone()[0]
        )
    finally:
        con.close()


@pytest.fixture(scope="module")
def dane_panelu(tmp_path_factory):
    if not _jest_ryzyko():
        pytest.skip("brak ocen w ryzyko_wind (zadanie ryzyko-wind albo ryzyko_wstecz.py)")
    katalog = tmp_path_factory.mktemp("panel")
    liczby = panel.zbuduj_panel(katalog=katalog)
    return katalog, liczby


def test_dane_panelu_maja_wszystkie_tabele_i_szesc_sygnalow(dane_panelu):
    katalog, liczby = dane_panelu
    assert set(liczby) == {
        "windy_ryzyko",
        "ryzyko_historia",
        "sygnaly_30d",
        "alerty",
        "podsumowanie_8_tyg",
        "panel_info",
    }
    assert liczby["windy_ryzyko"] == 140
    s = pd.read_parquet(katalog / "sygnaly_30d.parquet")
    assert s["sygnal"].nunique() == panel.LICZBA_SYGNALOW and s["etykieta"].nunique() == panel.LICZBA_SYGNALOW
    assert (s.groupby(["id_windy", "sygnal"])["czas"].nunique() <= 24 * panel.DNI_SYGNALOW).all()
    a = pd.read_parquet(katalog / "alerty.parquet")
    assert set(a["wynik"]) <= {"trafny", "fałszywy", "w toku"}
    assert (a.loc[a["wynik"] == "trafny", "wyprzedzenie_h"] > 0).all()


def test_zapytania_tablicy_dzialaja_na_plikach_panelu_i_zmienne_sa_cytowane_przez_grafane(dane_panelu):
    katalog, _ = dane_panelu
    szablon = json.loads((KATALOG_GRAFANY / "windy.szablon.json").read_text(encoding="utf-8"))
    zrodlo = (KATALOG_GRAFANY / "provisioning" / "datasources" / "duckdb.yaml").read_text(encoding="utf-8")
    con = duckdb.connect()
    for widok in re.findall(r"CREATE OR REPLACE VIEW (\w+) AS", zrodlo):
        con.execute(f"CREATE VIEW {widok} AS SELECT * FROM read_parquet('{(katalog / widok).as_posix()}.parquet')")
    zmienne = {}
    for v in szablon["templating"]["list"]:
        zmienne[v["name"]] = con.execute(v["query"]).fetchall()[0][0]
    for p in szablon["panels"]:
        for t in p.get("targets", []):
            assert t["format"] in (0, 1), p["title"]  # sqlds: 0 = szereg czasowy, 1 = tabela
            assert "'$" not in t["rawSql"], f"{p['title']}: zmienna w apostrofach (wtyczka sama cytuje)"
            sql = re.sub(
                r"\$\{(\w+):sqlstring\}", lambda m: "'" + str(zmienne[m.group(1)]).replace("'", "''") + "'", t["rawSql"]
            )
            assert len(con.execute(sql).fetchall()) > 0, p["title"]
    con.close()
