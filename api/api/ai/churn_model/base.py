"""Kontrakt modelu listy retencyjnej najemców (wspólny dla wszystkich wersji w versions/).

Wejście (`migawki`): DataFrame, jeden wiersz = kończąca się umowa roczna (B2C / B2B) w dniu migawki, 60 dni przed
`data_do` (tabela `migawki_najemcy`, docs/target_najemcy.md). Wymagane kolumny: `KOLUMNY_WEJSCIA`, czyli `id_umowy`,
`data_migawki` i cechy z `features/najemcy/cechy.py` (`KOLUMNY_CECH`; tylko zdarzenia sprzed dnia migawki,
docs/przecieki_najemcy.md). Wejście może zawierać inne kolumny (np. target w ewaluacji), ale żadna wersja nie może
uczyć się na kolumnach z `KOLUMNY_ZAKAZANE`: wynik po migawce i flaga wypowiedzenia z `migawki_najemcy`,
`score_polityki` i decyzje z `retencja_decyzje` (punkt odniesienia i oferta po migawce) oraz pola wykluczone
(`features/najemcy/wykluczone.yaml`: `rok_urodzenia`, `jezyk_kontaktu`).
Target (`y`): `migawki_najemcy.odejdzie` (1 = najem nie ma kolejnego okresu umowy).
Wynik (`predict`): ryzyko odejścia 0–1 na umowę; wyższe = wyżej na liście retencyjnej. Wersje porównujemy miarami
rankingu (AUC, recall w górnym decylu), więc wynik nie musi być skalibrowanym prawdopodobieństwem.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from api.ai.features.najemcy.wykluczone import WYKLUCZONE

KOLUMNY_WEJSCIA = ("id_umowy", "data_migawki", *KOLUMNY_CECH)
KOLUMNY_ZAKAZANE = frozenset(
    {
        "odejdzie",
        "id_umowy_nastepnej",
        "przeprowadzka",
        "id_najmu_przeprowadzki",
        "data_wyprowadzenia",
        "powod_odejscia",
        "wypowiedzenie_data",
        "wypowiedzenie_przed_migawka",
        "score_polityki",
        "kwalifikuje",
        "grupa",
        "okres",
        "data_oferty",
        "czy_otwarta",
        *WYKLUCZONE,
    }
)


class ModelNajemcow(ABC):
    """Ryzyko odejścia 0–1 dla kończącej się umowy. Każda wersja ustawia `wersja` (nazwa katalogu w versions/)."""

    wersja: str = ""

    def fit(self, migawki: pd.DataFrame, y: pd.Series) -> "ModelNajemcow":
        """Uczy model na migawkach i ich `odejdzie`. Wersje bez uczenia (reguły) zostawiają to tak."""
        return self

    @abstractmethod
    def predict(self, migawki: pd.DataFrame) -> np.ndarray:
        """Ryzyko odejścia 0–1 dla każdej umowy (tablica długości len(migawki))."""

    @abstractmethod
    def explain(self, migawki: pd.DataFrame) -> pd.DataFrame:
        """Z czego wynika ryzyko: wiersz na umowę (indeks jak w migawki), kolumna `wynik` + zależne od wersji."""

    # --- wspólne ---------------------------------------------------------------------------------------------

    @staticmethod
    def sprawdz_kolumny(migawki: pd.DataFrame) -> None:
        brak = [k for k in KOLUMNY_WEJSCIA if k not in migawki.columns]
        if brak:
            raise ValueError(f"Brak kolumn wymaganych przez model listy retencyjnej: {', '.join(brak)}")

    @staticmethod
    def sprawdz_cechy(cechy: Iterable[str], gdzie: str) -> None:
        """Błąd, gdy wersja chce się uczyć na kolumnie zakazanej (wynik, punkt odniesienia, pola wykluczone)."""
        zle = sorted(set(cechy) & KOLUMNY_ZAKAZANE)
        if zle:
            raise ValueError(f"{gdzie}: kolumny zakazane jako cechy (churn_model/base.py): {', '.join(zle)}")

    def zapisz(self, sciezka: Path) -> None:
        Path(sciezka).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, sciezka)

    @staticmethod
    def wczytaj(sciezka: Path) -> "ModelNajemcow":
        model = joblib.load(sciezka)
        if not isinstance(model, ModelNajemcow):
            raise TypeError(f"{sciezka} nie zawiera modelu listy retencyjnej")
        return model


# --- obecne wersje (current.yaml) ----------------------------------------------------------------------------------

KATALOG_MODELU = Path(__file__).resolve().parent
SCIEZKA_CURRENT = KATALOG_MODELU / "current.yaml"
CZESCI_OBECNEGO = ("ryzyko", "uplift")


@dataclass(frozen=True)
class ObecnyModelNajemcow:
    """Wersje listy retencyjnej z current.yaml: `ryzyko` (model przeżycia: ryzyko i czas), `uplift` (oferta)."""

    wersja: str
    wersja_ryzyka: str
    ryzyko: Any
    wersja_upliftu: str
    uplift: Any


def _wczytaj_czesc(opis: dict, czesc: str) -> Any:
    """Model jednej części current.yaml; sprawdza, że plik zawiera klasę i wersję wpisaną w current.yaml."""
    brak = [k for k in ("wersja", "model", "klasa") if not opis.get(k)]
    if brak:
        raise ValueError(f"churn_model/current.yaml: część `{czesc}` bez pól {', '.join(brak)}")
    model = joblib.load(KATALOG_MODELU / opis["model"])
    klasa = f"{type(model).__module__}.{type(model).__qualname__}"
    if klasa != opis["klasa"]:
        raise ValueError(f"current.yaml ({czesc}): klasa {opis['klasa']}, a plik {opis['model']} zawiera {klasa}")
    if getattr(model, "wersja", None) != opis["wersja"]:
        raise ValueError(f"current.yaml ({czesc}): wersja {opis['wersja']}, a model ma wersja = {model.wersja}")
    return model


def wczytaj_obecny(sciezka_current: Path = SCIEZKA_CURRENT) -> ObecnyModelNajemcow:
    """Obecne wersje listy retencyjnej. Pusty current.yaml albo brak części = błąd (nie zgadujemy wersji)."""
    current = yaml.safe_load(Path(sciezka_current).read_text(encoding="utf-8")) or {}
    brak = [c for c in CZESCI_OBECNEGO if not current.get(c)]
    if brak:
        raise ValueError(f"churn_model/current.yaml: brak części {', '.join(brak)} (żadna wersja nie jest aktywna)")
    ryzyko, uplift = (_wczytaj_czesc(current[c], c) for c in CZESCI_OBECNEGO)
    return ObecnyModelNajemcow(
        wersja=str(current.get("wersja") or f"{ryzyko.wersja}+{uplift.wersja}"),
        wersja_ryzyka=ryzyko.wersja,
        ryzyko=ryzyko,
        wersja_upliftu=uplift.wersja,
        uplift=uplift,
    )
