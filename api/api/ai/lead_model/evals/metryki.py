"""Miary rankingu dla kolejki zapytań: AUC, lift w czołówce, precyzja pierwszych k.

Wersje mają mało różnych wyników (v0: konwersja pary źródło × linia, v1: ocena 1–10), więc granica czołówki
zwykle przecina grupę remisów. Precyzję i lift liczymy jako wartość oczekiwaną przy losowej kolejności wewnątrz
remisu (tak działa kolejka, która remisu niczym nie rozstrzyga), a nie przy przypadkowej kolejności wierszy.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

FRAKCJA_LIFTU = 0.10


def precision_at_k(y, wynik, k: int) -> float:
    """Odsetek umów wśród k zapytań z najwyższym wynikiem (remis na granicy: średnia konwersja remisujących)."""
    y = np.asarray(y, dtype=float)
    wynik = np.asarray(wynik, dtype=float)
    prog = np.sort(wynik)[::-1][k - 1]
    wyzej = wynik > prog
    rowne = wynik == prog
    z_remisu = k - wyzej.sum()
    return float((y[wyzej].sum() + z_remisu * y[rowne].mean()) / k)


def lift_at(y, wynik, frakcja: float = FRAKCJA_LIFTU) -> float:
    """Konwersja w czołówce (frakcja zapytań z najwyższym wynikiem) / konwersja wszystkich."""
    y = np.asarray(y, dtype=float)
    k = max(1, round(frakcja * len(y)))
    return precision_at_k(y, wynik, k) / y.mean()


def dzienna_liczba_zapytan(utworzono: pd.Series) -> int:
    """Średnia liczba nowych zapytań na dzień kalendarzowy (czas warszawski), zaokrąglona do całości."""
    dni = pd.to_datetime(utworzono, utc=True).dt.tz_convert("Europe/Warsaw").dt.date
    return round(len(dni) / dni.nunique())


def metryki_rankingu(y, wynik, k: int) -> dict:
    y = np.asarray(y, dtype=int)
    return {
        "n": int(len(y)),
        "umowy": int(y.sum()),
        "konwersja": float(y.mean()),
        "auc": float(roc_auc_score(y, wynik)),
        "lift_10": lift_at(y, wynik, FRAKCJA_LIFTU),
        "k": int(k),
        "precision_k": precision_at_k(y, wynik, k),
    }


def bootstrap_par(y, wynik_a, wynik_b, k: int, n_prob: int = 2000, ziarno: int = 42) -> dict:
    """95% przedziały (percentylowe) dla AUC i liftu każdej wersji oraz różnic a − b na tych samych losowaniach."""
    y = np.asarray(y, dtype=int)
    wynik_a, wynik_b = np.asarray(wynik_a, dtype=float), np.asarray(wynik_b, dtype=float)
    rng = np.random.default_rng(ziarno)
    proby = {"auc_a": [], "auc_b": [], "lift_a": [], "lift_b": [], "prec_a": [], "prec_b": []}
    for _ in range(n_prob):
        i = rng.integers(0, len(y), len(y))
        proby["auc_a"].append(roc_auc_score(y[i], wynik_a[i]))
        proby["auc_b"].append(roc_auc_score(y[i], wynik_b[i]))
        proby["lift_a"].append(lift_at(y[i], wynik_a[i]))
        proby["lift_b"].append(lift_at(y[i], wynik_b[i]))
        proby["prec_a"].append(precision_at_k(y[i], wynik_a[i], k))
        proby["prec_b"].append(precision_at_k(y[i], wynik_b[i], k))
    p = {k_: np.asarray(v) for k_, v in proby.items()}
    p["auc_roznica"] = p["auc_a"] - p["auc_b"]
    p["lift_roznica"] = p["lift_a"] - p["lift_b"]
    p["prec_roznica"] = p["prec_a"] - p["prec_b"]
    return {k_: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k_, v in p.items()}
