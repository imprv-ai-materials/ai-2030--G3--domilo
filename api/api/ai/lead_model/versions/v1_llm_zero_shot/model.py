"""v1: ocena zapytania przez LLM bez uczenia (zero-shot), wynik = ocena / 10.

Prompt `ocena_leada_v1`, schemat `OcenaLeada`, wejście `opis_leada` (tylko pola znane przy utworzeniu zapytania,
bez imienia i języka; docs/llm_ocena_leada_v1.md). Wywołania przez `KlientLLM` (gpt-6-luna, reasoning `none`,
temperatura 0) z cache odpowiedzi w ai/llm/cache/. Klient powstaje przy pierwszym wywołaniu i nie jest zapisywany
z modelem. Błąd wywołania dla jednego zapytania daje wynik NaN i opis w kolumnie `blad` (bez przerwania reszty).
"""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from api.adapters.llm_client import MODEL, KlientLLM
from api.ai.features.leady.ocena_llm import opis_leada
from api.ai.lead_model.base import ModelLeadow
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.ocena_leada import OcenaLeada

SKALA = 10


class ModelLLMZeroShot(ModelLeadow):
    wersja = "v1_llm_zero_shot"

    def __init__(self, nazwa_promptu: str = "ocena_leada_v1", watki: int = 8, klient: KlientLLM | None = None):
        self.nazwa_promptu = nazwa_promptu
        self.model_llm = MODEL
        self.watki = watki
        self._klient = klient

    def __getstate__(self) -> dict:
        return {**self.__dict__, "_klient": None}

    def _klient_llm(self) -> KlientLLM:
        if self._klient is None:
            self._klient = KlientLLM()
        return self._klient

    def explain(self, leady: pd.DataFrame) -> pd.DataFrame:
        self.sprawdz_kolumny(leady)
        prompt = wczytaj_prompt(self.nazwa_promptu)
        klient = self._klient_llm()

        def jeden(wejscie: str) -> dict:
            try:
                w = klient.zapytaj(wejscie, prompt, OcenaLeada)
            except Exception as e:  # noqa: BLE001 — błąd jednego zapytania nie przerywa oceny pozostałych
                return {"blad": f"{type(e).__name__}: {e}"[:500]}
            return {
                "ocena": w.dane["ocena"],
                "uzasadnienie": w.dane["uzasadnienie"],
                "sygnaly": ",".join(w.dane["sygnaly"]),
                "z_cache": w.z_cache,
                "tokeny_wejscia": w.tokeny_wejscia,
                "tokeny_wejscia_z_cache": w.tokeny_wejscia_z_cache,
                "tokeny_wyjscia": w.tokeny_wyjscia,
                "blad": None,
            }

        wejscia = [opis_leada(r) for r in leady.to_dict("records")]
        with ThreadPoolExecutor(max_workers=self.watki) as pula:
            wiersze = list(pula.map(jeden, wejscia))
        wyj = pd.DataFrame(wiersze, index=leady.index).reindex(
            columns=[
                "ocena",
                "uzasadnienie",
                "sygnaly",
                "z_cache",
                "tokeny_wejscia",
                "tokeny_wejscia_z_cache",
                "tokeny_wyjscia",
                "blad",
            ]
        )
        wyj.insert(0, "wynik", wyj["ocena"].astype(float) / SKALA)
        return wyj

    def predict(self, leady: pd.DataFrame) -> np.ndarray:
        return self.explain(leady)["wynik"].to_numpy()
