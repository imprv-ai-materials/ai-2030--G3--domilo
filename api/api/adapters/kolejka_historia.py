"""Historia kolejek doradców do eksperymentu (docs/kolejka_eksperyment.md): tabela `kolejka_historia` w domilo.duckdb.

Jeden wiersz = pozycja kolejki doradcy w dniu kolejki z dziennego zadania (to, co poszło do CRM), z wariantem
eksperymentu i informacją, czy pozycja była losowa:
- `wariant`: `model` albo `od_najnowszego` (leasing_bc/eksperyment.py, plan tygodni);
- `losowa`: zapytanie wylosowane z otwartych zapytań miasta (5% pozycji, na losowym miejscu), a nie wybrane przez
  wariant; `p_losowania`: prawdopodobieństwo, że dowolne otwarte zapytanie miasta trafiło tego dnia na pozycję
  losową (= pozycje losowe w mieście / `pula_losowania`); `ziarno`: wejście losowania (dzień:miasto:wariant);
- `ranga_ev`: miejsce zapytania w rankingu EV miasta (ten sam ranking w obu wariantach).
Klucz (data_kolejki, id_leada) jak w kolejka_doradcow i webhooku do CRM. Zapis zastępuje cały dzień, a losowanie ma
stałe ziarno, więc drugi przebieg tego samego dnia zapisuje to samo. Tabela nie pochodzi z data/, więc przebudowa
bazy (duckdb_baza.zbuduj_baze) przenosi ją ze starego pliku.
"""

from datetime import date

import duckdb
import pandas as pd

TABELA = "kolejka_historia"
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    data_kolejki DATE NOT NULL,
    id_doradcy VARCHAR NOT NULL,
    miasto VARCHAR NOT NULL,
    pozycja INTEGER NOT NULL CHECK (pozycja >= 1),
    id_leada VARCHAR NOT NULL,
    wariant VARCHAR NOT NULL CHECK (wariant IN ('model', 'od_najnowszego')),
    losowa BOOLEAN NOT NULL,
    p_losowania DOUBLE NOT NULL CHECK (p_losowania >= 0 AND p_losowania <= 1),
    pula_losowania INTEGER NOT NULL CHECK (pula_losowania >= 1),
    ziarno VARCHAR NOT NULL,
    ranga_ev INTEGER NOT NULL CHECK (ranga_ev >= 1),
    p DOUBLE NOT NULL,
    ev_pln DOUBLE NOT NULL,
    wersja_modelu VARCHAR NOT NULL,
    id_przebiegu VARCHAR NOT NULL,
    PRIMARY KEY (data_kolejki, id_leada),
    UNIQUE (data_kolejki, id_doradcy, pozycja)
)
"""
KOLUMNY = (
    "data_kolejki",
    "id_doradcy",
    "miasto",
    "pozycja",
    "id_leada",
    "wariant",
    "losowa",
    "p_losowania",
    "pula_losowania",
    "ziarno",
    "ranga_ev",
    "p",
    "ev_pln",
    "wersja_modelu",
    "id_przebiegu",
)


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_TABELI)


def zapisz(con: duckdb.DuckDBPyConnection, data_kolejki: date, historia: pd.DataFrame) -> int:
    """Zastępuje dzień `data_kolejki` wierszami `historia` (kolumny KOLUMNY); zwraca liczbę wierszy."""
    utworz(con)
    df = historia[list(KOLUMNY)]
    if (pd.to_datetime(df["data_kolejki"]).dt.date != data_kolejki).any():
        raise ValueError(f"kolejka_historia.zapisz: wiersze spoza dnia {data_kolejki}")
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM {TABELA} WHERE data_kolejki = ?", [data_kolejki])
        con.register("_historia_nowa", df)
        con.execute(f"INSERT INTO {TABELA} ({', '.join(KOLUMNY)}) SELECT {', '.join(KOLUMNY)} FROM _historia_nowa")
        con.unregister("_historia_nowa")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return len(df)
