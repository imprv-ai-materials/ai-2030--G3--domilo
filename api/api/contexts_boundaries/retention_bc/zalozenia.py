"""Odczyt stałych ekonomicznych oferty retencyjnej z zalozenia.yaml (wartości tylko od użytkownika, ze źródłem)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

SCIEZKA_ZALOZEN = Path(__file__).with_name("zalozenia.yaml")
POLA = ("wartosc", "jednostka", "opis", "zrodlo", "data", "odpowiedzialny")


@dataclass(frozen=True)
class ZalozeniaOferty:
    R: float  # koszt odejścia najemcy (PLN)
    D: float  # roczny rabat dla przedłużającego z ofertą (PLN)
    k: float  # koszt kontaktu / wysłania oferty (PLN)


def wczytaj_zalozenia(sciezka: Path = SCIEZKA_ZALOZEN) -> dict[str, dict]:
    """Słownik: nazwa -> {wartosc, jednostka, opis, zrodlo, data, odpowiedzialny}."""
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))


def zalozenia_oferty(sciezka: Path = SCIEZKA_ZALOZEN) -> ZalozeniaOferty:
    """R, D, k z pliku; błąd, gdy brakuje wartości albo opisu źródła / osoby odpowiedzialnej."""
    z = wczytaj_zalozenia(sciezka)
    for nazwa in ("koszt_odejscia_R", "rabat_roczny_D", "koszt_kontaktu_k"):
        brak = [p for p in POLA if z.get(nazwa, {}).get(p) is None]
        if brak:
            raise ValueError(f"retention_bc/zalozenia.yaml: {nazwa} bez pól {', '.join(brak)}")
    return ZalozeniaOferty(
        R=float(z["koszt_odejscia_R"]["wartosc"]),
        D=float(z["rabat_roczny_D"]["wartosc"]),
        k=float(z["koszt_kontaktu_k"]["wartosc"]),
    )


def budzet_rabatow(sciezka: Path = SCIEZKA_ZALOZEN) -> float | None:
    """Roczny budżet rabatów (PLN) albo None, gdy nie ustalono (wtedy /risk nie ogranicza ofert budżetem)."""
    wartosc = wczytaj_zalozenia(sciezka).get("budzet_rabatow_rok", {}).get("wartosc")
    return None if wartosc is None else float(wartosc)
