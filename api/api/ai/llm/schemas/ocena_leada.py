"""Ocena zapytania (leada) przez LLM: szansa, że skończy się umową, w skali 1–10 (prompt ai/llm/prompts/ocena_leada_v*).

`sygnaly` to zamknięty słownik: structured outputs w API nie pozwala modelowi zwrócić wartości spoza listy,
a `extra="forbid"` odrzuca dodatkowe pola. Sygnały to zbiór: schemat usuwa powtórzenia i porządkuje je według
kolejności w słowniku, więc ta sama ocena z inną kolejnością sygnałów daje identyczną odpowiedź.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAKS_DLUGOSC_UZASADNIENIA = 140


class Sygnal(StrEnum):
    konkretne_pytania = "konkretne_pytania"
    niedopasowanie_oferty = "niedopasowanie_oferty"
    pilny_termin = "pilny_termin"
    relokacja = "relokacja"
    budzet_niski = "budzet_niski"
    brak_informacji = "brak_informacji"


_KOLEJNOSC_SYGNALOW = {s: i for i, s in enumerate(Sygnal)}


class OcenaLeada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ocena: Annotated[int, Field(ge=1, le=10)] = Field(
        description="Szansa, że zapytanie skończy się podpisaniem umowy najmu: 1 = znikoma, 10 = bardzo wysoka."
    )
    uzasadnienie: str = Field(
        max_length=MAKS_DLUGOSC_UZASADNIENIA,
        description=f"Jedno zdanie po polsku, najwyżej {MAKS_DLUGOSC_UZASADNIENIA} znaków.",
    )
    sygnaly: list[Sygnal] = Field(
        description="Sygnały widoczne w zapytaniu; pusta lista, gdy żaden nie występuje.",
    )

    @field_validator("sygnaly")
    @classmethod
    def _zbior_w_kolejnosci_slownika(cls, sygnaly: list[Sygnal]) -> list[Sygnal]:
        return sorted(set(sygnaly), key=_KOLEJNOSC_SYGNALOW.__getitem__)
