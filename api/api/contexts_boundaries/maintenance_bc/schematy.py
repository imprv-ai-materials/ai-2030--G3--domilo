"""Schematy odpowiedzi API dla wind (GET /lifts/{id_windy}/risk)."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class Sygnal(BaseModel):
    sygnal: str = Field(description="sygnał telemetrii (features/windy/katalog.yaml)")
    rodzina: str
    zrodlo: str = Field(description="kolumna Telemetry, z której liczony jest sygnał")
    jednostka: str
    wklad: float = Field(description="wkład sygnału w log-szansę awarii (suma SHAP jego cech); > 0 podnosi ryzyko")
    cecha: str = Field(description="cecha sygnału o największym wkładzie")
    wartosc: float | None = Field(description="wartość tej cechy w dniu oceny")
    podzespoly: list[str]


class Podzespol(BaseModel):
    podzespol: str
    wklad: float = Field(description="suma wkładów sygnałów wskazujących ten podzespół")
    sygnaly: list[str]


class Alarm(BaseModel):
    pozycja: int
    id_zgloszenia: str | None = Field(description="zgłoszenie w Serwisowniku (None = jeszcze nie wysłane)")


class OdpowiedzRyzykaWindy(BaseModel):
    id_windy: str
    dzien_oceny: date
    moment_oceny: datetime = Field(description="06:00 Europe/Warsaw dnia oceny; cechy z okien do 05:50")
    wersja_modelu: str
    ryzyko: float | None = Field(description="P(awaria w ciągu 7 dni od oceny), po kalibracji (p_awarii_7d)")
    wynik_modelu: float = Field(description="wynik rankingu (predict); tym wynikiem reguła wybiera alarmy")
    ranga: int = Field(description="miejsce windy w rankingu dnia (1 = najwyższe ryzyko)")
    ocenione_windy: int
    stoi: bool = Field(description="o 05:50 winda w trybie 'wylaczona' (bez alarmu)")
    ostatnie_okno: datetime | None = Field(description="ostatnie okno telemetrii windy przed odcięciem")
    okna_24h: int = Field(description="okna telemetrii z 24 h przed odcięciem (pełna doba = 144)")
    sygnaly: list[Sygnal] = Field(description="najwyżej 3 sygnały o największym dodatnim wkładzie")
    podzespoly: list[Podzespol] = Field(description="podejrzane podzespoły, od najsilniejszego wskazania")
    alarm: Alarm | None = Field(description="alarm z reguły w dniu oceny (tylko w dzień alarmu)")
