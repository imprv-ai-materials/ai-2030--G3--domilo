"""Klient LLM (OpenAI Responses API, structured outputs) z cache odpowiedzi na dysku.

- Model `gpt-6-luna`, reasoning effort `none`, temperatura 0. Gdy model odrzuca parametr `temperature`
  (błąd 400 z `param == "temperature"`), klient ponawia zapytanie bez niego i zapisuje w cache `temperatura: null`.
- Klucz API tylko ze zmiennej środowiskowej `OPENAI_API_KEY`. Klient nie czyta pliku `.env`. Przed uruchomieniem
  załaduj go do środowiska, np. `set -a && . ./.env && set +a`.
- Cache: `ai/llm/cache/<sha256(wersja promptu + opis)>.json`. W pliku zapisany jest też skrót treści promptu.
  Jeśli treść promptu zmieniła się bez zmiany wersji, klient zgłasza błąd zamiast oddać starą odpowiedź.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openai
from api.ai.llm.prompty import Prompt
from pydantic import BaseModel

MODEL = "gpt-6-luna"
REASONING_EFFORT = "none"
TEMPERATURA = 0
KATALOG_CACHE = Path(__file__).resolve().parents[1] / "ai" / "llm" / "cache"


class BrakKluczaAPI(RuntimeError):
    pass


class PromptZmienionyBezNowejWersji(RuntimeError):
    pass


@dataclass(frozen=True)
class WynikLLM:
    dane: dict
    surowy_tekst: str
    z_cache: bool
    tokeny_wejscia: int | None = None
    tokeny_wyjscia: int | None = None


def klucz_cache(opis: str, wersja_promptu: str) -> str:
    return hashlib.sha256(f"{wersja_promptu}\n{opis}".encode("utf-8")).hexdigest()


def _odrzucona_temperatura(blad: openai.BadRequestError) -> bool:
    return isinstance(blad.body, dict) and blad.body.get("param") == "temperature"


class KlientLLM:
    def __init__(
        self,
        model: str = MODEL,
        katalog_cache: Path = KATALOG_CACHE,
        klient_openai: openai.OpenAI | None = None,
    ):
        if klient_openai is None:
            klucz = os.environ.get("OPENAI_API_KEY")
            if not klucz:
                raise BrakKluczaAPI("Brak zmiennej środowiskowej OPENAI_API_KEY (załaduj .env do środowiska).")
            klient_openai = openai.OpenAI(api_key=klucz, max_retries=5)
        self.model = model
        self.katalog_cache = Path(katalog_cache)
        self._openai = klient_openai
        self._temperatura: float | None = TEMPERATURA

    def zapytaj(
        self,
        opis: str,
        prompt: Prompt,
        schemat: type[BaseModel],
        czytaj_cache: bool = True,
        zapisuj_cache: bool = True,
    ) -> WynikLLM:
        plik = self.katalog_cache / f"{klucz_cache(opis, prompt.wersja)}.json"
        if czytaj_cache and plik.exists():
            wpis = json.loads(plik.read_text(encoding="utf-8"))
            if wpis["skrot_promptu"] != prompt.skrot_tresci:
                raise PromptZmienionyBezNowejWersji(
                    f"Treść promptu {prompt.wersja} różni się od tej z cache ({plik.name}); nadaj nową wersję."
                )
            return WynikLLM(dane=wpis["odpowiedz"], surowy_tekst=wpis["surowy_tekst"], z_cache=True)

        odpowiedz = self._wywolaj(opis, prompt, schemat)
        dane = schemat.model_validate_json(odpowiedz.output_text).model_dump(mode="json")
        uzycie = odpowiedz.usage
        wynik = WynikLLM(
            dane=dane,
            surowy_tekst=odpowiedz.output_text,
            z_cache=False,
            tokeny_wejscia=uzycie.input_tokens if uzycie else None,
            tokeny_wyjscia=uzycie.output_tokens if uzycie else None,
        )
        if zapisuj_cache:
            self._zapisz(plik, prompt, wynik)
        return wynik

    def _wywolaj(self, opis: str, prompt: Prompt, schemat: type[BaseModel]):
        parametry = dict(
            model=self.model,
            instructions=prompt.instrukcja,
            input=prompt.wiadomosc(opis),
            reasoning={"effort": REASONING_EFFORT},
            text_format=schemat,
            store=False,
        )
        if self._temperatura is not None:
            try:
                return self._openai.responses.parse(**parametry, temperature=self._temperatura)
            except openai.BadRequestError as blad:
                if not _odrzucona_temperatura(blad):
                    raise
                self._temperatura = None
        return self._openai.responses.parse(**parametry)

    def _zapisz(self, plik: Path, prompt: Prompt, wynik: WynikLLM) -> None:
        wpis = {
            "wersja_promptu": prompt.wersja,
            "skrot_promptu": prompt.skrot_tresci,
            "model": self.model,
            "reasoning_effort": REASONING_EFFORT,
            "temperatura": self._temperatura,
            "utworzono_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tokeny_wejscia": wynik.tokeny_wejscia,
            "tokeny_wyjscia": wynik.tokeny_wyjscia,
            "odpowiedz": wynik.dane,
            "surowy_tekst": wynik.surowy_tekst,
        }
        self.katalog_cache.mkdir(parents=True, exist_ok=True)
        tymczasowy = plik.with_suffix(".tmp")
        tymczasowy.write_text(json.dumps(wpis, ensure_ascii=False, indent=2), encoding="utf-8")
        tymczasowy.replace(plik)
