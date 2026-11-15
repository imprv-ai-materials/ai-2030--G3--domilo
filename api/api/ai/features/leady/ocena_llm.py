"""Wejście do oceny zapytania przez LLM (prompt ai/llm/prompts/ocena_leada_v1.yaml, docs/llm_ocena_leada_v1.md).

Do modelu trafia tylko to, co było znane w chwili utworzenia zapytania: źródło, miasto, linia, budżet, termin,
liczba osób, zwierzę, liczba lokali i treść. Nie wysyłamy imienia ani języka: imię usuwamy też z treści (podpis
w ok. 1/3 wiadomości), a stan na dzień eksportu (`crm_leady.status`, `id_umowy`) w ogóle nie jest czytany.
Termin podajemy w dniach od zapytania, bo model nie zna daty zapytania i data bezwzględna (np. z 2023) wyglądałaby
na termin, który już minął.
"""

import re
from collections.abc import Mapping
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

STREFA = ZoneInfo("Europe/Warsaw")
ZNACZNIK_IMIENIA = "[imię]"
BRAK = "brak"

# imie jest czytane tylko po to, by usunąć je z treści wiadomości; do modelu nie trafia.
SQL_LEADOW = """
SELECT
    id_leada, utworzono, zrodlo, miasto, linia_pref, budzet_max, termin_wprowadzenia,
    liczba_osob, zwierze, liczba_lokali, wiadomosc, imie
FROM crm_leady
ORDER BY id_leada
"""


def _brak(wartosc) -> bool:
    return wartosc is None or (not isinstance(wartosc, str) and bool(pd.isna(wartosc)))


def _bez_imienia(tresc: str, imie) -> str:
    if _brak(imie) or not str(imie).strip():
        return tresc
    return re.sub(rf"\b{re.escape(str(imie).strip())}\b", ZNACZNIK_IMIENIA, tresc, flags=re.IGNORECASE)


def _termin(termin, utworzono) -> str:
    if _brak(termin):
        return BRAK
    dzien_zapytania = pd.Timestamp(utworzono).tz_convert(STREFA).date()
    dni = (pd.Timestamp(termin).date() - dzien_zapytania).days
    return f"{dni} dni po zapytaniu"


def _tak_nie(wartosc) -> str:
    return BRAK if _brak(wartosc) else ("tak" if wartosc else "nie")


def _liczba(wartosc, jednostka: str = "") -> str:
    return BRAK if _brak(wartosc) else f"{int(wartosc)}{jednostka}"


def opis_leada(lead: Mapping) -> str:
    """Tekst zapytania dla LLM: pola formularza (brak = „brak”) i treść wiadomości bez imienia."""
    tresc = lead.get("wiadomosc")
    wiersze = [
        f"źródło: {lead['zrodlo']}",
        f"miasto: {lead['miasto']}",
        f"linia: {lead['linia_pref']}",
        f"budżet maks.: {_liczba(lead.get('budzet_max'), ' zł')}",
        f"termin wprowadzenia: {_termin(lead.get('termin_wprowadzenia'), lead['utworzono'])}",
        f"liczba osób: {_liczba(lead.get('liczba_osob'))}",
        f"zwierzę: {_tak_nie(lead.get('zwierze'))}",
        f"liczba lokali: {_liczba(lead.get('liczba_lokali'))}",
        f"treść zapytania: {BRAK if _brak(tresc) else _bez_imienia(str(tresc), lead.get('imie'))}",
    ]
    return "\n".join(wiersze)


def losuj_leady(con: duckdb.DuckDBPyConnection, n: int, ziarno: int) -> pd.DataFrame:
    """n różnych zapytań z crm_leady (losowanie bez zwracania, powtarzalne dla ziarna), tylko pola wejścia."""
    leady = con.execute(SQL_LEADOW).df()
    wybrane = np.random.default_rng(ziarno).choice(len(leady), size=n, replace=False)
    return leady.iloc[wybrane].reset_index(drop=True)
