"""Kontrakt modelu alertów o awariach wind (wspólny dla wszystkich wersji w versions/).

Wejście (`dni`): DataFrame, jeden wiersz = winda × dzień oceny z `dni_wind` (ocena o 06:00 Europe/Warsaw;
docs/b4_target.md). Wymagane kolumny: `KOLUMNY_KLUCZA` (`id_windy`, `dzien`) i cechy wersji (atrybut `cechy`
po `fit`), czyli kolumny `cechy_windy` (docs/b4_cechy.md) i `cechy_windy_tsfresh` (docs/b4_tsfresh.md), liczone
tylko z telemetrii zakończonej do 05:50 dnia oceny (`features/windy/zbior.py` składa je w jedną ramkę).
Wejście może zawierać inne kolumny (np. target w ewaluacji), ale żadna wersja nie może uczyć się na kolumnach
z `KOLUMNY_ZAKAZANE`: target i opis przyszłej awarii z `dni_wind` oraz identyfikatory (winda, budynek), które
pozwalałyby zapamiętać konkretną windę zamiast uczyć się objawów.
Target (`y`): `dni_wind.awaria_7d` (1 = start awarii w (06:00 t; 06:00 t+7]).
Wynik (`predict`): ryzyko 0–1 na wiersz; wyższe = wyżej na liście alertów. Wersje porównujemy miarami rankingu
(ROC AUC, PR-AUC), więc wynik nie musi być skalibrowanym prawdopodobieństwem.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

KATALOG_MODELU = Path(__file__).resolve().parent
SCIEZKA_CURRENT = KATALOG_MODELU / "current.yaml"

KOLUMNY_KLUCZA = ("id_windy", "dzien")
KOLUMNY_ZAKAZANE = frozenset(
    {
        # target i przyszłość (dni_wind)
        "awaria_7d",
        "liczba_awarii_7d",
        "id_awarii",
        "podzespol",
        "godziny_do_startu",
        "koniec_okna",
        # identyfikatory i czas oceny
        "id_windy",
        "id_budynku",
        "dzien",
        "moment_predykcji",
    }
)


class ModelWind(ABC):
    """Ryzyko awarii windy w 7 dni (0–1). Każda wersja ustawia `wersja` (nazwa katalogu w versions/)."""

    wersja: str = ""
    cechy: tuple[str, ...] = ()

    def fit(self, dni: pd.DataFrame, y: pd.Series, **kwargs) -> "ModelWind":
        """Uczy model na wierszach dni_wind i ich `awaria_7d`. Wersje bez uczenia (reguły) zostawiają to tak."""
        return self

    @abstractmethod
    def predict(self, dni: pd.DataFrame) -> np.ndarray:
        """Ryzyko 0–1 dla każdego wiersza (tablica długości len(dni))."""

    @abstractmethod
    def explain(self, dni: pd.DataFrame) -> pd.DataFrame:
        """Z czego wynika ryzyko: wiersz na wiersz wejścia (indeks jak w dni), kolumna `wynik` + zależne od wersji."""

    # --- wspólne ---------------------------------------------------------------------------------------------

    def sprawdz_kolumny(self, dni: pd.DataFrame) -> None:
        brak = [k for k in (*KOLUMNY_KLUCZA, *self.cechy) if k not in dni.columns]
        if brak:
            raise ValueError(f"Brak kolumn wymaganych przez {self.wersja or 'model wind'}: {', '.join(brak)}")

    @staticmethod
    def sprawdz_cechy(cechy: Iterable[str], gdzie: str) -> None:
        """Błąd, gdy wersja chce się uczyć na kolumnie zakazanej (target, przyszła awaria, identyfikator)."""
        zle = sorted(set(cechy) & KOLUMNY_ZAKAZANE)
        if zle:
            raise ValueError(f"{gdzie}: kolumny zakazane jako cechy (failure_model/base.py): {', '.join(zle)}")

    def zapisz(self, sciezka: Path) -> None:
        Path(sciezka).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, sciezka)

    @staticmethod
    def wczytaj(sciezka: Path) -> "ModelWind":
        model = joblib.load(sciezka)
        if not isinstance(model, ModelWind):
            raise TypeError(f"{sciezka} nie zawiera modelu wind")
        return model


def wczytaj_obecny(sciezka_current: Path = SCIEZKA_CURRENT) -> ModelWind:
    """Wersja wskazana w current.yaml (pole `model`, ścieżka względem failure_model/). Pusty = błąd (nie zgadujemy)."""
    current = yaml.safe_load(Path(sciezka_current).read_text(encoding="utf-8")) or {}
    if not current.get("model"):
        raise ValueError("failure_model/current.yaml: brak wersji (żadna wersja nie jest aktywna)")
    model = ModelWind.wczytaj(Path(sciezka_current).parent / current["model"])
    if model.wersja != current.get("wersja"):
        raise ValueError(f"current.yaml wskazuje {current.get('wersja')}, a plik zawiera {model.wersja}")
    return model
