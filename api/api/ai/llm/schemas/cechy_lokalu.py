"""Cechy lokalu, które są tylko w opisie ogłoszenia (radar_oferty.opis), a nie w kolumnach: schemat odpowiedzi LLM.

Każde pole ma wartość „brak informacji” (None albo `brak_info`), bo opis nie musi wspominać o danej cesze.
Schemat celowo nie ma pól na kwoty (cena, rata, czynsz): `extra="forbid"` odrzuca odpowiedź z dodatkowym polem,
a structured outputs w API nie pozwala modelowi ich dopisać.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Ekspozycja(StrEnum):
    polnoc = "polnoc"
    polnocny_wschod = "polnocny_wschod"
    wschod = "wschod"
    poludniowy_wschod = "poludniowy_wschod"
    poludnie = "poludnie"
    poludniowy_zachod = "poludniowy_zachod"
    zachod = "zachod"
    polnocny_zachod = "polnocny_zachod"
    brak_info = "brak_info"


class Widok(StrEnum):
    park = "park"
    woda = "woda"
    ulica = "ulica"
    podworze = "podworze"
    brak_info = "brak_info"


class Balkon(StrEnum):
    tak = "tak"
    nie = "nie"
    brak_info = "brak_info"


class StanBudynku(StrEnum):
    nowy = "nowy"
    zadbany = "zadbany"
    do_remontu = "do_remontu"
    brak_info = "brak_info"


class Pewnosc(StrEnum):
    wysoka = "wysoka"
    srednia = "srednia"
    niska = "niska"


class CechyLokalu(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_1_5: Annotated[int, Field(ge=1, le=5)] | None = Field(
        description=(
            "Standard wykończenia lokalu: 1 = do remontu albo stan deweloperski (bez wykończenia), "
            "2 = do odświeżenia, 3 = standardowy / dobry, 4 = wysoki / podwyższony / świeżo wyremontowany, "
            "5 = premium / luksusowy. null, gdy opis nic o tym nie mówi."
        )
    )
    ekspozycja: Ekspozycja = Field(description="Strona świata, na którą wychodzą okna; brak_info, gdy nie podano.")
    widok: Widok = Field(description="Na co wychodzą okna; brak_info, gdy nie podano.")
    balkon: Balkon = Field(description="Czy lokal ma balkon, loggię lub taras; brak_info, gdy opis o tym milczy.")
    stan_budynku: StanBudynku = Field(
        description=(
            "Stan budynku (nie lokalu): nowy = nowa inwestycja / nowy budynek, zadbany = zadbana klatka, "
            "odnowiona elewacja, do_remontu = budynek wymaga remontu; brak_info, gdy opis nie ocenia budynku."
        )
    )
    pewnosc: Pewnosc = Field(
        description=(
            "wysoka = wszystkie wartości wprost z opisu; srednia = co najmniej jedna wymagała interpretacji; "
            "niska = opis jest sprzeczny w którejś cesze."
        )
    )
