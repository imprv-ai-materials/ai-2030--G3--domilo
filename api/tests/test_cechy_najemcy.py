"""Cechy najemców na dzień migawki: tylko zdarzenia sprzed migawki, bez pól wykluczonych i stanu na eksport."""

import duckdb
import pandas as pd
import pytest
from api.ai.features.najemcy.cechy import KATALOG_SQL, KOLUMNY_CECH, RODZINY, zbuduj_cechy, zbuduj_tabele_cech
from api.ai.features.najemcy.wykluczone import (
    WYKLUCZONE,
    CechaWykluczona,
    sprawdz_brak_wykluczonych,
    wczytaj_wykluczone,
    zakazane_w_sql,
)

# Dzień migawki obu umów: 2025-06-15 (data_do 2025-08-14). Zdarzenia w dniu migawki i później nie mogą zmienić cech.
MIGAWKA = "2025-06-15"


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute("""
        CREATE TABLE migawki_najemcy AS SELECT * FROM (VALUES
            ('U2', 'N1', 'T1', 'L1', 'B2C', 'przedłużenie', 2, 12, DATE '2025-06-15', 0),
            ('UB', 'NB', 'TB', 'L9', 'B2B', 'pierwsza', 1, 12, DATE '2025-06-15', 1)
        ) AS t(id_umowy, id_najmu, id_najemcy, id_lokalu, linia, typ, nr_okresu, miesiecy_umowy, data_migawki,
               odejdzie)
        """)
    con.execute("""
        CREATE TABLE pms_najmy AS SELECT id_najmu, id_lokalu, id_najemcy, linia,
            data_wprowadzenia::TIMESTAMP_NS AS data_wprowadzenia FROM (VALUES
            ('N1', 'L1', 'T1', 'B2C', '2023-08-15'),
            ('NB', 'L9', 'TB', 'B2B', '2024-08-15'),
            ('NX', 'L2', 'TX', 'B2C', '2025-01-01'),
            ('NY', 'L3', 'TY', 'B2C', '2025-03-01'),
            ('NZ', 'L4', 'TZ', 'B2C', '2025-06-15')
        ) AS t(id_najmu, id_lokalu, id_najemcy, linia, data_wprowadzenia)
        """)
    # Nowe umowy podobnych lokali: L2, L3 przed migawką; L4 w dniu migawki (nie liczy się).
    con.execute("""
        CREATE TABLE pms_umowy AS SELECT id_umowy, id_najmu, nr_okresu, typ, data_od::TIMESTAMP_NS AS data_od,
            czynsz, indeksacja_pct FROM (VALUES
            ('U1', 'N1', 1, 'pierwsza', '2023-08-15', 2000, NULL),
            ('U2', 'N1', 2, 'przedłużenie', '2024-08-15', 2100, 5.0),
            ('UB', 'NB', 1, 'pierwsza', '2024-08-15', 3000, NULL),
            ('UX', 'NX', 1, 'pierwsza', '2025-01-01', 2500, NULL),
            ('UY', 'NY', 1, 'pierwsza', '2025-03-01', 2700, NULL),
            ('UZ', 'NZ', 1, 'pierwsza', '2025-06-15', 9900, NULL)
        ) AS t(id_umowy, id_najmu, nr_okresu, typ, data_od, czynsz, indeksacja_pct)
        """)
    con.execute("""
        CREATE TABLE pms_lokale AS SELECT * FROM (VALUES
            ('L1', 'B1', 2, 50.0, 9999, 'wolny'), ('L2', 'B1', 2, 50.0, 1, 'wolny'),
            ('L3', 'B1', 2, 50.0, 1, 'wolny'), ('L4', 'B1', 2, 50.0, 1, 'wolny'),
            ('L9', 'B2', 3, 70.0, 1, 'wolny')
        ) AS t(id_lokalu, id_budynku, pokoje, metraz, czynsz_katalogowy, status)
        """)
    con.execute(
        "CREATE TABLE pms_budynki AS SELECT * FROM (VALUES ('B1', 'Kraków'), ('B2', 'Łódź')) t(id_budynku, miasto)"
    )
    # Płatności najmu N1 (obie umowy): termin 10. dnia miesiąca; okno [2025-03-17, 2025-06-15) → 04, 05, 06.
    con.execute("""
        CREATE TABLE pms_platnosci AS SELECT id_umowy, miesiac, data_platnosci::TIMESTAMP_NS AS data_platnosci,
            dni_opoznienia FROM (VALUES
            ('U2', '2025-03', '2025-03-30', 20),
            ('U2', '2025-04', '2025-04-05', 0),
            ('U2', '2025-05', '2025-05-13', 3),
            ('U2', '2025-06', '2025-06-25', 15),
            ('U2', '2025-07', '2025-07-01', 0)
        ) AS t(id_umowy, miesiac, data_platnosci, dni_opoznienia)
        """)
    con.execute("""
        CREATE TABLE portal_zgloszenia AS SELECT id_zgloszenia, id_najemcy, id_lokalu,
            utworzono::TIMESTAMP_NS AS utworzono, zamknieto::TIMESTAMP_NS AS zamknieto, ocena_obslugi,
            status FROM (VALUES
            ('Z1', 'T1', 'L1', '2025-05-01 10:00', '2025-05-03 12:00', 2.0, 'zamkniete'),
            ('Z2', 'T1', 'L1', '2025-06-10 10:00', '2025-06-20 12:00', 5.0, 'zamkniete'),
            ('Z3', 'T1', 'L1', '2025-06-15 08:00', NULL, NULL, 'otwarte'),
            ('Z4', 'T1', 'L7', '2025-06-01 08:00', '2025-06-02 08:00', 1.0, 'zamkniete'),
            ('Z5', 'T1', 'L1', '2023-01-10 08:00', '2023-01-11 08:00', 1.0, 'zamkniete')
        ) AS t(id_zgloszenia, id_najemcy, id_lokalu, utworzono, zamknieto, ocena_obslugi, status)
        """)
    con.execute("""
        CREATE TABLE ankiety_satysfakcji AS SELECT id_najemcy, data_wysylki::TIMESTAMP_NS AS data_wysylki,
            data_odpowiedzi::TIMESTAMP_NS AS data_odpowiedzi, wynik_0_10 FROM (VALUES
            ('T1', '2024-10-01', '2024-10-03', 9.0),
            ('T1', '2025-05-01', '2025-05-11', 4.0),
            ('T1', '2025-06-01', '2025-06-15', 1.0),
            ('T1', '2025-06-05', NULL, NULL),
            ('TB', '2024-01-01', '2024-01-02', 10.0)
        ) AS t(id_najemcy, data_wysylki, data_odpowiedzi, wynik_0_10)
        """)
    # Miesiąc migawki (2025-06) jest niepełny: nie wchodzi; pełne miesiące: 2025-03, 04, 05.
    con.execute("""
        CREATE TABLE portal_logowania_mies AS SELECT * FROM (VALUES
            ('T1', '2025-02', 100, 100), ('T1', '2025-03', 1, 0), ('T1', '2025-04', 2, 1),
            ('T1', '2025-05', 3, 2), ('T1', '2025-06', 50, 50)
        ) AS t(id_najemcy, miesiac, liczba_logowan, odslony_oferty_przedluzenia)
        """)
    con.execute(
        "CREATE TABLE serwis_windy AS SELECT * FROM (VALUES ('W1', 'B1'), ('W2', 'B1')) t(id_windy, id_budynku)"
    )
    # Awarie wind B1: okno [2025-03-17 00:00, 2025-06-15 00:00).
    con.execute("""
        CREATE TABLE serwis_zgloszenia AS SELECT id_budynku, typ_urzadzenia, kategoria,
            utworzono::TIMESTAMP_NS AS utworzono FROM (VALUES
            ('B1', 'winda', 'awaria', '2025-03-17 00:00'),
            ('B1', 'winda', 'awaria', '2025-06-14 23:59'),
            ('B1', 'winda', 'awaria', '2025-06-15 00:00'),
            ('B1', 'winda', 'awaria', '2025-03-16 23:59'),
            ('B1', 'winda', 'usterka', '2025-05-01 10:00'),
            ('B1', 'pompa', 'awaria', '2025-05-01 10:00'),
            ('B2', 'winda', 'awaria', '2025-05-01 10:00')
        ) AS t(id_budynku, typ_urzadzenia, kategoria, utworzono)
        """)
    return con


@pytest.fixture
def cechy(con):
    return zbuduj_cechy(con).set_index("id_umowy")


def test_jeden_wiersz_na_migawke_i_tylko_znane_kolumny(cechy):
    assert sorted(cechy.index) == ["U2", "UB"]
    assert set(KOLUMNY_CECH) <= set(cechy.columns)
    assert "odejdzie" not in cechy.columns


def test_umowa_staz_indeksacja_i_czynsz_wzgledem_nowych_umow_sprzed_migawki(con, cechy):
    w = cechy.loc["U2"]
    assert w["staz_dni"] == 670  # 2023-08-15 → 2025-06-15
    assert w["nr_okresu"] == 2
    assert w["indeksacja_ostatnia_pct"] == 5.0
    assert pd.isna(cechy.loc["UB", "indeksacja_ostatnia_pct"])  # pierwsza umowa: nie było przedłużenia
    # Za mało podobnych umów (2 < 5): brak porównania; czynsz_katalogowy (9999) nie wpływa na wynik.
    assert pd.isna(w["czynsz_do_podobnych"])
    con.execute("UPDATE pms_lokale SET czynsz_katalogowy = 1")
    assert pd.isna(zbuduj_cechy(con).set_index("id_umowy").loc["U2", "czynsz_do_podobnych"])


def test_czynsz_do_podobnych_z_mediany_nowych_umow(con):
    # Pięć podobnych umów przed migawką w budynku B1 (2 pokoje, B2C, 50 m²): mediana 2500 zł → 50 zł/m².
    for i, czynsz in enumerate([2300, 2400, 2500, 2600, 2700]):
        con.execute(f"INSERT INTO pms_najmy VALUES ('NP{i}', 'LP{i}', 'TP{i}', 'B2C', '2025-02-0{i + 1}')")
        con.execute(f"INSERT INTO pms_lokale VALUES ('LP{i}', 'B1', 2, 50.0, 1, 'wolny')")
        con.execute(
            f"INSERT INTO pms_umowy VALUES ('UP{i}', 'NP{i}', 1, 'pierwsza', '2025-02-0{i + 1}', {czynsz}, NULL)"
        )
    con.execute("DELETE FROM pms_umowy WHERE id_umowy IN ('UX', 'UY')")
    w = zbuduj_cechy(con).set_index("id_umowy").loc["U2"]
    assert w["podobne_poziom"] == "budynek"
    assert w["podobne_liczba"] == 5  # UZ (data_od = dzień migawki, 9900 zł) się nie liczy
    assert w["czynsz_do_podobnych"] == pytest.approx(2100 / 2500)


def test_platnosci_tylko_opoznienia_znane_w_dniu_migawki(cechy):
    w = cechy.loc["U2"]
    # Terminy w oknie: 10.04 (0 dni), 10.05 (3 dni), 10.06 (zapłacona 25.06, czyli po migawce: znane 5 dni zaległości).
    assert w["plat_liczba_90d"] == 3
    assert w["plat_spoznione_90d"] == 2
    assert w["plat_zalegle_na_migawke"] == 1
    assert w["plat_max_opoznienie_90d"] == 5  # nie 15 (końcowe opóźnienie znamy dopiero po migawce)
    assert w["plat_srednie_opoznienie_90d"] == pytest.approx((0 + 3 + 5) / 3)
    assert cechy.loc["UB", "plat_liczba_90d"] == 0
    assert pd.isna(cechy.loc["UB", "plat_max_opoznienie_90d"])


def test_relacja_zgloszenia_oceny_i_otwarte_na_migawke(cechy):
    w = cechy.loc["U2"]
    # Z1, Z2 w tym lokalu przed migawką; Z3 w dniu migawki, Z4 w innym lokalu, Z5 przed najmem (od 2023-08-15).
    assert w["zgl_90d"] == 2
    assert w["zgl_365d"] == 2
    assert w["zgl_otwarte_na_migawke"] == 1  # Z2 zamknięte dopiero 2025-06-20 (status 'zamkniete' to stan na eksport)
    assert w["ocena_liczba_365d"] == 1  # tylko Z1 (Z2 oceniono przy zamknięciu po migawce)
    assert w["ocena_srednia_365d"] == 2.0


def test_relacja_ankieta_asof_z_flaga_braku(cechy):
    w = cechy.loc["U2"]
    assert w["ankieta_ostatni_wynik"] == 4.0  # odpowiedź z 2025-06-15 (dzień migawki) jeszcze nieznana
    assert w["ankieta_dni_od_odpowiedzi"] == 35
    assert w["ankieta_brak_wyniku"] == 0
    assert w["ankiety_bez_odpowiedzi_365d"] == 2  # wysłane 01.06 i 05.06, bez odpowiedzi przed migawką
    # TB odpowiedział przed początkiem najmu NB (2024-08-15): brak wyniku w tym najmie.
    assert cechy.loc["UB", "ankieta_brak_wyniku"] == 1
    assert pd.isna(cechy.loc["UB", "ankieta_ostatni_wynik"])


def test_relacja_logowania_tylko_pelne_miesiace_przed_migawka(cechy):
    w = cechy.loc["U2"]
    assert w["portal_miesiace_3m"] == 3
    assert w["portal_logowania_3m"] == 1 + 2 + 3  # bez 2025-06 (miesiąc migawki) i 2025-02 (poza 3 miesiącami)
    assert w["portal_odslony_oferty_3m"] == 0 + 1 + 2
    assert cechy.loc["UB", "portal_miesiace_3m"] == 0
    assert pd.isna(cechy.loc["UB", "portal_logowania_3m"])


def test_budynek_awarie_wind_z_90_dni(cechy):
    w = cechy.loc["U2"]
    assert w["liczba_wind"] == 2
    assert w["windy_awarie_90d"] == 2  # 2025-03-17 00:00 i 2025-06-14 23:59
    assert w["windy_awarie_90d_na_winde"] == 1.0
    assert cechy.loc["UB", "liczba_wind"] == 0
    assert pd.isna(cechy.loc["UB", "windy_awarie_90d_na_winde"])


def test_zdarzenia_po_migawce_nie_zmieniaja_cech(con, cechy):
    con.execute("INSERT INTO pms_platnosci VALUES ('U2', '2025-06', '2025-07-30', 45)")
    con.execute("INSERT INTO portal_zgloszenia VALUES ('Z9', 'T1', 'L1', '2025-06-15 00:00', NULL, 1.0, 'otwarte')")
    con.execute("INSERT INTO ankiety_satysfakcji VALUES ('T1', '2025-06-15', '2025-06-16', 0.0)")
    con.execute("INSERT INTO portal_logowania_mies VALUES ('T1', '2025-07', 99, 99)")
    con.execute("INSERT INTO serwis_zgloszenia VALUES ('B1', 'winda', 'awaria', '2025-06-20 10:00')")
    po = zbuduj_cechy(con).set_index("id_umowy")
    pd.testing.assert_frame_equal(po, cechy)


def test_zapis_tabeli(con):
    assert zbuduj_tabele_cech(con) == 2
    assert con.execute("SELECT count(DISTINCT id_umowy) FROM cechy_najemcy").fetchone()[0] == 2


# --- pola wykluczone i zakazane ------------------------------------------------------------------------------


def test_lista_wykluczonych_najemcow():
    lista = wczytaj_wykluczone()
    assert set(lista) == {"rok_urodzenia", "jezyk_kontaktu"} == set(WYKLUCZONE)
    for nazwa, pozycja in lista.items():
        assert {"zrodlo", "uzasadnienie", "dozwolone_uzycie"} <= set(pozycja), nazwa


@pytest.mark.parametrize("kolumna", ["rok_urodzenia", "jezyk_kontaktu", "wiek_rok_urodzenia"])
def test_straznik_odrzuca_wykluczona_kolumne(kolumna):
    with pytest.raises(CechaWykluczona):
        sprawdz_brak_wykluczonych(["staz_dni", kolumna], "test")


@pytest.mark.parametrize("rodzina", RODZINY)
def test_sql_rodziny_nie_czyta_pol_zakazanych(rodzina):
    sql = (KATALOG_SQL / f"{rodzina}.sql").read_text(encoding="utf-8")
    assert zakazane_w_sql(sql) == []


def test_zakazane_w_sql_pomija_komentarze_i_wykrywa_uzycie():
    assert zakazane_w_sql("-- czynsz_katalogowy to stan na eksport\nSELECT 1") == []
    assert zakazane_w_sql("SELECT l.czynsz_katalogowy, n.jezyk_kontaktu FROM x") == [
        "czynsz_katalogowy",
        "jezyk_kontaktu",
    ]
