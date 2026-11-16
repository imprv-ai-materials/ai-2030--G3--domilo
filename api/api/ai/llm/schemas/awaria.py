"""Awaria windy odczytana z notatek konserwatorów (prompt ai/llm/prompts/awaria_v*): schemat odpowiedzi LLM.

Wejście to jedno zgłoszenie Serwisownika ze wszystkimi notatkami (`api.ai.llm.ekstrakcja_awarii.opis_zgloszenia`).
Definicja awarii jest taka sama jak w złotym zbiorze koordynatora (`serwis_zloty_zbior`): winda stała albo była
wyłączona z ruchu z powodu usterki lub przyczyny zewnętrznej. W złotym zbiorze `podzespol` ma też wartość
`wandalizm`; tutaj to `zewnetrzna` (porównując wyniki, łączymy `wandalizm` i `zewnetrzna`).

Zasady spójności (`model_validator`): bez awarii -> `podzespol = brak`, `start_wg_notatki` i `czas_naprawy_h` = null.
Awaria może mieć `podzespol = brak`, gdy notatki nie mówią, co się zepsuło (np. tylko „Naprawa zakończona”).
`start_wg_notatki` to czas lokalny Europe/Warsaw bez strefy (`RRRR-MM-DD GG:MM`), jak w Serwisowniku.
Pola idą w kolejności: najpierw `objaw` (co mówią notatki), potem decyzja — model generuje je w tej kolejności.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAKS_DLUGOSC_OBJAWU = 120
FORMAT_STARTU = "%Y-%m-%d %H:%M"
WZORZEC_STARTU = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"


class Podzespol(StrEnum):
    drzwi = "drzwi"
    naped = "naped"
    hamulec_liny = "hamulec_liny"
    sterownik = "sterownik"
    zewnetrzna = "zewnetrzna"
    brak = "brak"


class Awaria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objaw: str = Field(
        max_length=MAKS_DLUGOSC_OBJAWU,
        description=(
            f"Krótko po polsku (najwyżej {MAKS_DLUGOSC_OBJAWU} znaków), co według notatek stało się z windą, "
            "np. „winda stała, uszkodzony falownik” albo „kontrola po naprawie, bez usterek”."
        ),
    )
    czy_awaria: bool = Field(
        description="true, gdy według notatek winda stała albo była wyłączona z ruchu z powodu usterki lub "
        "przyczyny zewnętrznej; false w każdym innym przypadku."
    )
    podzespol: Podzespol = Field(
        description="Co spowodowało awarię; brak, gdy nie ma awarii albo notatki nie wskazują przyczyny."
    )
    start_wg_notatki: Annotated[str, Field(pattern=WZORZEC_STARTU)] | None = Field(
        description="Początek awarii (RRRR-MM-DD GG:MM, czas lokalny), tylko gdy notatka wprost go podaje; "
        "inaczej null."
    )
    czas_naprawy_h: Annotated[float, Field(ge=0)] | None = Field(
        description="Godziny od początku awarii (a gdy nieznany: od utworzenia zgłoszenia) do przywrócenia windy "
        "do ruchu według notatek; null, gdy nie ma awarii albo notatki nie mówią, kiedy winda znów ruszyła."
    )
    pewnosc: Annotated[float, Field(ge=0, le=1)] = Field(
        description="Pewność odczytu czy_awaria i podzespol: 1 = notatki mówią to wprost, 0,5 = trzeba się "
        "domyślać, poniżej 0,5 = notatki są sprzeczne albo prawie nic nie mówią."
    )

    @field_validator("start_wg_notatki")
    @classmethod
    def _prawdziwa_data(cls, v: str | None) -> str | None:
        if v is not None:
            datetime.strptime(v, FORMAT_STARTU)  # ValueError np. dla 2025-02-30 albo 25:00
        return v

    @model_validator(mode="after")
    def _spojnosc(self) -> Self:
        if not self.czy_awaria:
            zbedne = [
                nazwa
                for nazwa, jest in (
                    ("podzespol", self.podzespol != Podzespol.brak),
                    ("start_wg_notatki", self.start_wg_notatki is not None),
                    ("czas_naprawy_h", self.czas_naprawy_h is not None),
                )
                if jest
            ]
            if zbedne:
                raise ValueError(f"czy_awaria = false, a wypełnione: {', '.join(zbedne)}")
        return self

    @property
    def start(self) -> datetime | None:
        return datetime.strptime(self.start_wg_notatki, FORMAT_STARTU) if self.start_wg_notatki else None
