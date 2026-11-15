"""Schematy API wyceny (main.py): wejście POST /valuation i odpowiedzi dla panelu rzeczoznawcy."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

STREFA = ZoneInfo("Europe/Warsaw")


def dzis() -> date:
    return datetime.now(STREFA).date()


class ZapytanieWyceny(BaseModel):
    """Lokal do wyceny. Cena nie jest polem wejścia: model wycenia z cech, nie z ceny ofertowej."""

    model_config = ConfigDict(extra="forbid")

    miasto: str = Field(min_length=1, max_length=60)
    dzielnica: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=49.0, le=54.9, description="Szerokość geograficzna (Polska)")
    lon: float = Field(ge=14.1, le=24.2, description="Długość geograficzna (Polska)")
    metraz: float = Field(gt=0, le=500)
    pokoje: int = Field(ge=1, le=12)
    pietro: int = Field(ge=-1, le=80)
    rok_budowy: int | None = Field(default=None, ge=1800, le=2035)
    opis: str | None = Field(
        default=None,
        max_length=5000,
        description="Opis lokalu; zdania z kwotą są usuwane, cechy odczytuje LLM (prompt cechy_lokalu_v1)",
    )
    dzien_wyceny: date | None = Field(default=None, description="Domyślnie dziś (Europe/Warsaw)")

    @field_validator("dzien_wyceny")
    @classmethod
    def nie_z_przyszlosci(cls, v: date | None) -> date | None:
        if v is not None and v > dzis():
            raise ValueError("dzień wyceny nie może być w przyszłości")
        return v


class Czynnik(BaseModel):
    cecha: str
    opis: str
    wplyw_pln: int = Field(description="Wkład cechy do wyceny w PLN względem wartości bazowej modelu")


class PozaZakresem(BaseModel):
    czy: bool
    powod: str | None = None


class OdpowiedzWyceny(BaseModel):
    wersja_modelu: str
    dzien_wyceny: date
    wartosc: int | None = Field(description="P50 w PLN; null, gdy lokal jest poza zakresem modelu")
    p10: int | None
    p90: int | None
    poza_zakresem: PozaZakresem
    czynniki: list[Czynnik] = Field(description="3 cechy o największym wpływie (|PLN|); pusta lista przy odmowie")
    wartosc_bazowa_pln: int | None = Field(description="Wycena „przeciętnego” lokalu z treningu (punkt odniesienia)")
    cechy_z_opisu: bool


class PozycjaKolejki(BaseModel):
    rodzaj: str
    id_obiektu: str
    miasto: str | None
    dzielnica: str | None
    metraz: float | None
    cena_ofertowa: float | None
    powod: str | None
    czas_przebiegu: datetime


class OfertaPonizejP10(BaseModel):
    id_obiektu: str
    miasto: str | None
    dzielnica: str | None
    metraz: float | None
    cena_ofertowa: float
    p10: float
    p50: float
    p90: float
    cena_do_p10: float
    czas_przebiegu: datetime


class PunktHistorii(BaseModel):
    czas_przebiegu: datetime
    p10: float | None
    p50: float | None
    p90: float | None
    odmowa: bool


class KartaWyceny(BaseModel):
    rodzaj: str
    id_obiektu: str
    miasto: str | None
    dzielnica: str | None
    metraz: float | None
    wersja_modelu: str
    czas_przebiegu: datetime
    dzien_wyceny: date | None
    p10: float | None
    p50: float | None
    p90: float | None
    odmowa: bool
    powod: str | None
    cena_ofertowa: float | None
    wartosc_bazowa: float | None
    czynniki: list[Czynnik] = Field(description="Wszystkie cechy, od największego |wpływu| w PLN")
    historia: list[PunktHistorii]
