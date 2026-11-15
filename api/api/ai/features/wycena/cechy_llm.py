"""Cechy lokalu z LLM (schemat CechyLokalu): ekstrakcja równoległa przez KlientLLM i kolumny dla modelu wyceny.

Prompty: `cechy_lokalu_v1` (opis bez kwot, ceny_w_opisie.bez_kwot) i `cechy_lokalu_zdjecia_v1` (zdjęcia lokalu).
Odpowiedzi trafiają do cache klienta (ai/llm/cache), więc ponowne uruchomienie nie płaci drugi raz.
Raport: docs/b1_v4_llm_cechy.md.
"""

import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from api.adapters.llm_client import KlientLLM
from api.ai.llm.prompty import Prompt
from api.ai.llm.schemas.cechy_lokalu import CechyLokalu

POLA = tuple(CechyLokalu.model_fields)
KOLUMNY_TOKENOW = ("tokeny_wejscia", "tokeny_wyjscia", "tokeny_wejscia_z_cache")
# Kolumny modelu wyceny (v4_llm_cechy). `pewnosc` opisuje odczyt, nie lokal, i była najmniej stabilna
# (docs/llm_cechy_lokalu_v1.md), więc nie jest cechą modelu.
KOLUMNY_LLM = ("llm_standard", "llm_ekspozycja", "llm_widok", "llm_balkon", "llm_stan_budynku")
LLM_LICZBOWE = ("llm_standard",)
LLM_KATEGORII = ("llm_ekspozycja", "llm_widok", "llm_balkon", "llm_stan_budynku")
_Z_POLA = {
    "standard_1_5": "llm_standard",
    "ekspozycja": "llm_ekspozycja",
    "widok": "llm_widok",
    "balkon": "llm_balkon",
    "stan_budynku": "llm_stan_budynku",
}


def wyciagnij(
    klient: KlientLLM, rekordy: pd.DataFrame, prompt: Prompt, watki: int = 16, postep: int | None = None
) -> pd.DataFrame:
    """Jeden wiersz na rekord (kolejność wejścia): id, pola schematu, z_cache, tokeny, blad.

    `rekordy`: kolumny `id`, `tekst` i opcjonalnie `obrazy` (lista ścieżek JPEG). Błąd jednego rekordu
    (np. po wyczerpaniu ponowień w SDK) zapisujemy w `blad` i idziemy dalej.
    """
    ma_obrazy = "obrazy" in rekordy.columns
    zrobione = [0]

    def jeden(r) -> dict:
        try:
            w = klient.zapytaj(r.tekst, prompt, CechyLokalu, obrazy=r.obrazy if ma_obrazy else ())
            wiersz = {"id": r.id, **w.dane, "z_cache": w.z_cache, "blad": None}
            wiersz.update({k: getattr(w, k) for k in KOLUMNY_TOKENOW})
        except Exception as e:  # noqa: BLE001 — błąd jednego rekordu nie przerywa ekstrakcji; liczony w raporcie
            wiersz = {"id": r.id, **{p: None for p in POLA}, "z_cache": False, "blad": f"{type(e).__name__}: {e}"[:500]}
            wiersz.update({k: None for k in KOLUMNY_TOKENOW})
        zrobione[0] += 1
        if postep and zrobione[0] % postep == 0:
            print(f"{prompt.wersja}: {zrobione[0]} / {len(rekordy)}", file=sys.stderr, flush=True)
        return wiersz

    with ThreadPoolExecutor(max_workers=watki) as pula:
        wiersze = list(pula.map(jeden, rekordy.itertuples(index=False)))
    wynik = pd.DataFrame(wiersze, columns=["id", *POLA, "z_cache", *KOLUMNY_TOKENOW, "blad"])
    for k in KOLUMNY_TOKENOW:
        wynik[k] = pd.to_numeric(wynik[k], errors="coerce")
    return wynik


def cechy_do_modelu(surowe: pd.DataFrame) -> pd.DataFrame:
    """id + KOLUMNY_LLM z udanych odczytów: standard jako liczba (NaN = brak informacji), reszta jako napisy."""
    ok = surowe[surowe["blad"].isna()]
    wynik = ok[["id", *_Z_POLA]].rename(columns=_Z_POLA).reset_index(drop=True)
    wynik["llm_standard"] = pd.to_numeric(wynik["llm_standard"], errors="coerce").astype(float)
    for k in LLM_KATEGORII:
        wynik[k] = wynik[k].astype(object).where(wynik[k].notna(), np.nan)
    return wynik[["id", *KOLUMNY_LLM]]
