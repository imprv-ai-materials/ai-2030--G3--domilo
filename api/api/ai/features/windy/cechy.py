"""Cechy modelu awarii wind z telemetrii: tabela cechy_windy (wiersz = wiersz dni_wind: id_windy × dzien).

Rodziny: jeden plik SQL na rodzinę w `sql/` (drzwi, naped, wibracje, sterownik, uzycie). Plik rodziny zwraca
sygnały z 10-minutowych okien (`id_windy`, `ts_utc`, kolumny sygnałów) z widoku `telemetria` = `telemetra_windy`
(Parquet `data/telemetra/telemetra_windy/`, czytany przez DuckDB) bez okien z `tryb = 'serwis'`.
Rodzina może mieć cechy dodatkowe (`DODATKOWE`): plik SQL zwracający wiersz na (id_windy, dzien) z `kotwice`.

Dla każdego sygnału ten moduł generuje SQL (`sql_rodziny`) i liczy:
- `<s>_sr_24h|3d|7d`, `<s>_max_24h|3d|7d` — średnia i maksimum z okien kończących się w (odcięcie − 24 h / 72 h /
  168 h; odcięcie], odcięcie = 05:50 Europe/Warsaw dnia oceny (okno kończące się o 06:00 już się nie liczy);
- `<s>_norma` — mediana średnich dobowych (`<s>_sr_24h`) z dni 15–44 przed oceną (kotwice t−43 … t−14), gdy
  wartość ma co najmniej `NORMA_MIN_DNI` z 30 dni (inaczej NULL);
- `<s>_do_normy_24h|3d|7d` — średnia z okna / norma (NULL, gdy norma = 0 albo NULL);
- `<s>_trend_7d` — nachylenie prostej (regr_slope) średnich dobowych z 7 dni (t−6 … t) na dzień; NULL, gdy mniej
  niż `TREND_MIN_DNI` dni z wartością.
Okna liczone dokładnie w godzinach (także przy zmianie czasu): okna 10-min zbieramy w godziny kończące się
o :50 UTC (Polska ma przesunięcie w pełnych godzinach, więc 05:50 lokalnie jest końcem takiej godziny).

Opis, decyzje i liczby: docs/b4_cechy.md. Budowa: `pypyr baza` (po dni_wind) albo
`cd api && python -m api.ai.features.windy.cechy`.
"""

import sys
from pathlib import Path

import duckdb

KATALOG_SQL = Path(__file__).with_name("sql")
TABELA = "cechy_windy"
RODZINY = ("drzwi", "naped", "wibracje", "sterownik", "uzycie")
DODATKOWE = {"wibracje": "wibracje_czujnik", "sterownik": "sterownik_firmware"}
PIERWSZY_DZIEN = "2023-01-01"  # kotwice od początku telemetrii: norma dla 2023-03-01 sięga do 2023-01-17
OSTATNI_DZIEN = "2026-09-22"  # ostatni dzień dni_wind
ODCIECIE = "05:50"  # koniec ostatniego okna telemetrii przed oceną o 06:00
OKNA_GODZIN = {"24h": 24, "3d": 72, "7d": 168}
NORMA_DNI = (15, 44)
NORMA_MIN_DNI = 20
TREND_DNI = 7
TREND_MIN_DNI = 5
KLUCZ = ("id_windy", "ts_utc")


def sql_pliku(nazwa: str) -> str:
    return (KATALOG_SQL / f"{nazwa}.sql").read_text(encoding="utf-8").strip().rstrip(";")


def przygotuj(con: duckdb.DuckDBPyConnection) -> None:
    """Widok `telemetria` (bez okien serwisowych, do odcięcia ostatniego dnia) i tabela `kotwice` (winda × dzień)."""
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW telemetria AS
        SELECT *
        FROM telemetra_windy
        WHERE tryb IS DISTINCT FROM 'serwis'
          AND ts_utc <= timezone('Europe/Warsaw', TIMESTAMP '{OSTATNI_DZIEN} {ODCIECIE}')
        """)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE kotwice AS
        WITH zakres AS (SELECT id_windy, min(ts_utc) AS od FROM telemetra_windy GROUP BY id_windy)
        SELECT
            z.id_windy,
            CAST(d.dzien AS DATE) AS dzien,
            timezone('Europe/Warsaw', d.dzien + INTERVAL '{ODCIECIE}') AS moment_odciecia,
            CAST(epoch(timezone('Europe/Warsaw', d.dzien + INTERVAL '{ODCIECIE}')) AS BIGINT) AS odciecie_s
        FROM zakres AS z
        CROSS JOIN generate_series(
            TIMESTAMP '{PIERWSZY_DZIEN}', TIMESTAMP '{OSTATNI_DZIEN}', INTERVAL 1 DAY
        ) AS d(dzien)
        WHERE timezone('Europe/Warsaw', d.dzien + INTERVAL '{ODCIECIE}') >= z.od
        """)


def sygnaly(con: duckdb.DuckDBPyConnection, rodzina: str) -> list[str]:
    """Kolumny sygnałów rodziny (wszystko poza id_windy i ts_utc); wymaga widoku `telemetria`."""
    kolumny = [r[0] for r in con.execute(f"DESCRIBE {sql_pliku(rodzina)}").fetchall()]
    brak = [k for k in KLUCZ if k not in kolumny]
    if brak:
        raise ValueError(f"sql/{rodzina}.sql nie zwraca kolumn {brak}")
    return [k for k in kolumny if k not in KLUCZ]


def nazwy_cech(sygnal: str) -> list[str]:
    srednie = [f"{sygnal}_sr_{o}" for o in OKNA_GODZIN]
    maksima = [f"{sygnal}_max_{o}" for o in OKNA_GODZIN]
    stosunki = [f"{sygnal}_do_normy_{o}" for o in OKNA_GODZIN]
    pary = [x for para in zip(srednie, maksima, strict=True) for x in para]
    return pary + [f"{sygnal}_norma", *stosunki, f"{sygnal}_trend_7d"]


def sql_rodziny(rodzina: str, sygnaly_rodziny: list[str]) -> str:
    """Pełne zapytanie cech rodziny: wiersz na (id_windy, dzien) z `kotwice`."""
    godziny = ",\n        ".join(
        f"sum(CAST({s} AS DOUBLE)) AS {s}__suma, count({s}) AS {s}__n, max(CAST({s} AS DOUBLE)) AS {s}__max"
        for s in sygnaly_rodziny
    )
    okna = []
    for nazwa, godz in OKNA_GODZIN.items():
        w_oknie = f"g.koniec_godziny > k.odciecie_s - {godz * 3600}"
        for s in sygnaly_rodziny:
            okna.append(
                f"sum(g.{s}__suma) FILTER ({w_oknie}) / nullif(sum(g.{s}__n) FILTER ({w_oknie}), 0) AS {s}_sr_{nazwa}"
            )
            okna.append(f"max(g.{s}__max) FILTER ({w_oknie}) AS {s}_max_{nazwa}")
    normy = []
    for s in sygnaly_rodziny:
        normy.append(
            f"CASE WHEN count({s}_sr_24h) OVER w_norma >= {NORMA_MIN_DNI} "
            f"THEN median({s}_sr_24h) OVER w_norma END AS {s}_norma"
        )
        normy.append(
            f"CASE WHEN regr_count({s}_sr_24h, nr_dnia) OVER w_trend >= {TREND_MIN_DNI} "
            f"THEN regr_slope({s}_sr_24h, nr_dnia) OVER w_trend END AS {s}_trend_7d"
        )
    wynik = []
    for s in sygnaly_rodziny:
        for kolumna in nazwy_cech(s):
            if "_do_normy_" in kolumna:
                okno = kolumna.rsplit("_", 1)[1]
                wynik.append(f"{s}_sr_{okno} / nullif({s}_norma, 0) AS {kolumna}")
            else:
                wynik.append(kolumna)
    max_okno = max(OKNA_GODZIN.values()) * 3600
    od, do = NORMA_DNI
    return f"""
WITH sygnaly AS (
{sql_pliku(rodzina)}
),
godziny AS (
    -- okna 10-min -> godziny kończące się o :50 UTC: ts w (H:50 − 1 h; H:50]
    SELECT
        id_windy,
        CAST(floor((epoch(ts_utc) + 540) / 3600) * 3600 + 3000 AS BIGINT) AS koniec_godziny,
        {godziny}
    FROM sygnaly
    GROUP BY ALL
),
okna AS (
    SELECT
        k.id_windy, k.dzien,
        {(',' + chr(10) + '        ').join(okna)}
    FROM kotwice AS k
    LEFT JOIN godziny AS g
        ON g.id_windy = k.id_windy
       AND g.koniec_godziny > k.odciecie_s - {max_okno}
       AND g.koniec_godziny <= k.odciecie_s
    GROUP BY k.id_windy, k.dzien
),
normy AS (
    SELECT
        *,
        {(',' + chr(10) + '        ').join(normy)}
    FROM (SELECT *, date_diff('day', DATE '{PIERWSZY_DZIEN}', dzien) AS nr_dnia FROM okna)
    WINDOW
        w_norma AS (PARTITION BY id_windy ORDER BY dzien
                    RANGE BETWEEN INTERVAL {do - 1} DAY PRECEDING AND INTERVAL {od - 1} DAY PRECEDING),
        w_trend AS (PARTITION BY id_windy ORDER BY dzien
                    RANGE BETWEEN INTERVAL {TREND_DNI - 1} DAY PRECEDING AND CURRENT ROW)
)
SELECT
    id_windy, dzien,
    {(',' + chr(10) + '    ').join(wynik)}
FROM normy
"""


def zbuduj_cechy_windy(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę cechy_windy dla wierszy dni_wind; zwraca liczbę wierszy."""
    przygotuj(con)
    czesci = []
    for rodzina in RODZINY:
        con.execute(f"CREATE OR REPLACE TEMP TABLE cechy_{rodzina} AS {sql_rodziny(rodzina, sygnaly(con, rodzina))}")
        czesci.append(f"cechy_{rodzina}")
        if rodzina in DODATKOWE:
            nazwa = DODATKOWE[rodzina]
            con.execute(f"CREATE OR REPLACE TEMP TABLE cechy_{nazwa} AS {sql_pliku(nazwa)}")
            czesci.append(f"cechy_{nazwa}")
    zlaczenia = "\n".join(f"LEFT JOIN {t} USING (id_windy, dzien)" for t in czesci)
    kolumny = ", ".join(f"{t}.* EXCLUDE (id_windy, dzien)" for t in czesci)
    con.execute(f"""
        CREATE OR REPLACE TABLE {TABELA} AS
        SELECT d.id_windy, d.dzien, {kolumny}
        FROM dni_wind AS d
        {zlaczenia}
        ORDER BY d.dzien, d.id_windy
        """)
    n, unikalne = con.execute(f"SELECT count(*), count(DISTINCT (id_windy, dzien)) FROM {TABELA}").fetchone()
    if n != unikalne:
        raise ValueError(f"{TABELA}: (id_windy, dzien) nie jest unikalne")
    return n


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        jest = polaczenie_bazy.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'dni_wind'"
        ).fetchone()[0]
        if not jest:
            print(f"{TABELA}: pomijam, brak tabeli dni_wind")
            sys.exit(0)
        print(f"{TABELA}: {zbuduj_cechy_windy(polaczenie_bazy):,} wierszy".replace(",", " "))
