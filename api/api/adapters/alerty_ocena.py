"""Oceny alertów wind przez koordynatora: tabela `alerty_ocena` w domilo.duckdb (nowe etykiety do ponownego uczenia).

Koordynator w Serwisowniku (atrapa: dev/serwisownik_mock/, strona /koordynator) oznacza zgłoszenie z alertu jako
`trafny` (winda rzeczywiście się psuła / technik znalazł usterkę) albo `falszywy`, opcjonalnie z faktycznym
podzespołem i komentarzem. Serwisownik przekazuje ocenę do API Domilo (`POST /lifts/alerts/feedback`), a ono zapisuje
ją tutaj. Klucz = alert: (dzien, id_windy), jak w alarmy_wind i kluczu idempotencji zgłoszenia
`{id_windy}:{data_alarmu}`. Ta sama ocena drugi raz to powtórzenie (bez zmian), inna to poprawka (nadpisuje ocenę,
`poprawki` + 1, `pierwsza_ocena` zostaje). Ocena alertu, którego nie ma w alarmy_wind, jest odrzucana
(`AlertNieznany`).

Uwaga dla uczenia: etykiety dotyczą tylko wind z alarmem (wybranych przez model), więc nie są losową próbą dni —
ponowne uczenie musi to uwzględnić (docs/b4_panel_techniczny.md).
Tabela nie pochodzi z data/, więc przebudowa bazy (duckdb_baza.zbuduj_baze) przenosi ją ze starego pliku.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone

import duckdb
import pandas as pd
from api.adapters.ryzyko_wind import TABELA_ALARMOW

TABELA = "alerty_ocena"
OCENY = ("trafny", "falszywy")
PODZESPOLY = ("drzwi", "naped", "hamulec_liny", "sterownik", "zewnetrzna", "brak")
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    dzien DATE NOT NULL,
    id_windy VARCHAR NOT NULL,
    id_zgloszenia VARCHAR,
    ocena VARCHAR NOT NULL CHECK (ocena IN ('trafny', 'falszywy')),
    podzespol VARCHAR CHECK (podzespol IS NULL OR podzespol IN
        ('drzwi', 'naped', 'hamulec_liny', 'sterownik', 'zewnetrzna', 'brak')),
    komentarz VARCHAR,
    oceniajacy VARCHAR,
    oceniono TIMESTAMPTZ NOT NULL,
    pierwsza_ocena TIMESTAMPTZ NOT NULL,
    poprawki INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dzien, id_windy)
)
"""


class AlertNieznany(LookupError):
    """Nie ma takiego alertu w alarmy_wind."""


@dataclass(frozen=True)
class Ocena:
    id_windy: str
    dzien: date
    ocena: str
    podzespol: str | None = None
    komentarz: str | None = None
    oceniajacy: str | None = None
    id_zgloszenia: str | None = None


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_TABELI)


def rozbij_klucz(klucz_idempotencji: str) -> tuple[str, date]:
    """`{id_windy}:{data_alarmu}` -> (id_windy, data); ValueError przy złym formacie."""
    id_windy, _, dzien = klucz_idempotencji.rpartition(":")
    if not id_windy:
        raise ValueError(f"Klucz {klucz_idempotencji!r} nie ma postaci id_windy:RRRR-MM-DD")
    return id_windy, date.fromisoformat(dzien)


def zapisz(con: duckdb.DuckDBPyConnection, o: Ocena, teraz: datetime | None = None) -> str:
    """Zapisuje ocenę; zwraca `zapisano`, `powtorzenie` albo `poprawka`."""
    if o.ocena not in OCENY:
        raise ValueError(f"Nieznana ocena {o.ocena!r} (dozwolone: {', '.join(OCENY)})")
    if o.podzespol is not None and o.podzespol not in PODZESPOLY:
        raise ValueError(f"Nieznany podzespół {o.podzespol!r} (dozwolone: {', '.join(PODZESPOLY)})")
    utworz(con)
    alarm = con.execute(
        f"SELECT id_zgloszenia FROM {TABELA_ALARMOW} WHERE dzien = ? AND id_windy = ?", [o.dzien, o.id_windy]
    ).fetchall()
    if not alarm:
        raise AlertNieznany(f"Nie ma alertu windy {o.id_windy} z dnia {o.dzien}")
    chwila = teraz or datetime.now(timezone.utc)
    id_zgloszenia = o.id_zgloszenia or alarm[0][0]
    stara = con.execute(
        f"SELECT ocena, podzespol, komentarz FROM {TABELA} WHERE dzien = ? AND id_windy = ?", [o.dzien, o.id_windy]
    ).fetchone()
    if stara is None:
        con.execute(
            f"""INSERT INTO {TABELA} (dzien, id_windy, id_zgloszenia, ocena, podzespol, komentarz, oceniajacy,
                oceniono, pierwsza_ocena, poprawki) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            [o.dzien, o.id_windy, id_zgloszenia, o.ocena, o.podzespol, o.komentarz, o.oceniajacy, chwila, chwila],
        )
        return "zapisano"
    if tuple(stara) == (o.ocena, o.podzespol, o.komentarz):
        return "powtorzenie"
    con.execute(
        f"""UPDATE {TABELA} SET ocena = ?, podzespol = ?, komentarz = ?, oceniajacy = ?, oceniono = ?,
            id_zgloszenia = ?, poprawki = poprawki + 1 WHERE dzien = ? AND id_windy = ?""",
        [o.ocena, o.podzespol, o.komentarz, o.oceniajacy, chwila, id_zgloszenia, o.dzien, o.id_windy],
    )
    return "poprawka"


def oceny(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Wszystkie oceny (pusta ramka, gdy tabeli nie ma)."""
    jest = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [TABELA]).fetchone()[0]
    if not jest:
        return pd.DataFrame(columns=["dzien", "id_windy", "id_zgloszenia", "ocena", "podzespol", "komentarz"])
    return con.execute(f"SELECT * FROM {TABELA} ORDER BY dzien, id_windy").df()
