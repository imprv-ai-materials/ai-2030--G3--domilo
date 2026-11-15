"""Cechy lokalu z opisu (LLM) dla pojedynczej wyceny: ten sam prompt i schemat co przy uczeniu v4.

Opis trafia tu już bez zdań z kwotą (ceny_w_opisie.bez_kwot). Klient LLM powstaje przy pierwszym użyciu, więc API
bez klucza OPENAI_API_KEY działa dla wycen bez opisu; z opisem zgłasza BrakKluczaAPI.
"""

from functools import lru_cache

import pandas as pd
from api.adapters.llm_client import KlientLLM
from api.ai.features.wycena.cechy_llm import KOLUMNY_LLM, cechy_do_modelu
from api.ai.llm.prompty import Prompt, wczytaj_prompt
from api.ai.llm.schemas.cechy_lokalu import CechyLokalu

PROMPT_OPISU = "cechy_lokalu_v1"


@lru_cache(maxsize=1)
def _klient() -> KlientLLM:
    return KlientLLM()


@lru_cache(maxsize=1)
def _prompt() -> Prompt:
    return wczytaj_prompt(PROMPT_OPISU)


def cechy_z_opisu(opis_bez_kwot: str) -> dict:
    """KOLUMNY_LLM (llm_standard jako liczba albo NaN, reszta jako napisy) z jednego opisu."""
    w = _klient().zapytaj(opis_bez_kwot, _prompt(), CechyLokalu)
    wiersz = cechy_do_modelu(pd.DataFrame([{"id": "opis", **w.dane, "blad": None}])).iloc[0]
    return {k: wiersz[k] for k in KOLUMNY_LLM}
