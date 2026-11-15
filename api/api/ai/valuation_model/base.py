"""Kontrakt modelu wyceny lokali (wspólny dla wszystkich wersji w versions/).

Wejście (`X`): DataFrame z kolumnami `KOLUMNY_CECH`, jeden wiersz = jeden lokal. Te same kolumny da się zbudować
dla transakcji RCN (`rcn_transakcje`) i dla lokali Domilo (`pms_lokale` + `pms_budynki`: miasto, dzielnica,
`rok_oddania` jako `rok_budowy`).
Target (`y`): cena transakcyjna w PLN (`rcn_transakcje.cena_pln`), nie cena ofertowa.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

KOLUMNY_CECH = ("miasto", "dzielnica", "metraz", "pokoje", "pietro", "rok_budowy")
KOLUMNY_PRZEDZIALU = ("p10", "p50", "p90")


class ModelWyceny(ABC):
    """Wycena lokalu w PLN. Każda wersja ustawia `wersja` (nazwa katalogu w versions/)."""

    wersja: str = ""

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelWyceny":
        """Uczy model na lokalach `X` i cenach transakcyjnych `y` (PLN). Zwraca self."""

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Wycena punktowa każdego lokalu w PLN (tablica długości len(X))."""

    def predict_interval(self, X: pd.DataFrame) -> pd.DataFrame:
        """Przedział wyceny w PLN: kolumny p10, p50, p90 (przedział 80% = p10–p90), indeks jak w X."""
        raise NotImplementedError(f"{type(self).__name__} nie ma jeszcze przedziału wyceny")

    @abstractmethod
    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Z czego wynika wycena: jeden wiersz na lokal (indeks jak w X), kolumny zależne od wersji."""

    # --- wspólne ---------------------------------------------------------------------------------------------

    @staticmethod
    def sprawdz_kolumny(X: pd.DataFrame) -> None:
        brak = [k for k in KOLUMNY_CECH if k not in X.columns]
        if brak:
            raise ValueError(f"Brak kolumn wymaganych przez model wyceny: {', '.join(brak)}")

    def zapisz(self, sciezka: Path) -> None:
        Path(sciezka).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, sciezka)

    @staticmethod
    def wczytaj(sciezka: Path) -> "ModelWyceny":
        model = joblib.load(sciezka)
        if not isinstance(model, ModelWyceny):
            raise TypeError(f"{sciezka} nie zawiera modelu wyceny")
        return model
