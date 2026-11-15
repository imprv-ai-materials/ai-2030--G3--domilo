"""Demonstracja przecieku: v1_ryzyko z `odslony_faq_wypowiedzenie` z miesiąca, w którym wypada migawka.

Nie zmienia zapisanej wersji v1_ryzyko ani cech (`cechy_najemcy`): uczy trzy kopie modelu v1 (ta sama klasa,
parametry i podział z features/najemcy/zbior.py) i porównuje je na teście 2026-04 – 2026-09:
- bez: cechy v1 (KOLUMNY_CECH);
- faq_miesiac_migawki: + odsłony FAQ o wypowiedzeniu z miesiąca kalendarzowego migawki (agregat za cały miesiąc,
  więc zawiera dni po migawce i reakcję na ofertę przedłużenia wysłaną w dniu migawki) = PRZECIEK;
- faq_3_pelne_miesiace: + odsłony FAQ z 3 pełnych miesięcy przed miesiącem migawki (jak portal_* w relacja.sql).
Uruchomienie: cd api && poetry run python -m api.ai.churn_model.evals.przeciek_faq
Wynik: evals/wyniki/przeciek_faq.json.
"""

import json

import numpy as np
from api.adapters.duckdb_baza import polacz
from api.ai.churn_model.evals.ewaluacja_v1 import KATALOG_WYNIKOW
from api.ai.churn_model.evals.metryki import bootstrap_par, metryki_rankingu
from api.ai.churn_model.versions.v1_ryzyko.model import ModelRyzyko
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from api.ai.features.najemcy.zbior import podziel, wczytaj_zbior

SQL_FAQ = """
WITH m AS (
    SELECT mg.id_umowy, mg.id_najemcy, date_trunc('month', mg.data_migawki)::DATE AS mies_m,
           date_trunc('month', n.data_wprowadzenia)::DATE AS mies_wpr
    FROM migawki_najemcy AS mg JOIN pms_najmy AS n USING (id_najmu)
),
l AS (SELECT id_najemcy, strptime(miesiac, '%Y-%m')::DATE AS mies, odslony_faq_wypowiedzenie FROM portal_logowania_mies)
SELECT
    m.id_umowy,
    sum(l.odslony_faq_wypowiedzenie) FILTER (WHERE l.mies = m.mies_m) AS faq_miesiac_migawki,
    sum(l.odslony_faq_wypowiedzenie) FILTER (WHERE l.mies >= m.mies_m - INTERVAL 3 MONTH AND l.mies < m.mies_m)
        AS faq_3_pelne_miesiace
FROM m LEFT JOIN l ON l.id_najemcy = m.id_najemcy AND l.mies >= m.mies_wpr
GROUP BY m.id_umowy
"""
WARIANTY = {
    "bez": (),
    "faq_miesiac_migawki": ("faq_miesiac_migawki",),
    "faq_3_pelne_miesiace": ("faq_3_pelne_miesiace",),
}


def main() -> dict:
    with polacz() as con:
        zbior = wczytaj_zbior(con).merge(con.execute(SQL_FAQ).df(), on="id_umowy", how="left", validate="1:1")
    zb = podziel(zbior)
    trening, test = zb["trening"], zb["test"]
    y = test["odejdzie"].to_numpy(dtype=int)
    segmenty = {
        "wszystkie": np.ones(len(test), dtype=bool),
        "bez_wypowiedzenia_przed_migawka": ~test["wypowiedzenie_przed_migawka"].to_numpy(dtype=bool),
        "B2C": (test["linia_umowy"] == "B2C").to_numpy(),
    }
    ryzyka, modele = {}, {}
    for nazwa, dodatkowe in WARIANTY.items():
        model = ModelRyzyko(cechy=(*KOLUMNY_CECH, *dodatkowe)).fit(trening, trening["odejdzie"])
        modele[nazwa] = model
        ryzyka[nazwa] = model.predict(test)
    wynik = {"warianty": {}, "roznice_vs_bez": {}, "cecha": {}}
    for nazwa, model in modele.items():
        waz = model.waznosc_cech()
        wynik["warianty"][nazwa] = {
            "liczba_drzew": model.liczba_drzew_,
            "auc_walidacji_w_czasie": model.auc_walidacji_,
            **{s: metryki_rankingu(y[m], ryzyka[nazwa][m]) for s, m in segmenty.items()},
            "waznosc_top3": waz.head(3).to_dict("records"),
        }
        if nazwa != "bez":
            wynik["roznice_vs_bez"][nazwa] = {
                s: bootstrap_par(y[m], ryzyka[nazwa][m], ryzyka["bez"][m]) for s, m in segmenty.items()
            }
    for kol in ("faq_miesiac_migawki", "faq_3_pelne_miesiace"):
        x = test[kol]
        wynik["cecha"][kol] = {
            "test_pct_gt_0": float((x > 0).mean()),
            "test_pct_odejsc_gdy_gt_0": float(test.loc[x > 0, "odejdzie"].mean()),
            "test_pct_odejsc_gdy_0_lub_brak": float(test.loc[~(x > 0), "odejdzie"].mean()),
        }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    (KATALOG_WYNIKOW / "przeciek_faq.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=2), "utf-8")
    return wynik


if __name__ == "__main__":
    w = main()
    for nazwa, r in w["warianty"].items():
        print(nazwa, "drzewa", r["liczba_drzew"], "auc_walid", round(r["auc_walidacji_w_czasie"], 4))
        for s in ("wszystkie", "bez_wypowiedzenia_przed_migawka", "B2C"):
            print("  ", s, {k: round(float(v), 4) for k, v in r[s].items() if k in ("n", "auc", "recall_10")})
        print("   top3", [(x["cecha"], round(x["udzial"], 3)) for x in r["waznosc_top3"]])
    for nazwa, d in w["roznice_vs_bez"].items():
        for s, ci in d.items():
            print(
                "roznica",
                nazwa,
                s,
                "AUC",
                [round(v, 4) for v in ci["auc_roznica"]],
                "recall",
                [round(v, 4) for v in ci["recall_roznica"]],
            )
    print(json.dumps(w["cecha"], indent=1))
