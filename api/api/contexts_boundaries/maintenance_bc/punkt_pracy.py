"""Punkt pracy alarmów wind: reguła `alarmy_wind.wybierz_alarmy` na wynikach v2b_lgbm_czas_winda w okresie testowym
(2026-01-01 – 2026-09-22, poniedziałki 2026-01-05 – 2026-09-21). Wyniki: docs/b4_punkt_pracy.md.

Porównujemy tę samą regułę (3 windy w poniedziałek, przerwa 7 dni) z różnymi rankingami ryzyka:
- model: v2b_lgbm_czas_winda (`versions/v2b_lgbm_czas_winda/model.joblib`, bez douczania);
- baseline: reguła `drzwi_ponowne_otwarcia_do_normy_24h` (ta sama co w evals/porownanie.md);
- losowo: ranking losowy (LOSOWAN symulacji, średnia i 2,5–97,5 percentyl);
- wyrocznia: ranking = `awaria_7d` (wiedza o przyszłości; górna granica przy 3 alarmach tygodniowo);
- model bez przerwy (`przerwa_dni = 0`; tak samo działa „odstęp ≥ 7 dni”, bo alarmy są co 7 dni).
95% CI: bootstrap tygodni (BOOTSTRAP losowań 38 tygodni ze zwracaniem, te same dla modelu i baseline).
Uruchomienie (z api/): `python -m api.contexts_boundaries.maintenance_bc.punkt_pracy` (drukuje tabele Markdown).
"""

import numpy as np
import pandas as pd
from api.contexts_boundaries.maintenance_bc.alarmy_wind import (
    PODZESPOLY_Z_SYGNALEM,
    ocen_alarmy,
    wczytaj_zalozenia,
    wybierz_alarmy,
)

LOSOWAN = 1000
BOOTSTRAP = 10000
ZIARNO = 2026

# te same awarie i ten sam start co dni_wind.sql (CTE `awarie`)
SQL_AWARIE = """
SELECT id_awarii, id_windy, podzespol,
    coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS start_tz
FROM awarie_odtworzone
"""


def dane():
    """(test: wiersze dni_wind z cechami i kolumnami ryzyko_model / ryzyko_regula, awarie)."""
    from api.adapters.duckdb_baza import polacz
    from api.ai.failure_model.base import ModelWind
    from api.ai.failure_model.evals.ewaluacja_v2 import (
        KATALOG_WERSJI,
        REGULA,
        podzial_czas_winda,
        wynik_reguly,
    )
    from api.ai.features.windy.zbior import wczytaj_zbior

    con = polacz()
    df, _ = wczytaj_zbior(con)
    maski, poza = podzial_czas_winda(df)
    test = df[maski["test"]].copy()
    model = ModelWind.wczytaj(KATALOG_WERSJI / "v2b_lgbm_czas_winda" / "model.joblib")
    test["ryzyko_model"] = model.predict(test)
    test["ryzyko_regula"] = wynik_reguly(test[REGULA].to_numpy())
    test["winda_niewidziana"] = test["id_windy"].isin(poza)
    cel = con.execute("SELECT id_windy, dzien, godziny_do_startu FROM dni_wind").df()
    cel["dzien"] = pd.to_datetime(cel["dzien"])
    test = test.merge(cel, on=["id_windy", "dzien"], how="left", validate="1:1")
    awarie = con.execute(SQL_AWARIE).df()
    return test, awarie


def ranking(test: pd.DataFrame, kolumna: str) -> pd.DataFrame:
    return test[["id_windy", "dzien"]].assign(ryzyko=test[kolumna].to_numpy())


def uruchom(test, awarie, kolumna, poniedzialki, z, przerwa_dni=None) -> dict:
    przerwa = z["przerwa_dni"] if przerwa_dni is None else przerwa_dni
    alarmy = wybierz_alarmy(ranking(test, kolumna), z["alarmy_na_tydzien"], przerwa, z["dzien_alarmu"])
    return ocen_alarmy(alarmy, awarie, poniedzialki)


def sprawdz_z_dni_wind(wynik: dict, test: pd.DataFrame) -> None:
    """Trafność i wyprzedzenie z `ocen_alarmy` muszą się zgadzać z dni_wind.awaria_7d / godziny_do_startu."""
    al = wynik["alarmy"].merge(test, left_on=["id_windy", "dzien"], right_on=["id_windy", "dzien"], how="left")
    assert (al["trafny"].astype(int) == al["awaria_7d"]).all(), "trafny ≠ dni_wind.awaria_7d"
    t = al[al["trafny"]]
    assert np.allclose(t["wyprzedzenie_h"].round(2), t["godziny_do_startu"]), "wyprzedzenie ≠ godziny_do_startu"


def losowo(test, awarie, poniedzialki, z) -> dict:
    rng = np.random.default_rng(ZIARNO)
    wyniki = []
    for _ in range(LOSOWAN):
        t = test[["id_windy", "dzien"]].assign(los=rng.random(len(test)))
        wyniki.append(uruchom(t, awarie, "los", poniedzialki, z)["ogolem"])
    w = pd.DataFrame(wyniki)
    return {k: (w[k].mean(), w[k].quantile(0.025), w[k].quantile(0.975)) for k in w.columns}


def bootstrap(tyg_a: pd.DataFrame, tyg_b: pd.DataFrame) -> dict:
    """95% CI precyzji i czułości dla a i b oraz różnicy a − b (te same losowania tygodni)."""
    rng = np.random.default_rng(ZIARNO)
    n = len(tyg_a)
    idx = rng.integers(0, n, size=(BOOTSTRAP, n))

    def miary(t):
        s = {
            k: t[k].to_numpy()[idx].sum(axis=1)
            for k in ("alarmy", "trafne", "awarie", "zlapane", "awarie_sygnal", "zlapane_sygnal")
        }
        return {
            "precyzja": s["trafne"] / s["alarmy"],
            "czulosc": s["zlapane"] / s["awarie"],
            "czulosc_sygnal": s["zlapane_sygnal"] / s["awarie_sygnal"],
        }

    a, b = miary(tyg_a), miary(tyg_b)
    q = lambda x: (float(np.quantile(x, 0.025)), float(np.quantile(x, 0.975)))  # noqa: E731
    return {k: {"a": q(a[k]), "b": q(b[k]), "a_minus_b": q(a[k] - b[k])} for k in a}


# --- formatowanie -------------------------------------------------------------------------------------------


def pl(x: float, miejsca: int = 1) -> str:
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def proc(x: float, miejsca: int = 1) -> str:
    return f"{pl(100 * x, miejsca)}%"


def przedzial(lo_hi: tuple[float, float], znak: bool = False) -> str:
    """95% CI; znak=True: różnica w punktach procentowych (pp) ze znakiem."""
    f = (lambda v: ("+" if v >= 0 else "−") + pl(100 * abs(v)) + " pp") if znak else proc  # noqa: E731
    return f"{f(lo_hi[0])} … {f(lo_hi[1])}"


def tabela_rozkladu(wyniki: dict[str, dict]) -> str:
    """Ile tygodni miało 0, 1, 2, 3 trafne alarmy."""
    wiersze = ["| ranking ryzyka | 0 / 3 | 1 / 3 | 2 / 3 | 3 / 3 |", "|---|---:|---:|---:|---:|"]
    for nazwa, (w, _) in wyniki.items():
        n = w["tygodnie"]["trafne"].value_counts()
        wiersze.append(f"| {nazwa} | " + " | ".join(str(int(n.get(k, 0))) for k in range(4)) + " |")
    return "\n".join(wiersze)


def tabela_ogolem(wyniki: dict[str, dict], ci: dict, los: dict) -> str:
    wiersze = [
        "| ranking ryzyka | alarmy | trafne | precyzja | awarie | złapane | czułość | awarie z sygnałem | "
        "złapane z sygnałem | czułość z sygnałem | mediana wyprzedzenia (h) | różne windy z alarmem |",
        "|---|---:|---:|---|---:|---:|---|---:|---:|---|---:|---:|",
    ]
    for nazwa, (w, klucz) in wyniki.items():
        o = w["ogolem"]
        c = ci.get(klucz, {})
        f = lambda m: proc(o[m]) + (f" ({przedzial(c[m])})" if m in c else "")  # noqa: E731
        wiersze.append(
            f"| {nazwa} | {o['alarmy']} | {o['trafne']} | {f('precyzja')} | {o['awarie']} | {o['zlapane']} | "
            f"{f('czulosc')} | {o['awarie_sygnal']} | {o['zlapane_sygnal']} | {f('czulosc_sygnal')} | "
            f"{pl(o['mediana_wyprzedzenia_h'])} | {w['alarmy']['id_windy'].nunique()} |"
        )
    o = los
    wiersze.append(
        f"| losowo (średnia z {LOSOWAN}; 2,5–97,5 percentyl) | {pl(o['alarmy'][0], 0)} | {pl(o['trafne'][0])} | "
        f"{proc(o['precyzja'][0])} ({proc(o['precyzja'][1])} … {proc(o['precyzja'][2])}) | {pl(o['awarie'][0], 0)} | "
        f"{pl(o['zlapane'][0])} | {proc(o['czulosc'][0])} ({proc(o['czulosc'][1])} … {proc(o['czulosc'][2])}) | "
        f"{pl(o['awarie_sygnal'][0], 0)} | {pl(o['zlapane_sygnal'][0])} | {proc(o['czulosc_sygnal'][0])} "
        f"({proc(o['czulosc_sygnal'][1])} … {proc(o['czulosc_sygnal'][2])}) | "
        f"{pl(o['mediana_wyprzedzenia_h'][0])} | — |"
    )
    return "\n".join(wiersze)


def opis_alarmow(al: pd.DataFrame) -> str:
    czesci = []
    for _, a in al.sort_values("pozycja").iterrows():
        if a["trafny"]:
            czesci.append(f"{a['id_windy']} ✓ {pl(a['wyprzedzenie_h'], 0)} h, {a['podzespol']}")
        else:
            czesci.append(f"{a['id_windy']} ✗")
    return "; ".join(czesci)


def tabela_tygodni(model: dict, regula: dict) -> str:
    tm, tr = model["tygodnie"].set_index("tydzien"), regula["tygodnie"].set_index("tydzien")
    wiersze = [
        "| tydzień (pon. 06:00) | alarmy modelu (✓ trafny: godziny do startu, podzespół) | trafne | awarie | "
        "złapane | z sygnałem | złapane z sygnałem | trafne reguły | złapane reguły |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    al = model["alarmy"]
    for d, w in tm.iterrows():
        wiersze.append(
            f"| {d:%Y-%m-%d} | {opis_alarmow(al[al['dzien'] == d])} | {w['trafne']} / {w['alarmy']} | {w['awarie']} | "
            f"{w['zlapane']} | {w['awarie_sygnal']} | {w['zlapane_sygnal']} | {tr.loc[d, 'trafne']} / "
            f"{tr.loc[d, 'alarmy']} | {tr.loc[d, 'zlapane']} |"
        )
    s, r = tm.sum(), tr.sum()
    wiersze.append(
        f"| **razem** | | **{s['trafne']} / {s['alarmy']}** | **{s['awarie']}** | **{s['zlapane']}** | "
        f"**{s['awarie_sygnal']}** | **{s['zlapane_sygnal']}** | **{r['trafne']} / {r['alarmy']}** | "
        f"**{r['zlapane']}** |"
    )
    return "\n".join(wiersze)


def tabela_podzespolow(wyniki: dict[str, dict]) -> str:
    nazwy = list(wyniki)
    aw = next(iter(wyniki.values()))[0]["awarie"]
    wiersze = [
        "| podzespół | z sygnałem | awarie | " + " | ".join(f"złapane: {n}" for n in nazwy) + " |",
        "|---|---|---:|" + "---:|" * len(nazwy),
    ]
    for p in aw["podzespol"].value_counts().index:
        komorki = []
        for w, _ in wyniki.values():
            a = w["awarie"]
            komorki.append(str(int(a.loc[a["podzespol"] == p, "zlapana"].sum())))
        sygnal = "tak" if p in PODZESPOLY_Z_SYGNALEM else "nie"
        wiersze.append(f"| {p} | {sygnal} | {int((aw['podzespol'] == p).sum())} | " + " | ".join(komorki) + " |")
    return "\n".join(wiersze)


def tabela_wyprzedzenia(wyniki: dict[str, dict]) -> str:
    wiersze = [
        "| ranking ryzyka | trafne | min | kwartyl 1 | mediana | kwartyl 3 | max | do 24 h |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for nazwa, (w, _) in wyniki.items():
        x = w["alarmy"]["wyprzedzenie_h"].dropna()
        wiersze.append(
            f"| {nazwa} | {len(x)} | {pl(x.min())} | {pl(x.quantile(0.25))} | {pl(x.median())} | "
            f"{pl(x.quantile(0.75))} | {pl(x.max())} | {int((x <= 24).sum())} |"
        )
    return "\n".join(wiersze)


def main() -> None:
    z = wczytaj_zalozenia()
    test, awarie = dane()
    dni = pd.Series(sorted(test["dzien"].unique()))
    poniedzialki = list(dni[dni.dt.day_of_week == z["dzien_alarmu"]])

    model = uruchom(test, awarie, "ryzyko_model", poniedzialki, z)
    regula = uruchom(test, awarie, "ryzyko_regula", poniedzialki, z)
    bez_przerwy = uruchom(test, awarie, "ryzyko_model", poniedzialki, z, przerwa_dni=0)
    wyrocznia = uruchom(test.assign(wyr=test["awaria_7d"].astype(float)), awarie, "wyr", poniedzialki, z)
    for w in (model, regula, bez_przerwy, wyrocznia):
        sprawdz_z_dni_wind(w, test)
    los = losowo(test, awarie, poniedzialki, z)
    ci = bootstrap(model["tygodnie"], regula["tygodnie"])

    from sklearn.metrics import average_precision_score

    print(
        "kontrola: PR-AUC modelu na teście", round(average_precision_score(test["awaria_7d"], test["ryzyko_model"]), 4)
    )
    print(
        f"poniedziałki: {len(poniedzialki)} ({poniedzialki[0]:%Y-%m-%d} – {poniedzialki[-1]:%Y-%m-%d}); "
        f"wiersze testu: {len(test)}, wiersze w poniedziałki: {int(test['dzien'].isin(poniedzialki).sum())}, "
        f"dodatnie w poniedziałki: {int(test.loc[test['dzien'].isin(poniedzialki), 'awaria_7d'].sum())}"
    )
    nie = model["alarmy"].merge(test[["id_windy", "dzien", "winda_niewidziana"]], on=["id_windy", "dzien"])
    print(
        "alarmy modelu na windach niewidzianych:",
        int(nie["winda_niewidziana"].sum()),
        "trafne:",
        int(nie.loc[nie["winda_niewidziana"], "trafny"].sum()),
    )
    aw = model["awarie"]
    print("awarie w zakresie:", len(aw), "od", aw["start_tz"].min(), "do", aw["start_tz"].max())

    wyniki = {
        "**model v2b_lgbm_czas_winda**": (model, "a"),
        "baseline: reguła `drzwi_ponowne_otwarcia_do_normy_24h`": (regula, "b"),
        "model bez przerwy (`przerwa_dni = 0`)": (bez_przerwy, "-"),
        "wyrocznia (zna `awaria_7d`)": (wyrocznia, "-"),
    }
    ci_tab = {"a": {k: v["a"] for k, v in ci.items()}, "b": {k: v["b"] for k, v in ci.items()}}
    print("\n## T1\n")
    print(tabela_ogolem(wyniki, ci_tab, los))
    print("\n## T2 model − baseline (bootstrap tygodni)\n")
    o_m, o_r = model["ogolem"], regula["ogolem"]
    print("| miara | model | baseline | model − baseline | 95% CI różnicy |\n|---|---|---|---|---|")
    for k, n in (
        ("precyzja", "precyzja"),
        ("czulosc", "czułość (wszystkie awarie)"),
        ("czulosc_sygnal", "czułość (awarie z sygnałem)"),
    ):
        d = o_m[k] - o_r[k]
        print(
            f"| {n} | {proc(o_m[k])} | {proc(o_r[k])} | {'+' if d >= 0 else '−'}{pl(abs(100 * d))} pp | "
            f"{przedzial(ci[k]['a_minus_b'], znak=True)} |"
        )
    print("\n## T3 tydzień po tygodniu\n")
    print(tabela_tygodni(model, regula))
    print("\n## T3b tygodnie według liczby trafnych alarmów\n")
    print(tabela_rozkladu({k: v for k, v in wyniki.items() if "wyrocznia" not in k}))
    print("\n## T4 podzespoły\n")
    print(tabela_podzespolow({k: v for k, v in wyniki.items() if "wyrocznia" not in k}))
    print("\n## T5 wyprzedzenie\n")
    print(tabela_wyprzedzenia(wyniki))


if __name__ == "__main__":
    main()
