"""Odczyt stałych ekonomicznych kolejki zapytań z zalozenia.yaml (wartości tylko od użytkownika, ze źródłem i datą)."""

from pathlib import Path

import yaml

SCIEZKA_ZALOZEN = Path(__file__).with_name("zalozenia.yaml")
MILION = 1_000_000


def wczytaj_zalozenia(sciezka: Path = SCIEZKA_ZALOZEN) -> dict[str, dict]:
    """Słownik: nazwa -> {wartosc, jednostka, opis, zrodlo, data, odpowiedzialny}."""
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))


def koszt_na_1000_zapytan(
    tokeny_wejscia: int, tokeny_wejscia_z_cache: int, tokeny_wyjscia: int, zapytan: int, cennik: dict
) -> float | None:
    """Koszt 1 000 zapytań w walucie cennika; None, gdy w cenniku brakuje którejkolwiek ceny.

    Tokeny to sumy z `zapytan` wywołań. Tokeny z cache promptu są częścią tokenów wejścia (tak liczy OpenAI).
    """
    ceny = ("wejscie_za_1m_tokenow", "wejscie_z_cache_za_1m_tokenow", "wyjscie_za_1m_tokenow")
    if any(cennik.get(c) is None for c in ceny):
        return None
    koszt = (
        (tokeny_wejscia - tokeny_wejscia_z_cache) * cennik["wejscie_za_1m_tokenow"]
        + tokeny_wejscia_z_cache * cennik["wejscie_z_cache_za_1m_tokenow"]
        + tokeny_wyjscia * cennik["wyjscie_za_1m_tokenow"]
    ) / MILION
    return koszt / zapytan * 1000
