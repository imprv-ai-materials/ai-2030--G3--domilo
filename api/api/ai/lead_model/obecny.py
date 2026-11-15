"""Obecna wersja modelu kolejki zapytań: current.yaml (wersja, model, klasa) wczytany przez base.ModelLeadow."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from api.ai.lead_model.base import ModelLeadow

KATALOG_MODELU = Path(__file__).resolve().parent
SCIEZKA_CURRENT = KATALOG_MODELU / "current.yaml"


@dataclass(frozen=True)
class ObecnyModelLeadow:
    wersja: str
    model: ModelLeadow


def wczytaj_obecny(sciezka_current: Path = SCIEZKA_CURRENT) -> ObecnyModelLeadow:
    """Model wskazany w current.yaml. Ścieżka `model` względem katalogu lead_model (albo bezwzględna).

    Sprawdza, że wczytany obiekt ma klasę z pola `klasa`: inaczej current.yaml i plik modelu się rozjechały.
    """
    current = yaml.safe_load(Path(sciezka_current).read_text(encoding="utf-8"))
    model = ModelLeadow.wczytaj(KATALOG_MODELU / current["model"])
    klasa = f"{type(model).__module__}.{type(model).__qualname__}"
    if klasa != current["klasa"]:
        raise ValueError(f"current.yaml: klasa {current['klasa']}, a plik {current['model']} zawiera {klasa}")
    if model.wersja != current["wersja"]:
        raise ValueError(f"current.yaml: wersja {current['wersja']}, a model ma wersja = {model.wersja}")
    return ObecnyModelLeadow(wersja=current["wersja"], model=model)
