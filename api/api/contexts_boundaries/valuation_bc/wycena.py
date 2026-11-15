"""Wycena lokali (valuation_bc): cechy punktu na dzień wyceny, wycena z przedziałem albo odmowa, czynniki w PLN.

Używana przez API (`POST /valuation`, main.py) i zadanie nocne (nocne.py). Model: obecna wersja z current.yaml
(api.ai.valuation_model.obecny), przez kontrakt base.ModelWyceny: `predict_interval` (p10, p50, p90, odmowa, powod)
i `explain` (wkłady SHAP do ln wyceny: kolumny `wklad_<cecha>` i `wklad_bazowy`).

Czynniki w PLN: SHAP LightGBM sumuje się do ln(P50) = ln(B) + Σ φ_i, gdzie B = exp(wklad_bazowy) to wycena
„przeciętnego” lokalu z treningu. Każdy wkład mnożymy przez średnią logarytmiczną L = (P50 − B) / (ln P50 − ln B), więc
Σ czynników = P50 − B dokładnie, znak każdego czynnika zostaje, a skala nie rośnie, gdy wkłady się znoszą.
"""

import math
import uuid

import duckdb
import numpy as np
import pandas as pd
from api.ai.features.wycena.geo import KOLUMNY_GEO, cechy_geo
from api.ai.features.wycena.sasiedztwo import KOLUMNY_SASIEDZTWA, cechy_sasiedztwa_punktow
from api.ai.valuation_model.base import ModelWyceny
from api.ai.valuation_model.versions.v3_przedzialy.ood import OPISY_CECH as OPISY_CECH_OOD

OPISY_CECH = {
    "miasto": "miasto",
    "dzielnica": "dzielnica",
    **OPISY_CECH_OOD,
    "geohash6": "kwadrat mapy (geohash)",
    "llm_standard": "standard wykończenia (z opisu)",
    "llm_ekspozycja": "ekspozycja okien (z opisu)",
    "llm_widok": "widok z okien (z opisu)",
    "llm_balkon": "balkon (z opisu)",
    "llm_stan_budynku": "stan budynku (z opisu)",
}
KOLUMNY_PUNKTU = ("id", "miasto", "dzielnica", "lat", "lon", "dzien_wyceny")


def czynniki_pln(wklady: dict[str, float], ln_bazowa: float, p50: float) -> dict[str, float]:
    """Wkłady SHAP do ln(wyceny) przeliczone na PLN (średnia logarytmiczna, suma = P50 − B)."""
    bazowa = math.exp(ln_bazowa)
    roznica_ln = math.log(p50) - ln_bazowa
    srednia_log = p50 if abs(roznica_ln) < 1e-12 else (p50 - bazowa) / roznica_ln
    return {k: float(v) * srednia_log for k, v in wklady.items()}


def najwazniejsze(czynniki: dict[str, float], n: int = 3) -> list[tuple[str, float]]:
    return sorted(czynniki.items(), key=lambda kv: abs(kv[1]), reverse=True)[:n]


def cechy_punktow(con: duckdb.DuckDBPyConnection, punkty: pd.DataFrame) -> pd.DataFrame:
    """Punkty (KOLUMNY_PUNKTU + cechy lokalu) + cechy otoczenia (geo.sql) i sąsiedztwa na `dzien_wyceny`.

    Sąsiedztwo: tylko transakcje RCN opublikowane przed dniem wyceny (sasiedztwo_punktow.sql).
    """
    brak = [k for k in KOLUMNY_PUNKTU if k not in punkty.columns]
    if brak:
        raise ValueError(f"Brak kolumn punktów: {', '.join(brak)}")
    if punkty["id"].duplicated().any():
        raise ValueError("Powtórzone id punktu")
    widok = f"_punkty_{uuid.uuid4().hex}"
    con.register(widok, punkty[list(KOLUMNY_PUNKTU)])
    try:
        geo = cechy_geo(con, f"SELECT id AS id_transakcji, miasto, dzielnica, lat, lon FROM {widok}")
        sas = cechy_sasiedztwa_punktow(con, f"SELECT id AS id_transakcji, miasto, lat, lon, dzien_wyceny FROM {widok}")
    finally:
        con.unregister(widok)
    cechy = geo[["id_transakcji", *KOLUMNY_GEO]].merge(
        sas[["id_transakcji", *KOLUMNY_SASIEDZTWA]], on="id_transakcji", how="left", validate="one_to_one"
    )
    wynik = punkty.merge(cechy.rename(columns={"id_transakcji": "id"}), on="id", how="left", validate="one_to_one")
    wynik["sasiedzi_liczba"] = wynik["sasiedzi_liczba"].fillna(0)
    return wynik


def wycen(model: ModelWyceny, X: pd.DataFrame) -> pd.DataFrame:
    """p10, p50, p90, odmowa, powod, wartosc_bazowa (B w PLN) i czynniki (cecha -> PLN; {} przy odmowie)."""
    p = model.predict_interval(X)
    if "odmowa" not in p.columns:
        p = p.assign(odmowa=False, powod="")
    wyj = p[["p10", "p50", "p90", "odmowa", "powod"]].copy()
    wyj["wartosc_bazowa"] = np.nan
    wyj["czynniki"] = [{} for _ in range(len(wyj))]
    przyjete = ~wyj["odmowa"].to_numpy(dtype=bool)
    if not przyjete.any():
        return wyj
    e = model.explain(X[przyjete])
    if "wklad_bazowy" not in e.columns:
        return wyj
    kolumny = [k for k in e.columns if k.startswith("wklad_") and k != "wklad_bazowy"]
    for idx, w in e.iterrows():
        wklady = {k.removeprefix("wklad_"): w[k] for k in kolumny}
        wyj.at[idx, "czynniki"] = czynniki_pln(wklady, ln_bazowa=w["wklad_bazowy"], p50=wyj.at[idx, "p50"])
        wyj.at[idx, "wartosc_bazowa"] = math.exp(w["wklad_bazowy"])
    return wyj
