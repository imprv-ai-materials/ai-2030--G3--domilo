"""Cechy listy retencyjnej na dzień migawki: jeden plik SQL na rodzinę (sql/<rodzina>.sql).

Rodziny: umowa (staż, nr okresu, indeksacja, czynsz względem nowych umów podobnych lokali), platnosci (opóźnienia
z 90 dni), relacja (zgłoszenia i oceny z portalu, ankieta ASOF, logowania i odsłony oferty z pełnych miesięcy),
budynek (awarie wind z 90 dni). Każda rodzina liczy cechy dla wierszy migawki_najemcy wyłącznie ze zdarzeń z datą
< data_migawki. Bez rok_urodzenia i jezyk_kontaktu (wykluczone.yaml). Opis przecieków: docs/przecieki_najemcy.md.
Wynik: tabela cechy_najemcy (id_umowy + kolumny cech), budowa:
`cd api && python -m api.ai.features.najemcy.cechy` (także krok `pypyr baza`, po migawki_najemcy).
"""

from pathlib import Path

import duckdb
import pandas as pd
from api.ai.features.najemcy.wykluczone import sprawdz_brak_wykluczonych, zakazane_w_sql

KATALOG_SQL = Path(__file__).with_name("sql")
TABELA = "cechy_najemcy"
RODZINY = ("umowa", "platnosci", "relacja", "budynek")
# Kolumny wejścia modelu według rodziny; kolumny pomocnicze (czynsz, podobne_*) zostają w tabeli, ale poza modelem.
CECHY_RODZIN = {
    "umowa": (
        "linia",
        "miesiecy_umowy",
        "nr_okresu",
        "staz_dni",
        "indeksacja_ostatnia_pct",
        "czynsz_m2",
        "czynsz_do_podobnych",
    ),
    "platnosci": (
        "plat_liczba_90d",
        "plat_spoznione_90d",
        "plat_zalegle_na_migawke",
        "plat_max_opoznienie_90d",
        "plat_srednie_opoznienie_90d",
    ),
    "relacja": (
        "zgl_90d",
        "zgl_365d",
        "zgl_otwarte_na_migawke",
        "ocena_srednia_365d",
        "ocena_min_365d",
        "ocena_liczba_365d",
        "ankieta_ostatni_wynik",
        "ankieta_dni_od_odpowiedzi",
        "ankieta_brak_wyniku",
        "ankiety_bez_odpowiedzi_365d",
        "portal_miesiace_3m",
        "portal_logowania_3m",
        "portal_odslony_oferty_3m",
    ),
    "budynek": ("liczba_wind", "windy_awarie_90d", "windy_awarie_90d_na_winde"),
}
KOLUMNY_CECH = tuple(k for rodzina in RODZINY for k in CECHY_RODZIN[rodzina])
sprawdz_brak_wykluczonych(KOLUMNY_CECH, "KOLUMNY_CECH")
KATEGORIE = ("linia",)


def sql_rodziny(rodzina: str) -> str:
    sql = (KATALOG_SQL / f"{rodzina}.sql").read_text(encoding="utf-8").strip().rstrip(";")
    zakazane = zakazane_w_sql(sql)
    if zakazane:
        raise ValueError(f"sql/{rodzina}.sql czyta pola zakazane: {', '.join(zakazane)}")
    return sql


def zbuduj_cechy(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Wszystkie rodziny złączone po id_umowy (wymaga tabeli migawki_najemcy); liczby jako float64 (brak = NaN)."""
    czesci = [con.execute(sql_rodziny(r)).df().set_index("id_umowy") for r in RODZINY]
    cechy = pd.concat(czesci, axis=1, join="outer")
    sprawdz_brak_wykluczonych(cechy.columns, "zbuduj_cechy")
    if not cechy.index.is_unique:
        raise ValueError("Cechy najemców: id_umowy nie jest unikalne")
    liczbowe = [k for k in cechy.columns if k not in KATEGORIE and k != "podobne_poziom"]
    cechy[liczbowe] = cechy[liczbowe].astype("float64")
    return cechy.reset_index()


def zbuduj_tabele_cech(con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje (od nowa) tabelę cechy_najemcy; zwraca liczbę wierszy."""
    cechy = zbuduj_cechy(con)
    con.register("cechy_df", cechy)
    try:
        con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS SELECT * FROM cechy_df")
    finally:
        con.unregister("cechy_df")
    return len(cechy)


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_tabele_cech(polaczenie_bazy):,} wierszy".replace(",", " "))
