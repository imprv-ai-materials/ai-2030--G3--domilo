"""Kontrakt modelu kolejki zapytań (wspólny dla wszystkich wersji w versions/).

Wejście (`leady`): DataFrame z kolumnami `KOLUMNY_WEJSCIA`, jeden wiersz = jedno zapytanie z `crm_leady`. Są to
tylko pola znane w chwili utworzenia zapytania; stan na dzień eksportu (`status`, `data_statusu`, `powod_utraty`,
`id_doradcy`, `id_umowy`) nie wchodzi do modelu. `imie` jest w wejściu wyłącznie po to, by wersje z LLM mogły usunąć
je z treści wiadomości; żadna wersja nie może go używać jako cechy.
Target (`y`): `leady_cel.umowa_45d` (umowa w ciągu 45 dni od zapytania; docs/kolejka_target.md).
Wynik (`predict`): liczba z przedziału 0–1 na zapytanie; wyższa = wcześniej w kolejce. Nie musi być
prawdopodobieństwem (v1_llm_zero_shot zwraca ocenę / 10), więc porównujemy wersje miarami rankingu.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

KOLUMNY_WEJSCIA = (
    "id_leada",
    "utworzono",
    "zrodlo",
    "miasto",
    "linia_pref",
    "budzet_max",
    "termin_wprowadzenia",
    "liczba_osob",
    "zwierze",
    "liczba_lokali",
    "wiadomosc",
    "imie",
)


class ModelLeadow(ABC):
    """Wynik 0–1 dla zapytania. Każda wersja ustawia `wersja` (nazwa katalogu w versions/)."""

    wersja: str = ""

    def fit(self, leady: pd.DataFrame, y: pd.Series) -> "ModelLeadow":
        """Uczy model na zapytaniach i ich `umowa_45d`. Wersje bez uczenia (np. zero-shot LLM) zostawiają to tak."""
        return self

    @abstractmethod
    def predict(self, leady: pd.DataFrame) -> np.ndarray:
        """Wynik 0–1 dla każdego zapytania (tablica długości len(leady); NaN = brak wyniku, np. błąd API)."""

    @abstractmethod
    def explain(self, leady: pd.DataFrame) -> pd.DataFrame:
        """Z czego wynika wynik: jeden wiersz na zapytanie (indeks jak w leady), kolumna `wynik` + zależne od wersji."""

    # --- wspólne ---------------------------------------------------------------------------------------------

    @staticmethod
    def sprawdz_kolumny(leady: pd.DataFrame) -> None:
        brak = [k for k in KOLUMNY_WEJSCIA if k not in leady.columns]
        if brak:
            raise ValueError(f"Brak kolumn wymaganych przez model kolejki: {', '.join(brak)}")

    def zapisz(self, sciezka: Path) -> None:
        Path(sciezka).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, sciezka)

    @staticmethod
    def wczytaj(sciezka: Path) -> "ModelLeadow":
        model = joblib.load(sciezka)
        if not isinstance(model, ModelLeadow):
            raise TypeError(f"{sciezka} nie zawiera modelu kolejki")
        return model
