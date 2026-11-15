"""Uzasadnienia w kolejce: top 3 cechy SHAP v2b -> fakty -> jedno zdanie z LLM (docs/kolejka_uzasadnienia.md).

Uruchomienie (po `pypyr baza`; sygnały v1 w ai/llm/cache; zdania z LLM wymagają klucza w środowisku):
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.lead_model.evals.uzasadnienia

- Model: zapisany `v2b_lgbm_ipw` (versions/v2b_lgbm_ipw/model.joblib, uczony na danych do 2026-02). SHAP = wkłady
  w log-szansę z LightGBM (`explain`, pred_contrib). Kalibracja izotoniczna nie zmienia kolejności zapytań, więc
  wyjaśnia tę samą kolejność.
- SHAP, top 3 i fakty: każde zapytanie zwykłego testu (2026-03-01 – 2026-06-30, features/leady/podzial_v2.py).
- Zdania z LLM: wszystkie zapytania utworzone 2026-06-15 (dzień przykładu) + losowe `PROBA_LLM` zapytań testu
  (ziarno 42). Pozostałe zapytania mają tylko fakty (bez wywołań API).
- Kolejka D03 z 2026-06-15: zapytania utworzone tego dnia (czas warszawski) z `crm_leady.id_doradcy = 'D03'`
  (stan na dzień eksportu: doradca przypisany; tylko do wyboru przykładu, nie jako cecha), według EV malejąco.
  EV = p × mediana czynszu × czas najmu × liczba lokali (leasing_bc/wartosc.py), p = wynik v2b.
Zapis: evals/wyniki/uzasadnienia.parquet (każde zapytanie testu), evals/wyniki/uzasadnienia.json (podsumowanie
i 20 przykładów D03).
"""

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.llm_client import KlientLLM
from api.ai.features.leady.fakty import fakty_leada, kontekst_faktow
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.evals.ewaluacja import KATALOG_MODELU, KATALOG_WYNIKOW
from api.ai.lead_model.evals.ewaluacja_v2 import _json, przygotuj
from api.ai.lead_model.uzasadnienie import WERSJA_PROMPTU, top_wklady, uzasadnij
from api.ai.llm.prompty import wczytaj_prompt
from api.contexts_boundaries.leasing_bc.wartosc import wartosc_oczekiwana

STREFA = "Europe/Warsaw"
DZIEN_PRZYKLADU = pd.Timestamp("2026-06-15").date()
DORADCA_PRZYKLADU = "D03"
PROBA_LLM = 300
LICZBA_PRZYKLADOW = 20
WATKI = 16


def main(z_llm: bool = True) -> None:
    con = polacz()
    zbiory, cechy = przygotuj(con)
    kontekst = kontekst_faktow(con).set_index("id_leada")
    doradcy = con.execute("SELECT id_leada, id_doradcy FROM crm_leady").df().set_index("id_leada")["id_doradcy"]
    con.close()
    test, X = zbiory["test"], cechy["test"]

    v2b = ModelLeadow.wczytaj(KATALOG_MODELU / "versions" / "v2b_lgbm_ipw" / "model.joblib")
    wyj = v2b.explain(X)
    df = test[["id_leada", "utworzono", "zrodlo", "miasto", "linia_pref", "liczba_lokali", "umowa_45d"]].copy()
    df["p"] = wyj["wynik"].to_numpy()
    df["ev"] = wartosc_oczekiwana(df["p"], df)
    df["dzien"] = pd.to_datetime(df["utworzono"], utc=True).dt.tz_convert(STREFA).dt.date
    df["id_doradcy"] = df["id_leada"].map(doradcy)

    kolumny_wkladow = [c for c in wyj.columns if c.startswith("wklad_")]
    top, fakty_top, fakty_poz = [], [], []
    for i, wiersz in enumerate(X[list(v2b.cechy)].to_dict("records")):
        id_leada = df["id_leada"].iat[i]
        kont = kontekst.loc[id_leada].to_dict()
        wszystkie = fakty_leada(wiersz, kont, v2b.cechy)
        t = top_wklady(wyj.iloc[i][kolumny_wkladow])
        top.append(t)
        fakty_top.append([wszystkie[c] for c, _ in t])
        fakty_poz.append([f for c, f in wszystkie.items() if c not in {c for c, _ in t}])

    df["top3"] = [json.dumps([{"cecha": c, "wklad": w} for c, w in t], ensure_ascii=False) for t in top]
    df["fakty_top"] = [json.dumps([f.jako_slownik() for f in ft], ensure_ascii=False) for ft in fakty_top]
    df["fakty_pozostale"] = [json.dumps([f.jako_slownik() for f in fp], ensure_ascii=False) for fp in fakty_poz]

    do_llm = (df["dzien"] == DZIEN_PRZYKLADU).to_numpy().copy()
    do_llm[np.random.default_rng(42).choice(len(df), PROBA_LLM, replace=False)] = True
    df["z_llm"] = do_llm
    for k in ("zdanie", "zrodlo_zdania", "zdanie_llm", "problemy_llm"):
        df[k] = None
    if z_llm:
        klient, prompt = KlientLLM(), wczytaj_prompt(WERSJA_PROMPTU)
        idx = np.flatnonzero(do_llm)
        with ThreadPoolExecutor(max_workers=WATKI) as pula:
            wyniki = list(pula.map(lambda i: uzasadnij(fakty_top[i], fakty_poz[i], klient, prompt), idx))
        for i, w in zip(idx, wyniki):
            df.iloc[i, df.columns.get_loc("zdanie")] = w.zdanie
            df.iloc[i, df.columns.get_loc("zrodlo_zdania")] = w.zrodlo
            df.iloc[i, df.columns.get_loc("zdanie_llm")] = w.zdanie_llm
            df.iloc[i, df.columns.get_loc("problemy_llm")] = "; ".join(w.problemy_llm) or None

    z = df[df["z_llm"]]
    licznik_cech = Counter(c["cecha"] for t in df["top3"] for c in json.loads(t))
    kolejka = df[(df["dzien"] == DZIEN_PRZYKLADU) & (df["id_doradcy"] == DORADCA_PRZYKLADU)].sort_values(
        "ev", ascending=False
    )
    przyklady = [
        {
            "pozycja": n,
            "id_leada": r.id_leada,
            "godzina": pd.Timestamp(r.utworzono).tz_convert(STREFA).strftime("%H:%M"),
            "linia": r.linia_pref,
            "zrodlo": r.zrodlo,
            "p": float(r.p),
            "ev": float(r.ev),
            "fakty_top": [f["tekst"] for f in json.loads(r.fakty_top)],
            "wklady": [c["wklad"] for c in json.loads(r.top3)],
            "zdanie": r.zdanie,
            "zrodlo_zdania": r.zrodlo_zdania,
            "zdanie_llm": r.zdanie_llm,
            "problemy_llm": r.problemy_llm,
            "umowa_45d": int(r.umowa_45d),
        }
        for n, r in enumerate(kolejka.head(LICZBA_PRZYKLADOW).itertuples(), start=1)
    ]
    dlugosci = z["zdanie"].dropna().str.len()
    podsumowanie = {
        "model": "versions/v2b_lgbm_ipw/model.joblib (SHAP: LightGBM pred_contrib, log-szansa)",
        "prompt": WERSJA_PROMPTU,
        "test_zapytan": len(df),
        "liczba_faktow_top": dict(Counter(len(json.loads(t)) for t in df["top3"])),
        "cechy_w_top3": dict(licznik_cech.most_common()),
        "cechy_na_1_miejscu": dict(
            Counter(json.loads(t)[0]["cecha"] for t in df["top3"] if json.loads(t)).most_common()
        ),
        "llm": {
            "zapytan": int(df["z_llm"].sum()),
            "z_dnia_przykladu": int((df["dzien"] == DZIEN_PRZYKLADU).sum()),
            "zrodlo_zdania": z["zrodlo_zdania"].value_counts().to_dict(),
            "problemy_llm": z["problemy_llm"].dropna().value_counts().to_dict(),
            "dlugosc_min_mediana_max": (
                [int(dlugosci.min()), float(dlugosci.median()), int(dlugosci.max())] if len(dlugosci) else None
            ),
        },
        "kolejka_d03": {"dzien": str(DZIEN_PRZYKLADU), "zapytan": len(kolejka), "przyklady": przyklady},
    }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    df.drop(columns=["dzien"]).assign(dzien=df["dzien"].astype(str)).to_parquet(
        KATALOG_WYNIKOW / "uzasadnienia.parquet", index=False
    )
    (KATALOG_WYNIKOW / "uzasadnienia.json").write_text(
        json.dumps(podsumowanie, ensure_ascii=False, indent=2, default=_json), "utf-8"
    )
    print(json.dumps({k: v for k, v in podsumowanie.items() if k != "kolejka_d03"}, ensure_ascii=False, indent=1))
    for p in przyklady:
        print(
            p["pozycja"], p["linia"], f"{p['p']:.3f}", round(p["ev"]), "|", " / ".join(p["fakty_top"]), "|", p["zdanie"]
        )


if __name__ == "__main__":
    main(z_llm="--bez-llm" not in sys.argv[1:])
