"""Miary rankingu listy retencyjnej: AUC, recall i precyzja w górnym decylu, lift.

Górny decyl: k = round(10% liczby umów) umów z najwyższym ryzykiem. Remis na granicy rozstrzygamy wartością
oczekiwaną losowej kolejności wewnątrz remisu (średni odsetek odejść remisujących), a nie kolejnością wierszy.
recall_10 = odejścia w górnym decylu / wszystkie odejścia; precision_10 = odejścia w górnym decylu / k.
"""

import numpy as np
from sklearn.metrics import roc_auc_score

FRAKCJA = 0.10


def k_decyla(n: int, frakcja: float = FRAKCJA) -> int:
    return max(1, round(frakcja * n))


def odejscia_w_czolowce(y, wynik, k: int) -> float:
    """Oczekiwana liczba odejść wśród k umów z najwyższym wynikiem (remis na granicy: średnia remisujących)."""
    y = np.asarray(y, dtype=float)
    wynik = np.asarray(wynik, dtype=float)
    prog = np.sort(wynik)[::-1][k - 1]
    wyzej = wynik > prog
    rowne = wynik == prog
    return float(y[wyzej].sum() + (k - wyzej.sum()) * y[rowne].mean())


def recall_at(y, wynik, frakcja: float = FRAKCJA) -> float:
    y = np.asarray(y, dtype=float)
    return odejscia_w_czolowce(y, wynik, k_decyla(len(y), frakcja)) / y.sum()


def precision_at(y, wynik, frakcja: float = FRAKCJA) -> float:
    k = k_decyla(len(y), frakcja)
    return odejscia_w_czolowce(y, wynik, k) / k


def metryki_rankingu(y, wynik) -> dict:
    y = np.asarray(y, dtype=int)
    precyzja = precision_at(y, wynik)
    return {
        "n": int(len(y)),
        "odejscia": int(y.sum()),
        "odsetek_odejsc": float(y.mean()),
        "k_decyl": k_decyla(len(y)),
        "auc": float(roc_auc_score(y, wynik)),
        "recall_10": recall_at(y, wynik),
        "precision_10": precyzja,
        "lift_10": precyzja / float(y.mean()),
    }


def bootstrap_par(y, wynik_a, wynik_b, n_prob: int = 2000, ziarno: int = 42) -> dict:
    """95% przedziały (percentylowe) AUC i recall_10 obu wersji oraz różnic a − b na tych samych losowaniach."""
    y = np.asarray(y, dtype=int)
    wynik_a, wynik_b = np.asarray(wynik_a, dtype=float), np.asarray(wynik_b, dtype=float)
    rng = np.random.default_rng(ziarno)
    proby = {"auc_a": [], "auc_b": [], "recall_a": [], "recall_b": []}
    for _ in range(n_prob):
        i = rng.integers(0, len(y), len(y))
        proby["auc_a"].append(roc_auc_score(y[i], wynik_a[i]))
        proby["auc_b"].append(roc_auc_score(y[i], wynik_b[i]))
        proby["recall_a"].append(recall_at(y[i], wynik_a[i]))
        proby["recall_b"].append(recall_at(y[i], wynik_b[i]))
    p = {k: np.asarray(v) for k, v in proby.items()}
    p["auc_roznica"] = p["auc_a"] - p["auc_b"]
    p["recall_roznica"] = p["recall_a"] - p["recall_b"]
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in p.items()}
