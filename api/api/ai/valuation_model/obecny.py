"""Obecna wersja modelu wyceny: current.yaml (wersja, model, klasa) wczytany przez kontrakt base.ModelWyceny."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from api.ai.valuation_model.base import ModelWyceny

KATALOG_MODELU = Path(__file__).resolve().parent
SCIEZKA_CURRENT = KATALOG_MODELU / "current.yaml"


@dataclass(frozen=True)
class ObecnyModel:
    wersja: str
    model: ModelWyceny


def wczytaj_obecny(sciezka_current: Path = SCIEZKA_CURRENT) -> ObecnyModel:
    """Model wskazany w current.yaml. Ścieżka `model` względem katalogu valuation_model (albo bezwzględna).

    Sprawdza, że wczytany obiekt ma klasę z pola `klasa`: inaczej current.yaml i plik modelu się rozjechały.
    """
    current = yaml.safe_load(Path(sciezka_current).read_text(encoding="utf-8"))
    model = ModelWyceny.wczytaj(KATALOG_MODELU / current["model"])
    klasa = f"{type(model).__module__}.{type(model).__qualname__}"
    if klasa != current["klasa"]:
        raise ValueError(f"current.yaml: klasa {current['klasa']}, a plik {current['model']} zawiera {klasa}")
    return ObecnyModel(wersja=current["wersja"], model=model)
