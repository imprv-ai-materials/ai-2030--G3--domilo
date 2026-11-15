"""Odczyt stałych ekonomicznych i warunków banku z zalozenia.yaml (wartości tylko od użytkownika, ze źródłem)."""

from pathlib import Path

import yaml

SCIEZKA_ZALOZEN = Path(__file__).with_name("zalozenia.yaml")


def wczytaj_zalozenia(sciezka: Path = SCIEZKA_ZALOZEN) -> dict[str, dict]:
    """Słownik: nazwa -> {wartosc, jednostka, opis, zrodlo, odpowiedzialny}."""
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))


def bez_odpowiedzialnego(zalozenia: dict[str, dict]) -> list[str]:
    """Nazwy pozycji bez wpisanej osoby odpowiedzialnej (do uzupełnienia przed użyciem w decyzji)."""
    return [k for k, v in zalozenia.items() if not v.get("odpowiedzialny")]
