"""Cechy modelu kolejki liczone na moment utworzenia zapytania: jeden plik SQL na rodzinę (cechy_<rodzina>.sql).

Rodziny: zapytanie (formularz), budzet (budżet / mediana czynszu w mieście), www (sesje przed utworzeniem),
firma_b2b (umowa ramowa obowiązująca w chwili zapytania), tekst (długość wiadomości + sygnały LLM v1).
Żadna rodzina nie czyta kolumn stanu z crm_leady (status, data_statusu, powod_utraty, id_doradcy, id_umowy) ani cech
wykluczonych (wykluczone.yaml: jezyk, imie, rok_urodzenia); KOLUMNY_CECH i wynik zbuduj_cechy są sprawdzane.
Wynik: jeden wiersz na zapytanie z crm_leady (id_leada + kolumny cech). Raport: docs/kolejka_v2_lgbm_naiwny.md.
"""

from pathlib import Path

import duckdb
import pandas as pd
from api.ai.features.leady.wykluczone import sprawdz_brak_wykluczonych

KATALOG_SQL = Path(__file__).parent
RODZINY = ("zapytanie", "budzet", "www", "firma_b2b", "tekst")
SYGNALY_KOLUMNY = (
    "syg_konkretne_pytania",
    "syg_niedopasowanie_oferty",
    "syg_pilny_termin",
    "syg_relokacja",
    "syg_budzet_niski",
    "syg_brak_informacji",
)
# Kolumny wejścia modelu według rodziny (kolumny pomocnicze, np. budzet_max i mediana, zostają poza modelem).
CECHY_RODZIN = {
    "zapytanie": ("zrodlo", "miasto", "linia", "termin_dni", "liczba_osob", "zwierze", "liczba_lokali"),
    "budzet": ("budzet_do_mediany",),
    "www": ("www_liczba_sesji", "www_spacer_3d", "www_kalkulator"),
    "firma_b2b": ("umowa_ramowa",),
    "tekst": ("dlugosc_wiadomosci", *SYGNALY_KOLUMNY),
}
KOLUMNY_CECH = tuple(k for rodzina in RODZINY for k in CECHY_RODZIN[rodzina])
sprawdz_brak_wykluczonych(KOLUMNY_CECH, "KOLUMNY_CECH")  # jezyk, imie, rok_urodzenia: wykluczone.yaml
KATEGORIE = ("zrodlo", "miasto", "linia")


def sql_rodziny(rodzina: str) -> str:
    return (KATALOG_SQL / f"cechy_{rodzina}.sql").read_text(encoding="utf-8").strip().rstrip(";")


def zbuduj_cechy(con: duckdb.DuckDBPyConnection, sygnaly: pd.DataFrame) -> pd.DataFrame:
    """Wszystkie rodziny złączone po id_leada; cechy liczbowe jako float64 (brak = NaN).

    `sygnaly`: id_leada, sygnaly (z sygnaly_v1.wczytaj_sygnaly).
    """
    con.register("sygnaly_v1", sygnaly[["id_leada", "sygnaly"]])
    try:
        czesci = [con.execute(sql_rodziny(r)).df().set_index("id_leada") for r in RODZINY]
    finally:
        con.unregister("sygnaly_v1")
    cechy = pd.concat(czesci, axis=1, join="outer")
    sprawdz_brak_wykluczonych(cechy.columns, "zbuduj_cechy")
    # Liczby jako float64 z NaN (DuckDB oddaje nullable Int64 z pd.NA, a LightGBM oczekuje NaN).
    liczbowe = [k for k in KOLUMNY_CECH if k not in KATEGORIE]
    cechy[liczbowe] = cechy[liczbowe].astype("float64")
    if not cechy.index.is_unique:
        raise ValueError("Cechy kolejki: id_leada nie jest unikalne")
    return cechy.reset_index()
