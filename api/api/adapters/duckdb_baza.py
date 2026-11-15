"""Połączenie z bazą domilo.duckdb i jej budowa z plików Parquet w data/.

Budowa: `pypyr baza` (albo `cd api && python -m api.adapters.duckdb_baza`).

Czas w bazie:
- CRM (`crm_*`, `www_sesje`): tekst ISO 8601 z przesunięciem -> TIMESTAMPTZ (dokładny moment, bez straty).
- Serwisownik (`serwis_*`): zostaje TIMESTAMP bez strefy = czas lokalny Europe/Warsaw, jak w źródle.
  Godzina 02:00–03:00 w dniu 2025-10-26 jest niejednoznaczna i baza tego nie rozstrzyga.
- Telemetra (`telemetra_windy`, `telemetra_cieplo`): `ts_utc` jest w Parquecie jako TIMESTAMPTZ (UTC), bez zmian.
`polacz()` ustawia strefę sesji Europe/Warsaw, więc porównanie TIMESTAMP z TIMESTAMPTZ traktuje TIMESTAMP
jako czas warszawski: to poprawne dla Serwisownika, PMS i portalu.
"""

import os
import re
from pathlib import Path

import duckdb

KATALOG_REPO = Path(__file__).resolve().parents[3]
KATALOG_DANYCH = KATALOG_REPO / "data"
SCIEZKA_BAZY = KATALOG_REPO / "domilo.duckdb"
STREFA_BIZNESOWA = "Europe/Warsaw"

# Katalogi partycjonowane (rok=/miesiac=) — w bazie jako widoki, nie tabele.
WIDOKI_TELEMETRII = ("telemetra_windy", "telemetra_cieplo")

# Kolumny CRM zapisane jako tekst ISO 8601 z przesunięciem strefy (data/README.md, „Konwencje systemów”).
KOLUMNY_CZASU_CRM = {
    "crm_aktywnosci": ("data_czas",),
    "crm_historia_statusow": ("data_czas",),
    "crm_leady": ("utworzono", "data_statusu"),
    "www_sesje": ("data_czas",),
}

_NAZWA_TABELI = re.compile(r"^[a-z][a-z0-9_]*$")


def polacz(sciezka: Path = SCIEZKA_BAZY, tylko_odczyt: bool = True) -> duckdb.DuckDBPyConnection:
    """Otwiera bazę ze strefą Europe/Warsaw i ścieżkami względnymi liczonymi od katalogu repozytorium."""
    if tylko_odczyt and not Path(sciezka).exists():
        raise FileNotFoundError(f"Brak bazy {sciezka}. Zbuduj ją: pypyr baza")
    con = duckdb.connect(str(sciezka), read_only=tylko_odczyt)
    con.execute(f"SET TimeZone = '{STREFA_BIZNESOWA}'")
    # Widoki telemetrii mają ścieżki względne (data/...), żeby baza działała na hoście i w devcontainerze.
    con.execute(f"SET file_search_path = '{KATALOG_REPO.as_posix()}'")
    return con


def pliki_tabel(katalog_danych: Path = KATALOG_DANYCH) -> dict[str, Path]:
    """Nazwa tabeli -> plik Parquet. Pomija partycje telemetrii (to widoki); zdjęcia JPEG nie są Parquetem."""
    pliki: dict[str, Path] = {}
    for plik in sorted(katalog_danych.rglob("*.parquet")):
        if any(czesc in WIDOKI_TELEMETRII for czesc in plik.relative_to(katalog_danych).parts):
            continue
        nazwa = plik.stem
        if not _NAZWA_TABELI.match(nazwa):
            raise ValueError(f"Nazwa pliku nie nadaje się na nazwę tabeli: {plik}")
        if nazwa in pliki:
            raise ValueError(f"Dwa pliki dają tę samą nazwę tabeli {nazwa}: {pliki[nazwa]}, {plik}")
        pliki[nazwa] = plik
    return pliki


def _select_tabeli(nazwa: str, sciezka_wzgledna: str) -> str:
    zamiany = [f"CAST({kol} AS TIMESTAMPTZ) AS {kol}" for kol in KOLUMNY_CZASU_CRM.get(nazwa, ())]
    if nazwa == "serwis_czesci":
        # Eksport z przecinkiem dziesiętnym i spacją tysięcy: '1 234,50' -> 1234.50
        zamiany.append("CAST(replace(replace(koszt_netto, ' ', ''), ',', '.') AS DECIMAL(12, 2)) AS koszt_netto")
    replace = f" REPLACE ({', '.join(zamiany)})" if zamiany else ""
    return f"SELECT *{replace} FROM read_parquet('{sciezka_wzgledna}')"


def _select_widoku(nazwa: str) -> str:
    return (
        f"SELECT * FROM read_parquet('data/telemetra/{nazwa}/*/*/*.parquet', hive_partitioning = true, "
        "hive_types = {'rok': INTEGER, 'miesiac': INTEGER})"
    )


def zbuduj_baze(sciezka: Path = SCIEZKA_BAZY) -> dict[str, int]:
    """Buduje bazę od zera (do pliku tymczasowego, potem podmiana). Zwraca liczbę wierszy każdej tabeli."""
    sciezka = Path(sciezka)
    tymczasowa = sciezka.with_name(sciezka.name + ".tmp")
    tymczasowa.unlink(missing_ok=True)
    liczby: dict[str, int] = {}
    con = polacz(tymczasowa, tylko_odczyt=False)
    try:
        for nazwa, plik in pliki_tabel().items():
            wzgledna = plik.relative_to(KATALOG_REPO).as_posix()
            con.execute(f"CREATE TABLE {nazwa} AS {_select_tabeli(nazwa, wzgledna)}")
            liczby[nazwa] = con.execute(f"SELECT count(*) FROM {nazwa}").fetchone()[0]
        for nazwa in WIDOKI_TELEMETRII:
            con.execute(f"CREATE VIEW {nazwa} AS {_select_widoku(nazwa)}")
            liczby[nazwa] = con.execute(f"SELECT count(*) FROM {nazwa}").fetchone()[0]
        con.execute("CHECKPOINT")
    except BaseException:
        con.close()
        tymczasowa.unlink(missing_ok=True)
        raise
    con.close()
    os.replace(tymczasowa, sciezka)
    return liczby


if __name__ == "__main__":
    for tabela, n in zbuduj_baze().items():
        print(f"{tabela:32} {n:>12,}".replace(",", " "))
    print(f"Zapisano {SCIEZKA_BAZY}")
