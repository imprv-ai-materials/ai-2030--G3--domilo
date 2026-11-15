"""Statystyki zmienności tygodniowej do docs/kolejka_metryki.md (api.data_platform.kolejka_metryki)."""

import math

import pytest
from api.data_platform.kolejka_metryki import bootstrap_odchylenia_proc, statystyki_tygodni


def test_odchylenie_z_proby_w_procentach_sredniej():
    # Średnia 4, odchylenie z próby (n − 1) = sqrt(((2^2 + 0 + 2^2) / 2)) = 2, czyli 50% średniej.
    s = statystyki_tygodni([2.0, 4.0, 6.0])
    assert s["tygodnie"] == 3
    assert s["srednia"] == pytest.approx(4.0)
    assert s["odchylenie_std"] == pytest.approx(2.0)
    assert s["odchylenie_proc_sredniej"] == pytest.approx(50.0)
    assert s["min"] == 2.0 and s["max"] == 6.0


def test_autokorelacja_serii_rosnacej_jest_dodatnia():
    s = statystyki_tygodni([1.0, 2.0, 3.0, 4.0, 5.0])
    assert s["autokorelacja_lag1"] == pytest.approx(1.0)


def test_jeden_tydzien_to_za_malo():
    with pytest.raises(ValueError):
        statystyki_tygodni([1.0])


def test_bootstrap_jest_powtarzalny_i_obejmuje_wartosc_z_proby():
    x = [10.0, 12.0, 9.0, 15.0, 11.0, 8.0, 14.0, 13.0]
    a = bootstrap_odchylenia_proc(x, losowania=500)
    b = bootstrap_odchylenia_proc(x, losowania=500)
    assert a == b
    cv = statystyki_tygodni(x)["odchylenie_proc_sredniej"]
    assert a[0] < cv < a[1]
    assert not any(math.isnan(v) for v in a)
