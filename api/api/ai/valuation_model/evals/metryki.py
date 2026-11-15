"""Metryki wyceny: błędy w PLN (MAE, RMSE) i błędy względne w % (MAPE, MdAPE)."""

import numpy as np


def metryki(y_prawdziwe, y_wycena) -> dict[str, float]:
    y = np.asarray(y_prawdziwe, dtype=float)
    p = np.asarray(y_wycena, dtype=float)
    blad = p - y
    blad_wzgl = np.abs(blad) / y
    return {
        "n": int(len(y)),
        "mae": float(np.mean(np.abs(blad))),
        "rmse": float(np.sqrt(np.mean(blad**2))),
        "mape": float(100 * np.mean(blad_wzgl)),
        "mdape": float(100 * np.median(blad_wzgl)),
        # Mediana błędu ze znakiem (%): < 0 = model zaniża wycenę.
        "mediana_bledu_proc": float(100 * np.median(blad / y)),
    }
