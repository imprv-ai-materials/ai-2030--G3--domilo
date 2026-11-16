import numpy as np
import pandas as pd
import pytest
from api.contexts_boundaries.retention_bc.kampania_2026q3 import (
    bootstrap_wyniku,
    przedzial,
    wynik_kampanii,
)
from api.contexts_boundaries.retention_bc.zalozenia import ZalozeniaOferty

Z = ZalozeniaOferty(R=1000.0, D=100.0, k=10.0)


def _ramka(n_o: int, prz_o: int, rabat_o: int, n_k: int, prz_k: int) -> pd.DataFrame:
    """Umowy oferty (pierwsze `rabat_o` przedłużeń z rabatem) i kontroli."""
    prz = np.r_[np.ones(prz_o), np.zeros(n_o - prz_o), np.ones(prz_k), np.zeros(n_k - prz_k)]
    rabat = np.r_[np.ones(rabat_o), np.zeros(n_o - rabat_o), np.zeros(n_k)]
    return pd.DataFrame(
        {
            "id_najemcy": [f"T{i}" for i in range(n_o + n_k)],
            "oferta": np.r_[np.ones(n_o, dtype=bool), np.zeros(n_k, dtype=bool)],
            "przedluzona": prz.astype(int),
            "rabat": rabat.astype(bool),
        }
    )


def test_wynik_kampanii_wzor_z_polecenia():
    # oferta: 60/100 przedłużeń (58 z rabatem), kontrola: 10/25 = 40%
    w = wynik_kampanii(_ramka(100, 60, 58, 25, 10), Z)
    assert w["odsetek_oferta"] == pytest.approx(0.60)
    assert w["odsetek_kontrola"] == pytest.approx(0.40)
    assert w["ate"] == pytest.approx(0.20)
    assert w["dodatkowe_przedluzenia"] == pytest.approx(20.0)  # 0,20 × 100 ofert
    assert w["rabaty_szt"] == 58
    assert w["korzysc"] == pytest.approx(20_000.0)  # 20 × R
    assert w["koszt_rabatow"] == pytest.approx(5_800.0)  # 58 × D
    assert w["koszt_kontaktu"] == pytest.approx(1_000.0)  # 100 × k
    assert w["wynik_netto"] == pytest.approx(13_200.0)
    assert w["roi"] == pytest.approx(13_200.0 / 6_800.0)
    # próg opłacalności: ATE, przy którym wynik = 0 (te same rabaty i kontakty)
    assert w["ate_prog_zera"] == pytest.approx(6_800.0 / 1000.0 / 100)


def test_wynik_kampanii_ujemny_gdy_efekt_zerowy():
    w = wynik_kampanii(_ramka(100, 40, 40, 50, 20), Z)
    assert w["ate"] == pytest.approx(0.0)
    assert w["wynik_netto"] == pytest.approx(-(40 * 100.0 + 100 * 10.0))
    assert w["roi"] == pytest.approx(-1.0)


def test_bootstrap_losuje_w_grupach_i_jest_powtarzalny():
    df = _ramka(100, 60, 58, 25, 10)
    a = bootstrap_wyniku(df, Z, n_prob=200, ziarno=1)
    b = bootstrap_wyniku(df, Z, n_prob=200, ziarno=1)
    assert len(a) == 200
    pd.testing.assert_frame_equal(a, b)
    # liczebności grup stałe (losowanie warstwowe), więc koszt kontaktu się nie zmienia
    assert (a["koszt_kontaktu"] == 1_000.0).all()
    assert a["ate"].std() > 0


def test_bootstrap_klastrow_trzyma_umowy_najemcy_razem():
    df = _ramka(100, 60, 58, 25, 10)
    df["id_najemcy"] = [f"T{i // 2}" for i in range(len(df))]  # po 2 umowy na najemcę
    b = bootstrap_wyniku(df, Z, n_prob=50, ziarno=3, klastry="id_najemcy")
    assert len(b) == 50 and b["wynik_netto"].notna().all()


def test_przedzial_percentylowy():
    s = pd.Series(np.arange(1001, dtype=float))
    assert przedzial(s) == pytest.approx([25.0, 975.0])
