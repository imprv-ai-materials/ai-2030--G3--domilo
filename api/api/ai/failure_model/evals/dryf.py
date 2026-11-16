"""Dryf cech modelu wind: tabela `psi_cech_windy` i ocena korekty `bledy_drzwi` dla Liftar LF-5 (bez ponownego uczenia).

PSI (Population Stability Index) każdej cechy aktywnego modelu (failure_model/current.yaml, `cechy`), osobno dla
każdego producenta (`serwis_windy.producent`):
- punkt odniesienia: wiersze treningu modelu (`podzial_czas_winda`: dni 2023-03-01 – 2025-06-30, bez 28 wind poza
  treningiem) danego producenta;
- przedziały: 10 przedziałów z decyli wartości treningowych (np.quantile 0,1 … 0,9; powtórzone granice łączymy, więc
  cecha z dużą liczbą zer ma mniej przedziałów — kolumna `przedzialy`) + osobny „przedział” braków (NULL);
- tydzień: poniedziałek–niedziela według `dzien` (dzień oceny), wszystkie windy producenta, tylko pełne tygodnie
  (7 dni); w tabeli tygodnie od 2025-06-30 (pierwszy pełny tydzień z dniami od 2025-07) do 2026-09-14;
- PSI = Σ (a − e) · ln(a / e), a = udział tygodnia w przedziale, e = udział treningu; udziały poniżej `EPS` zastępuje
  `EPS` (inaczej ln(0)); `EPS` = 1e-4 to stała techniczna przyjęta w tej pracy.
- `psi_trening_maks`: największe PSI tej cechy u tego producenta w pełnych tygodniach treningu (2023-03-06 –
  2025-06-23) wobec tego samego punktu odniesienia = zmienność tydzień do tygodnia bez dryfu; `ponad_trening` =
  PSI tygodnia > tej wartości. Zamiast progów „z literatury” używamy progu z danych.
- `wariant`: `obecna` (cechy jak w cechy_windy) i `korekta_lf5` (cechy sygnału drzwi_bledy z tabeli
  cechy_windy_korekta_lf5, features/windy/cechy.py: SQL_BLEDY_DRZWI_LF5).
Uruchomienie: `cd api && poetry run python -m api.ai.failure_model.evals.dryf [--buduj-korekte]` (zapisuje
psi_cech_windy w domilo.duckdb; `--buduj-korekte` najpierw buduje cechy_windy_korekta_lf5, ok. 25 s).
Raport: docs/b4_dryf_i_fallback.md.
"""

import sys

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polaczenie
from api.ai.failure_model.base import wczytaj_obecny
from api.ai.failure_model.evals.ewaluacja_v2 import TEST, ocen, podzial_czas_winda, roznica
from api.ai.features.windy.cechy import zbuduj_cechy_windy
from api.ai.features.windy.zbior import wczytaj_zbior
from api.contexts_boundaries.maintenance_bc.alarmy_wind import ocen_alarmy, wczytaj_zalozenia, wybierz_alarmy
from api.contexts_boundaries.maintenance_bc.wyjasnienie import sygnal_cechy

TABELA = "psi_cech_windy"
TABELA_KOREKTY = "cechy_windy_korekta_lf5"
EPS = 1e-4
DECYLE = np.linspace(0.1, 0.9, 9)
OD_TYGODNIA = pd.Timestamp("2025-06-30")
SYGNAL_KOREKTY = "drzwi_bledy"


def granice(x: np.ndarray) -> np.ndarray:
    """Granice przedziałów z decyli wartości treningowych (bez braków; powtórzone granice połączone)."""
    x = x[~np.isnan(x)]
    return np.unique(np.quantile(x, DECYLE)) if len(x) else np.array([])


def przedzial(x: np.ndarray, gr: np.ndarray) -> np.ndarray:
    """Numer przedziału: 0 … len(gr) (przedziały prawostronnie domknięte), len(gr) + 1 = brak."""
    wynik = np.searchsorted(gr, x, side="left")
    return np.where(np.isnan(x), len(gr) + 1, wynik)


def psi(a: np.ndarray, e: np.ndarray, eps: float = EPS) -> float:
    a, e = np.maximum(a, eps), np.maximum(e, eps)
    return float(np.sum((a - e) * np.log(a / e)))


def tygodnie(dzien: pd.Series) -> pd.Series:
    d = pd.to_datetime(dzien)
    return (d - pd.to_timedelta(d.dt.day_of_week, unit="D")).dt.normalize()


def psi_tygodniowe(zbior: pd.DataFrame, cechy: list[str], trening: np.ndarray, wariant: str) -> pd.DataFrame:
    """Wiersz na producent × tydzień × cecha (wszystkie pełne tygodnie, także treningowe)."""
    df = zbior.assign(tydzien=tygodnie(zbior["dzien"]), _trening=np.asarray(trening, dtype=bool))
    dni_w_tyg = df.groupby("tydzien")["dzien"].nunique()
    df = df[df["tydzien"].isin(dni_w_tyg[dni_w_tyg == 7].index)]
    wiersze = []
    for producent, grupa in df.groupby("producent", sort=True):
        tr = grupa["_trening"].to_numpy()
        tyg_kody, tyg = pd.factorize(grupa["tydzien"], sort=True)
        n_tyg = np.bincount(tyg_kody, minlength=len(tyg))
        for cecha in cechy:
            x = grupa[cecha].to_numpy(dtype="float64")
            gr = granice(x[tr])
            p = przedzial(x, gr)
            k = len(gr) + 2
            e = np.bincount(p[tr], minlength=k) / tr.sum()
            licz = np.bincount(tyg_kody * k + p, minlength=len(tyg) * k).reshape(len(tyg), k)
            udz = licz / n_tyg[:, None]
            for i, t in enumerate(tyg):
                wiersze.append(
                    (
                        producent,
                        t.date(),
                        cecha,
                        wariant,
                        psi(udz[i], e),
                        int(n_tyg[i]),
                        int(tr.sum()),
                        len(gr) + 1,
                        float(udz[i, -1]),
                        float(e[-1]),
                    )
                )
    kol = ["producent", "tydzien", "cecha", "wariant", "psi", "n_tydzien", "n_trening", "przedzialy"]
    return pd.DataFrame(wiersze, columns=[*kol, "brak_tydzien", "brak_trening"])


def tabela_psi(zbior: pd.DataFrame, cechy: list[str], trening_maska: np.ndarray, wariant: str) -> pd.DataFrame:
    """PSI tygodni od OD_TYGODNIA + psi_trening_maks (największe PSI w pełnych tygodniach treningu)."""
    wszystkie = psi_tygodniowe(zbior.reset_index(drop=True), cechy, trening_maska, wariant)
    tydzien = pd.to_datetime(wszystkie["tydzien"])
    w_treningu = (tydzien >= pd.Timestamp("2023-03-01")) & (
        tydzien + pd.Timedelta(days=6) <= pd.Timestamp("2025-06-30")
    )
    maks = wszystkie[w_treningu].groupby(["producent", "cecha"])["psi"].max().rename("psi_trening_maks")
    po = wszystkie[tydzien >= OD_TYGODNIA].join(maks, on=["producent", "cecha"])
    po["ponad_trening"] = po["psi"] > po["psi_trening_maks"]
    po["sygnal"] = po["cecha"].map(sygnal_cechy)
    return po


def zapisz(con, df: pd.DataFrame) -> int:
    con.register("_psi", df)
    try:
        con.execute(f"""
            CREATE OR REPLACE TABLE {TABELA} AS
            SELECT producent, CAST(tydzien AS DATE) AS tydzien, cecha, sygnal, wariant, psi, psi_trening_maks,
                ponad_trening, n_tydzien, n_trening, przedzialy, brak_tydzien, brak_trening
            FROM _psi ORDER BY wariant, producent, cecha, tydzien
            """)
    finally:
        con.unregister("_psi")
    return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


def zbuduj_psi() -> int:
    model = wczytaj_obecny()
    cechy = list(model.cechy)
    with polaczenie() as con:
        zbior, _ = wczytaj_zbior(con)
        korekta, _ = wczytaj_zbior(con, tabela_cech=TABELA_KOREKTY)
    maski, _ = podzial_czas_winda(zbior)
    cechy_korekty = [c for c in cechy if sygnal_cechy(c) == SYGNAL_KOREKTY]
    df = pd.concat(
        [
            tabela_psi(zbior, cechy, maski["trening"], "obecna"),
            tabela_psi(korekta, cechy_korekty, podzial_czas_winda(korekta)[0]["trening"], "korekta_lf5"),
        ],
        ignore_index=True,
    )
    with polaczenie(tylko_odczyt=False) as con:
        return zapisz(con, df)


def ocena_korekty() -> dict:
    """Ten sam model (bez uczenia) na cechach obecnych i po korekcie: test 2026-01-01 – 2026-09-22 (wszyscy i Liftar)
    oraz reguła alarmu (poniedziałek, 3 windy, przerwa 7 dni)."""
    model = wczytaj_obecny()
    with polaczenie() as con:
        zbior, _ = wczytaj_zbior(con)
        korekta, _ = wczytaj_zbior(con, tabela_cech=TABELA_KOREKTY)
        awarie = con.execute("""
            SELECT id_awarii, id_windy, podzespol,
                coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS start_tz
            FROM awarie_odtworzone""").df()
    z = wczytaj_zalozenia()
    wyniki = {}
    test = {}
    for nazwa, zb in (("obecna", zbior), ("korekta_lf5", korekta)):
        t = zb[zb["dzien"].between(*TEST)].reset_index(drop=True)
        t["wynik"] = model.predict(t)
        test[nazwa] = t
    assert (test["obecna"][["id_windy", "dzien"]] == test["korekta_lf5"][["id_windy", "dzien"]]).all().all()
    for zakres, maska in (("wszystkie", slice(None)), ("Liftar", test["obecna"]["producent"] == "Liftar")):
        a, b = test["korekta_lf5"][maska], test["obecna"][maska]
        wyniki[zakres] = {
            "obecna": ocen(b.reset_index(drop=True), b["wynik"].to_numpy()),
            "korekta_lf5": ocen(a.reset_index(drop=True), a["wynik"].to_numpy()),
            "roznica": roznica(a.reset_index(drop=True), a["wynik"].to_numpy(), b["wynik"].to_numpy()),
        }
    poniedzialki = sorted({d for d in test["obecna"]["dzien"] if d.day_of_week == 0})
    for nazwa, t in test.items():
        al = wybierz_alarmy(
            t.rename(columns={"wynik": "ryzyko"}),
            int(z["alarmy_na_tydzien"]),
            int(z["przerwa_dni"]),
            int(z["dzien_alarmu"]),
        )
        oc = ocen_alarmy(al, awarie, poniedzialki)
        al = al.merge(t[["id_windy", "producent"]].drop_duplicates(), on="id_windy")
        wyniki[f"alarmy_{nazwa}"] = {**oc["ogolem"], "alarmy_liftar": int((al["producent"] == "Liftar").sum())}
    return wyniki


if __name__ == "__main__":
    if "--buduj-korekte" in sys.argv:
        with polaczenie(tylko_odczyt=False) as con:
            print(TABELA_KOREKTY, zbuduj_cechy_windy(con, tabela=TABELA_KOREKTY, korekta_lf5=True))
    print(TABELA, zbuduj_psi())
    for k, v in ocena_korekty().items():
        print(k, v)
