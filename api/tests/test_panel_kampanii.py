"""Dane panelu kampanii w Metabase (retention_bc/panel_kampanii.py): pliki Parquet czytane przez DuckDB w Metabase."""

import json

import duckdb
import pandas as pd
import pytest
from api.contexts_boundaries.retention_bc import panel_kampanii as pk


def test_co_robimy_kontrola_nigdy_nie_dostaje_oferty():
    assert pk.co_robimy("polityka", "rabat", True) == "Wyślij ofertę rabatową"
    assert pk.co_robimy("kontrola", "rabat", False) == "Nic nie wysyłaj (grupa kontrolna)"
    assert pk.co_robimy("polityka", "nie budzić", False) == "Nie proponuj rabatu (mógłby zniechęcić)"
    assert pk.co_robimy("polityka", "bez rabatu", False) == "Bez rabatu (zwykłe przedłużenie)"


@pytest.mark.parametrize(
    "od, do, poczatek",
    [(-405_402.0, -117.0, "Nie."), (10.0, 500.0, "Tak."), (-100.0, 100.0, "Nie wiadomo.")],
)
def test_werdykt_z_przedzialu_wyniku_netto(od, do, poczatek):
    assert pk.werdykt(od, do).startswith(poczatek)


def test_lista_dla_panelu_tlumaczy_zargon_i_dopisuje_powod_kontroli():
    lista = pd.DataFrame(
        {
            "data_listy": ["2026-11-16", "2026-11-16"], "grupa": ["kontrola", "polityka"],
            "akcja": ["bez rabatu", "nie budzić"], "wyslac_oferte": [False, False],
            "uzasadnienie": ["Bez rabatu: x; zalecenie policzymy w dniu migawki 2026-11-21.", "Nie budzić: oferta obniża."],
            "id_umowy": ["U1", "U2"], "id_najemcy": ["T1", "T2"], "linia": ["B2C", "B2B"], "miasto": ["Łódź"] * 2,
            "budynek": ["B"] * 2, "data_do": ["2027-01-15"] * 2, "dni_do_konca": [60, 60], "ryzyko": [0.3, 0.7],
            "uplift": [0.01, -0.1], "kampania": ["kampania_2026q4"] * 2,
        }
    )  # fmt: skip
    p = pk.lista_dla_panelu(lista)
    assert p.loc[0, "powod"].startswith("Umowa wylosowana do grupy kontrolnej")
    assert "migawki" not in p.loc[0, "powod"] and "60 dni przed końcem umowy" in p.loc[0, "powod"]
    assert p.loc[1, "powod"].startswith("Nie proponuj rabatu:")
    assert list(p["rodzaj_klienta"]) == ["prywatny", "firma"]


def test_tabele_kampanii_zgodne_z_wynikami_kampanii_q3():
    k = json.loads(pk.SCIEZKA_KAMPANII.read_text(encoding="utf-8"))
    t = pk.tabele_kampanii(k)
    g = t["kampania_grupy"].set_index("grupa")
    assert g.loc["z ofertą", "umowy"] == k["glowny"]["n_oferta"]
    assert g.loc["bez oferty (kontrolna)", "przedluzenia"] == k["glowny"]["przedluzone_kontrola"]
    p = t["kampania_podsumowanie"].iloc[0]
    assert p["wynik_netto_zl"] == pytest.approx(k["glowny"]["wynik_netto"])
    assert p["czy_kampania_zarabia"] == pk.werdykt(*k["glowny"]["ci95_bootstrap"]["wynik_netto"])
    w = t["kampania_wynik"].set_index("pozycja")
    skladniki = w.loc[[i for i in w.index if i.startswith(("Korzyść", "Koszt"))], "wartosc"].sum()
    assert skladniki == pytest.approx(k["glowny"]["wynik_netto"])  # korzyść − rabaty − kontakt = wynik netto


def test_zbuduj_panel_zapisuje_parquet_czytelne_dla_duckdb(tmp_path):
    wiersze = pk.zbuduj_panel(katalog=tmp_path)
    assert set(wiersze) == {
        "lista_tydzien", "kampania_grupy", "kampania_wynik", "kampania_podsumowanie", "kampania_segmenty",
        "zalozenia", "panel_info",
    }  # fmt: skip
    con = duckdb.connect()
    for nazwa, n in wiersze.items():
        assert con.execute(f"SELECT count(*) FROM read_parquet('{tmp_path / nazwa}.parquet')").fetchone()[0] == n
    assert not list(tmp_path.glob(".*.tmp"))  # pliki tymczasowe podmienione
