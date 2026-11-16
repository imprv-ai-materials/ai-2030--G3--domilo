"""Tabele trwałe oceny wind w domilo.duckdb: `ryzyko_wind` (codzienna ocena) i `alarmy_wind` (alarmy z reguły).

`ryzyko_wind`: wiersz = winda × dzień oceny (06:00 Europe/Warsaw) z zadania `ryzyko-wind`
(maintenance_bc/ryzyko_dzienne.py): `wynik` = ranking modelu (`predict`, tym wynikiem reguła wybiera alarmy),
`p_awarii_7d` = P(awaria w 7 dni) po kalibracji (`prawdopodobienstwo`; NULL, gdy wersja go nie ma), `ranga` w dniu,
`stoi` = ostatnie okno przed odcięciem ma `tryb = 'wylaczona'` (winda stoi, alarmu nie dostaje), `sygnaly` (JSON:
najsilniejsze sygnały), `podzespoly` (JSON: podejrzane podzespoły z sumą wkładów SHAP) i `opis` (zdanie alertu)
z maintenance_bc/wyjasnienie.py; `tryb_oceny` (`model` / `zapasowa` = winda bez normy, reguła zapasowa),
`dni_telemetrii`, `wynik_zapasowy`, `prog_zapasowy`, `odchylenia` (JSON) z reguły zapasowej
(docs/b4_dryf_i_fallback.md).
Kolumny dodane później (KOLUMNY_DODANE) `utworz` dopisuje także do tabel założonych wcześniej.
Zapis zastępuje cały dzień (ponowny przebieg tego dnia liczy to samo z tych samych cech).

`alarmy_wind`: alarmy dnia z reguły maintenance_bc/alarmy_wind.wybierz_alarmy. Pierwsza decyzja dnia zostaje:
gdy dzień ma już alarmy, `zapisz_alarmy` ich nie zmienia (zgłoszenia mogły już pójść do Serwisownika), tylko je
zwraca. `id_zgloszenia` i `wyslano` uzupełnia krok wysyłki (`oznacz_wyslany`).
Tabele nie pochodzą z data/, więc przebudowa bazy (duckdb_baza.zbuduj_baze) przenosi je ze starego pliku.
"""

import json
from datetime import date

import duckdb
import pandas as pd

TABELA_RYZYKA = "ryzyko_wind"
TABELA_ALARMOW = "alarmy_wind"
SQL_RYZYKA = f"""
CREATE TABLE IF NOT EXISTS {TABELA_RYZYKA} (
    dzien DATE NOT NULL,
    id_windy VARCHAR NOT NULL,
    moment_oceny TIMESTAMPTZ NOT NULL,
    wynik DOUBLE NOT NULL,
    p_awarii_7d DOUBLE,
    ranga INTEGER NOT NULL CHECK (ranga >= 1),
    stoi BOOLEAN NOT NULL,
    ostatnie_okno TIMESTAMPTZ,
    okna_24h INTEGER NOT NULL,
    sygnaly VARCHAR NOT NULL,
    podzespoly VARCHAR NOT NULL,
    wersja_modelu VARCHAR NOT NULL,
    id_przebiegu VARCHAR NOT NULL,
    opis VARCHAR,
    tryb_oceny VARCHAR,
    dni_telemetrii INTEGER,
    wynik_zapasowy DOUBLE,
    prog_zapasowy DOUBLE,
    odchylenia VARCHAR,
    PRIMARY KEY (dzien, id_windy)
)
"""
SQL_ALARMOW = f"""
CREATE TABLE IF NOT EXISTS {TABELA_ALARMOW} (
    dzien DATE NOT NULL,
    pozycja INTEGER NOT NULL CHECK (pozycja >= 1),
    id_windy VARCHAR NOT NULL,
    wynik DOUBLE NOT NULL,
    p_awarii_7d DOUBLE,
    wersja_modelu VARCHAR NOT NULL,
    id_przebiegu VARCHAR NOT NULL,
    id_zgloszenia VARCHAR,
    wyslano TIMESTAMPTZ,
    tryb_oceny VARCHAR,
    wynik_zapasowy DOUBLE,
    PRIMARY KEY (dzien, id_windy),
    UNIQUE (dzien, pozycja)
)
"""
KOLUMNY_RYZYKA = (
    "dzien",
    "id_windy",
    "moment_oceny",
    "wynik",
    "p_awarii_7d",
    "ranga",
    "stoi",
    "ostatnie_okno",
    "okna_24h",
    "sygnaly",
    "podzespoly",
    "wersja_modelu",
    "id_przebiegu",
    "opis",
    "tryb_oceny",
    "dni_telemetrii",
    "wynik_zapasowy",
    "prog_zapasowy",
    "odchylenia",
)
KOLUMNY_ALARMOW = (
    "dzien",
    "pozycja",
    "id_windy",
    "wynik",
    "p_awarii_7d",
    "wersja_modelu",
    "id_przebiegu",
    "tryb_oceny",
    "wynik_zapasowy",
)
# kolumny dopisane po pierwszej wersji tabel (ALTER TABLE ... ADD COLUMN IF NOT EXISTS w `utworz`)
KOLUMNY_DODANE = {
    TABELA_RYZYKA: {
        "opis": "VARCHAR",
        "tryb_oceny": "VARCHAR",
        "dni_telemetrii": "INTEGER",
        "wynik_zapasowy": "DOUBLE",
        "prog_zapasowy": "DOUBLE",
        "odchylenia": "VARCHAR",
    },
    TABELA_ALARMOW: {"tryb_oceny": "VARCHAR", "wynik_zapasowy": "DOUBLE"},
}


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_RYZYKA)
    con.execute(SQL_ALARMOW)
    for tabela, kolumny in KOLUMNY_DODANE.items():
        for kolumna, typ in kolumny.items():
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {kolumna} {typ}")


def _istnieje(con: duckdb.DuckDBPyConnection, tabela: str) -> bool:
    return bool(
        con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [tabela]).fetchone()[0]
    )


def _wstaw(con: duckdb.DuckDBPyConnection, tabela: str, kolumny: tuple[str, ...], df: pd.DataFrame) -> None:
    con.register("_nowe_wiersze", df[list(kolumny)])
    try:
        con.execute(f"INSERT INTO {tabela} ({', '.join(kolumny)}) SELECT {', '.join(kolumny)} FROM _nowe_wiersze")
    finally:
        con.unregister("_nowe_wiersze")


def zapisz_ryzyko(con: duckdb.DuckDBPyConnection, dzien: date, ryzyko: pd.DataFrame) -> int:
    """Zastępuje dzień `dzien` wierszami `ryzyko` (kolumny KOLUMNY_RYZYKA); zwraca liczbę wierszy."""
    utworz(con)
    if (pd.to_datetime(ryzyko["dzien"]).dt.date != dzien).any():
        raise ValueError(f"ryzyko_wind.zapisz_ryzyko: wiersze spoza dnia {dzien}")
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM {TABELA_RYZYKA} WHERE dzien = ?", [dzien])
        _wstaw(con, TABELA_RYZYKA, KOLUMNY_RYZYKA, ryzyko)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return len(ryzyko)


def alarmy(con: duckdb.DuckDBPyConnection, od: date | None = None, do: date | None = None) -> pd.DataFrame:
    """Alarmy z dni [od; do] (None = bez granicy); pusta ramka, gdy tabeli nie ma."""
    if not _istnieje(con, TABELA_ALARMOW):
        return pd.DataFrame(columns=[*KOLUMNY_ALARMOW, "id_zgloszenia", "wyslano"])
    return con.execute(
        f"""
        SELECT * FROM {TABELA_ALARMOW}
        WHERE (CAST(? AS DATE) IS NULL OR dzien >= ?) AND (CAST(? AS DATE) IS NULL OR dzien <= ?)
        ORDER BY dzien, pozycja
        """,
        [od, od, do, do],
    ).df()


def zapisz_alarmy(con: duckdb.DuckDBPyConnection, dzien: date, nowe: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Zapisuje alarmy dnia, jeśli dzień ich jeszcze nie ma. Zwraca (alarmy dnia z tabeli, czy zapisano teraz)."""
    utworz(con)
    if len(alarmy(con, dzien, dzien)):
        return alarmy(con, dzien, dzien), False
    if len(nowe):
        if (pd.to_datetime(nowe["dzien"]).dt.date != dzien).any():
            raise ValueError(f"ryzyko_wind.zapisz_alarmy: wiersze spoza dnia {dzien}")
        _wstaw(con, TABELA_ALARMOW, KOLUMNY_ALARMOW, nowe)
    return alarmy(con, dzien, dzien), True


def oznacz_wyslany(con: duckdb.DuckDBPyConnection, dzien: date, id_windy: str, id_zgloszenia: str) -> None:
    con.execute(
        f"""
        UPDATE {TABELA_ALARMOW}
        SET id_zgloszenia = ?, wyslano = coalesce(wyslano, now())
        WHERE dzien = ? AND id_windy = ?
        """,
        [id_zgloszenia, dzien, id_windy],
    )


def ocena_windy(con: duckdb.DuckDBPyConnection, id_windy: str, dzien: date | None = None) -> dict | None:
    """Najnowsza ocena windy (albo z dnia `dzien`) z alarmem tego dnia, jeśli był; None = brak oceny."""
    if not _istnieje(con, TABELA_RYZYKA):
        return None
    wiersz = con.execute(
        f"""
        SELECT r.*, (SELECT count(*) FROM {TABELA_RYZYKA} AS x WHERE x.dzien = r.dzien) AS ocenione_windy
        FROM {TABELA_RYZYKA} AS r
        WHERE r.id_windy = ? AND (CAST(? AS DATE) IS NULL OR r.dzien = ?)
        ORDER BY r.dzien DESC
        LIMIT 1
        """,
        [id_windy, dzien, dzien],
    ).df()
    if wiersz.empty:
        return None
    w = wiersz.iloc[0].to_dict()
    w["sygnaly"] = json.loads(w["sygnaly"])
    w["podzespoly"] = json.loads(w["podzespoly"])
    w = {k: (None if not isinstance(v, (list, dict, str)) and pd.isna(v) else v) for k, v in w.items()}
    dzien_oceny = pd.Timestamp(w["dzien"]).date()
    alarm = alarmy(con, dzien_oceny, dzien_oceny)
    alarm = alarm[alarm["id_windy"] == id_windy]
    w["alarm"] = None
    if len(alarm):
        a = alarm.iloc[0]
        w["alarm"] = {
            "pozycja": int(a["pozycja"]),
            "id_zgloszenia": None if pd.isna(a["id_zgloszenia"]) else str(a["id_zgloszenia"]),
            "tryb_oceny": None if pd.isna(a.get("tryb_oceny")) else str(a.get("tryb_oceny")),
        }
    return w


def wyczysc(con: duckdb.DuckDBPyConnection) -> None:
    """Usuwa oceny i alarmy wind (tylko na kopii bazy: testy i symulacje, które mają zacząć od pustej historii)."""
    utworz(con)
    con.execute(f"DELETE FROM {TABELA_ALARMOW}")
    con.execute(f"DELETE FROM {TABELA_RYZYKA}")
    if _istnieje(con, "alerty_ocena"):
        con.execute("DELETE FROM alerty_ocena")
