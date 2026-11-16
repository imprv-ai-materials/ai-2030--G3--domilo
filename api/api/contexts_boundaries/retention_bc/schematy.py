"""Schematy API retencji (GET /risk/{id_najmu}); logika: retention_bc/ryzyko_najmu.py i oferta_najmu.py."""

from datetime import date
from typing import Literal

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


class CechaUzasadnienia(BaseModel):
    cecha: str = Field(description="nazwa cechy modelu (macierz v3: linia jako b2b)")
    opis: str = Field(description="opis cechy z wartością, po polsku")
    wartosc: float | None
    wklad_pp: float = Field(description="wkład cechy w uplift, punkty procentowe (SHAP v3 przeliczony na p)")


class ZalozeniaOfertyApi(BaseModel):
    R: float = Field(description="koszt odejścia najemcy, PLN (retention_bc/zalozenia.yaml)")
    D: float = Field(description="roczny rabat dla przedłużającego z ofertą, PLN")
    k: float = Field(description="koszt kontaktu, PLN")
    budzet_rabatow_rok: float | None = Field(description="roczny budżet rabatów, PLN; None = nie ustalono")


class OfertaRetencyjna(BaseModel):
    wersja_modelu: str = Field(description="model uplift (v3_uplift_tlearner)")
    id_umowy: str = Field(description="bieżący okres umowy, którego koniec dotyczy oferta")
    koniec_okresu: date
    data_decyzji: date = Field(description="cechy ze zdarzeń sprzed tego dnia: migawka (koniec − 60 dni) albo dziś")
    p_przedluzy_z_oferta: float
    p_przedluzy_bez_oferty: float
    uplift: float = Field(description="p_przedluzy_z_oferta − p_przedluzy_bez_oferty")
    ev_pln: float = Field(description="wartość oczekiwana oferty: uplift × R − D × p_przedluzy_z_oferta − k")
    zalecana_akcja: Literal["rabat", "bez rabatu", "nie budzić"]
    uzasadnienie: str = Field(description="jedno zdanie oparte na trzech najważniejszych cechach")
    najwazniejsze_cechy: list[CechaUzasadnienia]
    prog_nie_budzic: float = Field(description="uplift <= próg -> „nie budzić” (20. percentyl upliftu v3)")
    poza_zakresem_modelu: list[str] = Field(
        description="cechy poza zakresem danych uczących v3; niepuste -> „bez rabatu”, decyzja w dniu migawki"
    )
    w_budzecie: bool | None = Field(description="czy oferta mieści się w rocznym budżecie; None = nie sprawdzano")
    zalozenia: ZalozeniaOfertyApi
    uwagi: list[str]


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
    oferta: OfertaRetencyjna | None = Field(
        default=None, description="uplift, EV i zalecana akcja (None, gdy brak modelu v3_uplift_tlearner)"
    )
