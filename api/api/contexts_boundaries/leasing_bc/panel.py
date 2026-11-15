"""Odczyty panelu kierownika zespołu najmu (GET /team/dashboard) z modeli dbt w schemacie `metryki`.

Wszystkie metryki liczą modele dbt (api/api/data_platform/dbt/models/panel, docs/kolejka_panel.md); tu tylko je
czytamy i sumujemy dla całego okresu (sumy liczników, nie średnie z tygodni). Mediana czasu do kontaktu dla okresu
jest liczona na zapytaniach, nie z median tygodniowych.
"""

import math
from datetime import date

import duckdb
import pandas as pd
from api.contexts_boundaries.leasing_bc.pominiecia import POWODY_POMINIECIA

PRZYCHOD_OD = date(2025, 7, 1)  # okres zmienności tygodniowej z docs/kolejka_metryki.md

SQL_PRZYCHOD = """
SELECT tydzien, koniec_tygodnia, pelny_tydzien_przychodu, podpisania_z_zapytan, godziny_doradcow,
       wartosc_umow_z_zapytan, przychod_na_godzine_doradcy
FROM metryki.panel_tydzien
WHERE przychod_na_godzine_doradcy IS NOT NULL AND tydzien >= $od
ORDER BY tydzien
"""
SQL_WYJSCIOWA = """
SELECT poczatek_okresu, koniec_okresu, przychod_na_godzine_doradcy, wartosc_umow_z_zapytan, godziny_doradcow
FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'kwartal' AND poczatek_okresu = DATE '2026-04-01'
"""
SQL_TYGODNIE_KOLEJKI = """
SELECT * EXCLUDE (pelny_tydzien_przychodu, podpisania_z_zapytan, godziny_doradcow, wartosc_umow_z_zapytan,
                 przychod_wartosc_wyjsciowa)
FROM metryki.panel_tydzien
WHERE zrodlo_kolejki IS NOT NULL
ORDER BY tydzien
"""
SQL_OKRES_ADOPCJA = """
SELECT zrodlo_kolejki, min(data_kolejki) AS od, max(data_kolejki) AS do, count(DISTINCT data_kolejki) AS dni,
       count(DISTINCT data_kolejki) FILTER (WHERE dane_kontaktow) AS dni_z_kontaktami,
       sum(pierwsze_kontakty) AS pierwsze_kontakty, sum(z_top) AS z_top, sum(poza_rankingiem) AS poza_rankingiem,
       sum(z_top) / nullif(sum(pierwsze_kontakty), 0) AS adopcja,
       sum(adopcja_losowa * pierwsze_kontakty) / nullif(sum(pierwsze_kontakty), 0) AS adopcja_losowa
FROM metryki.adopcja_dzien
GROUP BY zrodlo_kolejki
ORDER BY zrodlo_kolejki
"""
# Przychód w pełnych tygodniach z kolejką danego źródła: Σ wartość umów / Σ godziny (jak kwartał w dbt).
SQL_OKRES_PRZYCHOD = """
WITH t AS (
    SELECT unnest(string_split(zrodlo_kolejki, ',')) AS zrodlo_kolejki, tydzien, wartosc_umow_z_zapytan,
           godziny_doradcow
    FROM metryki.panel_tydzien
    WHERE zrodlo_kolejki IS NOT NULL AND pelny_tydzien_przychodu
)
SELECT zrodlo_kolejki, min(tydzien) AS od, max(tydzien) AS do, count(*) AS tygodnie,
       sum(wartosc_umow_z_zapytan) AS wartosc_umow_z_zapytan, sum(godziny_doradcow) AS godziny_doradcow,
       sum(wartosc_umow_z_zapytan) / nullif(sum(godziny_doradcow), 0) AS przychod_na_godzine_doradcy
FROM t
GROUP BY zrodlo_kolejki
ORDER BY zrodlo_kolejki
"""
SQL_OKRES_DECYL = """
SELECT zrodlo_kolejki, gorny_decyl, count(*) AS zapytania, sum(umowa_45d) AS umowy, avg(umowa_45d) AS konwersja,
       median(godz_do_pierwszego_kontaktu) FILTER (WHERE obsluzony) AS mediana_godz_kontaktu,
       avg(CASE WHEN obsluzony THEN 0.0 ELSE 1.0 END) AS bez_kontaktu
FROM metryki.kolejka_zapytania
WHERE nowe AND NOT cenzurowany
GROUP BY ALL
ORDER BY ALL
"""
SQL_DORADCY = """
SELECT zrodlo_kolejki, id_doradcy, any_value(miasto) AS miasto, count(*) FILTER (WHERE dane_kontaktow) AS dni,
       sum(pierwsze_kontakty) AS pierwsze_kontakty, sum(z_top) AS z_top,
       sum(z_top) / nullif(sum(pierwsze_kontakty), 0) AS adopcja,
       sum(adopcja_losowa * pierwsze_kontakty) / nullif(sum(pierwsze_kontakty), 0) AS adopcja_losowa
FROM metryki.adopcja_dzien
GROUP BY ALL
ORDER BY zrodlo_kolejki, miasto, id_doradcy
"""
SQL_POMINIECIA_POWODY = """
SELECT powod, count(*) AS pominiecia, count(*) FILTER (WHERE gorny_decyl) AS w_gornym_decylu
FROM metryki.pominiecia
GROUP BY powod
"""
SQL_POMINIECIA_OSTATNIE = """
SELECT data_kolejki, id_doradcy, miasto, pozycja, id_leada, powod, komentarz, zgloszono, zmieniono, ev_pln
FROM metryki.pominiecia
ORDER BY zmieniono DESC, data_kolejki DESC, id_leada
LIMIT $limit
"""


def _czyste(v):
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat() if v.tzinfo else v.date().isoformat()
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy
        v = v.item()
        return None if isinstance(v, float) and math.isnan(v) else v
    return v


def _rekordy(df: pd.DataFrame) -> list[dict]:
    return [{k: _czyste(v) for k, v in r.items()} for r in df.to_dict("records")]


def dane_panelu(con: duckdb.DuckDBPyConnection, przychod_od: date = PRZYCHOD_OD, limit_pominiec: int = 50) -> dict:
    wyjsciowa = _rekordy(con.execute(SQL_WYJSCIOWA).df())
    powody = {r["powod"]: r for r in _rekordy(con.execute(SQL_POMINIECIA_POWODY).df())}
    decyl = _rekordy(con.execute(SQL_OKRES_DECYL).df())
    return {
        "przychod": {
            "wartosc_wyjsciowa": wyjsciowa[0] if wyjsciowa else None,
            "tygodnie": _rekordy(con.execute(SQL_PRZYCHOD, {"od": przychod_od}).df()),
        },
        "tygodnie": _rekordy(con.execute(SQL_TYGODNIE_KOLEJKI).df()),
        "okresy": {
            "adopcja": _rekordy(con.execute(SQL_OKRES_ADOPCJA).df()),
            "decyl": decyl,
            "przychod": _rekordy(con.execute(SQL_OKRES_PRZYCHOD).df()),
        },
        "doradcy": _rekordy(con.execute(SQL_DORADCY).df()),
        "pominiecia": {
            "powody": [
                {
                    "powod": k,
                    "opis": opis,
                    "pominiecia": int(powody.get(k, {}).get("pominiecia") or 0),
                    "w_gornym_decylu": int(powody.get(k, {}).get("w_gornym_decylu") or 0),
                }
                for k, opis in POWODY_POMINIECIA.items()
            ],
            "ostatnie": _rekordy(con.execute(SQL_POMINIECIA_OSTATNIE, {"limit": limit_pominiec}).df()),
        },
    }
