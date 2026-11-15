"""Zadanie nocne (valuation_bc/nocne.py), raport kwartalny dla banku (raport_bank.py) i funkcja Inngest."""

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
from api.adapters import wyceny_historia as h
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.cechy_llm import KOLUMNY_LLM
from api.ai.valuation_model.obecny import wczytaj_obecny
from api.contexts_boundaries.valuation_bc import nocne
from api.contexts_boundaries.valuation_bc.raport_bank import (
    dane_operatow,
    metryki_operatow,
    ostatni_kwartal,
    portfel,
    raport_markdown,
)

DZIEN = date(2026, 11, 15)


@pytest.fixture(scope="module")
def con():
    c = polacz()
    yield c
    c.close()


@pytest.fixture(scope="module")
def obecny():
    return wczytaj_obecny()


# --- wycena lokali Domilo ------------------------------------------------------------------------------------------


def test_wycena_wszystkich_lokali_domilo(con, obecny):
    w = nocne.wycen_lokale(con, obecny.model, DZIEN)
    assert len(w) == con.execute("SELECT count(*) FROM pms_lokale").fetchone()[0]
    assert w["id_obiektu"].is_unique
    przyjete = w[~w["odmowa"]]
    assert (przyjete["p10"] <= przyjete["p50"]).all() and (przyjete["p50"] <= przyjete["p90"]).all()
    assert przyjete["czynniki"].map(len).gt(0).all()
    assert w.loc[w["odmowa"], "powod"].str.len().gt(0).all()


def test_lokale_jednego_budynku_maja_te_same_cechy_otoczenia(con):
    X = nocne.cechy_lokali(con, DZIEN)
    jeden = X[X["id_budynku"] == "B01"]
    assert jeden["sasiedzi_mediana_ceny_m2"].nunique() == 1
    assert jeden["odl_centrum_m"].nunique() == 1


def test_lokale_maja_cechy_z_opisu_z_ekstrakcji(con):
    X = nocne.cechy_lokali(con, DZIEN)
    assert X["llm_ekspozycja"].notna().all()


# --- nowe oferty ---------------------------------------------------------------------------------------------------


def test_nowe_oferty_to_ostatnie_30_dni_danych_bez_juz_wycenionych(con):
    wszystkie = nocne.nowe_oferty(con, DZIEN, wycenione=set())
    assert wszystkie["data_publikacji"].max() == pd.Timestamp("2026-10-03")
    assert wszystkie["data_publikacji"].min() > pd.Timestamp("2026-09-03")
    bez_dwoch = nocne.nowe_oferty(con, DZIEN, wycenione=set(wszystkie["id_oferty"].head(2)))
    assert len(bez_dwoch) == len(wszystkie) - 2


def test_oferty_opublikowane_po_dniu_wyceny_nie_sa_wyceniane(con):
    o = nocne.nowe_oferty(con, date(2026, 9, 30), wycenione=set())
    assert o["data_publikacji"].max() <= pd.Timestamp("2026-09-30")


def test_wycena_ofert_uzywa_ekstraktora_na_opisach_bez_kwot_i_zachowuje_cene_ofertowa(con, obecny):
    oferty = nocne.nowe_oferty(con, DZIEN, wycenione=set()).head(5)
    teksty = []

    def ekstraktor(rekordy: pd.DataFrame) -> pd.DataFrame:
        teksty.extend(rekordy["tekst"])
        return pd.DataFrame({"id": rekordy["id"], **{k: np.nan for k in KOLUMNY_LLM}})

    w = nocne.wycen_oferty(con, obecny.model, DZIEN, oferty, ekstraktor)
    assert w["id_obiektu"].tolist() == oferty["id_oferty"].tolist()
    assert w["cena_ofertowa"].tolist() == oferty["cena_ofertowa"].astype(float).tolist()
    assert len(teksty) == 5 and not any("zł" in t for t in teksty)


# --- raport kwartalny ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dzien, oczekiwany",
    [
        (date(2026, 11, 15), (2026, 3, date(2026, 7, 1), date(2026, 9, 30))),
        (date(2026, 10, 1), (2026, 3, date(2026, 7, 1), date(2026, 9, 30))),
        (date(2026, 1, 15), (2025, 4, date(2025, 10, 1), date(2025, 12, 31))),
    ],
)
def test_ostatni_pelny_kwartal(dzien, oczekiwany):
    assert ostatni_kwartal(dzien) == oczekiwany


def _wycena(id_, p50, p10=None, p90=None, odmowa=False, powod=""):
    return {"id_obiektu": id_, "p10": p10 if p10 is not None else 0.9 * p50 if p50 else None, "p50": p50,
            "p90": p90 if p90 is not None else 1.1 * p50 if p50 else None, "odmowa": odmowa, "powod": powod}  # fmt: skip


def test_metryki_operatow_na_przyjetych_z_warunkami_banku():
    d = pd.DataFrame(
        [
            {**_wycena("L1", 110.0), "wartosc_operatu": 100.0},  # błąd 10%, w przedziale [99; 121]
            {**_wycena("L2", 95.0), "wartosc_operatu": 100.0},  # błąd 5%, w przedziale [85,5; 104,5]
            {**_wycena("L3", 80.0), "wartosc_operatu": 100.0},  # błąd 20%, poza [72; 88]
            {**_wycena("L4", None, odmowa=True, powod="Metraż"), "wartosc_operatu": 100.0},
        ]
    )
    m = metryki_operatow(d, mape_max=8.0, pokrycie_min=77.0, pokrycie_max=83.0)
    assert (m["operaty"], m["odmowy"], m["przyjete"]) == (4, 1, 3)
    assert m["mape"] == pytest.approx(35 / 3)
    assert m["pokrycie"] == pytest.approx(200 / 3)
    assert (m["mape_ok"], m["pokrycie_ok"]) == (False, False)


def test_portfel_sumuje_p50_przyjetych_a_odmowy_wycenia_ostatnim_operatem_rocznym():
    lokale = pd.DataFrame(
        [_wycena("L1", 100.0), _wycena("L2", 200.0), _wycena("L3", None, odmowa=True, powod="X")]
    ).assign(operat_roczny=[90.0, 210.0, 300.0])
    p = portfel(lokale)
    assert (p["lokale"], p["przyjete"], p["odmowy"]) == (3, 2, 1)
    assert (p["suma_p50"], p["suma_p10"], p["suma_p90"]) == pytest.approx((300.0, 270.0, 330.0))
    assert p["odmowy_operat_roczny"] == 300.0


def test_raport_ma_uklad_wnioski_tabele_sql_i_brak_ltv(con, tmp_path):
    czas = datetime(2026, 11, 15, 1, tzinfo=timezone.utc)
    hcon = polacz(tmp_path / "x.duckdb", tylko_odczyt=False)
    lok = con.execute("SELECT id_lokalu FROM operaty WHERE typ = 'kontrolny' ORDER BY id_lokalu LIMIT 3").df()
    w = pd.DataFrame(
        [{"id_obiektu": i, "miasto": "Warszawa", "dzielnica": "Wola", "metraz": 50.0, "dzien_wyceny": DZIEN,
          "p10": 400_000.0, "p50": 500_000.0, "p90": 600_000.0, "odmowa": False, "powod": "", "cena_ofertowa": None,
          "wartosc_bazowa": 450_000.0, "czynniki": {"metraz": 1.0}} for i in lok["id_lokalu"]]
    )  # fmt: skip
    h.zapisz(hcon, "run-1", czas, "v4_llm_cechy", "lokal", w)
    d = dane_operatow(con, hcon, ostatni_kwartal(DZIEN))
    hcon.close()
    assert len(d) == 300 and d["p50"].notna().sum() == 3

    tekst = raport_markdown(con, ostatni_kwartal(DZIEN), d, pd.DataFrame(), czas_przebiegu=czas, wersja="v4_llm_cechy")
    naglowki = [l for l in tekst.splitlines() if l.startswith("## ")]
    assert naglowki[:3] == ["## Wnioski", "## Tabele", "## SQL i kod"]
    assert "LTV" in tekst and "brak w danych" in tekst


# --- funkcja Inngest ------------------------------------------------------------------------------------------------


def test_zadanie_nocne_wycenia_lokale_potem_oferty_potem_raport_z_tym_samym_czasem(monkeypatch):
    from api import inngest_app

    wywolania = []
    monkeypatch.setattr(nocne, "przebieg_lokali", lambda i, c: wywolania.append(("lokale", i, c)) or {"lokale": 1})
    monkeypatch.setattr(nocne, "przebieg_ofert", lambda i, c: wywolania.append(("oferty", i, c)) or {"oferty": 2})
    monkeypatch.setattr(nocne, "przebieg_raportu", lambda c: wywolania.append(("raport", c)) or {"raport": "x"})
    kroki = []

    def krok(id_kroku, handler, *args):
        kroki.append(id_kroku)
        return handler(*args)

    wynik = inngest_app.wykonaj_wyceny_nocne(krok, "run-7")

    assert kroki == ["czas-przebiegu", "wycena-lokali", "wycena-nowych-ofert", "raport-kwartalny"]
    czas = wynik["czas"]
    assert wywolania == [("lokale", "run-7", czas), ("oferty", "run-7", czas), ("raport", czas)]
    assert datetime.fromisoformat(czas).tzinfo is not None
    assert (wynik["lokale"], wynik["oferty"], wynik["raport"]) == ({"lokale": 1}, {"oferty": 2}, {"raport": "x"})


def test_funkcja_inngest_ma_harmonogram_nocny_w_czasie_warszawskim_i_zdarzenie_reczne():
    from api import inngest_app

    [fn] = inngest_app.FUNKCJE
    cfg = fn.get_config("http://app:8101/api/inngest").main
    assert fn.local_id == "wyceny-nocne"
    wyzwalacze = [t.model_dump(exclude_none=True) for t in cfg.triggers]
    assert {"cron": "TZ=Europe/Warsaw 0 2 * * *"} in wyzwalacze
    assert {"event": "domilo/wyceny.nocne"} in wyzwalacze


def test_raport_podaje_czas_przebiegu_i_utworzenia_w_czasie_warszawskim_a_wnioski_jako_liste(con):
    czas = pd.Timestamp("2026-11-15 18:43", tz="Europe/Warsaw")  # tak oddaje go DuckDB z TimeZone = Europe/Warsaw
    utworzono = datetime(2026, 11, 15, 17, 50, tzinfo=timezone.utc)
    d = pd.DataFrame(
        columns=["id_lokalu", "budynek", "miasto", "wartosc_operatu", "p10", "p50", "p90", "odmowa", "powod"]
    )
    tekst = raport_markdown(con, ostatni_kwartal(DZIEN), d, pd.DataFrame(), czas_przebiegu=czas, wersja="v4",
                            czas_raportu=utworzono)  # fmt: skip
    assert "2026-11-15 18:43 (czas warszawski)" in tekst
    assert "utworzono 2026-11-15 18:50 (czas warszawski)" in tekst
    wnioski = tekst.split("## Wnioski")[1].split("## Tabele")[0].strip().splitlines()
    assert [w[:3] for w in wnioski] == ["1. ", "2. ", "3. ", "4. "]
