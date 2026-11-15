"""Kwoty w opisach: cena sprzedaży w ogłoszeniach (radar_oferty.opis) i czynsz najmu w opisach Domilo.

Szablony wzmianek o cenie w `radar_oferty.opis` (częstości: docs/b1_przeciek_opisu.md):
- kwota:   „Cena: 414 000 zł.”, „Cena 1305 tys.”, „Cena 518 tys. zł.”, „Cena do negocjacji: 605 000.”;
- zl_m2:   „Tylko 17 800 zł/m².”;
- rata:    „Rata od 1 880 zł miesięcznie.”;
- obnizka: „Obniżka z 814 do 761 tys.” (druga liczba = cena po obniżce).
Zdania bez kwoty („cena uwzględnia nakłady”, „Niski czynsz administracyjny”) nie są wzmianką o cenie.

Opis lokalu Domilo (`lokale_domilo_opisy.opis_marketingowy`) podaje czynsz najmu, a nie cenę sprzedaży:
„Miesięcznie 2 550 zł”, „Czynsz 3 540 zł + media”, „Czynsz: 3 230 zł/mies.”.

UWAGA: cena z opisu to cena ofertowa tego samego lokalu. Jako cecha modelu wyceny to przeciek: w ten sposób
podajemy modelowi prawie gotową odpowiedź, której przy wycenie lokalu Domilo nie ma.
"""

import re

_LICZBA = r"-?\d{1,3}(?:[   ]\d{3})+|-?\d+"  # „1 220 000” (spacja zwykła lub nierozdzielająca) albo „1305”
_WZORCE = {
    "kwota_zl": re.compile(rf"Cena: ({_LICZBA}) zł"),
    "kwota_tys": re.compile(rf"Cena ({_LICZBA}) tys\."),
    "kwota_negocjacje": re.compile(rf"Cena do negocjacji: ({_LICZBA})"),
    "zl_m2": re.compile(rf"({_LICZBA}) zł/m²"),
    "rata": re.compile(rf"Rata od ({_LICZBA}) zł"),
    "obnizka": re.compile(rf"Obniżka z ({_LICZBA}) do ({_LICZBA}) tys\."),
}
_TYP = {"kwota_zl": "kwota", "kwota_tys": "kwota", "kwota_negocjacje": "kwota"}
_CZYNSZ = re.compile(rf"(?:Miesięcznie|Czynsz:?) ({_LICZBA}) zł")


def _liczba(tekst: str) -> int:
    return int(re.sub(r"[   ]", "", tekst))


def wzmianki_o_cenie(opis: str) -> set[str]:
    """Typy wzmianek z kwotą: podzbiór {kwota, zl_m2, rata, obnizka}."""
    return {_TYP.get(nazwa, nazwa) for nazwa, wzor in _WZORCE.items() if wzor.search(opis)}


# Szablon -> (wzorzec, numer grupy z liczbą, mnożnik). Kolejność = pierwszeństwo: kwota całkowita, cena po obniżce,
# cena za m² (mnożnik None = × metraż). Rata nie wystarcza do ustalenia ceny.
_CENA = {
    "cena_zl": (_WZORCE["kwota_zl"], 1, 1),
    "cena_negocjacje": (_WZORCE["kwota_negocjacje"], 1, 1),
    "cena_tys": (_WZORCE["kwota_tys"], 1, 1000),
    "obnizka": (_WZORCE["obnizka"], 2, 1000),
    "zl_m2": (_WZORCE["zl_m2"], 1, None),
}


def szablon_ceny(opis: str) -> str | None:
    """Szablon, z którego cena_z_opisu bierze cenę (klucz _CENA), albo None."""
    return next((nazwa for nazwa, (wzor, _, _) in _CENA.items() if wzor.search(opis)), None)


def cena_z_opisu(opis: str, metraz: float) -> float | None:
    """Cena sprzedaży w PLN podana w opisie albo None (kolejność szablonów: _CENA)."""
    szablon = szablon_ceny(opis)
    if szablon is None:
        return None
    wzor, grupa, mnoznik = _CENA[szablon]
    liczba = _liczba(wzor.search(opis).group(grupa))
    return round(liczba * metraz) if mnoznik is None else liczba * mnoznik


def czynsz_najmu_z_opisu(opis: str) -> int | None:
    """Miesięczny czynsz najmu w PLN z opisu marketingowego lokalu Domilo albo None."""
    m = _CZYNSZ.search(opis)
    return _liczba(m.group(1)) if m else None
