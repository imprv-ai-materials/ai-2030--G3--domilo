"""Wyjaśnienie ryzyka windy: najsilniejsze sygnały i podejrzane podzespoły (GET /lifts/{id}/risk, zgłoszenie).

Źródło: `explain` aktywnej wersji modelu (failure_model/current.yaml): wkład każdej cechy w log-szansę (SHAP z LightGBM,
kolumny `wklad_<cecha>`). Cechy grupujemy w sygnały (`sygnal_cechy`):
- cechy ręczne `<sygnał>_<statystyka>` (features/windy/katalog.yaml, `cechy_reczne.sygnaly`);
- cechy tsfresh `ts_<sygnał tsfresh>_<statystyka>` -> sygnał ręczny o tym samym źródle (TSFRESH_NA_SYGNAL);
- `firmware_*` -> `sterownik_firmware`, `ma_czujnik_wibracji` -> `wibracje_czujnik`.
Wkład sygnału = suma wkładów jego cech. Najsilniejsze sygnały = `LICZBA_SYGNALOW` sygnałów o największym dodatnim
wkładzie (podnoszą ryzyko), z cechą o największym wkładzie i jej wartością.
Podejrzane podzespoły: podzespoły sygnałów z dodatnim wkładem (podzespoly_sygnalow.yaml — założenie do potwierdzenia),
waga podzespołu = suma wkładów jego sygnałów (sygnał z dwoma podzespołami daje pełny wkład każdemu), malejąco.
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from api.ai.features.windy.cechy import nazwy_cech

PLIK_PODZESPOLOW = Path(__file__).with_name("podzespoly_sygnalow.yaml")
PLIK_KATALOGU = Path(__file__).resolve().parents[2] / "ai" / "features" / "windy" / "katalog.yaml"
LICZBA_SYGNALOW = 3
TSFRESH_NA_SYGNAL = {
    "drzwi_czas_zamykania": "drzwi_czas_zamykania_sr",
    "naped_prad": "naped_prad_sr",
    "wibracje_rms": "wibracje_rms",
}
DODATKOWE_NA_SYGNAL = {
    "ma_czujnik_wibracji": "wibracje_czujnik",
    "firmware_dni_od_zmiany": "sterownik_firmware",
    "firmware_zmiana_glowna_44d": "sterownik_firmware",
}
OPISY_DODATKOWYCH = {
    "wibracje_czujnik": {"rodzina": "wibracje", "zrodlo": "serwis_windy.czujnik_wibracji_od", "jednostka": "0/1"},
    "sterownik_firmware": {"rodzina": "sterownik", "zrodlo": "firmware (zmiany wersji)", "jednostka": "dni / 0–1"},
}


@lru_cache(maxsize=1)
def katalog_sygnalow() -> dict[str, dict]:
    """Sygnał -> {rodzina, zrodlo, jednostka} z katalogu cech wind (+ sygnały cech dodatkowych)."""
    katalog = yaml.safe_load(PLIK_KATALOGU.read_text(encoding="utf-8"))
    sygnaly = {k: dict(v) for k, v in katalog["cechy_reczne"]["sygnaly"].items()}
    return {**sygnaly, **OPISY_DODATKOWYCH}


@lru_cache(maxsize=1)
def podzespoly_sygnalow() -> dict[str, list[str]]:
    return {k: list(v or []) for k, v in yaml.safe_load(PLIK_PODZESPOLOW.read_text(encoding="utf-8")).items()}


def sygnal_cechy(cecha: str) -> str:
    """Nazwa sygnału, z którego pochodzi cecha modelu; ValueError dla cechy spoza katalogu."""
    if cecha in DODATKOWE_NA_SYGNAL:
        return DODATKOWE_NA_SYGNAL[cecha]
    if cecha.startswith("ts_"):
        for s_ts, s in TSFRESH_NA_SYGNAL.items():
            if cecha.startswith(f"ts_{s_ts}_"):
                return s
    for s in katalog_sygnalow():
        if cecha in nazwy_cech(s):
            return s
    raise ValueError(f"Cecha {cecha} nie należy do żadnego sygnału z katalogu cech wind")


def wyjasnij(cechy_wiersza: pd.Series, wklady: pd.Series, n: int = LICZBA_SYGNALOW) -> dict:
    """cechy_wiersza: wartości cech jednej windy; wklady: `wklad_<cecha>` z explain (log-szansa).
    Zwraca {"sygnaly": [...najwyżej n], "podzespoly": [...]} (opis w docstringu modułu)."""
    w = pd.Series({k.removeprefix("wklad_"): float(v) for k, v in wklady.items() if k != "wklad_staly"})
    df = pd.DataFrame({"cecha": w.index, "wklad": w.to_numpy()})
    df["sygnal"] = df["cecha"].map(sygnal_cechy)
    suma = df.groupby("sygnal")["wklad"].sum()
    dodatnie = suma[suma > 0].sort_values(ascending=False, kind="mergesort")
    opisy = katalog_sygnalow()
    sygnaly = []
    for s, wklad in dodatnie.head(n).items():
        cechy_s = df[df["sygnal"] == s].sort_values("wklad", ascending=False, kind="mergesort")
        cecha = str(cechy_s["cecha"].iloc[0])
        wartosc = cechy_wiersza.get(cecha)
        sygnaly.append(
            {
                "sygnal": s,
                "rodzina": opisy[s]["rodzina"],
                "zrodlo": str(opisy[s].get("zrodlo")),
                "jednostka": str(opisy[s].get("jednostka")),
                "wklad": round(float(wklad), 4),
                "cecha": cecha,
                "wartosc": None if wartosc is None or pd.isna(wartosc) else round(float(wartosc), 4),
                "podzespoly": podzespoly_sygnalow().get(s, []),
            }
        )
    wagi: dict[str, float] = {}
    zrodla: dict[str, list[str]] = {}
    for s, wklad in dodatnie.items():
        for p in podzespoly_sygnalow().get(s, []):
            wagi[p] = wagi.get(p, 0.0) + float(wklad)
            zrodla.setdefault(p, []).append(s)
    podzespoly = [
        {"podzespol": p, "wklad": round(v, 4), "sygnaly": zrodla[p]}
        for p, v in sorted(wagi.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {"sygnaly": sygnaly, "podzespoly": podzespoly}


def wyjasnij_ramke(cechy: pd.DataFrame, wyjasnienie: pd.DataFrame, n: int = LICZBA_SYGNALOW) -> list[dict]:
    """`wyjasnij` dla każdego wiersza (indeksy cechy i wyjasnienie z explain muszą się zgadzać)."""
    wklady = wyjasnienie[[k for k in wyjasnienie.columns if k.startswith("wklad_")]]
    return [wyjasnij(cechy.loc[i], wklady.loc[i], n) for i in cechy.index]


def podzespoly_z_wkladow(wklady: np.ndarray, cechy_modelu: list[str]) -> list[list[str]]:
    """Lista podejrzanych podzespołów (same nazwy, malejąco) dla macierzy wkładów [wiersze × cechy] (ewaluacja)."""
    sygnaly = pd.Series([sygnal_cechy(c) for c in cechy_modelu])
    po_sygnale = pd.DataFrame(wklady[:, : len(cechy_modelu)], columns=cechy_modelu).T.groupby(sygnaly.to_numpy()).sum()
    mapa = podzespoly_sygnalow()
    wyniki = []
    for kol in po_sygnale.columns:
        s = po_sygnale[kol]
        wagi: dict[str, float] = {}
        for sygnal, v in s[s > 0].items():
            for p in mapa.get(sygnal, []):
                wagi[p] = wagi.get(p, 0.0) + float(v)
        wyniki.append([p for p, _ in sorted(wagi.items(), key=lambda kv: (-kv[1], kv[0]))])
    return wyniki
