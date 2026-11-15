"""Szablon faktów: jedna cecha modelu kolejki (KOLUMNY_CECH) -> jeden krótki fakt po polsku (np. „relokacja: Altakom”).

Fakt powstaje z wartości cechy w chwili zapytania i z kontekstu z formularza (`kontekst_faktow`: budżet w zł, nazwa
firmy B2B). Nie używa treści wiadomości ani imienia. Każdy fakt ma `kotwice`: słowa (rdzenie, małe litery), po
których widać go w zdaniu; liczby z tekstu faktu sprawdzamy osobno (ai/lead_model/uzasadnienie.sprawdz_zdanie).
Kotwica pasuje tylko na początku słowa w zdaniu. Fakt ma najwyżej `MAKS_DLUGOSC_FAKTU` znaków, żeby zdanie
awaryjne z trzech faktów zmieściło się w 140 znakach.
"""

import math
import re
from dataclasses import asdict, dataclass

import duckdb
import pandas as pd

MAKS_DLUGOSC_FAKTU = 40
MAKS_DLUGOSC_FIRMY = 18

SQL_KONTEKST = """
SELECT l.id_leada, l.budzet_max, f.nazwa AS firma
FROM crm_leady AS l
LEFT JOIN crm_firmy_b2b AS f ON f.id_firmy = l.id_firmy_b2b
"""

ZRODLA = {  # wartość -> (tekst, kotwice)
    "lokum24": ("źródło: portal lokum24", ("lokum", "portal")),
    "domteraz": ("źródło: portal domteraz", ("domteraz", "portal")),
    "www": ("źródło: strona Domilo", ("strona domilo", "stronie domilo", "www")),
    "relokacja_b2b": ("źródło: program relokacji B2B", ("program relokac",)),
    "social": ("źródło: media społecznościowe", ("społeczno", "social")),
    "polecenie": ("źródło: polecenie", ("polec",)),
}
MIASTA = {
    "Warszawa": ("warszaw",),
    "Kraków": ("krak",),
    "Wrocław": ("wrocław",),
    "Poznań": ("pozna",),
    "Gdańsk": ("gdańs", "gdańsk"),
    "Łódź": ("łódź", "łodzi", "łódzk"),
}
LINIE = {
    "B2B": ("najem firmowy B2B", ("b2b", "firmow")),
    "B2C": ("najem roczny B2C", ("b2c", "roczn")),
    "MID": ("najem średnioterminowy MID", ("mid", "średnioterm")),
}
SYGNALY = {  # cecha -> (tekst gdy 1, tekst gdy 0, kotwice)
    "syg_konkretne_pytania": ("konkretne pytania w wiadomości", "bez konkretnych pytań", ("pytani", "pytań")),
    "syg_niedopasowanie_oferty": ("prośba spoza oferty Domilo", "zapytanie zgodne z ofertą", ("ofert",)),
    "syg_pilny_termin": ("pilny termin", "bez pilnego terminu", ("piln",)),
    "syg_relokacja": ("relokacja", "bez relokacji", ("relokac",)),
    "syg_budzet_niski": ("za niski budżet", "budżet nie jest za niski", ("nisk",)),
    "syg_brak_informacji": ("mało informacji o potrzebach", "konkretne informacje o potrzebach", ("informac",)),
}


@dataclass(frozen=True)
class Fakt:
    cecha: str
    tekst: str
    kotwice: tuple[str, ...]

    def jako_slownik(self) -> dict:
        return asdict(self) | {"kotwice": list(self.kotwice)}

    @staticmethod
    def ze_slownika(d: dict) -> "Fakt":
        return Fakt(cecha=d["cecha"], tekst=d["tekst"], kotwice=tuple(d["kotwice"]))


def kontekst_faktow(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """id_leada, budzet_max, firma (nazwa z crm_firmy_b2b, pola formularza znane w chwili zapytania)."""
    return con.execute(SQL_KONTEKST).df()


def _brak(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or x is pd.NA


def odmiana(n: int, jeden: str, kilka: str, wiele: str) -> str:
    """Polska forma liczebnika: 1 lokal, 2–4 lokale, 5–21 lokali, 22–24 lokale, …"""
    if n == 1:
        return jeden
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return kilka
    return wiele


def krotka_firma(nazwa) -> str | None:
    """Nazwa firmy bez formy prawnej (S.A., sp. z o.o., …), najwyżej MAKS_DLUGOSC_FIRMY znaków."""
    if _brak(nazwa):
        return None
    krotka = re.sub(r"\s+(S\.?A\.?|sp\.? z o\.? ?o\.?|sp\.? j\.?|sp\.? k\.?)$", "", str(nazwa), flags=re.I).strip()
    return krotka[:MAKS_DLUGOSC_FIRMY].rstrip()


def _kwota(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", " ")


def _z_firma(tekst: str, firma: str | None, kotwice: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    if firma and len(f"{tekst}: {firma}") <= MAKS_DLUGOSC_FAKTU:
        return f"{tekst}: {firma}", kotwice + (firma.lower(),)
    return tekst, kotwice


def fakt(cecha: str, wartosc, kontekst: dict) -> Fakt:
    """Fakt dla jednej cechy (`wartosc` jak w macierzy cech: kategorie tekstem, liczby float, brak = NaN)."""
    firma = krotka_firma(kontekst.get("firma"))
    if cecha == "zrodlo":
        tekst, kotwice = ZRODLA.get(wartosc, (f"źródło: {wartosc}", (str(wartosc).lower(),)))
        kotwice = kotwice + ("źródł",)
    elif cecha == "miasto":
        tekst, kotwice = f"miasto: {wartosc}", MIASTA.get(wartosc, (str(wartosc).lower(),))
    elif cecha == "linia":
        tekst, kotwice = LINIE.get(wartosc, (f"linia: {wartosc}", (str(wartosc).lower(),)))
    elif cecha == "termin_dni":
        kotwice = ("termin", "wprowadz")
        if _brak(wartosc):
            tekst = "termin wprowadzenia nie podany"
        elif wartosc < 0:
            tekst = "termin wprowadzenia już minął"
        elif wartosc == 0:
            tekst = "wprowadzenie od dnia zapytania"
        else:
            n = int(wartosc)
            tekst = f"wprowadzenie za {n} {odmiana(n, 'dzień', 'dni', 'dni')}"
    elif cecha == "liczba_osob":
        kotwice = ("osób", "osoby")  # nie „osoba”: ogólne słowo, liczbę osób łapie kontrola liczb
        if _brak(wartosc):
            tekst = "liczba osób nie podana"
        else:
            n = int(wartosc)
            tekst = f"{n} {odmiana(n, 'osoba', 'osoby', 'osób')}"
    elif cecha == "zwierze":
        kotwice = ("zwierz",)
        tekst = "zwierzę: nie podano" if _brak(wartosc) else ("ze zwierzęciem" if wartosc else "bez zwierzęcia")
    elif cecha == "liczba_lokali":
        kotwice = ("lokale", "lokali")
        if _brak(wartosc):
            tekst = "liczba lokali nie podana"
        else:
            n = int(wartosc)
            tekst, kotwice = _z_firma(f"{n} {odmiana(n, 'lokal', 'lokale', 'lokali')}", firma, kotwice)
    elif cecha == "budzet_do_mediany":
        kotwice = ("budżet", "budżec", "zł", "median")
        budzet = kontekst.get("budzet_max")
        if _brak(wartosc) or _brak(budzet):
            tekst = "budżet nie podany"
        else:
            tekst = f"budżet {_kwota(budzet)} zł, {round(wartosc * 100)}% mediany w mieście"
    elif cecha == "www_liczba_sesji":
        kotwice = ("wizyt", "sesj", "stron")
        n = 0 if _brak(wartosc) else int(wartosc)
        tekst = (
            "bez wizyt na stronie przed zapytaniem"
            if n == 0
            else f"{n} {odmiana(n, 'wizyta', 'wizyty', 'wizyt')} na stronie"
        )
    elif cecha == "www_spacer_3d":
        tekst, kotwice = ("obejrzany spacer 3D" if wartosc == 1 else "bez spaceru 3D"), ("spacer", "3d")
    elif cecha == "www_kalkulator":
        tekst, kotwice = ("użyty kalkulator na stronie" if wartosc == 1 else "bez kalkulatora"), ("kalkulat",)
    elif cecha == "umowa_ramowa":
        kotwice = ("ramow",)
        tekst, kotwice = _z_firma("umowa ramowa", firma, kotwice) if wartosc == 1 else ("bez umowy ramowej", kotwice)
    elif cecha == "dlugosc_wiadomosci":
        kotwice = ("wiadomo", "znak")
        n = 0 if _brak(wartosc) else int(wartosc)
        tekst = "bez wiadomości" if n == 0 else f"wiadomość {n} {odmiana(n, 'znak', 'znaki', 'znaków')}"
    elif cecha in SYGNALY:
        tak, nie, kotwice = SYGNALY[cecha]
        if _brak(wartosc):
            tekst = "brak oceny treści przez LLM"
        elif wartosc == 1:
            tekst = tak
            if cecha == "syg_relokacja":
                tekst, kotwice = _z_firma(tak, firma, kotwice)
        else:
            tekst = nie
    else:
        raise ValueError(f"Brak szablonu faktu dla cechy {cecha}")
    return Fakt(cecha=cecha, tekst=tekst[:MAKS_DLUGOSC_FAKTU], kotwice=tuple(kotwice))


def fakty_leada(cechy: dict, kontekst: dict, kolumny: tuple[str, ...]) -> dict[str, Fakt]:
    """Fakt dla każdej cechy z `kolumny` (wiersz cech jako słownik)."""
    return {c: fakt(c, cechy[c], kontekst) for c in kolumny}
