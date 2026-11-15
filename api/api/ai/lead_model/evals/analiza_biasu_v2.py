"""Analiza: co przewiduje v2_lgbm_naiwny: szansę na umowę czy decyzję doradcy (docs/kolejka_bias.md).

Tylko odczyt: zapisany model versions/v2_lgbm_naiwny/model.joblib, cechy z features/leady/cechy.py (sygnały v1
z ai/llm/cache, bez wywołań API) i leady_cel. Modelu nie uczymy od nowa i niczego w nim nie zmieniamy.

Uruchomienie (z katalogu głównego, po `pypyr baza`):
    cd api && poetry run python -m api.ai.lead_model.evals.analiza_biasu_v2

Wynik: tabele Markdown na standardowym wyjściu i evals/wyniki/bias_v2.json.
- A: źródło × zbiór (trening, test, okno): odsetek obsłużonych, konwersja wszystkich, obsłużonych, nieobsłużonych.
- B: miary v2 na teście i w oknie, ogółem i wewnątrz źródła (AUC w obrębie jednego źródła); AUC wyniku v2
  dla samej obsługi (`obsluzony`), czyli na ile wynik przewiduje decyzję o kontakcie.
- C: 10 najważniejszych cech: udział w gain (uczenie) i średni |wkład| (SHAP) na teście i w oknie.
- D: okno: średni wynik v2 wobec konwersji, średni wkład cechy `zrodlo` w log-szansę.
- E: test: średni wynik v2 wobec konwersji wszystkich i obsłużonych.
"""

import json

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.evals.ewaluacja import KATALOG_MODELU, KATALOG_WYNIKOW
from api.ai.lead_model.evals.ewaluacja_v2 import ZBIORY_OCENY, przygotuj
from api.ai.lead_model.evals.metryki import dzienna_liczba_zapytan, metryki_rankingu
from sklearn.metrics import roc_auc_score

# Te same granice co features/leady/podzial_v2.py (strefa sesji Europe/Warsaw z polacz()).
SQL_ZRODLA = """
WITH z AS (
    SELECT
        c.zrodlo, c.umowa_45d, c.obsluzony,
        CASE
            WHEN c.okno_migracji THEN 'okno_migracji'
            WHEN c.utworzono >= TIMESTAMPTZ '2026-03-01' AND c.utworzono < TIMESTAMPTZ '2026-07-01' THEN 'test'
            WHEN c.zamkniety AND c.utworzono >= TIMESTAMPTZ '2023-01-01'
                 AND c.utworzono < TIMESTAMPTZ '2026-03-01' THEN 'trening'
        END AS zbior
    FROM leady_cel AS c
    WHERE c.umowa_45d IS NOT NULL
)
SELECT
    zbior, zrodlo,
    count(*) AS zapytania,
    count(*) FILTER (WHERE NOT obsluzony) AS nieobsluzone,
    sum(umowa_45d) AS umowy,
    avg(obsluzony::INTEGER) AS obsluzone,
    avg(umowa_45d) AS konwersja_wszystkich,
    avg(umowa_45d) FILTER (WHERE obsluzony) AS konwersja_obsluzonych,
    avg(umowa_45d) FILTER (WHERE NOT obsluzony) AS konwersja_nieobsluzonych,
    -- target uczenia v2 („nieobsłużone = 0”)
    avg(CASE WHEN obsluzony THEN umowa_45d ELSE 0 END) AS konwersja_nieobsluzone_0
FROM z
WHERE zbior IS NOT NULL
GROUP BY ALL
ORDER BY zbior, zrodlo
"""


def _auc(y, w) -> float | None:
    y = np.asarray(y)
    return float(roc_auc_score(y, w)) if 0 < y.sum() < len(y) else None


def main() -> dict:
    con = polacz()
    zrodla = con.execute(SQL_ZRODLA).df()
    zbiory, cechy = przygotuj(con)
    con.close()
    model = ModelLeadow.wczytaj(KATALOG_MODELU / "versions" / "v2_lgbm_naiwny" / "model.joblib")

    wynik = {"A_zrodla": zrodla.to_dict("records"), "B_miary": {}, "C_cechy": {}, "D_okno": [], "E_test": []}
    gain = model.waznosc_cech().set_index("cecha")["udzial"]
    shap = {}
    for nazwa in ZBIORY_OCENY:
        zb, X = zbiory[nazwa], cechy[nazwa]
        wyj = model.explain(X)
        w = wyj["wynik"].to_numpy()
        y = zb["umowa_45d"].astype(int).to_numpy()
        k = dzienna_liczba_zapytan(zb["utworzono"])
        df = zb[["zrodlo", "obsluzony"]].assign(y=y, w=w, wklad_zrodlo=wyj["wklad_zrodlo"].to_numpy())
        wynik["B_miary"][nazwa] = {
            "ogolem": metryki_rankingu(y, w, k) | {"sredni_wynik": float(w.mean())},
            "auc_wewnatrz_zrodla": {z: _auc(g["y"], g["w"]) for z, g in df.groupby("zrodlo")},
            "auc_obsluzonych": _auc(df.loc[df["obsluzony"], "y"], df.loc[df["obsluzony"], "w"]),
            # Czy wynik v2 przewiduje samą decyzję o kontakcie (target: obsluzony zamiast umowy)?
            "auc_dla_obsluzenia": _auc(df["obsluzony"].astype(int), df["w"]),
            "auc_dla_obsluzenia_wewnatrz_zrodla": {
                z: _auc(g["obsluzony"].astype(int), g["w"]) for z, g in df.groupby("zrodlo")
            },
        }
        shap[nazwa] = wyj.filter(like="wklad_").drop(columns="wklad_staly").abs().mean()
        po_zrodle = (
            df.groupby("zrodlo")
            .agg(
                zapytania=("y", "size"),
                konwersja=("y", "mean"),
                obsluzone=("obsluzony", "mean"),
                sredni_wynik_v2=("w", "mean"),
                sredni_wklad_zrodla=("wklad_zrodlo", "mean"),
            )
            .reset_index()
        )
        obsl = (
            df[df["obsluzony"]]
            .groupby("zrodlo")
            .agg(konwersja_obsluzonych=("y", "mean"), sredni_wynik_obsluzonych=("w", "mean"))
        )
        po_zrodle = po_zrodle.merge(obsl, on="zrodlo", how="left")
        wynik["D_okno" if nazwa == "okno_migracji" else "E_test"] = po_zrodle.to_dict("records")

    tab_c = pd.DataFrame({"udzial_gain": gain})
    for nazwa in ZBIORY_OCENY:
        tab_c[f"sredni_abs_wklad_{nazwa}"] = shap[nazwa].rename(lambda c: c.removeprefix("wklad_"))
    tab_c = tab_c.sort_values("udzial_gain", ascending=False)
    wynik["C_cechy"] = tab_c.reset_index(names="cecha").to_dict("records")

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    (KATALOG_WYNIKOW / "bias_v2.json").write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2, default=_json), encoding="utf-8"
    )
    _drukuj(wynik)
    return wynik


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    if o is pd.NA or (isinstance(o, float) and np.isnan(o)):
        return None
    return str(o)


def _pct(x, d: int = 2) -> str:
    return "brak" if x is None or pd.isna(x) else f"{100 * x:.{d}f}%".replace(".", ",")


def _f(x, d: int = 3) -> str:
    return "brak" if x is None or pd.isna(x) else f"{x:+.{d}f}".replace(".", ",").replace("-", "−")


def _drukuj(w: dict) -> None:
    a = pd.DataFrame(w["A_zrodla"])
    print("A. Źródło × zbiór")
    print(
        "| Zbiór | Źródło | Zapytania | Umowy | Obsłużone | Konw. wszystkich | Konw. obsłużonych | "
        "Konw. nieobsłużonych | Konw. przy „nieobsł. = 0” |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in a.itertuples():
        print(f"| {r.zbior} | {r.zrodlo} | {r.zapytania} | {int(r.umowy)} | {_pct(r.obsluzone, 1)} | "
              f"{_pct(r.konwersja_wszystkich)} | {_pct(r.konwersja_obsluzonych)} | "
              f"{_pct(r.konwersja_nieobsluzonych)} | {_pct(r.konwersja_nieobsluzone_0)} |")  # fmt: skip
    print("\nB. Miary v2")
    for z, m in w["B_miary"].items():
        print(z, {k: m["ogolem"][k] for k in ("n", "konwersja", "sredni_wynik", "auc", "lift_10", "precision_k")})
        print("  AUC obsłużonych:", m["auc_obsluzonych"], " AUC wewnątrz źródła:", m["auc_wewnatrz_zrodla"])
        print("  AUC dla obsłużenia:", m["auc_dla_obsluzenia"], m["auc_dla_obsluzenia_wewnatrz_zrodla"])
    print("\nC. Cechy")
    for r in w["C_cechy"][:10]:
        print(r)
    for klucz in ("D_okno", "E_test"):
        print(f"\n{klucz}")
        for r in w[klucz]:
            print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
