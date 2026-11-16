import math

import numpy as np
import pandas as pd
import pytest
from api.ai.llm.evals.ocena_awarii import bootstrap, metryki, podzespoly, tabela_pomylek, wybierz_bledy


def test_tabela_pomylek_i_metryki():
    prawda = np.array([True, True, True, False, False])
    przew = np.array([True, True, False, True, False])
    assert tabela_pomylek(prawda, przew) == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    m = metryki(prawda, przew)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)
    assert m["trafnosc"] == pytest.approx(3 / 5)


def test_precision_bez_przewidzianych_awarii_to_nan():
    m = metryki(np.array([True, False]), np.array([False, False]))
    assert math.isnan(m["precision"]) and m["recall"] == 0 and m["f1"] == 0


def test_bootstrap_jest_powtarzalny_i_sparowany():
    prawda = np.array([True, False] * 50)
    metody = {"a": prawda.copy(), "b": ~prawda}
    b1, b2 = bootstrap(prawda, metody, losowania=50), bootstrap(prawda, metody, losowania=50)
    pd.testing.assert_frame_equal(b1["a"], b2["a"])
    assert (b1["a"]["f1"] == 1).all() and (b1["b"]["f1"] == 0).all()


def _df():
    # prawda / LLM; podzespol_zz = etykieta koordynatora przed zamianą wandalizm -> zewnetrzna
    wiersze = [
        ("Z1", True, True, "naped", "naped", "naped", 1.0),
        ("Z2", True, False, "drzwi", "drzwi", "brak", 0.3),  # pominięta awaria
        ("Z3", False, True, "brak", "brak", "drzwi", 0.9),  # fałszywy alarm
        ("Z4", True, True, "zewnetrzna", "wandalizm", "brak", 1.0),
        ("Z5", True, True, "drzwi", "drzwi", "brak", 0.8),
        ("Z6", True, True, "drzwi", "drzwi", "brak", 0.8),
        ("Z7", True, True, "zewnetrzna", "zewnetrzna", "zewnetrzna", 1.0),
    ]
    kol = ["id_zgloszenia", "prawda", "czy_awaria", "podzespol_prawda", "podzespol_zz", "podzespol", "pewnosc"]
    return pd.DataFrame(wiersze, columns=kol)


def test_bledy_najpierw_czy_awaria_od_najwyzszej_pewnosci_potem_po_jednym_na_podzespol():
    b = wybierz_bledy(_df(), n=4)
    assert list(b["id_zgloszenia"][:2]) == ["Z3", "Z2"]
    # drzwi (2 błędy) przed wandalizmem (1 błąd), po jednym z każdej grupy
    assert list(b["podzespol_zz"][2:]) == ["drzwi", "wandalizm"]


def test_trafnosc_podzespolu_liczona_na_prawdziwych_awariach_z_wandalizmem_jako_zewnetrzna():
    podsum, macierz = podzespoly(_df())
    # prawdziwe awarie: Z1, Z2, Z4, Z5, Z6, Z7; trafne: Z1 (naped), Z7 (zewnetrzna)
    # brak podzespołu: Z2 (pominięta awaria), Z4, Z5, Z6 (trafione awarie bez podzespołu)
    assert "| 6 | 2 | 33,3% | 4 | 1 | 3 | 2 | 2 | 100,0% |" in podsum
    assert "wandalizm" not in macierz
