"""Pominięcia pozycji kolejki przez doradców: tabela `kolejka_pominiecia` w domilo.duckdb.

Zapis przychodzi z CRM (atrapa: dev/mock_lejek/app.py) przez `POST /leads/skips` w api/api/main.py. Jeden wiersz =
jedna pozycja kolejki (data_kolejki, id_leada), czyli ten sam klucz co webhook kolejki (adapters/crm_lejek.py).
Pominąć można tylko pozycję, która jest w kolejce tego doradcy tego dnia (`kolejka_doradcow`).
Ten sam powód i komentarz drugi raz to powtórzenie (bez zmian); inny powód lub komentarz to poprawka doradcy
(nadpisuje powód, zostawia `zgloszono`, ustawia `zmieniono`). Kody powodów: leasing_bc/pominiecia.py.
Tabela nie pochodzi z data/, więc przebudowa bazy przenosi ją ze starego pliku.
"""

from dataclasses import dataclass
from datetime import date, datetime

import duckdb
from api.adapters import kolejka_doradcow
from api.contexts_boundaries.leasing_bc.pominiecia import POWODY_POMINIECIA

TABELA = "kolejka_pominiecia"
_KODY = ", ".join(f"'{k}'" for k in POWODY_POMINIECIA)
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    data_kolejki DATE NOT NULL,
    id_leada VARCHAR NOT NULL,
    id_doradcy VARCHAR NOT NULL,
    pozycja INTEGER NOT NULL CHECK (pozycja >= 1),
    powod VARCHAR NOT NULL CHECK (powod IN ({_KODY})),
    komentarz VARCHAR,
    zgloszono TIMESTAMPTZ NOT NULL,
    zmieniono TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (data_kolejki, id_leada)
)
"""


class PozycjaPozaKolejka(LookupError):
    """Nie ma takiej pozycji w kolejce tego doradcy tego dnia."""


@dataclass(frozen=True)
class Pominiecie:
    data_kolejki: date
    id_leada: str
    id_doradcy: str
    powod: str
    komentarz: str | None
    zgloszono: datetime


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_TABELI)


def zapisz(con: duckdb.DuckDBPyConnection, p: Pominiecie) -> str:
    """Zapisuje pominięcie; zwraca 'utworzono', 'powtorzenie' albo 'zmieniono'."""
    utworz(con)
    if p.powod not in POWODY_POMINIECIA:
        raise ValueError(f"Nieznany powód pominięcia: {p.powod}")
    pozycja = next(
        (
            x["pozycja"]
            for x in kolejka_doradcow.pozycje(con, p.id_doradcy, p.data_kolejki)
            if x["id_leada"] == p.id_leada
        ),
        None,
    )
    if pozycja is None:
        raise PozycjaPozaKolejka(f"{p.id_leada} nie jest w kolejce {p.id_doradcy} z {p.data_kolejki}")
    obecne = con.execute(
        f"SELECT powod, komentarz FROM {TABELA} WHERE data_kolejki = ? AND id_leada = ?", [p.data_kolejki, p.id_leada]
    ).fetchone()
    if obecne is None:
        con.execute(
            f"INSERT INTO {TABELA} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [p.data_kolejki, p.id_leada, p.id_doradcy, pozycja, p.powod, p.komentarz, p.zgloszono, p.zgloszono],
        )
        return "utworzono"
    if tuple(obecne) == (p.powod, p.komentarz):
        return "powtorzenie"
    con.execute(
        f"UPDATE {TABELA} SET powod = ?, komentarz = ?, zmieniono = ? WHERE data_kolejki = ? AND id_leada = ?",
        [p.powod, p.komentarz, p.zgloszono, p.data_kolejki, p.id_leada],
    )
    return "zmieniono"


def lista(con: duckdb.DuckDBPyConnection, limit: int = 100) -> list[dict]:
    utworz(con)
    df = con.execute(
        f"SELECT * FROM {TABELA} ORDER BY zmieniono DESC, data_kolejki DESC, id_leada LIMIT ?", [limit]
    ).df()
    return df.to_dict("records")
