"""Schematy API kolejki doradców (GET /leads/next); pola jak w webhooku (kolejka_doradcow.POLA_POZYCJI)."""

from datetime import date, datetime
from typing import Literal

from api.contexts_boundaries.leasing_bc.pominiecia import POWODY_Z_KOMENTARZEM
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Kody jak w POWODY_POMINIECIA (zgodność pilnuje test api/tests/test_panel_kierownika.py).
KodPowodu = Literal["znam_klienta", "brak_lokalu", "duplikat", "inne"]


class ZgloszeniePominiecia(BaseModel):
    """POST /leads/skips: CRM zgłasza, że doradca pominął pozycję kolejki (klucz: data_kolejki + id_leada)."""

    model_config = ConfigDict(extra="forbid")
    data_kolejki: date
    id_leada: str = Field(min_length=1)
    id_doradcy: str = Field(min_length=1)
    powod: KodPowodu
    komentarz: str | None = Field(default=None, max_length=500)
    zgloszono: datetime

    @model_validator(mode="after")
    def _komentarz_dla_inne(self):
        if self.powod in POWODY_Z_KOMENTARZEM and not (self.komentarz and self.komentarz.strip()):
            raise ValueError(f"Powód „{self.powod}” wymaga komentarza")
        if self.zgloszono.tzinfo is None:
            raise ValueError("zgloszono: podaj strefę czasową (ISO 8601 z przesunięciem)")
        return self


class WynikPominiecia(BaseModel):
    wynik: Literal["utworzono", "powtorzenie", "zmieniono"]


class PozycjaKolejkiDoradcy(BaseModel):
    pozycja: int
    id_leada: str
    utworzono: datetime
    status_crm: str
    zrodlo: str | None
    linia_pref: str | None
    liczba_lokali: float
    p: float
    ev_pln: float
    uzasadnienie: str
    zrodlo_uzasadnienia: str


class KolejkaDoradcy(BaseModel):
    id_doradcy: str
    miasto: str
    data_kolejki: date
    wersja_modelu: str
    stan_danych_na: datetime
    pozycje: list[PozycjaKolejkiDoradcy]
