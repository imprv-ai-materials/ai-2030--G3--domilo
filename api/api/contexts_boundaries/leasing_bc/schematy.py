"""Schematy API kolejki doradców (GET /leads/next); pola jak w webhooku (kolejka_doradcow.POLA_POZYCJI)."""

from datetime import date, datetime

from pydantic import BaseModel


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
