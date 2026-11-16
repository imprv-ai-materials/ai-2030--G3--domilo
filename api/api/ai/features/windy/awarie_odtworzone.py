"""Awarie wind odtworzone z notatek (LLM) i telemetrii: tabela awarie_odtworzone w domilo.duckdb.

Definicja w `awarie_odtworzone.sql` i `serie_przestoju.sql` obok tego pliku; opis i liczby w
`docs/b4_historia_awarii.md` (R10–R14). Wejście LLM: `features/windy/awarie_llm/<wersja>_windy.parquet`
z `python -m api.ai.llm.ekstrakcja_awarii --zbior windy` (wymaga klucza API; ponowne uruchomienie czyta cache).
Budowa: `pypyr baza` (krok po zgloszenia_wind; pomijany, gdy pliku z ekstrakcją nie ma) albo
`cd api && python -m api.ai.features.windy.awarie_odtworzone`.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd
from api.ai.llm.ekstrakcja_awarii import KATALOG_WYNIKOW, PROMPT

KATALOG = Path(__file__).parent
TABELA = "awarie_odtworzone"
PLIK_LLM = KATALOG_WYNIKOW / f"{PROMPT}_windy.parquet"
KOLUMNY_LLM = ("id_zgloszenia", "czy_awaria", "podzespol", "objaw", "pewnosc")


class BledyEkstrakcji(RuntimeError):
    pass


def _sql(nazwa: str) -> str:
    return (KATALOG / f"{nazwa}.sql").read_text(encoding="utf-8").strip().rstrip(";")


def utworz_serie_przestoju(con: duckdb.DuckDBPyConnection) -> None:
    """Tabela tymczasowa serie_przestoju (serie okien bez jazdy z telemetra_windy)."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE serie_przestoju AS {_sql('serie_przestoju')}")


def wczytaj_llm(plik: Path = PLIK_LLM) -> pd.DataFrame:
    """Odpowiedzi ekstrakcji; BledyEkstrakcji, gdy któreś zgłoszenie nie ma odpowiedzi (wtedy ponów ekstrakcję)."""
    df = pd.read_parquet(plik)
    bledy = df["blad"].notna()
    if bledy.any():
        raise BledyEkstrakcji(f"{plik.name}: {int(bledy.sum())} zgłoszeń z błędem ekstrakcji; uruchom ją ponownie")
    return df[list(KOLUMNY_LLM)].astype(
        {"id_zgloszenia": "string", "czy_awaria": "bool", "podzespol": "string", "objaw": "string", "pewnosc": "float"}
    )


def zbuduj_awarie_odtworzone(con: duckdb.DuckDBPyConnection, llm: pd.DataFrame) -> int:
    """Zapisuje (od nowa) tabelę awarie_odtworzone; zwraca liczbę awarii."""
    utworz_serie_przestoju(con)
    con.register("awarie_llm", llm)
    try:
        con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS {_sql('awarie_odtworzone')}")
    finally:
        con.unregister("awarie_llm")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchall()[0][0]


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    if not PLIK_LLM.exists():
        print(f"{TABELA}: pomijam, brak {PLIK_LLM} (uruchom api.ai.llm.ekstrakcja_awarii --zbior windy)")
        sys.exit(0)
    dane_llm = wczytaj_llm()
    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_awarie_odtworzone(polaczenie_bazy, dane_llm):,} awarii".replace(",", " "))
