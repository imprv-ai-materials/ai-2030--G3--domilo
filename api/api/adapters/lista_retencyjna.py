"""Cotygodniowa lista retencyjna (retention_bc/lista_retencyjna.py): tabela `lista_retencyjna` w domilo.duckdb.

Jeden wiersz = umowa, która w dniu listy (`data_listy`) kończy się za 60–66 dni: ryzyko i czas do odejścia (model
ryzyka z churn_model/current.yaml), uplift, EV i akcja (model upliftu z current.yaml) oraz grupa kampanii
wylosowana z hasha (`id_umowy`, `kampania`): `kontrola` (bez oferty niezależnie od akcji) albo `polityka`
(oferta, gdy akcja = rabat; `wyslac_oferte`). Klucz (data_listy, id_umowy). Zapis zastępuje cały dzień listy,
a grupa zależy tylko od id_umowy i nazwy kampanii, więc ponowny przebieg na tych samych danych zapisuje to samo.
Tabela nie pochodzi z data/, więc przebudowa bazy (duckdb_baza.zbuduj_baze) przenosi ją ze starego pliku.
"""

from datetime import date

import duckdb
import pandas as pd

TABELA = "lista_retencyjna"
SQL_TABELI = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    data_listy DATE NOT NULL,
    id_umowy VARCHAR NOT NULL,
    id_najmu VARCHAR NOT NULL,
    id_najemcy VARCHAR NOT NULL,
    linia VARCHAR NOT NULL CHECK (linia IN ('B2C', 'B2B')),
    data_do DATE NOT NULL,
    dni_do_konca INTEGER NOT NULL CHECK (dni_do_konca BETWEEN 60 AND 66),
    stan_danych_na DATE NOT NULL,
    data_decyzji DATE NOT NULL,
    wypowiedzenie_zlozone BOOLEAN NOT NULL,
    ryzyko DOUBLE NOT NULL CHECK (ryzyko BETWEEN 0 AND 1),
    ryzyko_12_od_poczatku_okresu DOUBLE NOT NULL,
    przezycie_12_mies DOUBLE NOT NULL,
    mediana_do_odejscia_mies DOUBLE,
    rmst60_mies DOUBLE NOT NULL,
    p_przedluzy_z_oferta DOUBLE NOT NULL,
    p_przedluzy_bez_oferty DOUBLE NOT NULL,
    uplift DOUBLE NOT NULL,
    ev_pln DOUBLE NOT NULL,
    poza_zakresem_modelu VARCHAR[] NOT NULL,
    akcja VARCHAR NOT NULL CHECK (akcja IN ('rabat', 'bez rabatu', 'nie budzić')),
    uzasadnienie VARCHAR NOT NULL,
    kampania VARCHAR NOT NULL,
    reszta_hasha INTEGER NOT NULL CHECK (reszta_hasha BETWEEN 0 AND 99),
    grupa VARCHAR NOT NULL CHECK (grupa IN ('kontrola', 'polityka')),
    wyslac_oferte BOOLEAN NOT NULL,
    wersja_modelu_ryzyka VARCHAR NOT NULL,
    wersja_modelu_upliftu VARCHAR NOT NULL,
    id_przebiegu VARCHAR NOT NULL,
    PRIMARY KEY (data_listy, id_umowy),
    CHECK (NOT wyslac_oferte OR (grupa = 'polityka' AND akcja = 'rabat'))
)
"""
KOLUMNY = (
    "data_listy",
    "id_umowy",
    "id_najmu",
    "id_najemcy",
    "linia",
    "data_do",
    "dni_do_konca",
    "stan_danych_na",
    "data_decyzji",
    "wypowiedzenie_zlozone",
    "ryzyko",
    "ryzyko_12_od_poczatku_okresu",
    "przezycie_12_mies",
    "mediana_do_odejscia_mies",
    "rmst60_mies",
    "p_przedluzy_z_oferta",
    "p_przedluzy_bez_oferty",
    "uplift",
    "ev_pln",
    "poza_zakresem_modelu",
    "akcja",
    "uzasadnienie",
    "kampania",
    "reszta_hasha",
    "grupa",
    "wyslac_oferte",
    "wersja_modelu_ryzyka",
    "wersja_modelu_upliftu",
    "id_przebiegu",
)


def utworz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL_TABELI)


def zapisz(con: duckdb.DuckDBPyConnection, data_listy: date, lista: pd.DataFrame) -> int:
    """Zastępuje dzień `data_listy` wierszami `lista` (kolumny KOLUMNY); zwraca liczbę wierszy."""
    utworz(con)
    df = lista[list(KOLUMNY)]
    if (pd.to_datetime(df["data_listy"]).dt.date != data_listy).any():
        raise ValueError(f"lista_retencyjna.zapisz: wiersze spoza dnia {data_listy}")
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM {TABELA} WHERE data_listy = ?", [data_listy])
        con.register("_lista_nowa", df)
        con.execute(f"INSERT INTO {TABELA} ({', '.join(KOLUMNY)}) SELECT {', '.join(KOLUMNY)} FROM _lista_nowa")
        con.unregister("_lista_nowa")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return len(df)


def wczytaj(con: duckdb.DuckDBPyConnection, data_listy: date) -> pd.DataFrame:
    """Lista z dnia `data_listy` posortowana po id_umowy (pusta, gdy tabeli albo dnia nie ma)."""
    istnieje = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ? AND schema_name = 'main'", [TABELA]
    ).fetchone()[0]
    if not istnieje:
        return pd.DataFrame(columns=list(KOLUMNY))
    return con.execute(f"SELECT * FROM {TABELA} WHERE data_listy = ? ORDER BY id_umowy", [data_listy]).df()
