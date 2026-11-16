import numpy as np
import pytest
from api.contexts_boundaries.retention_bc.polityka_rabatow import (
    ZalozeniaOferty,
    na_rok,
    wartosc_oferty,
    wynik_polityki,
)
from api.contexts_boundaries.retention_bc.zalozenia import wczytaj_zalozenia, zalozenia_oferty

Z = ZalozeniaOferty(R=4920.0, D=1800.0, k=60.0)


def test_zalozenia_z_pliku_ze_zrodlem_i_wlascicielem():
    z = zalozenia_oferty()
    assert (z.R, z.D, z.k) == (4920.0, 1800.0, 60.0)
    surowe = wczytaj_zalozenia()
    for nazwa in ("koszt_odejscia_R", "rabat_roczny_D", "koszt_kontaktu_k"):
        for pole in ("wartosc", "jednostka", "opis", "zrodlo", "data", "odpowiedzialny"):
            assert surowe[nazwa][pole] is not None, f"{nazwa}.{pole}"
    assert surowe["koszt_odejscia_R"]["odpowiedzialny"] == "Monika Lis"
    assert surowe["rabat_roczny_D"]["odpowiedzialny"] == "Joanna Michalak"
    assert surowe["koszt_kontaktu_k"]["odpowiedzialny"] == "Joanna Michalak"


def test_wartosc_oferty_wedlug_wzoru():
    # uplift 0,30, P(przedłuży | oferta) 0,50: 0,30 × 4 920 − 1 800 × 0,50 − 60 = 516
    ev = wartosc_oferty(np.array([0.30, 0.0]), np.array([0.50, 0.90]), Z)
    assert ev == pytest.approx([516.0, -1680.0])


def test_wynik_polityki_z_obserwacji_eksperymentu():
    # 4 umowy w polityce: 2 z ofertą (przedłużyły 2), 2 kontrola (przedłużyła 1); 2 poza polityką
    y = np.array([1, 1, 1, 0, 1, 1])
    w = np.array([1, 1, 0, 0, 1, 0])
    maska = np.array([True, True, True, True, False, False])
    uplift = np.full(6, 0.1)
    p_o = np.full(6, 0.8)
    r = wynik_polityki(maska, y, w, uplift, p_o, Z)
    assert r["oferty"] == 4
    assert r["dodatkowe_przedluzenia"] == pytest.approx((1.0 - 0.5) * 4)
    assert r["rabaty"] == pytest.approx(1.0 * 4)
    assert r["koszt_rabatow"] == pytest.approx(4 * 1800)
    assert r["koszt_kontaktow"] == pytest.approx(4 * 60)
    assert r["zysk_netto"] == pytest.approx(2 * 4920 - 4 * 1800 - 4 * 60)
    # wersja modelowa: suma EV = 4 × (0,1 × 4 920 − 1 800 × 0,8 − 60)
    assert r["model_zysk_netto"] == pytest.approx(4 * (492 - 1440 - 60))
    assert r["model_dodatkowe_przedluzenia"] == pytest.approx(0.4)
    # próg opłacalności rabatu: dodatkowe × R − kontakty = rabaty × D*
    assert r["prog_D"] == pytest.approx((2 * 4920 - 4 * 60) / 4)


def test_pusta_polityka_daje_zera():
    r = wynik_polityki(np.zeros(4, dtype=bool), np.ones(4), np.array([1, 0, 1, 0]), np.zeros(4), np.zeros(4), Z)
    assert r["oferty"] == 0 and r["zysk_netto"] == 0 and r["model_zysk_netto"] == 0


def test_na_rok_skaluje_liczby_kwotowe():
    r = {"oferty": 10, "zysk_netto": -100.0, "udzial": 0.5, "prog_D": 900.0}
    a = na_rok(r, 3.0)
    assert a["oferty"] == 30 and a["zysk_netto"] == -300.0
    assert a["udzial"] == 0.5 and a["prog_D"] == 900.0  # udziały i progi się nie skalują
