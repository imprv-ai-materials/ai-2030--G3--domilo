"""Ile zmienia wykluczenie okien `tryb = 'serwis'` z cech wind (wyniki: docs/b4_punkt_pracy.md, część „Tryb serwisowy”).

Warianty (te same wiersze dni_wind, ten sam podział, te same 179 kolumn cech i te same parametry LightGBM):
- „bez serwisu” (obecny): cechy_windy + cechy_windy_tsfresh, okna serwisowe wykluczone (docs/b4_cechy.md);
- „z serwisem”: te same cechy przeliczone bez filtra (`bez_serwisu=False` w features/windy/cechy.py
  i tsfresh_cechy.py) do tabel cechy_windy_z_serwisem i cechy_windy_tsfresh_z_serwisem. Lista 11 cech tsfresh
  zostaje ta sama (tsfresh_wybrane.yaml), żeby różnica dotyczyła tylko wartości cech.
Model: ModelLGBMCzasWinda uczony jak w failure_model/evals/ewaluacja_v2.py (`podzial_czas_winda`, trening
2023-03 – 2025-06, walidacja 2025-07 – 12, 28 wind poza treningiem). Kontrola: wariant „bez serwisu” uczony
ponownie musi dać te same wyniki co zapisany v2b_lgbm_czas_winda.
Porównanie: reguła alarmy_wind.wybierz_alarmy (3 alarmy w poniedziałek, przerwa 7 dni) na teście 2026, precyzja,
czułość, wartość w PLN (wartosc_alarmow.ekonomia), 95% CI z bootstrapu tygodni; baseline (reguła
`drzwi_ponowne_otwarcia_do_normy_24h`) w obu wariantach cech. Alarmy, które różnią się między wariantami, z najbliższą
konserwacją z serwis_harmonogram i oknami serwisowymi w 7 dniach przed alarmem.

Reguła wyboru wersji (ustalona przed uruchomieniem): wariant „z serwisem” zastępuje obecny tylko wtedy, gdy jego
precyzja przy 3 alarmach jest wyższa, a 95% CI różnicy nie obejmuje 0; inaczej zostaje „bez serwisu”.
Wybrany wariant + kalibracja izotoniczna na walidacji = versions/v3_punkt_pracy (zapis i current.yaml: `--zapisz`).

Uruchomienie (z api/):
  python -m api.contexts_boundaries.maintenance_bc.tryb_serwisowy --buduj   # tabele wariantu (zapis do bazy, ~3 min)
  python -m api.contexts_boundaries.maintenance_bc.tryb_serwisowy [--zapisz] [--bez-mlflow]
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from api.contexts_boundaries.maintenance_bc.alarmy_wind import ocen_alarmy, wczytaj_zalozenia, wybierz_alarmy
from api.contexts_boundaries.maintenance_bc.punkt_pracy import SQL_AWARIE
from api.contexts_boundaries.maintenance_bc.wartosc_alarmow import ekonomia, wartosc

TABELA_CECH_Z = "cechy_windy_z_serwisem"
TABELA_TSFRESH_Z = "cechy_windy_tsfresh_z_serwisem"
BOOTSTRAP = 10000
ZIARNO = 2026
PRZYKLADOW = 5

# okna serwisowe w 7 dniach przed odcięciem 05:50 dnia oceny (te same okna, które widzą cechy 7d)
SQL_SERWIS_7D = """
WITH s AS (SELECT id_windy, ts_utc FROM telemetra_windy WHERE tryb = 'serwis')
SELECT d.id_windy, d.dzien,
    count(s.ts_utc) AS okna_serwisu_7d,
    count(s.ts_utc) FILTER (s.ts_utc > timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50') - INTERVAL 24 HOUR)
        AS okna_serwisu_24h
FROM dni_wind AS d
LEFT JOIN s
    ON s.id_windy = d.id_windy
   AND s.ts_utc > timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50') - INTERVAL 168 HOUR
   AND s.ts_utc <= timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50')
WHERE d.dzien BETWEEN '2026-01-01' AND '2026-09-22'
GROUP BY d.id_windy, d.dzien
"""

# konserwacje / przeglądy wykonane (data bez godziny; okna serwisowe tego dnia: 08:10–16:30, czyli po alarmie 06:00)
SQL_HARMONOGRAM = """
SELECT id_windy, CAST(data_wykonania AS DATE) AS data_wykonania, typ
FROM serwis_harmonogram
WHERE data_wykonania IS NOT NULL
"""


def zbuduj_wariant() -> None:
    from api.adapters.duckdb_baza import polaczenie
    from api.ai.features.windy.cechy import zbuduj_cechy_windy
    from api.ai.features.windy.tsfresh_cechy import zbuduj_cechy_tsfresh

    with polaczenie(tylko_odczyt=False) as con:
        print(TABELA_CECH_Z, zbuduj_cechy_windy(con, tabela=TABELA_CECH_Z, bez_serwisu=False))
        print(TABELA_TSFRESH_Z, zbuduj_cechy_tsfresh(con, tabela=TABELA_TSFRESH_Z, bez_serwisu=False))


# --- dane i uczenie -----------------------------------------------------------------------------------------


def dane(con):
    from api.ai.features.windy.zbior import wczytaj_zbior

    bez, cechy = wczytaj_zbior(con)
    z, cechy_z = wczytaj_zbior(con, TABELA_CECH_Z, TABELA_TSFRESH_Z)
    assert cechy == cechy_z, "warianty mają różne kolumny cech"
    assert bez[["id_windy", "dzien"]].equals(z[["id_windy", "dzien"]]), "warianty mają różne wiersze"
    return bez, z, cechy


def naucz(df: pd.DataFrame, cechy: list[str], maski: dict, opis: dict):
    from api.ai.failure_model.versions.v2b_lgbm_czas_winda.model import ModelLGBMCzasWinda

    tr, wa = df[maski["trening"]], df[maski["walidacja"]]
    return ModelLGBMCzasWinda(cechy).fit(tr, tr["awaria_7d"], wa, wa["awaria_7d"], podzial=opis)


def roznice_cech(bez: pd.DataFrame, z: pd.DataFrame, cechy: list[str], maska: np.ndarray) -> pd.DataFrame:
    """Odsetek wierszy (maska), w których cecha ma inną wartość w wariancie z serwisem (NULL = NULL to brak różnicy)."""
    a, b = bez.loc[maska, cechy], z.loc[maska, cechy]
    rozne = ~((a == b) | (a.isna() & b.isna()) | np.isclose(a.fillna(0), b.fillna(0), rtol=1e-9, atol=1e-12))
    return pd.DataFrame({"cecha": cechy, "odsetek_wierszy": rozne.mean().to_numpy()}).sort_values(
        "odsetek_wierszy", ascending=False
    )


# --- reguła alarmu ------------------------------------------------------------------------------------------


def alarmy(test, kolumna, awarie, poniedzialki, z) -> dict:
    r = test[["id_windy", "dzien"]].assign(ryzyko=test[kolumna].to_numpy())
    a = wybierz_alarmy(r, z["alarmy_na_tydzien"], z["przerwa_dni"], z["dzien_alarmu"])
    return ocen_alarmy(a, awarie, poniedzialki)


def bootstrap(tyg_a: pd.DataFrame, tyg_b: pd.DataFrame) -> dict:
    """95% CI różnicy a − b: precyzja, czułość (bootstrap tygodni, te same losowania)."""
    rng = np.random.default_rng(ZIARNO)
    idx = rng.integers(0, len(tyg_a), size=(BOOTSTRAP, len(tyg_a)))

    def suma(t, k):
        return t[k].to_numpy()[idx].sum(axis=1)

    wynik = {}
    for nazwa, licz, mian in (("precyzja", "trafne", "alarmy"), ("czulosc", "zlapane", "awarie")):
        d = suma(tyg_a, licz) / suma(tyg_a, mian) - suma(tyg_b, licz) / suma(tyg_b, mian)
        wynik[nazwa] = (float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975)))
    return wynik


def opisz_alarmy(rozne: pd.DataFrame, harmonogram: pd.DataFrame) -> pd.DataFrame:
    """Dla alarmów: ostatnia konserwacja przed dniem alarmu i następna (od dnia alarmu), najbliższa z nich."""
    wiersze = []
    for _, a in rozne.iterrows():
        h = harmonogram[harmonogram["id_windy"] == a["id_windy"]]
        dzien = a["dzien"].date()
        przed = h[h["data_wykonania"] < dzien].sort_values("data_wykonania").tail(1)
        po = h[h["data_wykonania"] >= dzien].sort_values("data_wykonania").head(1)
        opis = {}
        for nazwa, x in (("przed", przed), ("po", po)):
            if len(x):
                d = x["data_wykonania"].iloc[0]
                opis[f"konserwacja_{nazwa}"] = d
                opis[f"typ_{nazwa}"] = x["typ"].iloc[0]
                opis[f"dni_{nazwa}"] = (d - dzien).days
            else:
                opis[f"konserwacja_{nazwa}"], opis[f"typ_{nazwa}"], opis[f"dni_{nazwa}"] = None, None, np.nan
        wiersze.append(opis)
    wyj = pd.concat([rozne.reset_index(drop=True), pd.DataFrame(wiersze)], axis=1)
    przed_blizej = wyj["dni_przed"].abs().fillna(1e9) <= wyj["dni_po"].abs().fillna(1e9)
    wyj["najblizsza"] = np.where(przed_blizej, wyj["konserwacja_przed"], wyj["konserwacja_po"])
    wyj["najblizsza_typ"] = np.where(przed_blizej, wyj["typ_przed"], wyj["typ_po"])
    wyj["najblizsza_dni"] = np.where(przed_blizej, wyj["dni_przed"], wyj["dni_po"])
    return wyj


# --- formatowanie -------------------------------------------------------------------------------------------


def pl(x: float, miejsca: int = 0) -> str:
    s = f"{abs(x):,.{miejsca}f}".replace(",", " ").replace(".", ",")
    return ("−" if x < 0 else "") + s


def proc(x: float, miejsca: int = 1) -> str:
    return pl(100 * x, miejsca) + "%"


def pp(lo_hi) -> str:
    return " … ".join(("+" if v >= 0 else "−") + pl(100 * abs(v), 1) + " pp" for v in lo_hi)


def main(zapisz: bool = False, z_mlflow: bool = True) -> None:
    from api.adapters.duckdb_baza import polacz
    from api.ai.failure_model.base import ModelWind
    from api.ai.failure_model.evals.ewaluacja_v2 import KATALOG_WERSJI, REGULA, ocen, podzial_czas_winda
    from api.ai.failure_model.versions.v3_punkt_pracy.model import ModelPunktPracy

    z = wczytaj_zalozenia()
    ekon = ekonomia(z)
    con = polacz()
    bez, zs, cechy = dane(con)
    maski, poza = podzial_czas_winda(bez)
    opis = {"rodzaj": "czas + windy poza treningiem", "windy_poza_treningiem": poza}

    zapisany = ModelWind.wczytaj(KATALOG_WERSJI / "v2b_lgbm_czas_winda" / "model.joblib")
    m_bez = naucz(bez, cechy, maski, opis | {"cechy": "bez serwisu"})
    m_z = naucz(zs, cechy, maski, opis | {"cechy": "z serwisem"})
    t = maski["test"]
    test = bez.loc[t, ["id_windy", "dzien", "awaria_7d", REGULA]].copy()
    test["model_bez"] = m_bez.predict(bez[t])
    test["model_z"] = m_z.predict(zs[t])
    test["zapisany"] = zapisany.predict(bez[t])
    test["regula_bez"] = bez.loc[t, REGULA].fillna(-1e9).to_numpy()
    test["regula_z"] = zs.loc[t, REGULA].fillna(-1e9).to_numpy()
    print(
        "kontrola: maks |ponownie uczony − zapisany v2b| =",
        float(np.abs(test["model_bez"] - test["zapisany"]).max()),
        "drzewa:",
        m_bez.liczba_drzew_,
        zapisany.liczba_drzew_,
        m_z.liczba_drzew_,
    )

    serwis = con.execute(SQL_SERWIS_7D).df()
    serwis["dzien"] = pd.to_datetime(serwis["dzien"])
    test = test.merge(serwis, on=["id_windy", "dzien"], how="left", validate="1:1")
    harmonogram = con.execute(SQL_HARMONOGRAM).df()
    harmonogram["data_wykonania"] = pd.to_datetime(harmonogram["data_wykonania"]).dt.date
    awarie = con.execute(SQL_AWARIE).df()
    dni = pd.Series(sorted(test["dzien"].unique()))
    poniedzialki = list(dni[dni.dt.day_of_week == z["dzien_alarmu"]])

    # --- różnice cech
    rc = roznice_cech(bez, zs, cechy, t)
    pon = test["dzien"].dt.day_of_week == 0
    print("\n## S1 dane\n")
    print(
        f"wiersze testu {len(test)}; z oknem serwisowym w 7 dniach przed 05:50: "
        f"{int((test['okna_serwisu_7d'] > 0).sum())} ({proc((test['okna_serwisu_7d'] > 0).mean())}); "
        f"w 24 h: {int((test['okna_serwisu_24h'] > 0).sum())}; "
        f"poniedziałki {int(pon.sum())}, z serwisem w 7 dniach {int((test.loc[pon, 'okna_serwisu_7d'] > 0).sum())}"
    )
    print(f"cechy różne choć w jednym wierszu testu: {int((rc['odsetek_wierszy'] > 0).sum())} z {len(cechy)}")
    print("| cecha | odsetek wierszy testu z inną wartością |\n|---|---:|")
    for _, r in rc.head(10).iterrows():
        print(f"| `{r['cecha']}` | {proc(r['odsetek_wierszy'])} |")
    for nazwa, maska in (("z serwisem w 7 dniach", test["okna_serwisu_7d"] > 0), ("bez", test["okna_serwisu_7d"] == 0)):
        g = test[maska]
        print(
            f"wiersze {nazwa}: {len(g)}, odsetek awaria_7d {proc(g['awaria_7d'].mean(), 2)}; śr. reguła bez/z "
            f"{g['regula_bez'].replace(-1e9, np.nan).mean():.3f} / {g['regula_z'].replace(-1e9, np.nan).mean():.3f}"
        )

    # --- jakość rankingu
    print("\n## S2 ranking na teście (bootstrap wind)\n")
    print("| wariant cech | ranking | ROC AUC | PR-AUC |\n|---|---|---|---|")
    for wariant, kol in (
        ("bez serwisu (obecny)", "model_bez"),
        ("z serwisem", "model_z"),
        ("bez serwisu (obecny)", "regula_bez"),
        ("z serwisem", "regula_z"),
    ):
        o = ocen(test, test[kol].to_numpy())
        nazwa = "model" if kol.startswith("model") else "baseline: reguła drzwi"
        print(
            f"| {wariant} | {nazwa} | {pl(o['roc_auc'], 3)} ({pl(o['roc_auc_lo'], 3)}–{pl(o['roc_auc_hi'], 3)}) | "
            f"{pl(o['pr_auc'], 3)} ({pl(o['pr_auc_lo'], 3)}–{pl(o['pr_auc_hi'], 3)}) |"
        )

    # --- reguła 3 alarmów
    wyniki = {k: alarmy(test, k, awarie, poniedzialki, z) for k in ("model_bez", "model_z", "regula_bez", "regula_z")}
    print("\n## S3 reguła 3 alarmów\n")
    print(
        "| wariant cech | ranking | alarmy | trafne | precyzja | złapane awarie | czułość | czułość z sygnałem | "
        "mediana wyprzedzenia (h) | alarmy z serwisem w 7 dniach | wartość w teście (PLN) |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k, w in wyniki.items():
        o = w["ogolem"]
        a = w["alarmy"].merge(test[["id_windy", "dzien", "okna_serwisu_7d"]], on=["id_windy", "dzien"])
        print(
            f"| {'bez serwisu (obecny)' if k.endswith('bez') else 'z serwisem'} | "
            f"{'model' if k.startswith('model') else 'baseline: reguła drzwi'} | {o['alarmy']} | {o['trafne']} | "
            f"{proc(o['precyzja'])} | {o['zlapane']} | {proc(o['czulosc'])} | {proc(o['czulosc_sygnal'])} | "
            f"{pl(o['mediana_wyprzedzenia_h'], 1)} | {int((a['okna_serwisu_7d'] > 0).sum())} | "
            f"{pl(float(wartosc(o['trafne'], o['alarmy'], ekon)))} |"
        )
    ci = {k: bootstrap(wyniki[f"{k}_z"]["tygodnie"], wyniki[f"{k}_bez"]["tygodnie"]) for k in ("model", "regula")}
    print("\n| ranking | precyzja: z − bez | 95% CI | czułość: z − bez | 95% CI |\n|---|---:|---|---:|---|")
    for k in ("model", "regula"):
        oz, ob = wyniki[f"{k}_z"]["ogolem"], wyniki[f"{k}_bez"]["ogolem"]
        dp, dc = oz["precyzja"] - ob["precyzja"], oz["czulosc"] - ob["czulosc"]
        print(
            f"| {'model' if k == 'model' else 'baseline: reguła drzwi'} | {pp((dp, dp)).split(' … ')[0]} | "
            f"{pp(ci[k]['precyzja'])} | {pp((dc, dc)).split(' … ')[0]} | {pp(ci[k]['czulosc'])} |"
        )

    # --- alarmy różne między wariantami (model)
    a_bez = wyniki["model_bez"]["alarmy"].assign(wariant="tylko bez serwisu")
    a_z = wyniki["model_z"]["alarmy"].assign(wariant="tylko z serwisem")
    klucz_bez = set(zip(a_bez["dzien"], a_bez["id_windy"], strict=True))
    klucz_z = set(zip(a_z["dzien"], a_z["id_windy"], strict=True))
    rozne = pd.concat(
        [
            a_bez[[(d, w) not in klucz_z for d, w in zip(a_bez["dzien"], a_bez["id_windy"], strict=True)]],
            a_z[[(d, w) not in klucz_bez for d, w in zip(a_z["dzien"], a_z["id_windy"], strict=True)]],
        ]
    )
    kol = ["id_windy", "dzien", "okna_serwisu_7d", "okna_serwisu_24h", "model_bez", "model_z", "regula_bez", "regula_z"]
    rozne = rozne.merge(test[kol], on=["id_windy", "dzien"], how="left").sort_values(["dzien", "wariant"])
    rozne = opisz_alarmy(rozne, harmonogram)
    # pozycja windy w rankingu dnia w każdym wariancie (1 = najwyższe ryzyko, wśród wind z wierszem w tym dniu)
    for k in ("model_bez", "model_z"):
        test[f"poz_{k}"] = test.groupby("dzien")[k].rank(ascending=False, method="first").astype(int)
    rozne = rozne.merge(test[["id_windy", "dzien", "poz_model_bez", "poz_model_z"]], on=["id_windy", "dzien"])

    print("\n## S4 alarmy różne między wariantami (model)\n")
    print(
        "| alarm tylko w wariancie | alarmy | trafne | precyzja | z oknem serwisowym w 7 dniach przed alarmem | "
        "mediana dni od ostatniej konserwacji |"
    )
    print("|---|---:|---:|---:|---:|---:|")
    for wariant, g in rozne.groupby("wariant"):
        print(
            f"| {wariant} | {len(g)} | {int(g['trafny'].sum())} | {proc(g['trafny'].mean())} | "
            f"{int((g['okna_serwisu_7d'] > 0).sum())} | {pl(-g['dni_przed'].median(), 1)} |"
        )
    # to samo dla baseline (reguła drzwi): alarmy tylko w jednym wariancie
    for k in ("regula_bez", "regula_z"):
        inny = "regula_z" if k == "regula_bez" else "regula_bez"
        ka = set(zip(wyniki[inny]["alarmy"]["dzien"], wyniki[inny]["alarmy"]["id_windy"], strict=True))
        a = wyniki[k]["alarmy"].merge(test[["id_windy", "dzien", "okna_serwisu_7d"]], on=["id_windy", "dzien"])
        a = a[[(d, w) not in ka for d, w in zip(a["dzien"], a["id_windy"], strict=True)]]
        print(
            f"| baseline, tylko {'bez serwisu' if k.endswith('bez') else 'z serwisem'} | {len(a)} | "
            f"{int(a['trafny'].sum())} | {proc(a['trafny'].mean())} | {int((a['okna_serwisu_7d'] > 0).sum())} | — |"
        )
    wspolne = len(klucz_bez & klucz_z)
    from scipy.stats import spearmanr

    rho = spearmanr(test["model_bez"], test["model_z"]).statistic
    print(f"\nwspólne alarmy modelu: {wspolne} z 114; Spearman wyników modelu bez/z na teście: {rho:.4f}")
    print("ważność (udział gain), 5 pierwszych:")
    for nazwa, m in (("bez", m_bez), ("z", m_z)):
        w = m.waznosc_cech().head(5)
        print(f"  {nazwa}: " + "; ".join(f"{c} {u:.3f}" for c, u in zip(w["cecha"], w["udzial"], strict=True)))
    print("\nwszystkie różne alarmy:")
    for _, r in rozne.iterrows():
        print(
            f"  {r['dzien']:%Y-%m-%d} {r['id_windy']} {r['wariant']:18} trafny={int(r['trafny'])} "
            f"serwis7d={r['okna_serwisu_7d']} 24h={r['okna_serwisu_24h']} poz bez/z {r['poz_model_bez']}/"
            f"{r['poz_model_z']} przed={r['konserwacja_przed']} ({r['typ_przed']}, {r['dni_przed']}) "
            f"po={r['konserwacja_po']} ({r['typ_po']}, {r['dni_po']}) podzespol={r['podzespol']} "
            f"reg bez/z {r['regula_bez']:.2f}/{r['regula_z']:.2f}"
        )
    # 5 przykładów: reguła ustalona przed obejrzeniem listy — pierwsze 5 różnych alarmów w kolejności daty
    print("\n## S5 pięć przykładów (pierwsze według daty)\n")
    print(
        "| poniedziałek | winda | alarm tylko w wariancie | pozycja: bez / z serwisem | trafny | "
        "okna serwisowe w 7 dniach (w tym 24 h) | najbliższa konserwacja (typ, dni od alarmu) | "
        "ostatnia przed alarmem |"
    )
    print("|---|---|---|---|---|---:|---|---|")
    for _, r in rozne.sort_values(["dzien", "id_windy"]).head(PRZYKLADOW).iterrows():
        traf = f"tak ({pl(r['wyprzedzenie_h'], 0)} h, {r['podzespol']})" if r["trafny"] else "nie"
        print(
            f"| {r['dzien']:%Y-%m-%d} | {r['id_windy']} | {r['wariant'].replace('tylko ', '')} | "
            f"{r['poz_model_bez']} / {r['poz_model_z']} | {traf} | {r['okna_serwisu_7d']} ({r['okna_serwisu_24h']}) | "
            f"{r['najblizsza']} ({r['najblizsza_typ']}, {int(r['najblizsza_dni']):+d}) | "
            f"{r['konserwacja_przed']} ({r['typ_przed']}) |"
        )

    # --- wybór wariantu i zapis v3
    oz, ob = wyniki["model_z"]["ogolem"], wyniki["model_bez"]["ogolem"]
    lepszy_z = oz["precyzja"] > ob["precyzja"] and ci["model"]["precyzja"][0] > 0
    wybrany, dane_wyb, tab = (m_z, zs, "z serwisem") if lepszy_z else (zapisany, bez, "bez serwisu")
    print(f"\nwybrany wariant cech: {tab}")
    if zapisz:
        wa = dane_wyb[maski["walidacja"]]
        v3 = ModelPunktPracy(wybrany, punkt_pracy=z, bez_serwisu=not lepszy_z).fit(wa, wa["awaria_7d"])
        metryki = {
            "wariant_cech": tab,
            "model_bazowy": wybrany.wersja,
            "liczba_drzew": wybrany.liczba_drzew_,
            "punkt_pracy": {k: z[k] for k in ("alarmy_na_tydzien", "dzien_alarmu", "przerwa_dni")},
            "kalibracja": "IsotonicRegression na walidacji 2025-07-01 – 2025-12-31",
            "test_3_alarmy": (
                {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in ob.items()}
                if not lepszy_z
                else {k: float(v) for k, v in oz.items()}
            ),
            "test_3_alarmy_wartosc_pln": float(
                wartosc((oz if lepszy_z else ob)["trafne"], (oz if lepszy_z else ob)["alarmy"], ekon)
            ),
            "test_ranking": ocen(test, test["model_z" if lepszy_z else "model_bez"].to_numpy()),
            "porownanie_trybu_serwisowego": {
                "precyzja_z_minus_bez": oz["precyzja"] - ob["precyzja"],
                "precyzja_ci": ci["model"]["precyzja"],
            },
            "p_test_srednia": float(v3.prawdopodobienstwo(dane_wyb[t]).mean()),
            "baseline_3_alarmy": {
                k: float(v) for k, v in wyniki["regula_z" if lepszy_z else "regula_bez"]["ogolem"].items()
            },
            "odsetek_awarii_test": float(dane_wyb.loc[t, "awaria_7d"].mean()),
        }
        katalog = zapisz_v3(v3, metryki)
        ustaw_current(metryki)
        print("zapisano", katalog)
        if z_mlflow:
            zapisz_mlflow(v3, metryki, katalog, oz, ob, ci)


def zapisz_v3(v3, metryki: dict) -> Path:
    from api.ai.failure_model.evals.ewaluacja_v2 import KATALOG_WERSJI

    katalog = KATALOG_WERSJI / v3.wersja
    v3.zapisz(katalog / "model.joblib")
    (katalog / "metryki.json").write_text(
        json.dumps(metryki, ensure_ascii=False, indent=2, default=float), encoding="utf-8"
    )
    return katalog


def ustaw_current(metryki: dict) -> None:
    from api.ai.failure_model.base import SCIEZKA_CURRENT

    o = metryki["test_3_alarmy"]
    r = metryki["test_ranking"]
    b = metryki["baseline_3_alarmy"]
    d = metryki["porownanie_trybu_serwisowego"]["precyzja_z_minus_bez"]
    tresc = {
        "wersja": "v3_punkt_pracy",
        "model": "versions/v3_punkt_pracy/model.joblib",
        "klasa": "api.ai.failure_model.versions.v3_punkt_pracy.model.ModelPunktPracy",
        "ustalono": date.today().isoformat(),
        "regula_wyboru": (
            "Polecenie użytkownika z 2026-11-16: „zapisz aktywną wersję jako versions/v3_punkt_pracy/ i ustaw ją "
            "w current.yaml”. Wariant cech wybrany regułą ustaloną przed porównaniem "
            "(maintenance_bc/tryb_serwisowy.py): "
            "okna serwisowe zostają w cechach tylko wtedy, gdy precyzja przy 3 alarmach rośnie, a 95% CI różnicy "
            f"nie obejmuje 0. Wybrano: {metryki['wariant_cech']}."
        ),
        "punkt_pracy": (
            f"maintenance_bc/alarmy_wind.wybierz_alarmy: {metryki['punkt_pracy']['alarmy_na_tydzien']} windy o "
            "najwyższym ryzyku (`predict`) w poniedziałek 06:00, przerwa "
            f"{metryki['punkt_pracy']['przerwa_dni']} dni (maintenance_bc/zalozenia.yaml); prawdopodobieństwo "
            "awarii w 7 dni: `prawdopodobienstwo` (izotonia na walidacji), próg opłacalności p* w "
            "maintenance_bc/wartosc_alarmow.py"
        ),
        "uzasadnienie": (
            f"Test 2026-01-05 – 2026-09-21 (38 poniedziałków), 3 alarmy / tydzień: {int(o['alarmy'])} alarmów, "
            f"{int(o['trafne'])} trafnych (precyzja {proc(o['precyzja'])}), czułość {proc(o['czulosc'])}, wartość "
            f"{pl(metryki['test_3_alarmy_wartosc_pln'])} PLN; ranking: ROC AUC {pl(r['roc_auc'], 3)}, PR-AUC "
            f"{pl(r['pr_auc'], 3)}. Baseline (reguła drzwi_ponowne_otwarcia_do_normy_24h) przy 3 alarmach: precyzja "
            f"{proc(b['precyzja'])}; przewaga modelu w precyzji i PLN niepotwierdzona (docs/b4_punkt_pracy.md). "
            f"Cechy z oknami serwisowymi: precyzja modelu z − bez {pp((d, d)).split(' … ')[0]} "
            f"(95% CI {pp(metryki['porownanie_trybu_serwisowego']['precyzja_ci'])})."
        ),
        "ograniczenia": (
            "Model bazowy uczony na danych do 2025-06. Przewaga nad regułą drzwi przy 3 alarmach nie jest "
            "potwierdzona (95% CI obejmuje 0). Kalibracja na tej samej walidacji, która wybrała liczbę drzew."
        ),
        "poprzednia": "brak (current.yaml był pusty)",
    }
    naglowek = "# Wersja modelu alertów o awariach wind używana obecnie (katalog w versions/); base.wczytaj_obecny().\n"
    SCIEZKA_CURRENT.write_text(
        naglowek + yaml.safe_dump(tresc, allow_unicode=True, sort_keys=False, width=118), encoding="utf-8"
    )


def zapisz_mlflow(v3, metryki, katalog, oz, ob, ci) -> None:
    from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run

    ustaw_eksperyment("windy")
    zapisz_run(
        v3.wersja,
        {
            "wersja": v3.wersja,
            "wariant_cech": metryki["wariant_cech"],
            "model_bazowy": metryki["model_bazowy"],
            "liczba_drzew": metryki["liczba_drzew"],
            **{f"punkt_pracy_{k}": v for k, v in metryki["punkt_pracy"].items()},
        },
        {
            "test_3_alarmy_precyzja": metryki["test_3_alarmy"]["precyzja"],
            "test_3_alarmy_czulosc": metryki["test_3_alarmy"]["czulosc"],
            "test_3_alarmy_wartosc_pln": metryki["test_3_alarmy_wartosc_pln"],
            "test_roc_auc": metryki["test_ranking"]["roc_auc"],
            "test_pr_auc": metryki["test_ranking"]["pr_auc"],
            "z_serwisem_precyzja": oz["precyzja"],
            "bez_serwisu_precyzja": ob["precyzja"],
            "z_minus_bez_precyzja_lo": ci["model"]["precyzja"][0],
            "z_minus_bez_precyzja_hi": ci["model"]["precyzja"][1],
        },
        {"model": "failure_model", "wersja": v3.wersja},
        [katalog / "metryki.json"],
    )


if __name__ == "__main__":
    if "--buduj" in sys.argv:
        zbuduj_wariant()
    else:
        main(zapisz="--zapisz" in sys.argv, z_mlflow="--bez-mlflow" not in sys.argv)
