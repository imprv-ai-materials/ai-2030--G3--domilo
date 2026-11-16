"""Wyjaśnienie ryzyka windy: sygnały, podejrzane podzespoły i opis alertu (GET /lifts/{id}/risk, zgłoszenie).

Źródło: `explain` aktywnej wersji modelu (failure_model/current.yaml) w dniu oceny: wkład każdej cechy w log-szansę
awarii (SHAP z LightGBM, kolumny `wklad_<cecha>`).
- Podejrzane podzespoły: suma wkładów wszystkich cech przypisanych do podzespołu w podzespoly.yaml (`cechy`:
  cecha -> drzwi / naped / hamulec_liny / sterownik / null); na liście podzespoły z sumą > 0, od największej.
  Przy podzespole: jego sygnały z dodatnią sumą wkładów (od największej).
- Najsilniejsze sygnały: cechy zgrupowane w sygnały (`sygnal_cechy`: `<sygnał>_<statystyka>`, tsfresh -> sygnał
  o tym samym źródle, `firmware_*` -> `sterownik_firmware`, `ma_czujnik_wibracji` -> `wibracje_czujnik`);
  `LICZBA_SYGNALOW` o największej dodatniej sumie wkładów.
- Opis alertu (`opis_alertu`): jedno zdanie prostym językiem o pierwszym podzespole: 2 jego sygnały o największym
  wkładzie z wartością dnia względem normy z 30 dni (norma = mediana średnich dobowych z dni 15–44 przed oceną,
  features/windy/cechy.py) i co sprawdzić, np. „Drzwi: najdłuższy czas zamykania +102% względem normy z 30 dni,
  ponowne otwarcia 9×. Sprawdź operator drzwi i rolki.”
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from api.ai.features.windy.cechy import OKNA_GODZIN, nazwy_cech

PLIK_PODZESPOLOW = Path(__file__).with_name("podzespoly.yaml")
PLIK_KATALOGU = Path(__file__).resolve().parents[2] / "ai" / "features" / "windy" / "katalog.yaml"
LICZBA_SYGNALOW = 3
SYGNALOW_W_OPISIE = 2
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
OKNA_W_ZDANIU = {"24h": "", "3d": " (ostatnie 3 dni)", "7d": " (ostatnie 7 dni)"}
NORMA_W_ZDANIU = " względem normy z 30 dni"


@lru_cache(maxsize=1)
def katalog_sygnalow() -> dict[str, dict]:
    """Sygnał -> {rodzina, zrodlo, jednostka} z katalogu cech wind (+ sygnały cech dodatkowych)."""
    katalog = yaml.safe_load(PLIK_KATALOGU.read_text(encoding="utf-8"))
    sygnaly = {k: dict(v) for k, v in katalog["cechy_reczne"]["sygnaly"].items()}
    return {**sygnaly, **OPISY_DODATKOWYCH}


@lru_cache(maxsize=1)
def konfiguracja() -> dict:
    """podzespoly.yaml: `podzespoly` (nazwa, sprawdz), `sygnaly` (nazwa, opis), `cechy` (cecha -> podzespół)."""
    return yaml.safe_load(PLIK_PODZESPOLOW.read_text(encoding="utf-8"))


def mapa_cech() -> dict[str, str | None]:
    return dict(konfiguracja()["cechy"])


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


def podzespol_sygnalu(sygnal: str) -> str | None:
    """Podzespół cech sygnału (w podzespoly.yaml wszystkie cechy jednego sygnału mają ten sam podzespół)."""
    podzespoly = {p for c, p in mapa_cech().items() if sygnal_cechy(c) == sygnal}
    if len(podzespoly) > 1:
        raise ValueError(f"podzespoly.yaml: cechy sygnału {sygnal} mają różne podzespoły {podzespoly}")
    return next(iter(podzespoly), None)


def _wartosc(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def _liczba(x: float, miejsca: int = 0) -> str:
    return f"{x:.{miejsca}f}".replace(".", ",").replace("-", "−")


def _wklady_cech(wklady: pd.Series) -> pd.Series:
    return pd.Series({k.removeprefix("wklad_"): float(v) for k, v in wklady.items() if k != "wklad_staly"})


def opis_sygnalu(sygnal: str, cechy: pd.Series, w: pd.Series, okna_24h: float | None, z_norma: bool) -> str | None:
    """Fragment zdania o sygnale (nazwa + wartość dnia względem normy); None, gdy nie ma czego pokazać."""
    konf = konfiguracja()["sygnaly"][sygnal]
    nazwa, sposob = konf["nazwa"], konf["opis"]
    if sposob == "firmware":
        dni = _wartosc(cechy.get("firmware_dni_od_zmiany"))
        if _wartosc(cechy.get("firmware_zmiana_glowna_44d")) == 1:
            kiedy = f" ({_liczba(dni)} dni temu)" if dni is not None else ""
            return f"nowa wersja główna oprogramowania sterownika{kiedy}"
        return f"{nazwa} zmienione {_liczba(dni)} dni temu" if dni is not None else None
    if sposob not in ("stosunek", "roznica"):
        return None
    # okno (24 h / 3 / 7 dni), którego stosunek do normy najmocniej podniósł ryzyko
    okno = max(OKNA_GODZIN, key=lambda o: w.get(f"{sygnal}_do_normy_{o}", -np.inf))
    sr, norma = _wartosc(cechy.get(f"{sygnal}_sr_{okno}")), _wartosc(cechy.get(f"{sygnal}_norma"))
    if sr is None:
        return None
    dopisek = (NORMA_W_ZDANIU if z_norma else "") + OKNA_W_ZDANIU[okno]
    if sposob == "roznica" and norma is not None:
        return f"{nazwa} {'+' if sr >= norma else ''}{_liczba(sr - norma)} °C{dopisek}"
    if norma:
        r = sr / norma
        if r >= 2:
            return f"{nazwa} {_liczba(r, 0 if r >= 10 or r == round(r) else 1)}×{dopisek}"
        return f"{nazwa} {'+' if r >= 1 else ''}{_liczba(100 * (r - 1))}%{dopisek}"
    licznik = "liczba" in str(katalog_sygnalow()[sygnal].get("jednostka", ""))
    sr_24h = _wartosc(cechy.get(f"{sygnal}_sr_24h"))
    if licznik and okna_24h and sr_24h is not None:
        zwykle = " (zwykle 0)" if norma == 0 else ""
        return f"{nazwa} {_liczba(sr_24h * okna_24h)} w ostatniej dobie{zwykle}"
    return None


def opis_alertu(cechy: pd.Series, w: pd.Series, podzespoly: list[dict], okna_24h: float | None = None) -> str:
    """Jedno zdanie dla technika: pierwszy podzespół, 2 jego sygnały z wartością dnia i co sprawdzić."""
    konf = konfiguracja()["podzespoly"]
    if not podzespoly:
        return "Ryzyko bez wskazania podzespołu (głównie obciążenie i tryb pracy windy). Sprawdź windę w całości."
    p = podzespoly[0]
    fragmenty: list[str] = []
    for s in p["sygnaly"]:
        f = opis_sygnalu(s, cechy, w, okna_24h, z_norma=not any(NORMA_W_ZDANIU in x for x in fragmenty))
        if f:
            fragmenty.append(f)
        if len(fragmenty) == SYGNALOW_W_OPISIE:
            break
    tresc = ", ".join(fragmenty) if fragmenty else "odchylenia w kilku sygnałach naraz"
    return f"{konf[p['podzespol']]['nazwa']}: {tresc}. Sprawdź {konf[p['podzespol']]['sprawdz']}."


def podzespoly_z_wkladow_cech(w: pd.Series) -> list[dict]:
    """[{podzespol, wklad, sygnaly}] z sumą wkładów > 0, malejąco (w: wkład na cechę)."""
    mapa = mapa_cech()
    df = pd.DataFrame({"cecha": w.index, "wklad": w.to_numpy()})
    df["podzespol"] = df["cecha"].map(mapa)
    df["sygnal"] = df["cecha"].map(sygnal_cechy)
    df = df[df["podzespol"].notna()]
    suma = df.groupby("podzespol")["wklad"].sum()
    wynik = []
    for p, v in sorted(suma[suma > 0].items(), key=lambda kv: (-kv[1], kv[0])):
        po_sygnale = df[df["podzespol"] == p].groupby("sygnal")["wklad"].sum()
        dodatnie = po_sygnale[po_sygnale > 0].sort_values(ascending=False, kind="mergesort")
        wynik.append({"podzespol": p, "wklad": round(float(v), 4), "sygnaly": list(dodatnie.index)})
    return wynik


def wyjasnij(
    cechy_wiersza: pd.Series, wklady: pd.Series, okna_24h: float | None = None, n: int = LICZBA_SYGNALOW
) -> dict:
    """cechy_wiersza: wartości cech jednej windy; wklady: `wklad_<cecha>` z explain (log-szansa).
    Zwraca {"sygnaly": [...najwyżej n], "podzespoly": [...], "opis": zdanie alertu}."""
    w = _wklady_cech(wklady)
    df = pd.DataFrame({"cecha": w.index, "wklad": w.to_numpy()})
    df["sygnal"] = df["cecha"].map(sygnal_cechy)
    suma = df.groupby("sygnal")["wklad"].sum()
    dodatnie = suma[suma > 0].sort_values(ascending=False, kind="mergesort")
    opisy = katalog_sygnalow()
    sygnaly = []
    for s, wklad in dodatnie.head(n).items():
        cechy_s = df[df["sygnal"] == s].sort_values("wklad", ascending=False, kind="mergesort")
        cecha = str(cechy_s["cecha"].iloc[0])
        sygnaly.append(
            {
                "sygnal": s,
                "rodzina": opisy[s]["rodzina"],
                "zrodlo": str(opisy[s].get("zrodlo")),
                "jednostka": str(opisy[s].get("jednostka")),
                "wklad": round(float(wklad), 4),
                "cecha": cecha,
                "wartosc": _wartosc(cechy_wiersza.get(cecha)) and round(float(cechy_wiersza.get(cecha)), 4),
                "podzespol": podzespol_sygnalu(s),
            }
        )
    podzespoly = podzespoly_z_wkladow_cech(w)
    return {"sygnaly": sygnaly, "podzespoly": podzespoly, "opis": opis_alertu(cechy_wiersza, w, podzespoly, okna_24h)}


def wyjasnij_ramke(cechy: pd.DataFrame, wyjasnienie: pd.DataFrame, okna_24h: pd.Series | None = None) -> list[dict]:
    """`wyjasnij` dla każdego wiersza (indeksy cechy i wyjasnienie z explain muszą się zgadzać)."""
    wklady = wyjasnienie[[k for k in wyjasnienie.columns if k.startswith("wklad_")]]
    return [
        wyjasnij(cechy.loc[i], wklady.loc[i], None if okna_24h is None else _wartosc(okna_24h.loc[i]))
        for i in cechy.index
    ]


def podzespoly_z_wkladow(wklady: np.ndarray, cechy_modelu: list[str], mapa: dict | None = None) -> list[list[str]]:
    """Lista podejrzanych podzespołów (nazwy, malejąco) dla macierzy wkładów [wiersze × cechy] (ewaluacja)."""
    mapa = mapa_cech() if mapa is None else mapa
    podzespoly = sorted({p for p in mapa.values() if p})
    przypisanie = np.array([[mapa.get(c) == p for p in podzespoly] for c in cechy_modelu], dtype=float)
    sumy = np.asarray(wklady[:, : len(cechy_modelu)], dtype=float) @ przypisanie
    wyniki = []
    for wiersz in sumy:
        kolejnosc = sorted((i for i in range(len(podzespoly)) if wiersz[i] > 0), key=lambda i: (-wiersz[i], i))
        wyniki.append([podzespoly[i] for i in kolejnosc])
    return wyniki
