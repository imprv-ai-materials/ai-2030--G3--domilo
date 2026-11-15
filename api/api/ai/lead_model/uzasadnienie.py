"""Uzasadnienie pozycji zapytania w kolejce: 3 cechy o największym dodatnim wkładzie SHAP -> fakty -> zdanie z LLM.

1. `top_wklady`: z `explain()` modelu LightGBM (wkłady SHAP w log-szansę, `wklad_<cecha>`) cechy o wkładzie > 0,
   malejąco, najwyżej 3. Zapytanie bez dodatnich wkładów nie dostaje faktów.
2. Fakty: szablon z features/leady/fakty.py (jeden fakt na cechę).
3. `uzasadnij`: LLM (prompt `uzasadnienie_v1`, schemat `Uzasadnienie`, temperatura 0, cache odpowiedzi w KlientLLM)
   układa jedno zdanie z faktów top 3. `sprawdz_zdanie` sprawdza długość (≤ 140 znaków), liczby (tylko z faktów
   top 3) i kotwice faktów spoza top 3 (np. miasto, firma, źródło, których nie ma w top 3). Gdy zdanie nie przejdzie
   kontroli albo wywołanie się nie uda, zostaje zdanie z szablonu (`zdanie_z_szablonu`).
Kontrola kotwic jest heurystyczna: wyłapie nazwę, liczbę lub słowo kluczowe innego faktu, ale nie omówienie
(np. „stolica” zamiast „Warszawa”).
"""

import re
from dataclasses import dataclass, field

import pandas as pd
from api.adapters.llm_client import KlientLLM
from api.ai.features.leady.fakty import Fakt
from api.ai.llm.prompty import Prompt, wczytaj_prompt
from api.ai.llm.schemas.uzasadnienie import MAKS_DLUGOSC_ZDANIA, Uzasadnienie

LICZBA_FAKTOW = 3
WERSJA_PROMPTU = "uzasadnienie_v1"
ZDANIE_BEZ_FAKTOW = "Żadna cecha tego zapytania nie podnosi jego wyniku."
POCZATEK_SZABLONU = "Za zapytaniem: "
KODY_Z_CYFRAMI = ("B2B", "B2C", "3D", "lokum24")  # nazwy z cyframi, które nie są liczbami


@dataclass(frozen=True)
class Wynik:
    zdanie: str
    zrodlo: str  # "llm" | "szablon" | "bez_faktow"
    zdanie_llm: str | None = None
    problemy_llm: tuple[str, ...] = field(default_factory=tuple)
    z_cache: bool | None = None


def top_wklady(wklady: pd.Series, n: int = LICZBA_FAKTOW) -> list[tuple[str, float]]:
    """[(cecha, wkład)] dla najwyżej n cech o dodatnim wkładzie, malejąco (`wklady`: indeks = wklad_<cecha>)."""
    w = wklady.drop(labels=["wklad_staly"], errors="ignore")
    w = w[w > 0].sort_values(ascending=False, kind="mergesort").head(n)
    return [(str(k).removeprefix("wklad_"), float(v)) for k, v in w.items()]


def _liczby(tekst: str) -> set[str]:
    for kod in KODY_Z_CYFRAMI:
        tekst = re.sub(re.escape(kod), " ", tekst, flags=re.I)
    tekst = re.sub(r"(?<=\d)[  ](?=\d{3}(?!\d))", "", tekst)  # 3 500 -> 3500
    return set(re.findall(r"\d+", tekst))


def sprawdz_zdanie(zdanie: str, top: list[Fakt], pozostale: list[Fakt]) -> list[str]:
    """Lista problemów (pusta = zdanie poprawne): długość, liczby spoza top 3, kotwice faktów spoza top 3."""
    problemy = []
    if not zdanie or not zdanie.strip():
        problemy.append("puste zdanie")
    if len(zdanie) > MAKS_DLUGOSC_ZDANIA:
        problemy.append(f"długość {len(zdanie)} > {MAKS_DLUGOSC_ZDANIA}")
    tekst_top = " ".join(f.tekst for f in top)
    obce_liczby = _liczby(zdanie) - _liczby(tekst_top)
    if obce_liczby:
        problemy.append(f"liczby spoza top 3: {', '.join(sorted(obce_liczby))}")
    male_top, male_zdanie = tekst_top.lower(), zdanie.lower()
    for f in pozostale:  # kotwica = początek słowa („pytani” nie trafia w „zapytanie”)
        trafione = [k for k in f.kotwice if k not in male_top and re.search(r"(?<!\w)" + re.escape(k), male_zdanie)]
        if trafione:
            problemy.append(f"fakt spoza top 3: {f.cecha} ({trafione[0]})")
    return problemy


def zdanie_z_szablonu(top: list[Fakt]) -> str:
    """Zdanie awaryjne: „Za zapytaniem: fakt1; fakt2; fakt3.” (odcina fakty od końca, gdyby przekroczyło limit)."""
    if not top:
        return ZDANIE_BEZ_FAKTOW
    for n in range(len(top), 0, -1):
        zdanie = POCZATEK_SZABLONU + "; ".join(f.tekst for f in top[:n]) + "."
        if len(zdanie) <= MAKS_DLUGOSC_ZDANIA:
            return zdanie
    return zdanie[:MAKS_DLUGOSC_ZDANIA]


def wejscie_llm(top: list[Fakt]) -> str:
    """Fakty jako lista numerowana (to jest `opis` w szablonie promptu i część klucza cache)."""
    return "\n".join(f"{i}. {f.tekst}" for i, f in enumerate(top, start=1))


def uzasadnij(top: list[Fakt], pozostale: list[Fakt], klient: KlientLLM | None, prompt: Prompt | None = None) -> Wynik:
    """Zdanie z LLM, gdy przejdzie `sprawdz_zdanie`; w przeciwnym razie zdanie z szablonu (z opisem problemów)."""
    if not top:
        return Wynik(zdanie=ZDANIE_BEZ_FAKTOW, zrodlo="bez_faktow")
    if klient is None:
        return Wynik(zdanie=zdanie_z_szablonu(top), zrodlo="szablon", problemy_llm=("bez klienta LLM",))
    prompt = prompt or wczytaj_prompt(WERSJA_PROMPTU)
    try:
        odp = klient.zapytaj(wejscie_llm(top), prompt, Uzasadnienie)
    except Exception as e:  # noqa: BLE001 — błąd API lub schematu: zdanie z szablonu, kolejka działa dalej
        return Wynik(zdanie=zdanie_z_szablonu(top), zrodlo="szablon", problemy_llm=(f"{type(e).__name__}",))
    zdanie = odp.dane["zdanie"].strip()
    problemy = sprawdz_zdanie(zdanie, top, pozostale)
    if problemy:
        return Wynik(
            zdanie=zdanie_z_szablonu(top), zrodlo="szablon", zdanie_llm=zdanie,
            problemy_llm=tuple(problemy), z_cache=odp.z_cache,
        )  # fmt: skip
    return Wynik(zdanie=zdanie, zrodlo="llm", zdanie_llm=zdanie, z_cache=odp.z_cache)
