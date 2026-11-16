"""Wartość oczekiwana oferty retencyjnej dla każdego najemcy i porównanie polityk rabatowych w złotówkach.

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`, oraz modelu churn_model/versions/v3_uplift_tlearner/model.joblib:
`python -m api.ai.churn_model.evals.uplift`):
    cd api && poetry run python -m api.contexts_boundaries.retention_bc.polityka_rabatow

EV jednej oferty (założenia R, D, k z retention_bc/zalozenia.yaml, podane przez użytkownika):
    EV = uplift × R − D × P(przedłuży | oferta) − k,
uplift = P(przedłuży | oferta) − P(przedłuży | kontrola) z v3_uplift_tlearner (T-learner).

Zbiór oceny: część testowa losowego testu oferty `test_2025` (30% umów według id_umowy, ta sama co w
churn_model/evals/uplift.md), której model nie widział przy uczeniu. Polityka = zbiór umów, którym dajemy ofertę:
- `wszyscy`: każdy kończący umowę;
- `gorne_35_ryzyka`: `score_polityki` >= kwantyl 0,65 z części treningowej (obecna reguła firmy);
- `gorne_20_upliftu`: 20% umów zbioru oceny z najwyższym upliftem v3;
- `ev_dodatnie` (dodatkowo): umowy z EV > 0.
Wynik polityki liczymy na dwa sposoby:
- z eksperymentu (główny): przydział oferty był losowy, więc w umowach polityki % przedłużeń w grupie oferta
  i w kontroli mówi, co by się stało, gdyby ofertę dostali wszyscy z polityki: dodatkowe przedłużenia =
  (p_oferta − p_kontrola) × oferty, rabaty = p_oferta × oferty, zysk = dodatkowe × R − rabaty × D − oferty × k;
- z modelu (dla porównania): suma EV, uplift i P(przedłuży | oferta) po umowach polityki.
Na rok: wynik na zbiorze oceny × (umowy roczne B2C / B2B kończące się w ostatnich 12 miesiącach danych, 2025-10 –
2026-09, z migawki_najemcy) / (umowy w zbiorze oceny). 95% przedziały: bootstrap wierszy zbioru oceny (2 000 losowań).
Zapis: retention_bc/wyniki/polityka_rabatow.json i ev_najemcow.parquet. Raport: docs/polityka_rabatow.md.
"""

import json
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.churn_model.versions.v3_uplift_tlearner.model import ModelUpliftT
from api.ai.features.najemcy.zbior import podziel_uplift, wczytaj_zbior
from api.contexts_boundaries.retention_bc.zalozenia import ZalozeniaOferty, zalozenia_oferty

__all__ = ["ZalozeniaOferty", "na_rok", "wartosc_oferty", "wynik_polityki"]

KATALOG_REPO = Path(__file__).resolve().parents[4]
SCIEZKA_MODELU = (
    Path(__file__).resolve().parents[2] / "ai" / "churn_model" / "versions" / "v3_uplift_tlearner" / "model.joblib"
)
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")
FRAKCJA_RYZYKA = 0.35
FRAKCJA_UPLIFTU = 0.20
N_BOOTSTRAP = 2000
ZIARNO = 42
D_Z_FK = 1950.0  # fk_rabaty: 13 pozycji × 150 PLN (mediana i maksimum, SQL_D_Z_FK); tylko wrażliwość
SQL_UMOWY_ROK = """
SELECT count(*) AS umowy, min(data_do) AS od, max(data_do) AS do_
FROM migawki_najemcy
WHERE data_do BETWEEN DATE '2025-10-01' AND DATE '2026-09-30'
"""
SQL_D_Z_FK = """
WITH f AS (SELECT id_umowy, sum(kwota_rabatu) AS suma, count(*) AS pozycje FROM fk_rabaty GROUP BY id_umowy)
SELECT count(*) AS przedluzenia_z_rabatem, count(*) FILTER (WHERE f.pozycje = 13) AS z_13_pozycjami,
       median(f.suma) AS mediana_suma, max(f.suma) AS max_suma, max(f.pozycje) AS max_pozycji
FROM retencja_decyzje AS r
JOIN migawki_najemcy AS m USING (id_umowy)
JOIN f ON f.id_umowy = m.id_umowy_nastepnej
WHERE r.okres = 'test_2025' AND r.grupa = 'oferta' AND r.data_konca < DATE '2025-10-01'
"""
NIE_SKALOWANE = frozenset(
    {"udzial", "odsetek_oferta", "odsetek_kontrola", "uplift_obserwowany", "prog_D", "prog_R", "zysk_na_oferte"}
)


def wartosc_oferty(uplift, p_oferta, z: ZalozeniaOferty) -> np.ndarray:
    """EV = uplift × R − D × P(przedłuży | oferta) − k (PLN na jedną ofertę)."""
    return np.asarray(uplift, dtype=float) * z.R - z.D * np.asarray(p_oferta, dtype=float) - z.k


def wynik_polityki(maska, y, w, uplift, p_oferta, z: ZalozeniaOferty) -> dict:
    """Wynik polityki „oferta dla umów z maska” z eksperymentu (y, w) i z modelu (uplift, p_oferta)."""
    maska = np.asarray(maska, dtype=bool)
    y, w = np.asarray(y, dtype=float), np.asarray(w, dtype=bool)
    uplift, p_oferta = np.asarray(uplift, dtype=float), np.asarray(p_oferta, dtype=float)
    n = int(maska.sum())
    wynik = {"oferty": n, "udzial": n / len(maska)}
    if n == 0:
        zera = ("dodatkowe_przedluzenia", "rabaty", "korzysc_z_przedluzen", "koszt_rabatow", "koszt_kontaktow",
                "zysk_netto", "model_dodatkowe_przedluzenia", "model_rabaty", "model_zysk_netto")  # fmt: skip
        return wynik | {k: 0.0 for k in zera} | {"prog_D": None, "prog_R": None, "zysk_na_oferte": None}
    o, c = maska & w, maska & ~w
    p_o, p_k = y[o].mean(), y[c].mean()
    dodatkowe = (p_o - p_k) * n
    rabaty = p_o * n
    zysk = dodatkowe * z.R - rabaty * z.D - n * z.k
    return wynik | {
        "umowy_oferta_w_tescie": int(o.sum()),
        "umowy_kontrola_w_tescie": int(c.sum()),
        "odsetek_oferta": float(p_o),
        "odsetek_kontrola": float(p_k),
        "uplift_obserwowany": float(p_o - p_k),
        "dodatkowe_przedluzenia": float(dodatkowe),
        "rabaty": float(rabaty),
        "korzysc_z_przedluzen": float(dodatkowe * z.R),
        "koszt_rabatow": float(rabaty * z.D),
        "koszt_kontaktow": float(n * z.k),
        "zysk_netto": float(zysk),
        "zysk_na_oferte": float(zysk / n),
        # D, przy którym polityka wychodzi na zero (przy tych samych R i k), i R potrzebne przy tym D
        "prog_D": float((dodatkowe * z.R - n * z.k) / rabaty) if rabaty > 0 and dodatkowe > 0 else None,
        "prog_R": float((rabaty * z.D + n * z.k) / dodatkowe) if dodatkowe > 0 else None,
        "model_dodatkowe_przedluzenia": float(uplift[maska].sum()),
        "model_rabaty": float(p_oferta[maska].sum()),
        "model_zysk_netto": float(wartosc_oferty(uplift[maska], p_oferta[maska], z).sum()),
    }


def na_rok(wynik: dict, mnoznik: float) -> dict:
    """Liczby i kwoty × mnoznik (rok zamiast zbioru oceny); udziały, odsetki i progi bez zmian."""
    return {
        k: (v * mnoznik if isinstance(v, (int, float)) and v is not None and k not in NIE_SKALOWANE else v)
        for k, v in wynik.items()
    }


def bootstrap_polityk(
    maski: dict[str, np.ndarray], y, w, uplift, p_oferta, z: ZalozeniaOferty, odniesienie: str,
    n_prob: int = N_BOOTSTRAP, ziarno: int = ZIARNO,
) -> dict:  # fmt: skip
    """95% przedziały (zbiór oceny) zysku netto i dodatkowych przedłużeń każdej polityki oraz różnicy zysku
    względem polityki `odniesienie`; te same losowania wierszy dla wszystkich polityk."""
    y, w = np.asarray(y), np.asarray(w)
    rng = np.random.default_rng(ziarno)
    proby = {n: {"zysk_netto": [], "dodatkowe_przedluzenia": []} for n in maski}
    for _ in range(n_prob):
        i = rng.integers(0, len(y), len(y))
        for nazwa, m in maski.items():
            r = wynik_polityki(m[i], y[i], w[i], uplift[i], p_oferta[i], z)
            proby[nazwa]["zysk_netto"].append(r["zysk_netto"])
            proby[nazwa]["dodatkowe_przedluzenia"].append(r["dodatkowe_przedluzenia"])

    def ci(v):
        return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]

    return {
        "przedzialy": {n: {m: ci(v) for m, v in d.items()} for n, d in proby.items()},
        "roznica_zysku_wzgledem_"
        + odniesienie: {n: ci(np.subtract(proby[n]["zysk_netto"], proby[odniesienie]["zysk_netto"])) for n in maski},
        "p_zysk_ujemny": {n: float(np.mean(np.asarray(d["zysk_netto"]) < 0)) for n, d in proby.items()},
    }


def maski_polityk(ocena: pd.DataFrame, prog_ryzyka: float, uplift: np.ndarray, ev: np.ndarray) -> dict:
    k = round(FRAKCJA_UPLIFTU * len(ocena))
    gora_upliftu = np.zeros(len(ocena), dtype=bool)
    gora_upliftu[np.argsort(-uplift, kind="stable")[:k]] = True
    return {
        "wszyscy": np.ones(len(ocena), dtype=bool),
        "gorne_35_ryzyka": (ocena["score_polityki"] >= prog_ryzyka).to_numpy(),
        "gorne_20_upliftu": gora_upliftu,
        "ev_dodatnie": ev > 0,
    }


def main() -> dict:
    z = zalozenia_oferty()
    with polacz() as con:
        zbiory = podziel_uplift(wczytaj_zbior(con))
        umowy_rok = con.execute(SQL_UMOWY_ROK).df().iloc[0]
        d_fk = con.execute(SQL_D_Z_FK).df().iloc[0]
    trening, ocena = zbiory["trening"], zbiory["test"]
    model: ModelUpliftT = joblib.load(SCIEZKA_MODELU)
    p_o, p_k = model.predict_skladowe(ocena)
    uplift = p_o - p_k
    ev = wartosc_oferty(uplift, p_o, z)
    y = 1 - ocena["odejdzie"].to_numpy(dtype=int)
    w = (ocena["grupa"] == "oferta").to_numpy()

    prog_ryzyka = float(np.quantile(trening["score_polityki"], 1 - FRAKCJA_RYZYKA))
    maski = maski_polityk(ocena, prog_ryzyka, uplift, ev)
    mnoznik = float(umowy_rok["umowy"]) / len(ocena)

    wyniki = {n: wynik_polityki(m, y, w, uplift, p_o, z) for n, m in maski.items()}
    boot = bootstrap_polityk(maski, y, w, uplift, p_o, z, odniesienie="gorne_35_ryzyka")
    z_fk = replace(z, D=D_Z_FK)
    wrazliwosc_d = {n: wynik_polityki(m, y, w, uplift, p_o, z_fk) for n, m in maski.items()}

    # Sprawdzenie na całym test_2025 (4 734 umowy): polityki bez modelu, ten sam próg ryzyka z części treningowej
    caly = pd.concat([trening, ocena], ignore_index=True)
    y_c = 1 - caly["odejdzie"].to_numpy(dtype=int)
    w_c = (caly["grupa"] == "oferta").to_numpy()
    zera = np.zeros(len(caly))
    maski_c = {
        "wszyscy": np.ones(len(caly), dtype=bool),
        "gorne_35_ryzyka": (caly["score_polityki"] >= prog_ryzyka).to_numpy(),
    }
    mnoznik_c = float(umowy_rok["umowy"]) / len(caly)
    caly_wyniki = {n: na_rok(wynik_polityki(m, y_c, w_c, zera, zera, z), mnoznik_c) for n, m in maski_c.items()}
    caly_boot = bootstrap_polityk(maski_c, y_c, w_c, zera, zera, z, odniesienie="gorne_35_ryzyka")

    # Czy P(przedłuży | oferta) i P(przedłuży | kontrola) z modelu zgadzają się ze średnimi w zbiorze oceny
    kalibracja = {
        "p_oferta_model_w_grupie_oferta": float(p_o[w].mean()),
        "przedluzenia_grupa_oferta": float(y[w].mean()),
        "p_kontrola_model_w_grupie_kontrola": float(p_k[~w].mean()),
        "przedluzenia_grupa_kontrola": float(y[~w].mean()),
    }
    ev_opis = {
        "srednia": float(ev.mean()),
        "mediana": float(np.median(ev)),
        "p90": float(np.percentile(ev, 90)),
        "maks": float(ev.max()),
        "dodatnie": int((ev > 0).sum()),
        "uplift_potrzebny_przy_p_oferta_mediana": float((z.D * np.median(p_o) + z.k) / z.R),
    }
    wynik = {
        "zalozenia": {"R": z.R, "D": z.D, "k": z.k},
        "zbior_oceny": {
            "opis": "test_2025, część testowa 30% według id_umowy (churn_model/evals/uplift.md)",
            "umowy": int(len(ocena)),
            "oferta": int(w.sum()),
            "kontrola": int((~w).sum()),
        },
        "rok": {
            "umowy": int(umowy_rok["umowy"]),
            "data_do_od": str(umowy_rok["od"])[:10],
            "data_do_do": str(umowy_rok["do_"])[:10],
            "mnoznik": mnoznik,
        },
        "prog_ryzyka_score": prog_ryzyka,
        "polityki_zbior_oceny": wyniki,
        "polityki_rok": {n: na_rok(r, mnoznik) for n, r in wyniki.items()},
        "bootstrap_zbior_oceny": boot,
        "bootstrap_rok": {
            "przedzialy": {
                n: {m: [a * mnoznik for a in v] for m, v in d.items()} for n, d in boot["przedzialy"].items()
            },
            "roznica_zysku_wzgledem_gorne_35_ryzyka": {
                n: [a * mnoznik for a in v] for n, v in boot["roznica_zysku_wzgledem_gorne_35_ryzyka"].items()
            },
            "p_zysk_ujemny": boot["p_zysk_ujemny"],
        },
        "wrazliwosc_D_z_fk": {
            "D": D_Z_FK,
            "fk_rabaty": {k: int(v) for k, v in d_fk.items()},
            "polityki_rok": {n: na_rok(r, mnoznik) for n, r in wrazliwosc_d.items()},
        },
        "sprawdzenie_caly_test_2025": {
            "umowy": int(len(caly)),
            "mnoznik": mnoznik_c,
            "polityki_rok": caly_wyniki,
            "zysk_netto_rok_ci95": {
                n: [a * mnoznik_c for a in d["zysk_netto"]] for n, d in caly_boot["przedzialy"].items()
            },
        },
        "kalibracja_modelu": kalibracja,
        "ev_najemcow": ev_opis,
    }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    (KATALOG_WYNIKOW / "polityka_rabatow.json").write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tabela = ocena[["id_umowy", "data_do", "linia_umowy", "score_polityki", "grupa", "odejdzie"]].copy()
    tabela["p_przedluzy_oferta"], tabela["p_przedluzy_kontrola"], tabela["uplift"], tabela["ev_pln"] = (
        p_o,
        p_k,
        uplift,
        ev,
    )
    for n, m in maski.items():
        tabela[f"polityka_{n}"] = m
    tabela.to_parquet(KATALOG_WYNIKOW / "ev_najemcow.parquet", index=False)
    return wynik


if __name__ == "__main__":
    w = main()
    print(
        {k: w[k] for k in ("zalozenia", "zbior_oceny", "rok", "prog_ryzyka_score", "kalibracja_modelu", "ev_najemcow")}
    )
    kol = ["oferty", "uplift_obserwowany", "dodatkowe_przedluzenia", "rabaty", "korzysc_z_przedluzen", "koszt_rabatow",
           "koszt_kontaktow", "zysk_netto", "zysk_na_oferte", "prog_D", "prog_R", "model_dodatkowe_przedluzenia",
           "model_zysk_netto"]  # fmt: skip
    for klucz in ("polityki_zbior_oceny", "polityki_rok"):
        print(f"\n## {klucz}")
        print(pd.DataFrame(w[klucz]).T[kol].to_string())
    print("\n## bootstrap rok", json.dumps(w["bootstrap_rok"], indent=1))
    print("\n## cały test_2025", json.dumps(w["sprawdzenie_caly_test_2025"]["zysk_netto_rok_ci95"]))
    print(pd.DataFrame(w["sprawdzenie_caly_test_2025"]["polityki_rok"]).T[kol[:10]].to_string())
    print("\n## wrażliwość D z FK", w["wrazliwosc_D_z_fk"]["fk_rabaty"])
    print(pd.DataFrame(w["wrazliwosc_D_z_fk"]["polityki_rok"]).T[["oferty", "zysk_netto", "prog_D"]].to_string())
