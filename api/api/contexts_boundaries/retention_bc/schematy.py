"""Schematy API retencji (GET /risk/{id_najmu}); logika: retention_bc/ryzyko_najmu.py."""

from datetime import date

from pydantic import BaseModel, Field


class OkresUmowy(BaseModel):
    id_umowy: str
    nr_okresu: int
    data_od: date
    data_do: date
    miesiecy_umowy: int
    minelo_miesiecy: float = Field(
        description="miesiące bieżącego okresu przed dniem oceny (0, gdy zaczyna się później)"
    )


class OdpowiedzRyzyka(BaseModel):
    id_najmu: str
    linia: str
    dzien_oceny: date = Field(description="dzień, na który liczymy (dzień eksportu danych)")
    wersja_modelu: str
    okres: OkresUmowy = Field(description="bieżący okres umowy (ostatni podpisany)")
    ryzyko_12_od_poczatku_okresu: float = Field(description="1 - S(12 mies. od początku okresu): wynik modelu v2")
    p_konca_w_biezacym_okresie: float = Field(description="szansa, że najem skończy się w bieżącym okresie")
    przezycie_12_mies: float = Field(description="szansa, że najem trwa jeszcze 12 mies. po dniu oceny")
    przezycie_24_mies: float = Field(description="szansa, że najem trwa jeszcze 24 mies. po dniu oceny")
    mediana_do_odejscia_mies: float | None = Field(
        description="spodziewany czas do odejścia: mediana z krzywej Coxa, mies. od dnia oceny; None = powyżej 60"
    )
    mediana_powyzej_horyzontu: bool
    rmst60_mies: float = Field(description="średnia liczba miesięcy najmu w ciągu 60 mies. od dnia oceny (RMST60)")
    horyzont_mies: float
    zalozenia: list[str]
