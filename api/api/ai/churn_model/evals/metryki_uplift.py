"""Miary rankingu uplift na danych z losowym przydziałem oferty (y = przedłużenie, w = 1 oferta / 0 kontrola).

Krzywa Qini (Radcliffe), w wersji znormalizowanej do liczebności grup w całym zbiorze:
    Qini(φ) = Y_o(φ) / N_o − Y_k(φ) / N_k,
gdzie Y_o(φ), Y_k(φ) to przedłużenia z grupy oferta / kontrola wśród φ umów z najwyższym wynikiem, a N_o, N_k to
liczebności grup w całym zbiorze. Qini(φ) to przyrost odsetka przedłużeń w całej populacji, gdy ofertę dostaje φ
umów z góry listy; Qini(1) = ATE. Losowa kolejność daje prostą od 0 do ATE.
AUUC = pole pod krzywą Qini na osi φ ∈ [0, 1] (trapezy). AUUC − ATE / 2 = przewaga nad losową kolejnością
(współczynnik Qini).
Remisy: punkty krzywej liczymy tylko na końcach grup równych wyników (między nimi prosta), więc kolejność wierszy
wewnątrz remisu nie zmienia wyniku. Ważne dla reguły 0/1 („górne 35% score_polityki”).
Uplift w czołówce: p_o − p_k wśród φ umów z najwyższym wynikiem; remis na granicy wchodzi z wagą ułamkową (wartość
oczekiwana losowego wyboru z remisu).
causalml.metrics.get_qini sortuje wiersze bez obsługi remisów, dlatego miary liczymy tutaj.
"""

import numpy as np
import pandas as pd


def _tablice(y, w, wynik) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    wynik = np.asarray(wynik, dtype=float)
    if not (len(y) == len(w) == len(wynik)):
        raise ValueError("y, w i wynik muszą mieć tę samą długość")
    return y, w, wynik


def krzywa_qini(y, w, wynik) -> pd.DataFrame:
    """Punkty (frakcja, qini) od (0, 0) do (1, ATE), po jednym na koniec każdej grupy równych wyników."""
    y, w, wynik = _tablice(y, w, wynik)
    porzadek = np.argsort(-wynik, kind="stable")
    y, w, wynik = y[porzadek], w[porzadek], wynik[porzadek]
    n_o, n_k = w.sum(), (1 - w).sum()
    q = np.cumsum(y * w) / n_o - np.cumsum(y * (1 - w)) / n_k
    koniec_grupy = np.r_[wynik[1:] != wynik[:-1], True]
    idx = np.flatnonzero(koniec_grupy)
    return pd.DataFrame({"frakcja": np.r_[0.0, (idx + 1) / len(y)], "qini": np.r_[0.0, q[idx]]})


def auuc(krzywa: pd.DataFrame) -> float:
    x, q = krzywa["frakcja"].to_numpy(), krzywa["qini"].to_numpy()
    return float(np.sum((x[1:] - x[:-1]) * (q[1:] + q[:-1]) / 2))


def qini_w(krzywa: pd.DataFrame, frakcja: float) -> float:
    """Wartość krzywej Qini w punkcie φ = frakcja (interpolacja liniowa)."""
    return float(np.interp(frakcja, krzywa["frakcja"], krzywa["qini"]))


def uplift_w_czolowce(y, w, wynik, frakcja: float) -> dict:
    """p_o − p_k wśród round(frakcja · n) umów z najwyższym wynikiem (remis na granicy z wagą ułamkową)."""
    y, w, wynik = _tablice(y, w, wynik)
    k = max(1, round(frakcja * len(y)))
    prog = np.sort(wynik)[::-1][k - 1]
    wyzej, rowne = wynik > prog, wynik == prog
    waga = wyzej.astype(float) + rowne * (k - wyzej.sum()) / rowne.sum()
    n_o, n_k = (waga * w).sum(), (waga * (1 - w)).sum()
    p_o = (waga * w * y).sum() / n_o
    p_k = (waga * (1 - w) * y).sum() / n_k
    return {"k": int(k), "n_oferta": float(n_o), "n_kontrola": float(n_k), "p_oferta": float(p_o),
            "p_kontrola": float(p_k), "uplift": float(p_o - p_k)}  # fmt: skip


def miary(y, w, wynik, frakcje_czolowki=(0.20, 0.35)) -> dict:
    k = krzywa_qini(y, w, wynik)
    ate = float(k["qini"].iloc[-1])
    wynik_m = {"auuc": auuc(k), "auuc_minus_losowo": auuc(k) - ate / 2, "ate": ate}
    for f in frakcje_czolowki:
        proc = round(100 * f)
        wynik_m[f"uplift_gora_{proc}"] = uplift_w_czolowce(y, w, wynik, f)["uplift"]
        wynik_m[f"qini_{proc}"] = qini_w(k, f)
    return wynik_m


def bootstrap_miar(
    y, w, wyniki: dict[str, np.ndarray], pary: list[tuple[str, str]] | None = None, n_prob: int = 2000, ziarno: int = 42
) -> dict:
    """95% przedziały percentylowe miar każdego rankingu i różnic a − b dla `pary` (domyślnie pierwszy ranking
    względem pozostałych); ten sam zestaw losowań wierszy dla wszystkich rankingów."""
    y, w = np.asarray(y, dtype=float), np.asarray(w, dtype=float)
    rng = np.random.default_rng(ziarno)
    proby: dict[str, dict[str, list]] = {n: {} for n in wyniki}
    for _ in range(n_prob):
        i = rng.integers(0, len(y), len(y))
        for nazwa, wynik in wyniki.items():
            for miara, v in miary(y[i], w[i], np.asarray(wynik)[i]).items():
                proby[nazwa].setdefault(miara, []).append(v)
    przedzialy = {
        n: {m: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for m, v in d.items()}
        for n, d in proby.items()
    }
    nazwy = list(wyniki)
    pary = pary or [(nazwy[0], n) for n in nazwy[1:]]
    roznice = {
        f"{a}_minus_{b}": {
            m: [float(np.percentile(np.subtract(proby[a][m], proby[b][m]), q)) for q in (2.5, 97.5)] for m in proby[a]
        }
        for a, b in pary
    }
    return {"przedzialy": przedzialy, "roznice": roznice}
