"""Trafność listy podejrzanych podzespołów (maintenance_bc/wyjasnienie.py) wobec baseline na teście v2b.

Wiersze: dni testu (2026-01-01 – 2026-09-22) z awarią w 7 dni (`awaria_7d = 1`), której pierwsza awaria w oknie
ma podzespół z sygnałem (drzwi, naped, hamulec_liny, sterownik; `dni_wind.podzespol`). Dodatkowo podzbiór: trafne
alarmy reguły (poniedziałek, 3 windy, przerwa 7 dni) — to te wiersze trafiają do Serwisownika.
- Model: lista z `explain` aktywnej wersji (current.yaml) i podzespoly_sygnalow.yaml (`podzespoly_z_wkladow`).
- Baseline: stała lista podzespołów według częstości na treningu (2023-03-01 – 2025-06-30, te same warunki wierszy).
Miary: trafienie na 1. miejscu (pierwszy podzespół = faktyczny), „w liście” (faktyczny gdziekolwiek na liście modelu)
i to samo dla baseline przy tej samej długości listy co model w danym wierszu (uczciwe porównanie: dłuższa lista
łatwiej trafia), średnia długość listy. 95% CI różnic: bootstrap awarii (`id_awarii`, 2 000 losowań), bo dni tej
samej awarii są zależne.
Uruchomienie: `cd api && poetry run python -m api.ai.failure_model.evals.podzespoly` (wynik: docs/b4_ryzyko_dzienne.md).
"""

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polaczenie
from api.ai.failure_model.base import wczytaj_obecny
from api.ai.failure_model.evals.ewaluacja_v2 import TEST, TRENING
from api.ai.features.windy.zbior import wczytaj_zbior
from api.contexts_boundaries.maintenance_bc.alarmy_wind import PODZESPOLY_Z_SYGNALEM, wczytaj_zalozenia, wybierz_alarmy
from api.contexts_boundaries.maintenance_bc.wyjasnienie import podzespoly_z_wkladow

LOSOWAN = 2_000
ZIARNO = 7


def miary(df: pd.DataFrame, lista_modelu: list[list[str]], kolejnosc_baseline: list[str]) -> pd.DataFrame:
    """Wiersz na dzień: trafienia modelu i baseline (1. miejsce, w liście tej samej długości)."""
    fakt = df["podzespol"].to_numpy()
    wyj = pd.DataFrame({"id_awarii": df["id_awarii"].to_numpy(), "podzespol": fakt})
    wyj["dlugosc"] = [len(lista) for lista in lista_modelu]
    wyj["model_1"] = [bool(lista) and lista[0] == f for lista, f in zip(lista_modelu, fakt, strict=True)]
    wyj["model_lista"] = [f in lista for lista, f in zip(lista_modelu, fakt, strict=True)]
    wyj["baseline_1"] = fakt == kolejnosc_baseline[0]
    wyj["baseline_lista"] = [f in kolejnosc_baseline[:n] for f, n in zip(fakt, wyj["dlugosc"], strict=True)]
    return wyj


def bootstrap_roznicy(wyj: pd.DataFrame, a: str, b: str, ziarno: int = ZIARNO) -> tuple[float, float, float]:
    """Różnica odsetków a − b (pp) i 95% CI z bootstrapu awarii."""
    grupy = wyj.groupby("id_awarii")[[a, b]].agg(["sum", "count"])
    sa, sb, n = grupy[(a, "sum")].to_numpy(), grupy[(b, "sum")].to_numpy(), grupy[(a, "count")].to_numpy()
    rng = np.random.default_rng(ziarno)
    roznice = []
    for _ in range(LOSOWAN):
        i = rng.integers(0, len(n), len(n))
        roznice.append((sa[i].sum() - sb[i].sum()) / n[i].sum())
    lo, hi = np.percentile(roznice, [2.5, 97.5])
    return 100 * (sa.sum() - sb.sum()) / n.sum(), 100 * lo, 100 * hi


def podsumuj(wyj: pd.DataFrame, nazwa: str) -> dict:
    r1 = bootstrap_roznicy(wyj, "model_1", "baseline_1")
    rl = bootstrap_roznicy(wyj, "model_lista", "baseline_lista")
    return {
        "wiersze": nazwa,
        "dni": len(wyj),
        "awarie": wyj["id_awarii"].nunique(),
        "model_1": 100 * wyj["model_1"].mean(),
        "baseline_1": 100 * wyj["baseline_1"].mean(),
        "roznica_1": r1,
        "model_lista": 100 * wyj["model_lista"].mean(),
        "baseline_lista": 100 * wyj["baseline_lista"].mean(),
        "roznica_lista": rl,
        "dlugosc_sr": wyj["dlugosc"].mean(),
        "pusta_lista": 100 * (wyj["dlugosc"] == 0).mean(),
    }


def oblicz() -> tuple[list[dict], pd.Series, pd.DataFrame]:
    model = wczytaj_obecny()
    with polaczenie() as con:
        zbior, _ = wczytaj_zbior(con)
        cel = con.execute("SELECT id_windy, dzien, podzespol FROM dni_wind").df()
    cel["dzien"] = pd.to_datetime(cel["dzien"])
    zbior = zbior.merge(cel, on=["id_windy", "dzien"], how="left", validate="1:1")
    sygnal = zbior["podzespol"].isin(PODZESPOLY_Z_SYGNALEM) & (zbior["awaria_7d"] == 1)

    trening = zbior[sygnal & zbior["dzien"].between(*TRENING)]
    czestosc = trening["podzespol"].value_counts()
    kolejnosc = list(czestosc.index) + [p for p in PODZESPOLY_Z_SYGNALEM if p not in czestosc.index]

    test = zbior[zbior["dzien"].between(*TEST)].reset_index(drop=True)
    z = wczytaj_zalozenia()
    alarmy = wybierz_alarmy(
        test.assign(ryzyko=model.predict(test)),
        limit=int(z["alarmy_na_tydzien"]),
        przerwa_dni=int(z["przerwa_dni"]),
        dzien_alarmu=int(z["dzien_alarmu"]),
    )
    pozytywne = test[test["podzespol"].isin(PODZESPOLY_Z_SYGNALEM) & (test["awaria_7d"] == 1)].reset_index(drop=True)
    wklady = model.explain(pozytywne)[[f"wklad_{c}" for c in model.cechy]].to_numpy()
    wyj = miary(pozytywne, podzespoly_z_wkladow(wklady, list(model.cechy)), kolejnosc)
    klucz_alarmu = set(zip(alarmy["id_windy"], pd.to_datetime(alarmy["dzien"])))
    w_alarmie = np.array([(w, d) in klucz_alarmu for w, d in zip(pozytywne["id_windy"], pozytywne["dzien"])])
    wyniki = [podsumuj(wyj, "wszystkie dni z awarią z sygnałem"), podsumuj(wyj[w_alarmie], "trafne alarmy reguły")]
    return wyniki, czestosc, wyj


def _pp(r: tuple[float, float, float]) -> str:
    return f"{r[0]:+.1f} ({r[1]:+.1f} … {r[2]:+.1f})".replace(".", ",")


def _p(x: float) -> str:
    return f"{x:.1f}%".replace(".", ",")


if __name__ == "__main__":
    wyniki, czestosc, wyj = oblicz()
    print("Częstość podzespołów na treningu (baseline):", czestosc.to_dict())
    print(
        "| Wiersze | dni | awarie | 1. miejsce: model | 1. miejsce: baseline | model − baseline (pp, 95% CI) "
        "| w liście: model | w liście: baseline (ta sama długość) | model − baseline (pp, 95% CI) "
        "| średnia długość listy | pusta lista |"
    )
    print("|---|---:|---:|---:|---:|---|---:|---:|---|---:|---:|")
    for w in wyniki:
        print(
            f"| {w['wiersze']} | {w['dni']} | {w['awarie']} | {_p(w['model_1'])} | {_p(w['baseline_1'])} "
            f"| {_pp(w['roznica_1'])} | {_p(w['model_lista'])} | {_p(w['baseline_lista'])} | {_pp(w['roznica_lista'])} "
            f"| {w['dlugosc_sr']:.2f} | {_p(w['pusta_lista'])} |".replace(".", ",")
        )
    print("\nTrafienie na 1. miejscu według faktycznego podzespołu (model / baseline, dni):")
    print(wyj.groupby("podzespol")[["model_1", "baseline_1"]].agg(["mean", "count"]).round(3).to_string())
