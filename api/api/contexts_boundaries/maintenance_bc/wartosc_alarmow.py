"""Wartość alarmów wind w PLN, próg opłacalności p* i koszt limitu 3 alarmów tygodniowo (docs/b4_punkt_pracy.md).

Ekonomia (założenia użytkownika, zalozenia.yaml): trafny alarm = skutecznosc × koszt_awarii_ponad_planowa −
koszt_wizyty, fałszywy = − koszt_wizyty, p* = koszt_wizyty / (skutecznosc × koszt_awarii_ponad_planowa): alarm się
opłaca, gdy prawdopodobieństwo awarii w 7 dni >= p*. Wartość liczymy na alarmach (trafny jak w alarmy_wind.py).

Kalibracja: wynik v2b_lgbm_czas_winda (i reguły-baseline) nie jest skalibrowanym prawdopodobieństwem
(failure_model/base.py), więc p* stosujemy do ryzyka po regresji izotonicznej dopasowanej na walidacji
2025-07-01 – 2025-12-31 (112 wind; ta sama walidacja służyła do wczesnego zatrzymania). Test 2026 nie jest
używany do kalibracji. Ranking (limit k alarmów) robimy na surowym wyniku: izotonia jest monotoniczna, ale robi
remisy.

Uruchomienie (z api/): `python -m api.contexts_boundaries.maintenance_bc.wartosc_alarmow` (tabele Markdown + wykres
docs/img/b4_krzywa_wartosci.png).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from api.contexts_boundaries.maintenance_bc.alarmy_wind import (
    ocen_alarmy,
    wczytaj_zalozenia,
    wczytaj_zalozenia_pelne,
    wybierz_alarmy,
)
from sklearn.isotonic import IsotonicRegression

KATALOG_GLOWNY = Path(__file__).resolve().parents[4]
PLIK_WYKRESU = KATALOG_GLOWNY / "docs" / "img" / "b4_krzywa_wartosci.png"
TYGODNI_W_ROKU = 52  # skala roku: 52 poniedziałki z alarmem (decyzja metodyczna, nie założenie biznesowe)
MAKS_ALARMOW = 30  # zakres krzywej: 1 … 30 alarmów tygodniowo
BOOTSTRAP = 10000
ZIARNO = 2026


# --- ekonomia -----------------------------------------------------------------------------------------------


def ekonomia(z: dict, skutecznosc: float | None = None) -> dict[str, float]:
    """Wartość trafnego i fałszywego alarmu oraz p* (PLN, z założeń; skutecznosc nadpisuje założenie)."""
    s = z["skutecznosc"] if skutecznosc is None else skutecznosc
    uniknieta = s * z["koszt_awarii_ponad_planowa"]
    return {
        "skutecznosc": s,
        "trafny": uniknieta - z["koszt_wizyty"],
        "falszywy": -float(z["koszt_wizyty"]),
        "prog": z["koszt_wizyty"] / uniknieta,
    }


def wartosc(trafne, alarmy, ekon: dict):
    """Wartość w PLN: trafne × wartość trafnego + (alarmy − trafne) × wartość fałszywego (działa na tablicach)."""
    trafne, alarmy = np.asarray(trafne, dtype=float), np.asarray(alarmy, dtype=float)
    return trafne * ekon["trafny"] + (alarmy - trafne) * ekon["falszywy"]


def kalibruj(wynik_walid: np.ndarray, y_walid: np.ndarray) -> IsotonicRegression:
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(wynik_walid, y_walid)


# --- dane i przebiegi ---------------------------------------------------------------------------------------


def dane():
    """(walid, test, awarie): wiersze dni_wind z kolumnami wynik_model, wynik_regula (+ p_model, p_regula w teście
    i walidacji po kalibracji na walidacji)."""
    from api.adapters.duckdb_baza import polacz
    from api.ai.failure_model.base import ModelWind
    from api.ai.failure_model.evals.ewaluacja_v2 import KATALOG_WERSJI, REGULA, podzial_czas_winda
    from api.ai.features.windy.zbior import wczytaj_zbior
    from api.contexts_boundaries.maintenance_bc.punkt_pracy import SQL_AWARIE

    con = polacz()
    df, _ = wczytaj_zbior(con)
    maski, _ = podzial_czas_winda(df)
    model = ModelWind.wczytaj(KATALOG_WERSJI / "v2b_lgbm_czas_winda" / "model.joblib")
    czesci = {}
    for nazwa in ("walidacja", "test"):
        z = df[maski[nazwa]].copy()
        z["wynik_model"] = model.predict(z)
        czesci[nazwa] = z
    # brak pomiaru reguły = najniżej; minimum wspólne dla walidacji i testu, żeby kalibracja pasowała do testu
    minimum = np.nanmin(np.concatenate([czesci[n][REGULA].to_numpy(dtype=float) for n in czesci]))
    for z in czesci.values():
        z["wynik_regula"] = np.where(z[REGULA].isna(), minimum - 1, z[REGULA].to_numpy(dtype=float))
    walid, test = czesci["walidacja"], czesci["test"]
    for k in ("model", "regula"):
        iso = kalibruj(walid[f"wynik_{k}"].to_numpy(), walid["awaria_7d"].to_numpy())
        for z in (walid, test):
            z[f"p_{k}"] = iso.predict(z[f"wynik_{k}"].to_numpy())
    return walid, test, con.execute(SQL_AWARIE).df()


def przebieg(test, awarie, poniedzialki, z, kolumna, limit=None, prog=None, przerwa_dni=None) -> dict:
    przerwa = z["przerwa_dni"] if przerwa_dni is None else przerwa_dni
    r = test[["id_windy", "dzien"]].assign(ryzyko=test[kolumna].to_numpy())
    alarmy = wybierz_alarmy(r, limit, przerwa, z["dzien_alarmu"], prog=prog)
    return ocen_alarmy(alarmy, awarie, poniedzialki)


def krzywa(test, awarie, poniedzialki, z, kolumna) -> pd.DataFrame:
    wiersze = []
    for k in range(1, MAKS_ALARMOW + 1):
        o = przebieg(test, awarie, poniedzialki, z, kolumna, limit=k)["ogolem"]
        wiersze.append({"k": k, "alarmy": o["alarmy"], "trafne": o["trafne"], "zlapane": o["zlapane"]})
    return pd.DataFrame(wiersze)


def bootstrap_roznicy(tyg_a: pd.DataFrame, tyg_b: pd.DataFrame, ekon: dict) -> tuple[float, float]:
    """95% CI różnicy wartości a − b (PLN w teście), bootstrap tygodni (te same losowania)."""
    rng = np.random.default_rng(ZIARNO)
    idx = rng.integers(0, len(tyg_a), size=(BOOTSTRAP, len(tyg_a)))
    wa = wartosc(tyg_a["trafne"].to_numpy(), tyg_a["alarmy"].to_numpy(), ekon)
    wb = wartosc(tyg_b["trafne"].to_numpy(), tyg_b["alarmy"].to_numpy(), ekon)
    d = (wa - wb)[idx].sum(axis=1)
    return float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))


# --- formatowanie -------------------------------------------------------------------------------------------


def pl(x: float, miejsca: int = 0) -> str:
    s = f"{abs(x):,.{miejsca}f}".replace(",", " ").replace(".", ",")
    return ("−" if x < 0 else "") + s


def kalibracja_tabela(test: pd.DataFrame, walid: pd.DataFrame) -> str:
    """Kalibracja na teście: przedziały p_model, średnie p vs odsetek awarii."""
    granice = [0, 0.02, 0.05, 0.1, 0.191176, 0.3, 1.0001]
    wiersze = [
        "| p (skalibrowane) | wiersze testu | średnie p | odsetek `awaria_7d` | wiersze w poniedziałki |",
        "|---|---:|---:|---:|---:|",
    ]
    przedzial = pd.cut(test["p_model"], granice, right=False)
    pon = test["dzien"].dt.day_of_week == 0
    for b, g in test.groupby(przedzial, observed=True):
        lo, hi = b.left, min(b.right, 1.0)
        wiersze.append(
            f"| [{pl(lo, 3)}; {pl(hi, 3)}) | {pl(len(g))} | {pl(g['p_model'].mean(), 3)} | "
            f"{pl(g['awaria_7d'].mean(), 3)} | {int(pon[g.index].sum())} |"
        )
    wiersze.append(
        f"| **razem test** | {pl(len(test))} | {pl(test['p_model'].mean(), 4)} | {pl(test['awaria_7d'].mean(), 4)} | "
        f"{int(pon.sum())} |"
    )
    wiersze.append(
        f"| walidacja (dopasowanie) | {pl(len(walid))} | {pl(walid['p_model'].mean(), 4)} | "
        f"{pl(walid['awaria_7d'].mean(), 4)} | — |"
    )
    return "\n".join(wiersze)


def main() -> None:
    z = wczytaj_zalozenia()
    pelne = wczytaj_zalozenia_pelne()
    ekon = ekonomia(z)
    walid, test, awarie = dane()
    dni = pd.Series(sorted(test["dzien"].unique()))
    poniedzialki = list(dni[dni.dt.day_of_week == z["dzien_alarmu"]])
    tyg = len(poniedzialki)
    skala = TYGODNI_W_ROKU / tyg
    skladniki = pelne["koszt_awarii_ponad_planowa"]["skladniki"]
    assert sum(s["wartosc"] for s in skladniki.values()) == z["koszt_awarii_ponad_planowa"]

    print(
        f"ekonomia: trafny {ekon['trafny']:.2f} PLN, fałszywy {ekon['falszywy']:.2f} PLN, p* {ekon['prog']:.6f}; "
        f"tygodni {tyg}, skala roku {skala:.4f}"
    )
    for s in pelne["skutecznosc"]["zakres"]:
        e = ekonomia(z, s)
        print(f"  skuteczność {s}: trafny {e['trafny']:.2f}, p* {e['prog']:.6f}")

    from sklearn.metrics import brier_score_loss, roc_auc_score

    print(
        "kalibracja: Brier test surowy",
        round(brier_score_loss(test["awaria_7d"], test["wynik_model"]), 5),
        "skalibrowany",
        round(brier_score_loss(test["awaria_7d"], test["p_model"]), 5),
        "| średnia surowa",
        round(test["wynik_model"].mean(), 4),
        "| ROC AUC p_model",
        round(roc_auc_score(test["awaria_7d"], test["p_model"]), 4),
        "| odsetek walidacji",
        round(walid["awaria_7d"].mean(), 4),
    )

    # przebiegi: 3 alarmy (limit), p* bez limitu (z przerwą i bez), dla modelu i reguły
    wyniki = {}
    for nazwa, kol, p_kol in (("model", "wynik_model", "p_model"), ("regula", "wynik_regula", "p_regula")):
        wyniki[(nazwa, "limit3")] = przebieg(test, awarie, poniedzialki, z, kol, limit=z["alarmy_na_tydzien"])
        for s in (z["skutecznosc"], *pelne["skutecznosc"]["zakres"]):
            e = ekonomia(z, s)
            wyniki[(nazwa, f"prog_{s}")] = przebieg(test, awarie, poniedzialki, z, p_kol, prog=e["prog"])
        wyniki[(nazwa, "prog_bez_przerwy")] = przebieg(
            test, awarie, poniedzialki, z, p_kol, prog=ekon["prog"], przerwa_dni=0
        )

    print("\n## W1 punkty pracy\n")
    print(
        "| ranking | reguła alarmu | alarmy | alarmy / tydzień (min–max) | trafne | precyzja | średnie p alarmów | "
        "złapane awarie (z 322) | wartość w teście (PLN) | wartość w skali roku (PLN) |"
    )
    print("|---|---|---:|---|---:|---:|---:|---:|---:|---:|")
    opisy = {
        "limit3": "3 alarmy w poniedziałek, przerwa 7 dni",
        f"prog_{z['skutecznosc']}": "p >= p* bez limitu, przerwa 7 dni",
        "prog_bez_przerwy": "p >= p* bez limitu, bez przerwy",
    }
    for nazwa, kol_p in (("model", "p_model"), ("regula", "p_regula")):
        for wariant, opis in opisy.items():
            w = wyniki[(nazwa, wariant)]
            o, t = w["ogolem"], w["tygodnie"]
            al = w["alarmy"].merge(test[["id_windy", "dzien", kol_p]], on=["id_windy", "dzien"])
            v = wartosc(o["trafne"], o["alarmy"], ekon)
            print(
                f"| {nazwa} | {opis} | {o['alarmy']} | {pl(o['alarmy'] / tyg, 1)} ({t['alarmy'].min()}–"
                f"{t['alarmy'].max()}) | {o['trafne']} | {pl(100 * o['precyzja'], 1)}% | {pl(al[kol_p].mean(), 3)} | "
                f"{o['zlapane']} | {pl(float(v))} | {pl(float(v) * skala)} |"
            )

    # krzywe
    k_model = krzywa(test, awarie, poniedzialki, z, "wynik_model")
    k_regula = krzywa(test, awarie, poniedzialki, z, "wynik_regula")
    for kr in (k_model, k_regula):
        kr["wartosc"] = wartosc(kr["trafne"], kr["alarmy"], ekon)
        for s in pelne["skutecznosc"]["zakres"]:
            kr[f"wartosc_{s}"] = wartosc(kr["trafne"], kr["alarmy"], ekonomia(z, s))
    print("\n## W2 krzywa (model / reguła)\n")
    print(
        "| alarmy / tydzień | model: trafne / alarmy | model: wartość (PLN) | reguła: trafne / alarmy | "
        "reguła: wartość (PLN) |"
    )
    print("|---:|---:|---:|---:|---:|")
    for (_, a), (_, b) in zip(k_model.iterrows(), k_regula.iterrows(), strict=True):
        print(
            f"| {int(a['k'])} | {int(a['trafne'])} / {int(a['alarmy'])} | {pl(a['wartosc'])} | "
            f"{int(b['trafne'])} / {int(b['alarmy'])} | "
            f"{pl(b['wartosc'])} |"
        )
    best = k_model.loc[k_model["wartosc"].idxmax()]
    print("najlepsze k modelu:", int(best["k"]), best["wartosc"])

    # koszt limitu i wrażliwość
    w3 = wyniki[("model", "limit3")]["ogolem"]
    v3 = float(wartosc(w3["trafne"], w3["alarmy"], ekon))
    print("\n## W3 koszt limitu i wrażliwość\n")
    print(
        "| skuteczność | p* | wartość trafnego (PLN) | model, 3 / tydz.: wartość w teście | "
        "model, p*: alarmy / tydz. | "
        "model, p*: precyzja | model, p*: wartość w teście | koszt limitu w teście | koszt limitu w skali roku | "
        "najlepsze k na krzywej (wartość w teście) |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for s in (z["skutecznosc"], *pelne["skutecznosc"]["zakres"]):
        e = ekonomia(z, s)
        w = wyniki[("model", f"prog_{s}")]["ogolem"]
        v_lim = float(wartosc(w3["trafne"], w3["alarmy"], e))
        v_p = float(wartosc(w["trafne"], w["alarmy"], e))
        col = "wartosc" if s == z["skutecznosc"] else f"wartosc_{s}"
        b = k_model.loc[k_model[col].idxmax()]
        print(
            f"| {pl(s, 2)} | {pl(e['prog'], 3)} | {pl(e['trafny'])} | {pl(v_lim)} | {pl(w['alarmy'] / tyg, 1)} | "
            f"{pl(100 * w['precyzja'], 1)}% | {pl(v_p)} | {pl(v_p - v_lim)} | {pl((v_p - v_lim) * skala)} | "
            f"{int(b['k'])} ({pl(b[col])}) |"
        )

    # model − reguła (bootstrap tygodni)
    print("\n## W4 model − reguła\n")
    print("| reguła alarmu | model (PLN) | reguła (PLN) | model − reguła | 95% CI |\n|---|---:|---:|---:|---|")
    for wariant, opis in (("limit3", "3 alarmy / tydzień"), (f"prog_{z['skutecznosc']}", "p >= p* bez limitu")):
        a, b = wyniki[("model", wariant)], wyniki[("regula", wariant)]
        va = float(wartosc(a["ogolem"]["trafne"], a["ogolem"]["alarmy"], ekon))
        vb = float(wartosc(b["ogolem"]["trafne"], b["ogolem"]["alarmy"], ekon))
        lo, hi = bootstrap_roznicy(a["tygodnie"], b["tygodnie"], ekon)
        print(f"| {opis} | {pl(va)} | {pl(vb)} | {pl(va - vb)} | {pl(lo)} … {pl(hi)} |")

    print("\n## W5 kalibracja (test)\n")
    print(kalibracja_tabela(test, walid))

    rysuj(k_model, k_regula, wyniki, ekon, z, pelne, tyg, v3)


# kolory: sloty 1–2 palety referencyjnej (skill dataviz; walidator: CVD ΔE 24,7, kontrast >= 3:1), tekst neutralny
KOLOR_MODEL = "#2a78d6"
KOLOR_REGULA = "#eb6834"
TEKST = "#0b0b0b"
TEKST_2 = "#52514e"
TLO = "#fcfcfb"


def rysuj(k_model, k_regula, wyniki, ekon, z, pelne, tyg, v3) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lo, hi = pelne["skutecznosc"]["zakres"]
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=150, facecolor=TLO)
    ax.set_facecolor(TLO)
    ax.fill_between(
        k_model["k"],
        k_model[f"wartosc_{lo}"] / 1000,
        k_model[f"wartosc_{hi}"] / 1000,
        color=KOLOR_MODEL,
        alpha=0.13,
        linewidth=0,
        label=f"model przy skuteczności {pl(lo, 2)}–{pl(hi, 2)}",
    )
    ax.plot(k_model["k"], k_model["wartosc"] / 1000, color=KOLOR_MODEL, linewidth=2, label="model v2b_lgbm_czas_winda")
    ax.plot(
        k_regula["k"],
        k_regula["wartosc"] / 1000,
        color=KOLOR_REGULA,
        linewidth=2,
        linestyle=(0, (5, 3)),
        label="baseline: reguła ponownych otwarć drzwi",
    )
    ax.axhline(0, color=TEKST_2, linewidth=0.8)
    # punkt: limit 3 alarmów (na krzywej modelu)
    k3 = z["alarmy_na_tydzien"]
    ax.scatter([k3], [v3 / 1000], s=64, color=KOLOR_MODEL, edgecolor=TLO, linewidth=2, zorder=5)
    ax.annotate(
        f"limit {k3} / tydz.: {pl(v3 / 1000, 1)} tys. PLN",
        (k3, v3 / 1000),
        textcoords="offset points",
        xytext=(24, -78),
        fontsize=9,
        color=TEKST,
        arrowprops={"arrowstyle": "-", "color": TEKST_2, "linewidth": 0.8},
    )
    # punkt: p* bez limitu (liczba alarmów zmienia się z tygodnia na tydzień; x = średnia)
    w = wyniki[("model", f"prog_{z['skutecznosc']}")]["ogolem"]
    vp = float(wartosc(w["trafne"], w["alarmy"], ekon))
    x = w["alarmy"] / tyg
    ax.scatter([x], [vp / 1000], s=72, marker="D", color=TEKST, edgecolor=TLO, linewidth=2, zorder=6)
    ax.annotate(
        f"p ≥ p* = {pl(ekon['prog'], 3)}, bez limitu:\nśr. {pl(x, 1)} alarmu / tydz., {pl(vp / 1000, 1)} tys. PLN",
        (x, vp / 1000),
        textcoords="offset points",
        xytext=(16, 14),
        fontsize=9,
        color=TEKST,
        arrowprops={"arrowstyle": "-", "color": TEKST_2, "linewidth": 0.8},
    )
    trafny = f"{pl(z['skutecznosc'], 2)} × {pl(z['koszt_awarii_ponad_planowa'])} − {pl(z['koszt_wizyty'])}"
    ax.set_title(
        f"Wartość alarmów wind w teście ({tyg} poniedziałków 2026)\n"
        f"trafny alarm = {trafny} PLN, fałszywy = −{pl(z['koszt_wizyty'])} PLN",
        fontsize=11,
        color=TEKST,
        loc="left",
    )
    ax.set_xlabel("alarmy w tygodniu (poniedziałek 06:00, przerwa 7 dni)", color=TEKST_2)
    ax.set_ylabel("wartość, tys. PLN", color=TEKST_2)
    ax.set_xlim(0.5, MAKS_ALARMOW + 0.5)
    ax.tick_params(colors=TEKST_2)
    ax.grid(color=TEKST_2, alpha=0.15, linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(TEKST_2)
    ax.legend(loc="lower left", fontsize=9, frameon=False, labelcolor=TEKST)
    fig.tight_layout()
    PLIK_WYKRESU.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLIK_WYKRESU, facecolor=TLO)
    print("wykres:", PLIK_WYKRESU)


if __name__ == "__main__":
    main()
