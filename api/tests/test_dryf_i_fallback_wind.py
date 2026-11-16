"""Dryf cech wind (PSI), korekta bledy_drzwi dla Liftar LF-5 i reguła zapasowa dla wind bez normy
(docs/b4_dryf_i_fallback.md)."""

import json
from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest
from api.adapters.duckdb_baza import SCIEZKA_BAZY, polaczenie
from api.ai.failure_model.base import ustawienia_cech, wczytaj_regule_zapasowa
from api.ai.failure_model.evals import dryf
from api.ai.failure_model.versions.zapasowa_if.model import DNI_BEZ_NORMY, STATYSTYKI, RegulaZapasowa
from api.ai.features.windy.cechy import SQL_BLEDY_DRZWI_LF5
from api.contexts_boundaries.maintenance_bc import alarmy_wind, ryzyko_dzienne

JEST_BAZA = SCIEZKA_BAZY.exists()
PON = pd.Timestamp("2026-09-21")


# --- korekta bledy_drzwi -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "firmware, kody, bledy, oczekiwane",
    [
        ("LF-5.0.1", "E07|E17", 2, 1),  # para z LF-5 = jeden błąd drzwi
        ("LF-5.0.1", "E17", 1, 0),  # samotny E17 nie jest błędem drzwi
        ("LF-5.0.1", "E07|E17|E07|E17", 4, 2),
        ("LF-5.0.1", "E31", 0, 0),
        ("LF-5.0.1", None, 0, 0),
        ("LF-4.1.5", "E07", 1, 1),  # inne firmware bez zmian
        ("DM-4.3.1", "DR01", 1, 1),
    ],
)
def test_korekta_liczy_tylko_e07_dla_lf5(firmware, kody, bledy, oczekiwane):
    con = duckdb.connect()
    wynik = con.execute(
        f"SELECT {SQL_BLEDY_DRZWI_LF5} "
        "FROM (SELECT ? AS firmware, ? AS kody_bledow, CAST(? AS TINYINT) AS bledy_drzwi)",
        [firmware, kody, bledy],
    ).fetchone()[0]
    assert wynik == oczekiwane


def test_korekta_domyslnie_wylaczona_w_current_yaml():
    assert ustawienia_cech()["korekta_bledow_drzwi_lf5"] is False


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb (pypyr baza)")
def test_korekta_nie_zmienia_okien_sprzed_lf5():
    with polaczenie() as con:
        rozne, lf5_przed = con.execute(f"""
            SELECT count(*) FILTER (bledy_drzwi IS DISTINCT FROM {SQL_BLEDY_DRZWI_LF5}),
                   count(*) FILTER (firmware LIKE 'LF-5%')
            FROM telemetra_windy WHERE ts_utc < TIMESTAMPTZ '2025-11-17 00:00:00+01'""").fetchone()
    assert (rozne, lf5_przed) == (0, 0)


# --- PSI ---------------------------------------------------------------------------------------------------------


def test_psi_zero_dla_tego_samego_rozkladu_i_dodatnie_dla_przesuniecia():
    e = np.array([0.5, 0.3, 0.2])
    assert dryf.psi(e, e) == pytest.approx(0.0)
    assert dryf.psi(np.array([0.2, 0.3, 0.5]), e) > 0


def test_przedzialy_z_decyli_treningu_i_osobny_przedzial_brakow():
    x = np.concatenate([np.zeros(50), np.arange(1, 51, dtype=float)])
    gr = dryf.granice(x)
    assert len(gr) < 9  # powtórzone granice (dużo zer) połączone
    p = dryf.przedzial(np.array([0.0, 100.0, np.nan]), gr)
    assert p[0] == 0 and p[1] == len(gr) and p[2] == len(gr) + 1


def test_tabela_psi_wykrywa_przesuniecie_ponad_zmiennosc_treningu():
    rng = np.random.default_rng(0)
    dni = pd.date_range("2023-03-06", "2025-09-28", freq="D")
    wiersze = [(f"W{i}", d) for d in dni for i in range(20)]
    df = pd.DataFrame(wiersze, columns=["id_windy", "dzien"]).assign(producent="Liftar")
    df["drzwi_bledy_sr_24h"] = rng.normal(size=len(df)) + np.where(df["dzien"] >= "2025-08-04", 2.0, 0.0)
    trening = (df["dzien"] <= "2025-06-30").to_numpy()
    t = dryf.tabela_psi(df, ["drzwi_bledy_sr_24h"], trening, "obecna")
    assert t["tydzien"].min() == date(2025, 6, 30)
    przed = t[pd.to_datetime(t["tydzien"]) < "2025-08-04"]
    po = t[pd.to_datetime(t["tydzien"]) >= "2025-08-04"]
    assert not przed["ponad_trening"].any() and po["ponad_trening"].all()
    assert set(t["sygnal"]) == {"drzwi_bledy"}


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb (pypyr baza)")
def test_tabela_psi_cech_windy_ma_wszystkie_cechy_producentow_i_tygodnie():
    with polaczenie() as con:
        if not con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'psi_cech_windy'"
        ).fetchone()[0]:
            pytest.skip("brak psi_cech_windy (failure_model/evals/dryf.py)")
        cechy, producenci, pierwszy = con.execute(
            "SELECT count(DISTINCT cecha), count(DISTINCT producent), min(tydzien) "
            "FROM psi_cech_windy WHERE wariant = 'obecna'"
        ).fetchone()
    assert (cechy, producenci, pierwszy) == (179, 4, date(2025, 6, 30))


# --- reguła zapasowa ---------------------------------------------------------------------------------------------


def _dane(n: int, model: str, przesuniecie: float = 0.0, ziarno: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(ziarno)
    kol = {f"naped_prad_sr_{st}": rng.normal(10 + przesuniecie, 1, n) for st in STATYSTYKI}
    kol |= {f"drzwi_bledy_{st}": rng.poisson(0.2, n).astype(float) for st in STATYSTYKI}
    return pd.DataFrame(kol).assign(model_windy=model)


def test_regula_zapasowa_alarmuje_jak_czesto_model_i_lapie_odstajaca_winde():
    r = RegulaZapasowa(["naped_prad_sr", "drzwi_bledy"], udzial_alarmow=0.05).fit(
        pd.concat([_dane(2000, "A"), _dane(2000, "B", ziarno=1)], ignore_index=True)
    )
    uczace = r.ocen(_dane(2000, "A"))
    assert uczace["alarm"].mean() == pytest.approx(0.05, abs=0.01)
    nowa = r.ocen(_dane(5, "A", przesuniecie=8, ziarno=2).assign(**{"drzwi_bledy_sr_24h": np.nan}))
    assert nowa["alarm"].all()
    assert nowa["odchylenia"].iloc[0][0]["cecha"].startswith("naped_prad_sr")
    nieznany = r.ocen(_dane(3, "C"))
    assert nieznany["wynik"].isna().all() and not nieznany["alarm"].any()


@pytest.mark.skipif(not JEST_BAZA, reason="brak domilo.duckdb (pypyr baza)")
def test_artefakt_reguly_zapasowej_ma_wszystkie_modele_wind():
    regula = wczytaj_regule_zapasowa()
    with polaczenie() as con:
        modele = {r[0] for r in con.execute("SELECT DISTINCT model FROM serwis_windy").fetchall()}
    assert set(regula.progi_) == modele
    assert regula.udzial_alarmow == pytest.approx(3 / 140)


def _ryzyko(**zmiany) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "id_windy": ["A", "B", "C", "D", "N1", "N2"],
            "dzien": [PON] * 6,
            "wynik": [0.9, 0.8, 0.7, 0.6, 0.95, 0.1],
            "stoi": [False] * 6,
            "tryb_oceny": ["model"] * 4 + ["zapasowa"] * 2,
            "alarm_zapasowy": [False] * 4 + [False, True],
            "wynik_zapasowy": [np.nan] * 4 + [0.5, 0.7],
            "prog_zapasowy": [np.nan] * 4 + [0.6, 0.6],
        }
    )
    return df.assign(**zmiany)


def test_alarm_zapasowy_najpierw_potem_model_do_limitu_bez_wind_zapasowych_w_rankingu():
    z = alarmy_wind.wczytaj_zalozenia()
    a = ryzyko_dzienne.wybierz_alarmy_dnia(_ryzyko(), pd.DataFrame(), z)
    assert list(a["id_windy"]) == ["N2", "A", "B"]  # N1 ma najwyższy wynik modelu, ale jest w trybie zapasowym
    assert list(a["tryb_oceny"]) == ["zapasowa", "model", "model"] and list(a["pozycja"]) == [1, 2, 3]
    poprzednie = pd.DataFrame({"id_windy": ["N2"], "dzien": [PON - pd.Timedelta(days=7)]})
    assert list(ryzyko_dzienne.wybierz_alarmy_dnia(_ryzyko(), poprzednie, z)["id_windy"]) == ["A", "B", "C"]
    stoi = _ryzyko(stoi=[False] * 5 + [True])
    assert "N2" not in set(ryzyko_dzienne.wybierz_alarmy_dnia(stoi, pd.DataFrame(), z)["id_windy"])
    assert ryzyko_dzienne.wybierz_alarmy_dnia(_ryzyko(dzien=[PON + pd.Timedelta(days=1)] * 6), None, z).empty


def test_winda_bez_normy_dostaje_tryb_zapasowy_opis_i_brak_p_z_modelu():
    r = RegulaZapasowa(["naped_prad_sr", "drzwi_bledy"], udzial_alarmow=0.05).fit(_dane(2000, "A"))
    cechy = pd.concat([_dane(1, "A", przesuniecie=8, ziarno=3), _dane(1, "A", ziarno=4)], ignore_index=True)
    cechy = cechy.assign(id_windy=["NOWA", "STARA"], dni_telemetrii=[DNI_BEZ_NORMY - 1, DNI_BEZ_NORMY])
    df = pd.DataFrame(
        {
            "id_windy": ["NOWA", "STARA"],
            "p_awarii_7d": [0.3, 0.2],
            "podzespoly": ["[]", "[]"],
            "opis": ["x", "y"],
        }
    )
    wynik = ryzyko_dzienne.dodaj_regule_zapasowa(df, cechy, r)
    nowa, stara = wynik.iloc[0], wynik.iloc[1]
    assert (nowa["tryb_oceny"], stara["tryb_oceny"]) == ("zapasowa", "model")
    assert np.isnan(nowa["p_awarii_7d"]) and stara["p_awarii_7d"] == 0.2
    assert bool(nowa["alarm_zapasowy"]) and nowa["opis"].startswith("Reguła zapasowa (nowa winda, 43 dni telemetrii")
    assert json.loads(nowa["podzespoly"])[0]["podzespol"] == "naped" and stara["opis"] == "y"
    bez_reguly = ryzyko_dzienne.dodaj_regule_zapasowa(df.copy(), cechy, None)
    assert set(bez_reguly["tryb_oceny"]) == {"model"}


def test_zgloszenie_z_reguly_zapasowej_ma_osobna_flage():
    ocena = {
        "opis": "Reguła zapasowa (nowa winda, 12 dni telemetrii, bez normy): …",
        "wersja_modelu": "v3_punkt_pracy",
        "podzespoly": [{"podzespol": "naped", "wklad": 4.0, "sygnaly": ["naped_prad_sr"]}],
        "sygnaly": [],
        "tryb_oceny": "zapasowa",
        "dni_telemetrii": 12,
        "wynik_zapasowy": 0.61,
        "prog_zapasowy": 0.57,
        "odchylenia": json.dumps([{"cecha": "naped_prad_sr_sr_24h", "odchylenie_iqr": 4.0}]),
    }
    alarm = {"id_windy": "B37-W4", "dzien": "2024-10-28", "pozycja": 1, "wynik": 0.2, "p_awarii_7d": None}
    z = ryzyko_dzienne.zgloszenie_alarmu(alarm, ocena, {"id_budynku": "B37", "firma_serwisowa": "X"})
    assert z["alarm"]["tryb_oceny"] == "zapasowa"
    assert z["alarm"]["regula_zapasowa"]["prog"] == 0.57 and z["alarm"]["regula_zapasowa"]["odchylenia"]
    model = ryzyko_dzienne.zgloszenie_alarmu(
        alarm, {**ocena, "tryb_oceny": "model"}, {"id_budynku": "B37", "firma_serwisowa": "X"}
    )
    assert model["alarm"]["tryb_oceny"] == "model" and "regula_zapasowa" not in model["alarm"]
