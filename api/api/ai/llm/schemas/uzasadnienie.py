"""Uzasadnienie pozycji zapytania w kolejce: jedno zdanie po polsku z faktów top 3 SHAP (prompt uzasadnienie_v*).

Limit długości jest w schemacie (`maxLength` w structured outputs), a pydantic odrzuca dłuższe zdanie także przy
odczycie z cache. Czy zdanie używa tylko podanych faktów, sprawdza `ai/lead_model/uzasadnienie.sprawdz_zdanie`.
"""

from pydantic import BaseModel, ConfigDict, Field

MAKS_DLUGOSC_ZDANIA = 140


class Uzasadnienie(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zdanie: str = Field(
        min_length=1,
        max_length=MAKS_DLUGOSC_ZDANIA,
        description=f"Jedno zdanie po polsku, najwyżej {MAKS_DLUGOSC_ZDANIA} znaków, wyłącznie z podanych faktów.",
    )
