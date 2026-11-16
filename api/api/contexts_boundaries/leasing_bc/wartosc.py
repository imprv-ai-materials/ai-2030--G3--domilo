"""Wartość zapytania w kolejce (leasing_bc): EV = p × czynsz × czas najmu × liczba lokali.

- `p`: szansa na umowę po kontakcie (skalibrowany model kolejki, ai/lead_model/evals/kalibracja.md).
- czynsz: mediana czynszu katalogowego linii w mieście (`czynsz_mediana_pln` w zalozenia.yaml), PLN / mies. / lokal.
- czas najmu: `czas_najmu_mies`, miesiące; od 2026-11-16 B2C i B2B = RMST60 z krzywej Kaplana-Meiera, MID = średnia
  z zakończonych najmów (opis i źródło w YAML).
- liczba lokali: `crm_leady.liczba_lokali` (podawana tylko w zapytaniach B2B; brak = 1 lokal).
Linia i miasto to `linia_pref` i `miasto` z zapytania. Para bez lokali danej linii w mieście (Łódź/MID) bierze czynsz
i czas linii z `czynsz_mediana_pln.zastepstwo`.

Wartość podpisanej umowy (do oceny kolejki, `wartosc_umow`): Σ czynsz z umowy × czas najmu linii tego najmu, po
umowie z `leady_cel.id_umowy` i, gdy ma `id_umowy_ramowej`, po wszystkich umowach tej umowy ramowej (każda to jeden
lokal; `pms_umowy.liczba_lokali` = liczba umów w umowie ramowej). Ten sam czas najmu co w EV, więc EV i wartość umów
różnią się tylko p, czynszem (mediana vs czynsz z umowy) i liczbą lokali (deklarowana vs podpisana).
"""

import duckdb
import numpy as np
import pandas as pd
from api.contexts_boundaries.leasing_bc.zalozenia import wczytaj_zalozenia

SQL_UMOWY_ZAPYTAN = """
WITH z AS (
    SELECT c.id_leada, u.id_umowy, u.id_umowy_ramowej
    FROM leady_cel AS c JOIN pms_umowy AS u ON u.id_umowy = c.id_umowy
    WHERE list_contains(?, c.id_leada)
)
SELECT z.id_leada, u.id_umowy, u.id_umowy_ramowej, u.id_najmu, u.czynsz, u.data_podpisania, n.linia
FROM z
JOIN pms_umowy AS u
  ON u.id_umowy = z.id_umowy OR (z.id_umowy_ramowej IS NOT NULL AND u.id_umowy_ramowej = z.id_umowy_ramowej)
JOIN pms_najmy AS n ON n.id_najmu = u.id_najmu
ORDER BY z.id_leada, u.id_umowy
"""


def _linia_wyceny(miasto: str, linia: str, czynsz: dict) -> str:
    return czynsz.get("zastepstwo", {}).get(f"{miasto}/{linia}", linia)


def czynsz_i_czas(leady: pd.DataFrame, zalozenia: dict | None = None) -> pd.DataFrame:
    """Dla każdego zapytania: linia_wyceny, czynsz (PLN / mies. / lokal), czas_najmu_mies, lokale (indeks jak leady)."""
    z = zalozenia or wczytaj_zalozenia()
    czynsz, czas = z["czynsz_mediana_pln"], z["czas_najmu_mies"]["wartosc"]
    linie = [_linia_wyceny(m, li, czynsz) for m, li in zip(leady["miasto"], leady["linia_pref"])]
    stawki = [czynsz["wartosc"].get(m, {}).get(li) for m, li in zip(leady["miasto"], linie)]
    if any(s is None for s in stawki):
        brak = sorted({f"{m}/{li}" for m, li, s in zip(leady["miasto"], linie, stawki) if s is None})
        raise ValueError(f"Brak mediany czynszu (i zastępstwa) w zalozenia.yaml dla: {', '.join(brak)}")
    lokale = pd.to_numeric(leady["liczba_lokali"], errors="coerce").fillna(1).astype(float)
    return pd.DataFrame(
        {
            "linia_wyceny": linie,
            "czynsz": np.asarray(stawki, dtype=float),
            "czas_najmu_mies": [float(czas[li]) for li in linie],
            "lokale": lokale.to_numpy(),
        },
        index=leady.index,
    )


def wartosc_oczekiwana(p, leady: pd.DataFrame, zalozenia: dict | None = None) -> np.ndarray:
    """EV (PLN) = p × czynsz × czas najmu × liczba lokali, jedna wartość na zapytanie."""
    s = czynsz_i_czas(leady, zalozenia)
    return (
        np.asarray(p, dtype=float) * s["czynsz"].to_numpy() * s["czas_najmu_mies"].to_numpy() * s["lokale"].to_numpy()
    )


def umowy_zapytan(con: duckdb.DuckDBPyConnection, id_leadow) -> pd.DataFrame:
    """Umowy podpisane z zapytań (z całą umową ramową): id_leada, id_umowy, id_umowy_ramowej, czynsz, linia, …"""
    return con.execute(SQL_UMOWY_ZAPYTAN, [list(id_leadow)]).df()


def wartosc_umow(umowy: pd.DataFrame, zalozenia: dict | None = None) -> pd.DataFrame:
    """Z `umowy_zapytan`: id_leada, umowy (= lokale), wartosc_umow (PLN) = Σ czynsz × czas najmu linii najmu."""
    czas = (zalozenia or wczytaj_zalozenia())["czas_najmu_mies"]["wartosc"]
    w = umowy.assign(wartosc=umowy["czynsz"].astype(float) * umowy["linia"].map(lambda li: float(czas[li])))
    return w.groupby("id_leada").agg(umowy=("id_umowy", "size"), wartosc_umow=("wartosc", "sum")).reset_index()
