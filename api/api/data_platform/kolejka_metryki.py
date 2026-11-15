"""Liczby do docs/kolejka_metryki.md: wartość wyjściowa przychodu na godzinę doradcy i jego zmienność tygodniowa.

Czyta wyłącznie modele dbt ze schematu `metryki` (te same, których użyje eksperyment), więc najpierw:
`pypyr baza` (buduje bazę, leady_cel i modele dbt) albo `python -m api.data_platform.dbt_uruchom build`.

Użycie: `cd api && poetry run python -m api.data_platform.kolejka_metryki`
Wynik: api/api/data_platform/wyniki/kolejka_metryki.json i przychod_tygodnie.parquet.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

KATALOG_WYNIKOW = Path(__file__).resolve().with_name("wyniki")
KWARTAL_WYJSCIOWY = "2026-04-01"  # 2026-Q2
OKRES_ZMIENNOSCI = ("2025-07-01", "2026-06-30")
LOSOWANIA_BOOTSTRAP = 2000
ZIARNO = 20261115

# Q1. Wartość wyjściowa: wiersz kwartału 2026-Q2.
SQL_KWARTAL = """
SELECT *
FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'kwartal' AND poczatek_okresu = DATE '{kwartal}'
"""

# Q2. Kwartały 2025-Q3 – 2026-Q2 (kontekst dla wartości wyjściowej).
SQL_KWARTALY = """
SELECT poczatek_okresu, koniec_okresu, liczba_doradcow, godziny_doradcow, podpisania_z_zapytan, lokale_z_zapytan,
       wartosc_umow_z_zapytan, przychod_na_godzine_doradcy, przychod_na_godzine_nowe_wszystkie
FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'kwartal' AND poczatek_okresu >= DATE '{od}' AND koniec_okresu <= DATE '{do}'
ORDER BY poczatek_okresu
"""

# Q3. Pełne tygodnie (pon.–niedz.) w całości w okresie zmienności.
SQL_TYGODNIE = """
SELECT poczatek_okresu, koniec_okresu, dni_pracy, liczba_doradcow, godziny_doradcow, podpisania_z_zapytan,
       lokale_z_zapytan, wartosc_umow_z_zapytan, przychod_na_godzine_doradcy,
       wartosc_umow_nowe_wszystkie, przychod_na_godzine_nowe_wszystkie
FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'tydzien' AND pelny_okres
  AND poczatek_okresu >= DATE '{od}' AND koniec_okresu <= DATE '{do}'
ORDER BY poczatek_okresu
"""

# Q4. Wartość 2026-Q2 według wzoru na umowie głównej (kontrola definicji wartosc_umowy dla umów ramowych).
SQL_WZOR = """
SELECT count(*) AS podpisania,
       count(*) FILTER (WHERE liczba_lokali > 1) AS ramowe,
       count(*) FILTER (WHERE liczba_lokali > 1 AND czynsz_mies_razem <> czynsz * liczba_lokali) AS ramowe_rozny_czynsz,
       sum(wartosc_umowy) AS wartosc_umowy,
       sum(wartosc_wg_wzoru) AS wartosc_wg_wzoru
FROM metryki.wartosc_umowy
WHERE z_zapytania AND data_podpisania BETWEEN DATE '{kwartal}' AND DATE '{kwartal}' + INTERVAL 3 MONTH - INTERVAL 1 DAY
"""


def statystyki_tygodni(wartosci: pd.Series | np.ndarray | list[float]) -> dict[str, float]:
    """Średnia, odchylenie standardowe z próby (n − 1) i odchylenie w % średniej dla serii tygodniowej."""
    x = np.asarray(wartosci, dtype=float)
    if x.size < 2:
        raise ValueError("Potrzeba co najmniej dwóch tygodni")
    srednia = float(x.mean())
    odchylenie = float(x.std(ddof=1))
    return {
        "tygodnie": int(x.size),
        "srednia": srednia,
        "odchylenie_std": odchylenie,
        "odchylenie_proc_sredniej": 100.0 * odchylenie / srednia,
        "mediana": float(np.median(x)),
        "min": float(x.min()),
        "max": float(x.max()),
        "autokorelacja_lag1": float(np.corrcoef(x[:-1], x[1:])[0, 1]),
    }


def bootstrap_odchylenia_proc(wartosci, losowania: int = LOSOWANIA_BOOTSTRAP, ziarno: int = ZIARNO) -> list[float]:
    """95% przedział (percentyle) odchylenia w % średniej z losowania tygodni ze zwracaniem."""
    x = np.asarray(wartosci, dtype=float)
    rng = np.random.default_rng(ziarno)
    proby = rng.choice(x, size=(losowania, x.size), replace=True)
    cv = 100.0 * proby.std(axis=1, ddof=1) / proby.mean(axis=1)
    return [float(np.percentile(cv, 2.5)), float(np.percentile(cv, 97.5))]


def _rekordy(df: pd.DataFrame) -> list[dict]:
    wynik = []
    for rekord in df.to_dict(orient="records"):
        wynik.append({k: (str(v.date()) if isinstance(v, pd.Timestamp) else v) for k, v in rekord.items()})
    return wynik


def policz(con) -> dict:
    od, do = OKRES_ZMIENNOSCI
    kwartal = con.execute(SQL_KWARTAL.format(kwartal=KWARTAL_WYJSCIOWY)).df()
    if len(kwartal) != 1:
        raise RuntimeError("Brak kwartału 2026-Q2 w metryki.przychod_na_godzine_doradcy: uruchom dbt build")
    kwartaly = con.execute(SQL_KWARTALY.format(od=od, do=do)).df()
    tygodnie = con.execute(SQL_TYGODNIE.format(od=od, do=do)).df()
    wzor = con.execute(SQL_WZOR.format(kwartal=KWARTAL_WYJSCIOWY)).df()

    zmiennosc = {}
    for nazwa, kolumna in [
        ("przychod_na_godzine_doradcy", "przychod_na_godzine_doradcy"),
        ("przychod_na_godzine_nowe_wszystkie", "przychod_na_godzine_nowe_wszystkie"),
        ("wartosc_umow_z_zapytan", "wartosc_umow_z_zapytan"),
        ("godziny_doradcow", "godziny_doradcow"),
    ]:
        s = statystyki_tygodni(tygodnie[kolumna])
        s["odchylenie_proc_95ci"] = bootstrap_odchylenia_proc(tygodnie[kolumna])
        zmiennosc[nazwa] = s

    q2 = tygodnie[tygodnie["poczatek_okresu"] >= pd.Timestamp(KWARTAL_WYJSCIOWY)]
    zmiennosc_q2 = statystyki_tygodni(q2["przychod_na_godzine_doradcy"])

    wynik = {
        "kwartal_wyjsciowy": _rekordy(kwartal)[0],
        "kwartaly": _rekordy(kwartaly),
        "okres_zmiennosci": {
            "od": od,
            "do": do,
            "pierwszy_tydzien": str(tygodnie["poczatek_okresu"].min().date()),
            "ostatni_tydzien": str(tygodnie["poczatek_okresu"].max().date()),
        },
        "zmiennosc_tygodniowa": zmiennosc,
        "zmiennosc_tygodniowa_2026q2": zmiennosc_q2,
        "kontrola_wzoru_2026q2": _rekordy(wzor)[0],
    }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    tygodnie.to_parquet(KATALOG_WYNIKOW / "przychod_tygodnie.parquet", index=False)
    (KATALOG_WYNIKOW / "kolejka_metryki.json").write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2, default=_json_domyslnie), encoding="utf-8"
    )
    return wynik


def _json_domyslnie(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if math.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return str(v)


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie() as polaczenie_bazy:
        print(json.dumps(policz(polaczenie_bazy), ensure_ascii=False, indent=2, default=_json_domyslnie))
