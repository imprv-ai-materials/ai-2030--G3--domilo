"""Cechy tsfresh z 7-dniowych przebiegów godzinowych: tabela cechy_windy_tsfresh i selekcja na treningu.

Przebieg = 168 godzinnych średnich sygnału przed chwilą odcięcia (05:50 Europe/Warsaw dnia oceny), z okien 10-min
bez `tryb = 'serwis'` (te same godziny co w cechy.py: kończące się o :50 UTC). Sygnały (SYGNALY): średni czas
zamykania drzwi, średni prąd silnika, wibracje RMS (przed montażem czujnika NULL, jak w sql/wibracje.sql).
Puste godziny (np. noc bez jazd) uzupełnia interpolacja liniowa wzdłuż czasu (na brzegach najbliższa wartość);
przebieg z mniej niż MIN_GODZIN godzinami z wartością pomijamy (cechy NULL).

Cechy tsfresh 0.21 (extract_features, FC_PARAMETERS): root_mean_square (RMS), kurtosis, abs_energy (energia)
i fft_coefficient (|A_k|, k = 1 … 84). Z |A_k|² liczymy udział pasm w energii widma bez składowej stałej (PASMA):
k = liczba cykli na 168 h, więc k = 7 to rytm dobowy (24 h).
Selekcja (wybierz_cechy): tsfresh calculate_relevance_table (Mann-Whitney + Benjamini-Yekutieli, fdr 0,05) tylko na
wierszach treningowych (dzien 2023-03-01 – 2025-06-30), osobno dla cech wibracji (wiersze z czujnikiem) i reszty.
Opis cech: katalog.yaml; porównanie modeli: failure_model/evals/tsfresh_porownanie.py, docs/b4_tsfresh.md.
Budowa: `cd api && python -m api.ai.features.windy.tsfresh_cechy` (po cechy_windy; kilka–kilkanaście minut).
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

TABELA = "cechy_windy_tsfresh"
PLIK_WYBRANYCH = Path(__file__).with_name("tsfresh_wybrane.yaml")
GODZIN = 168
MIN_GODZIN = 84
# nazwa sygnału -> wyrażenie na oknie 10-min telemetrii (t = telemetria, w = serwis_windy)
SYGNALY = {
    "drzwi_czas_zamykania": "t.czas_zamykania_drzwi_sr_s",
    "naped_prad": "t.prad_silnika_sr_a",
    "wibracje_rms": (
        "CASE WHEN t.ts_utc >= timezone('Europe/Warsaw', w.czujnik_wibracji_od) THEN t.wibracje_rms_mg END"
    ),
}
# pasmo -> (k_od, k_do) włącznie; okres = 168 h / k
PASMA = {
    "dlugie": (1, 6),  # 168–28 h: zmiany w ciągu tygodnia
    "doba": (7, 7),  # 24 h
    "pol_doby": (8, 14),  # 21–12 h
    "krotkie": (15, 84),  # 11,2–2 h
}
FC_PARAMETERS = {
    "root_mean_square": None,
    "kurtosis": None,
    "abs_energy": None,
    "fft_coefficient": [{"coeff": k, "attr": "abs"} for k in range(1, GODZIN // 2 + 1)],
}
TRENING = ("2023-03-01", "2025-06-30")
FDR = 0.05
WIERSZY_W_PORCJI = 20_000


def nazwy_cech() -> list[str]:
    return [f"ts_{s}_{c}" for s in SYGNALY for c in ("rms", "kurtoza", "energia", *(f"fft_{p}" for p in PASMA))]


def przygotuj(con: duckdb.DuckDBPyConnection, bez_serwisu: bool = True) -> int:
    """Tabele tymczasowe: `ts_godziny` (winda × godzina, średnie sygnałów) i `ts_wiersze` (dni_wind z numerem).
    bez_serwisu=False zostawia okna serwisowe (tylko do porównania, failure_model/evals/tryb_serwisowy.py)."""
    from api.ai.features.windy.cechy import filtr_serwisu

    sygnaly = ",\n            ".join(f"avg({wyr}) AS {s}" for s, wyr in SYGNALY.items())
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ts_godziny AS
        SELECT
            t.id_windy,
            CAST(floor((epoch(t.ts_utc) + 540) / 3600) * 3600 + 3000 AS BIGINT) AS koniec_godziny,
            {sygnaly}
        FROM telemetra_windy AS t
        JOIN serwis_windy AS w USING (id_windy)
        WHERE {filtr_serwisu(bez_serwisu, "t.")}
        GROUP BY ALL
        """)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE ts_wiersze AS
        SELECT
            row_number() OVER (ORDER BY dzien, id_windy) - 1 AS nr,
            id_windy,
            dzien,
            CAST(epoch(timezone('Europe/Warsaw', dzien + INTERVAL '05:50')) AS BIGINT) AS odciecie_s
        FROM dni_wind
        """)
    return con.execute("SELECT count(*) FROM ts_wiersze").fetchone()[0]


def przebiegi(con: duckdb.DuckDBPyConnection, od: int, do: int) -> dict[str, np.ndarray]:
    """Macierze [wiersze od…do−1, 168] godzinnych średnich (NaN = brak), godzina 0 = najstarsza."""
    kolumny = ", ".join(f"g.{s}" for s in SYGNALY)
    df = con.execute(
        f"""
        SELECT r.nr, j.j, {kolumny}
        FROM ts_wiersze AS r
        CROSS JOIN range({GODZIN}) AS j(j)
        LEFT JOIN ts_godziny AS g
            ON g.id_windy = r.id_windy
           AND g.koniec_godziny = r.odciecie_s - 3600 * ({GODZIN - 1} - j.j)
        WHERE r.nr >= ? AND r.nr < ?
        ORDER BY r.nr, j.j
        """,
        [od, do],
    ).df()
    return {s: df[s].to_numpy(dtype="float64").reshape(do - od, GODZIN) for s in SYGNALY}


def uzupelnij(macierz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Interpolacja liniowa wzdłuż godzin; zwraca (macierz, maska wierszy z co najmniej MIN_GODZIN wartościami)."""
    ok = np.isfinite(macierz).sum(axis=1) >= MIN_GODZIN
    wynik = pd.DataFrame(macierz[ok]).interpolate(axis=1, limit_direction="both").to_numpy()
    return wynik, ok


def dlugi_format(macierze: dict[str, np.ndarray], od: int) -> pd.DataFrame:
    """Format długi tsfresh: id (nr wiersza), godzina, kind (sygnał), wartosc."""
    czesci = []
    for s, m in macierze.items():
        wartosci, ok = uzupelnij(m)
        if not ok.any():
            continue
        ids = np.flatnonzero(ok) + od
        czesci.append(
            pd.DataFrame(
                {
                    "id": np.repeat(ids, GODZIN),
                    "godzina": np.tile(np.arange(GODZIN), len(ids)),
                    "kind": s,
                    "wartosc": wartosci.ravel(),
                }
            )
        )
    return pd.concat(czesci, ignore_index=True)


def cechy_z_tsfresh(surowe: pd.DataFrame) -> pd.DataFrame:
    """Kolumny tsfresh (`<sygnał>__<cecha>`) -> cechy katalogu: RMS, kurtoza, energia, udziały pasm FFT."""
    wynik = pd.DataFrame(index=surowe.index)
    for s in SYGNALY:
        if f"{s}__root_mean_square" not in surowe:
            for c in ("rms", "kurtoza", "energia", *(f"fft_{p}" for p in PASMA)):
                wynik[f"ts_{s}_{c}"] = np.nan
            continue
        wynik[f"ts_{s}_rms"] = surowe[f"{s}__root_mean_square"]
        wynik[f"ts_{s}_kurtoza"] = surowe[f"{s}__kurtosis"]
        wynik[f"ts_{s}_energia"] = surowe[f"{s}__abs_energy"]
        moc = {k: surowe[f'{s}__fft_coefficient__attr_"abs"__coeff_{k}'] ** 2 for k in range(1, GODZIN // 2 + 1)}
        calosc = sum(moc.values())
        for p, (k_od, k_do) in PASMA.items():
            wynik[f"ts_{s}_fft_{p}"] = sum(moc[k] for k in range(k_od, k_do + 1)) / calosc.replace(0, np.nan)
    return wynik


def wyciagnij(dlugi: pd.DataFrame, n_jobs: int = 0) -> pd.DataFrame:
    from tsfresh import extract_features

    surowe = extract_features(
        dlugi,
        column_id="id",
        column_sort="godzina",
        column_kind="kind",
        column_value="wartosc",
        default_fc_parameters=FC_PARAMETERS,
        n_jobs=n_jobs,
        disable_progressbar=True,
    )
    return cechy_z_tsfresh(surowe)


def zbuduj_cechy_tsfresh(
    con: duckdb.DuckDBPyConnection,
    n_jobs: int = 0,
    porcja: int = WIERSZY_W_PORCJI,
    tabela: str = TABELA,
    bez_serwisu: bool = True,
) -> int:
    """Zapisuje (od nowa) tabelę cech tsfresh (domyślnie cechy_windy_tsfresh: id_windy, dzien + nazwy_cech());
    zwraca liczbę wierszy."""
    n = przygotuj(con, bez_serwisu=bez_serwisu)
    czesci = []
    for od in range(0, n, porcja):
        do = min(od + porcja, n)
        cechy = wyciagnij(dlugi_format(przebiegi(con, od, do), od), n_jobs=n_jobs)
        czesci.append(cechy.reindex(range(od, do)))
        print(f"{tabela}: {do:,} / {n:,}".replace(",", " "), file=sys.stderr)
    wszystkie = pd.concat(czesci)[nazwy_cech()].rename_axis("nr").reset_index()
    con.register("ts_cechy_df", wszystkie)
    try:
        con.execute(f"""
            CREATE OR REPLACE TABLE {tabela} AS
            SELECT r.id_windy, r.dzien, c.* EXCLUDE (nr)
            FROM ts_wiersze AS r
            JOIN ts_cechy_df AS c USING (nr)
            ORDER BY r.dzien, r.id_windy
            """)
    finally:
        con.unregister("ts_cechy_df")
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def wybierz_cechy(dane: pd.DataFrame, y: pd.Series, fdr: float = FDR) -> pd.DataFrame:
    """Tabela istotności tsfresh (calculate_relevance_table) dla cech nazwy_cech() na podanych wierszach.

    `dane` i `y` muszą być już ograniczone do treningu. tsfresh nie przyjmuje NaN, więc cechy liczymy w grupach
    wierszy bez braków: wibracje osobno (wiersze z czujnikiem), reszta razem; korekta FDR w każdej grupie osobno.
    """
    from tsfresh.feature_selection.relevance import calculate_relevance_table

    grupy = {
        "wibracje": [c for c in nazwy_cech() if c.startswith("ts_wibracje")],
        "pozostale": [c for c in nazwy_cech() if not c.startswith("ts_wibracje")],
    }
    tabele = []
    for grupa, kolumny in grupy.items():
        x = dane[kolumny].dropna()
        tabela = calculate_relevance_table(x, y.loc[x.index], ml_task="classification", fdr_level=fdr, n_jobs=0)
        tabele.append(tabela.assign(grupa=grupa, wiersze=len(x), dodatnie=int(y.loc[x.index].sum())))
    return pd.concat(tabele).reset_index(drop=True)


def zapisz_wybrane(tabela: pd.DataFrame, plik: Path = PLIK_WYBRANYCH) -> list[str]:
    wybrane = tabela.loc[tabela["relevant"], "feature"].tolist()
    tresc = {
        "opis": "Cechy tsfresh istotne na treningu (wygenerowane przez tsfresh_cechy.wybierz_cechy; nie edytuj).",
        "trening": {"od": TRENING[0], "do": TRENING[1]},
        "test": "calculate_relevance_table: Mann-Whitney, Benjamini-Yekutieli",
        "fdr": FDR,
        "wybrane": wybrane,
        "odrzucone": tabela.loc[~tabela["relevant"], "feature"].tolist(),
    }
    plik.write_text(yaml.safe_dump(tresc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return wybrane


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        print(f"{TABELA}: {zbuduj_cechy_tsfresh(polaczenie_bazy):,} wierszy".replace(",", " "))
