"""Alerty o awariach wind w produkcji: magazyn okien Telemetry, cechy dnia (te same SQL co trening), ryzyko,
reguła alarmu z przerwą liczoną z tabeli, zgłoszenia w Serwisowniku i GET /lifts/{id}/risk (docs/b4_ryzyko_dzienne.md).
"""

import json
import shutil
import sys
from datetime import date, datetime, timedelta, timezone

import inngest
import numpy as np
import pandas as pd
import pytest
from api.adapters import ryzyko_wind, serwisownik_alarmy, telemetra
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polacz, polaczenie
from api.contexts_boundaries.maintenance_bc import (
    alarmy_wind,
    cechy_dzienne,
    ryzyko_dzienne,
    telemetria_biezaca,
    wyjasnienie,
)

JEST_BAZA = SCIEZKA_BAZY.exists()
PON = "2026-09-21"  # poniedziałek z telemetrią w eksporcie


def _okna(windy: list[str], od: str, n: int, kursy: int = 1) -> pd.DataFrame:
    ts = pd.date_range(pd.Timestamp(od, tz="UTC"), periods=n, freq="10min")
    wiersze = []
    for w in windy:
        for t in ts:
            wiersz = {k: None for k in telemetra.KOLUMNY}
            wiersz.update(id_windy=w, ts_utc=t, kursy=kursy, tryb="normalny", firmware="LF-4.1", prad_silnika_sr_a=1.5)
            wiersze.append(wiersz)
    return pd.DataFrame(wiersze)


# --- magazyn Telemetry -----------------------------------------------------------------------------------------


def test_magazyn_dopisuje_idempotentnie_po_windzie_i_ts_a_konflikt_zostawia_pierwsza_wersje(tmp_path):
    m = telemetra.MagazynTelemetrii(tmp_path)
    okna = _okna(["W1", "W2"], "2026-10-31T23:30:00", 6)  # przełom miesięcy (UTC) -> dwie partycje
    pierwszy = m.dopisz(okna)
    assert (pierwszy["nowe"], pierwszy["powtorzenia"], pierwszy["konflikty"]) == (12, 0, 0)
    assert [p.parent.name for p in m.pliki()] == ["miesiac=10", "miesiac=11"]
    assert m.dopisz(okna)["nowe"] == 0 and m.dopisz(okna)["powtorzenia"] == 12
    zmienione = okna.head(2).assign(kursy=7)
    wynik = m.dopisz(zmienione)
    assert (wynik["nowe"], wynik["konflikty"]) == (0, 2)
    stare = m.wczytaj_miesiac(2026, 10)
    assert set(stare["kursy"]) == {1}  # pierwsza wersja zostaje
    assert m.ostatnie_okno() == pd.Timestamp("2026-11-01T00:20:00", tz="UTC")


def test_magazyn_odrzuca_okna_poza_siatka_10_minut_i_bez_windy(tmp_path):
    okna = _okna(["W1"], "2026-10-01T00:00:00", 3)
    okna.loc[0, "ts_utc"] = pd.Timestamp("2026-10-01T00:03:00", tz="UTC")
    okna.loc[1, "id_windy"] = None
    wynik = telemetra.MagazynTelemetrii(tmp_path).dopisz(okna)
    assert (wynik["odrzucone"], wynik["nowe"]) == (2, 1)


def test_zrodlo_laczy_eksport_z_magazynem_bez_podwojenia_okien(tmp_path):
    eksport = tmp_path / "eksport" / "rok=2026" / "miesiac=10"
    eksport.mkdir(parents=True)
    _okna(["W1"], "2026-10-01T00:00:00", 3).pipe(telemetra.ujednolic)[0].to_parquet(eksport / "part-0.parquet")
    m = telemetra.MagazynTelemetrii(tmp_path / "magazyn")
    m.dopisz(_okna(["W1"], "2026-10-01T00:10:00", 4))  # 2 okna wspólne z eksportem, 2 nowe
    con = polacz(tmp_path / "x.duckdb", tylko_odczyt=False)
    widok = telemetra.utworz_widok_zrodla(con, m, katalog_eksportu=tmp_path / "eksport")
    n, unikalne = con.execute(f"SELECT count(*), count(DISTINCT (id_windy, ts_utc)) FROM {widok}").fetchone()
    con.close()
    assert n == unikalne == 5


def test_zakres_od_ostatniego_okna_minus_zakladka_a_zaleglosc_nadrabiana_po_24_h(tmp_path):
    m = telemetra.MagazynTelemetrii(tmp_path / "m")
    m.dopisz(_okna(["W1"], "2026-11-16T04:00:00", 1))
    pusty_eksport = str(tmp_path / "brak")
    z = telemetria_biezaca.krok_zakres(None, None, str(tmp_path / "m"), "2026-11-16T04:47:00+00:00", pusty_eksport)
    assert z["od"] == "2026-11-16T03:00:00+00:00" and z["do"] == "2026-11-16T04:40:00+00:00"
    z = telemetria_biezaca.krok_zakres(None, None, str(tmp_path / "m"), "2026-11-20T00:00:00+00:00", pusty_eksport)
    assert pd.Timestamp(z["do"]) - pd.Timestamp(z["od"]) == telemetria_biezaca.MAKS_ZAKRES
    assert len(z["kawalki"]) == 4


def test_zadanie_okien_drugi_raz_niczego_nie_dopisuje(tmp_path):
    class Zrodlo:
        def pobierz_okna(self, od, do):
            okna = _okna(["W1", "W2"], "2026-11-16T00:00:00", 6)
            return okna[(okna["ts_utc"] > od) & (okna["ts_utc"] <= do)]

    krok = lambda _id, h, *a: h(*a)  # noqa: E731
    args = ("2026-11-15T23:50:00+00:00", "2026-11-16T01:00:00+00:00", str(tmp_path))
    pierwszy = telemetria_biezaca.wykonaj_telemetre_okna(krok, *args, zrodlo=Zrodlo())
    drugi = telemetria_biezaca.wykonaj_telemetre_okna(krok, *args, zrodlo=Zrodlo())
    assert (pierwszy["nowe"], drugi["nowe"], drugi["powtorzenia"]) == (12, 0, 12)
    json.dumps(pierwszy)  # wynik kroku musi być JSON-em (Inngest)


def test_zrodlo_eksportu_zwraca_okna_z_przedzialu_lewostronnie_otwartego():
    od = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
    okna = telemetra.ZrodloEksportu().pobierz_okna(od, od + timedelta(minutes=20))
    assert set(okna["ts_utc"]) == {pd.Timestamp(od) + timedelta(minutes=10), pd.Timestamp(od) + timedelta(minutes=20)}
    assert okna["id_windy"].nunique() == 140


# --- reguła alarmu i wyjaśnienie -------------------------------------------------------------------------------


def test_przerwa_liczy_alarmy_zapisane_wczesniej():
    r = pd.DataFrame({"id_windy": ["A", "B", "C"], "dzien": [pd.Timestamp(PON)] * 3, "ryzyko": [0.9, 0.5, 0.1]})
    poprzednie = pd.DataFrame({"id_windy": ["A"], "dzien": [pd.Timestamp(PON) - pd.Timedelta(days=7)]})
    a = alarmy_wind.wybierz_alarmy(r, limit=2, przerwa_dni=7, poprzednie=poprzednie)
    assert list(a["id_windy"]) == ["B", "C"]
    dawne = poprzednie.assign(dzien=pd.Timestamp(PON) - pd.Timedelta(days=14))
    assert list(alarmy_wind.wybierz_alarmy(r, limit=2, przerwa_dni=7, poprzednie=dawne)["id_windy"]) == ["A", "B"]


def test_winda_ktora_stoi_nie_dostaje_alarmu():
    r = pd.DataFrame(
        {"id_windy": ["A", "B", "C", "D"], "dzien": [PON] * 4, "wynik": [0.9, 0.8, 0.7, 0.6], "stoi": [True, 0, 0, 0]}
    )
    a = ryzyko_dzienne.wybierz_alarmy_dnia(r, pd.DataFrame(), alarmy_wind.wczytaj_zalozenia())
    assert list(a["id_windy"]) == ["B", "C", "D"]
    wtorek = r.assign(dzien="2026-09-22")
    assert ryzyko_dzienne.wybierz_alarmy_dnia(wtorek, pd.DataFrame(), alarmy_wind.wczytaj_zalozenia()).empty


def test_wyjasnienie_grupuje_wklady_po_sygnalach_i_wskazuje_podzespoly():
    cechy = pd.Series({"drzwi_bledy_max_24h": 3.0, "drzwi_bledy_sr_24h": 0.5, "ts_naped_prad_rms": 2.0})
    wklady = pd.Series(
        {
            "wklad_drzwi_bledy_max_24h": 0.4,
            "wklad_drzwi_bledy_sr_24h": 0.3,
            "wklad_ts_naped_prad_rms": 0.5,
            "wklad_uzycie_kursy_sr_24h": 0.2,
            "wklad_wibracje_rms_max_3d": -0.9,
            "wklad_staly": -3.0,
        }
    )
    w = wyjasnienie.wyjasnij(cechy, wklady)
    assert [s["sygnal"] for s in w["sygnaly"]] == ["drzwi_bledy", "naped_prad_sr", "uzycie_kursy"]
    assert w["sygnaly"][0]["wklad"] == pytest.approx(0.7) and w["sygnaly"][0]["cecha"] == "drzwi_bledy_max_24h"
    assert w["sygnaly"][0]["wartosc"] == 3.0
    assert [p["podzespol"] for p in w["podzespoly"]] == ["drzwi", "naped"]  # wibracje < 0, użycie bez podzespołu


def test_kazda_cecha_aktywnego_modelu_ma_sygnal_a_kazdy_sygnal_wpis_o_podzespolach():
    from api.ai.failure_model.base import wczytaj_obecny

    sygnaly = {wyjasnienie.sygnal_cechy(c) for c in wczytaj_obecny().cechy}
    assert sygnaly == set(wyjasnienie.podzespoly_sygnalow())
    dozwolone = set(alarmy_wind.PODZESPOLY_Z_SYGNALEM)
    assert all(set(p) <= dozwolone for p in wyjasnienie.podzespoly_sygnalow().values())


# --- Serwisownik ----------------------------------------------------------------------------------------------


@pytest.fixture
def serwisownik(tmp_path):
    from fastapi.testclient import TestClient

    sys.path.insert(0, str(KATALOG_REPO / "dev" / "mock_serwisownik"))
    try:
        from app import utworz_aplikacje
    finally:
        sys.path.pop(0)
        sys.modules.pop("app", None)
    http = TestClient(utworz_aplikacje(tmp_path / "stan.json"))
    return serwisownik_alarmy.KlientSerwisownika(url="http://testserver", http=http), http


def _zgloszenie(pozycja: int = 1) -> dict:
    return {
        "id_budynku": "B01",
        "id_urzadzenia": "B01-W1",
        "typ_urzadzenia": "winda",
        "kategoria": "przegląd",
        "alarm": {"id_windy": "B01-W1", "dzien": PON, "pozycja": pozycja},
    }


def test_serwisownik_zaklada_zgloszenie_raz_a_inna_tresc_to_konflikt(serwisownik):
    klient, http = serwisownik
    pierwsze = klient.zglos_alarm(_zgloszenie())
    assert pierwsze == {"id_zgloszenia": "A000001", "utworzono": True}
    assert klient.zglos_alarm(_zgloszenie()) == {"id_zgloszenia": "A000001", "utworzono": False}
    with pytest.raises(serwisownik_alarmy.KonfliktIdempotencji):
        klient.zglos_alarm(_zgloszenie(pozycja=2))
    assert http.get("/api/zgloszenia").json()["liczba"] == 1


# --- Inngest ---------------------------------------------------------------------------------------------------


def test_trzy_osobne_funkcje_inngest_z_harmonogramem_i_zdarzeniem():
    from api import inngest_app

    oczekiwane = {
        "telemetra-okna": ("*/10 * * * *", "domilo/telemetra.okna"),
        "cechy-wind": ("TZ=Europe/Warsaw 50 5 * * *", "domilo/windy.cechy"),
        "ryzyko-wind": ("TZ=Europe/Warsaw 0 6 * * *", "domilo/windy.ryzyko"),
    }
    for fn in inngest_app.FUNKCJE:
        if fn.local_id in oczekiwane:
            wyzwalacze = [
                t.model_dump(exclude_none=True) for t in fn.get_config("http://app:8101/api/inngest").main.triggers
            ]
            cron, zdarzenie = oczekiwane.pop(fn.local_id)
            assert wyzwalacze == [{"cron": cron}, {"event": zdarzenie}]
    assert not oczekiwane


# --- na bazie domilo.duckdb ------------------------------------------------------------------------------------


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb (pypyr baza)")
@pytest.mark.parametrize("dzien", [date(2026, 9, 21), date(2024, 3, 31)])  # 2024-03-31: zmiana czasu
def test_cechy_dnia_takie_same_jak_tabele_treningowe(dzien):
    from api.ai.features.windy.cechy import cechy_dnia
    from api.ai.features.windy.tsfresh_cechy import cechy_tsfresh_dnia

    with polaczenie() as con:
        pary = [
            (cechy_dnia(con, dzien), con.execute("SELECT * FROM cechy_windy WHERE dzien = ?", [dzien]).df()),
            (
                cechy_tsfresh_dnia(con, dzien),
                con.execute("SELECT * FROM cechy_windy_tsfresh WHERE dzien = ?", [dzien]).df(),
            ),
        ]
    for dnia, trening in pary:
        assert len(trening) > 100 and set(trening["id_windy"]) <= set(dnia["id_windy"])
        kol = [k for k in trening.columns if k not in ("id_windy", "dzien")]
        a = dnia.set_index("id_windy").loc[trening["id_windy"], kol].astype(float).to_numpy()
        b = trening[kol].astype(float).to_numpy()
        assert np.allclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=True)


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb (pypyr baza)")
def test_kompletnosc_czeka_na_okno_0550_tylko_w_dniu_oceny_przed_0558(tmp_path):
    # eksport kończy się 2026-10-01 00:00 czasu Warszawy: okna 05:50 tego dnia nie ma dla żadnej windy
    with pytest.raises(inngest.RetryAfterError):
        cechy_dzienne.krok_kompletnosc("2026-10-01", str(tmp_path), SCIEZKA_BAZY, "2026-10-01T05:52:00+02:00")
    wynik = cechy_dzienne.krok_kompletnosc("2026-10-01", str(tmp_path), SCIEZKA_BAZY, "2026-10-01T05:59:00+02:00")
    assert wynik["bez_okna_odciecia"] == wynik["windy"] == 140
    assert cechy_dzienne.krok_kompletnosc(PON, str(tmp_path), SCIEZKA_BAZY)["bez_okna_odciecia"] == 0


class _Klient:
    def __init__(self):
        self.wyslane: dict[str, dict] = {}

    def zglos_alarm(self, z: dict) -> dict:
        klucz = serwisownik_alarmy.klucz_idempotencji(z["alarm"]["id_windy"], z["alarm"]["dzien"])
        if klucz in self.wyslane:
            assert self.wyslane[klucz] == z  # ponowny przebieg = ta sama treść
            return {"id_zgloszenia": f"Z-{klucz}", "utworzono": False}
        self.wyslane[klucz] = z
        return {"id_zgloszenia": f"Z-{klucz}", "utworzono": True}


@pytest.fixture(scope="module")
def przebiegi(tmp_path_factory):
    """Kopia bazy; cechy i ryzyko: poniedziałek PON (dwa razy), wtorek i następny poniedziałek."""
    if not JEST_BAZA:
        pytest.skip("brak domilo.duckdb (pypyr baza)")
    kat = tmp_path_factory.mktemp("windy")
    baza = kat / "domilo.duckdb"
    shutil.copy(SCIEZKA_BAZY, baza)
    krok = lambda _id, h, *a: json.loads(json.dumps(h(*a)))  # noqa: E731 — jak Inngest: wynik kroku to JSON
    klient = _Klient()
    wyniki = {}
    for nazwa, dzien in [("pon", PON), ("pon2", PON), ("wt", "2026-09-22"), ("pon_nast", "2026-09-28")]:
        cechy_dzienne.wykonaj_cechy_wind(krok, dzien, str(kat / "magazyn"), baza, kat / "dzienne")
        wyniki[nazwa] = ryzyko_dzienne.wykonaj_ryzyko_wind(krok, nazwa, dzien, baza, kat / "dzienne", klient)
    return {"baza": baza, "klient": klient, **wyniki}


def test_poniedzialek_trzy_alarmy_w_serwisowniku_a_ponowny_przebieg_ich_nie_zmienia(przebiegi):
    pon, pon2 = przebiegi["pon"], przebiegi["pon2"]
    assert pon["ryzyko"]["windy"] == 140 and pon["ryzyko"]["wersja_modelu"] == "v3_punkt_pracy"
    assert len(pon["alarmy"]["alarmy"]) == 3 and pon["alarmy"]["zapisano_teraz"]
    assert [s["utworzono"] for s in pon["serwisownik"]] == [True] * 3
    assert not pon2["alarmy"]["zapisano_teraz"]
    assert [s["utworzono"] for s in pon2["serwisownik"]] == [False] * 3
    assert len(przebiegi["klient"].wyslane) == 3 + len(przebiegi["pon_nast"]["alarmy"]["alarmy"])
    with polaczenie(sciezka=przebiegi["baza"]) as con:
        a = ryzyko_wind.alarmy(con, date.fromisoformat(PON), date.fromisoformat(PON))
    assert a["id_zgloszenia"].notna().all()


def test_wtorek_bez_alarmow_a_nastepny_poniedzialek_bez_wind_z_przerwy(przebiegi):
    assert przebiegi["wt"]["alarmy"]["alarmy"] == [] and przebiegi["wt"]["ryzyko"]["windy"] == 140
    poprzednie = {a["id_windy"] for a in przebiegi["pon"]["alarmy"]["alarmy"]}
    nast = przebiegi["pon_nast"]["alarmy"]
    assert set(nast["w_przerwie"]) == poprzednie
    assert len(nast["alarmy"]) == 3 and not poprzednie & {a["id_windy"] for a in nast["alarmy"]}


def test_ryzyko_dnia_to_samo_co_model_na_zbiorze_treningowym(przebiegi):
    from api.ai.failure_model.base import wczytaj_obecny
    from api.ai.features.windy.zbior import wczytaj_zbior

    with polaczenie(sciezka=przebiegi["baza"]) as con:
        zbior, _ = wczytaj_zbior(con)
        dnia = con.execute("SELECT id_windy, wynik FROM ryzyko_wind WHERE dzien = ?", [date.fromisoformat(PON)]).df()
    wiersze = zbior[zbior["dzien"] == pd.Timestamp(PON)].reset_index(drop=True)
    oczekiwane = pd.Series(wczytaj_obecny().predict(wiersze), index=wiersze["id_windy"])
    assert np.allclose(dnia.set_index("id_windy").loc[oczekiwane.index, "wynik"], oczekiwane, atol=1e-7)


def test_endpoint_ryzyka_windy(przebiegi):
    from fastapi.testclient import TestClient

    from api import main

    def baza():
        with polaczenie(sciezka=przebiegi["baza"]) as con:
            yield con

    main.app.dependency_overrides[main.baza] = baza
    try:
        klient = TestClient(main.app)
        [pierwszy] = [a for a in przebiegi["pon"]["alarmy"]["alarmy"] if a["pozycja"] == 1]
        r = klient.get(f"/lifts/{pierwszy['id_windy']}/risk", params={"dzien": PON})
        assert r.status_code == 200, r.text
        w = r.json()
        assert w["dzien_oceny"] == PON and w["moment_oceny"].startswith(f"{PON}T06:00:00")
        assert 0 <= w["ryzyko"] <= 1 and w["ranga"] == 1 and w["ocenione_windy"] == 140
        assert 1 <= len(w["sygnaly"]) <= 3 and all(s["wklad"] > 0 for s in w["sygnaly"])
        assert w["podzespoly"] and w["alarm"]["pozycja"] == 1 and w["alarm"]["id_zgloszenia"]
        najnowsza = klient.get(f"/lifts/{pierwszy['id_windy']}/risk").json()
        assert najnowsza["dzien_oceny"] == "2026-09-28"
        assert klient.get("/lifts/NIE-MA/risk").status_code == 404
        assert klient.get(f"/lifts/{pierwszy['id_windy']}/risk", params={"dzien": "2026-09-01"}).status_code == 404
    finally:
        main.app.dependency_overrides.clear()
