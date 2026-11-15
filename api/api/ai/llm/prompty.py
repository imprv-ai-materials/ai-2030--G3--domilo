"""Prompty LLM z plików YAML w ai/llm/prompts/ (pola: wersja, data, instrukcja, szablon z polem {opis})."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

KATALOG_PROMPTOW = Path(__file__).with_name("prompts")


@dataclass(frozen=True)
class Prompt:
    wersja: str
    instrukcja: str
    szablon: str
    data: str | None = None  # dzień utworzenia wersji (RRRR-MM-DD); poza skrótem treści, nie wpływa na cache

    def wiadomosc(self, opis: str) -> str:
        return self.szablon.format(opis=opis)

    @property
    def skrot_tresci(self) -> str:
        """Skrót treści promptu: pozwala wykryć edycję promptu bez zmiany wersji (stary cache byłby błędny)."""
        return hashlib.sha256(f"{self.instrukcja}\n---\n{self.szablon}".encode("utf-8")).hexdigest()


def wczytaj_prompt(nazwa: str, katalog: Path = KATALOG_PROMPTOW) -> Prompt:
    dane = yaml.safe_load((katalog / f"{nazwa}.yaml").read_text(encoding="utf-8"))
    data = dane.get("data")
    return Prompt(
        wersja=dane["wersja"],
        instrukcja=dane["instrukcja"],
        szablon=dane["szablon"],
        data=str(data) if data is not None else None,
    )
