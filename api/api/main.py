"""API Domilo: wycena lokali (POST /valuation), odczyty dla panelu rzeczoznawcy i funkcje Inngest (/api/inngest).

Uruchomienie (z katalogu api/, port jak w devcontainerze):
    poetry run uvicorn api.main:app --port 8101
Model: obecna wersja z current.yaml (valuation_model/obecny.py), wczytywana raz przy pierwszym zapytaniu.
Wycena z opisem wymaga OPENAI_API_KEY w środowisku (cechy z LLM); bez opisu cechy z opisu są brakiem.
"""

from collections.abc import Callable, Iterator
from functools import lru_cache

import duckdb
import inngest.fast_api
import numpy as np
import pandas as pd
from api.adapters import wyceny_historia
from api.adapters.duckdb_baza import polaczenie
from api.adapters.llm_client import BrakKluczaAPI
from api.ai.features.wycena.cechy_llm import KOLUMNY_LLM
from api.ai.features.wycena.ceny_w_opisie import bez_kwot
from api.ai.valuation_model.obecny import ObecnyModel, wczytaj_obecny
from api.contexts_boundaries.valuation_bc.cechy_opisu import cechy_z_opisu
from api.contexts_boundaries.valuation_bc.schematy import (
    Czynnik,
    KartaWyceny,
    OdpowiedzWyceny,
    OfertaPonizejP10,
    PozaZakresem,
    PozycjaKolejki,
    ZapytanieWyceny,
    dzis,
)
from api.contexts_boundaries.valuation_bc.wycena import OPISY_CECH, cechy_punktow, najwazniejsze, wycen
from api.inngest_app import FUNKCJE, klient_inngest
from fastapi import Depends, FastAPI, HTTPException

app = FastAPI(title="Domilo: wycena lokali", version="1.0")
inngest.fast_api.serve(app, klient_inngest, FUNKCJE)


@lru_cache(maxsize=1)
def obecny_model() -> ObecnyModel:
    return wczytaj_obecny()


def baza() -> Iterator[duckdb.DuckDBPyConnection]:
    with polaczenie() as con:
        yield con


def ekstraktor_cech_opisu() -> Callable[[str], dict]:
    return cechy_z_opisu


def _int(x) -> int | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else int(round(x))


def _czynniki(czynniki: dict[str, float], n: int | None = None) -> list[Czynnik]:
    lista = najwazniejsze(czynniki, n or len(czynniki))
    return [Czynnik(cecha=k, opis=OPISY_CECH.get(k, k), wplyw_pln=int(round(v))) for k, v in lista]


@app.post("/valuation", response_model=OdpowiedzWyceny)
def wycena(
    z: ZapytanieWyceny,
    obecny: ObecnyModel = Depends(obecny_model),
    con: duckdb.DuckDBPyConnection = Depends(baza),
    ekstraktor: Callable[[str], dict] = Depends(ekstraktor_cech_opisu),
) -> OdpowiedzWyceny:
    cechy_opisu = {k: np.nan for k in KOLUMNY_LLM}
    if z.opis and z.opis.strip():
        try:
            cechy_opisu = ekstraktor(bez_kwot(z.opis))
        except BrakKluczaAPI as e:
            raise HTTPException(503, f"Nie można odczytać cech z opisu (brak klucza LLM): {e}") from e
        except Exception as e:  # noqa: BLE001 — błąd usługi LLM to błąd bramy, nie wycena bez opisu
            raise HTTPException(502, f"Odczyt cech z opisu nie powiódł się: {type(e).__name__}") from e
    dzien = z.dzien_wyceny or dzis()
    punkt = pd.DataFrame(
        [{**z.model_dump(exclude={"opis", "dzien_wyceny"}), "id": "zapytanie", "dzien_wyceny": dzien, **cechy_opisu}]
    )
    punkt["rok_budowy"] = punkt["rok_budowy"].astype(float)
    w = wycen(obecny.model, cechy_punktow(con, punkt)).iloc[0]
    odmowa = bool(w["odmowa"])
    return OdpowiedzWyceny(
        wersja_modelu=obecny.wersja,
        dzien_wyceny=dzien,
        wartosc=None if odmowa else _int(w["p50"]),
        p10=None if odmowa else _int(w["p10"]),
        p90=None if odmowa else _int(w["p90"]),
        poza_zakresem=PozaZakresem(czy=odmowa, powod=w["powod"] or None if odmowa else None),
        czynniki=[] if odmowa else _czynniki(w["czynniki"], 3),
        wartosc_bazowa_pln=None if odmowa else _int(w["wartosc_bazowa"]),
        cechy_z_opisu=bool(z.opis and z.opis.strip()),
    )


def _rekordy(df: pd.DataFrame) -> list[dict]:
    return [] if df.empty else df.replace({np.nan: None}).to_dict("records")


@app.get("/valuation/kolejka-nie-wiem", response_model=list[PozycjaKolejki])
def kolejka_nie_wiem(con: duckdb.DuckDBPyConnection = Depends(baza)) -> list[dict]:
    """Obiekty, których najnowsza wycena z zadania nocnego to odmowa („nie wiem”), z powodem."""
    return _rekordy(wyceny_historia.odmowy(con))


@app.get("/valuation/oferty-ponizej-p10", response_model=list[OfertaPonizejP10])
def oferty_ponizej_p10(con: duckdb.DuckDBPyConnection = Depends(baza)) -> list[dict]:
    """Oferty z ceną ofertową poniżej P10 najnowszej wyceny, od największego rabatu."""
    return _rekordy(wyceny_historia.oferty_ponizej_p10(con))


@app.get("/valuation/karta/{rodzaj}/{id_obiektu}", response_model=KartaWyceny)
def karta(rodzaj: str, id_obiektu: str, con: duckdb.DuckDBPyConnection = Depends(baza)) -> KartaWyceny:
    k = wyceny_historia.karta(con, rodzaj, id_obiektu)
    if k is None:
        raise HTTPException(404, f"Brak wyceny: {rodzaj} {id_obiektu}")
    return KartaWyceny(**{**k, "czynniki": _czynniki(k["czynniki"])})
