"""Ewaluacja uplift: v3_uplift_tlearner (T-learner) i S-learner z causalml wobec reguły „górne 35% score_polityki”.

Uruchomienie (wymaga domilo.duckdb z migawki_najemcy i cechy_najemcy: `pypyr baza`):
    cd api && poetry run python -m api.ai.churn_model.evals.uplift [--bez-mlflow]

- Dane: losowy test oferty `test_2025` (końce umów 2025-07 – 2026-03), podział 70 / 30 według id_umowy
  (features/najemcy/zbior.py, podziel_uplift). Wynik y = przedłużenie (1 − odejdzie), w = 1 oferta / 0 kontrola.
- v3_uplift_tlearner: dwa LightGBM (oferta / kontrola) na 28 cechach v1 (versions/v3_uplift_tlearner/model.py).
- S-learner: causalml.inference.meta.BaseSClassifier z jednym LGBMClassifier na [oferta | te same cechy], te same
  parametry; liczba drzew z 5-krotnej CV na treningu (jak w T-learnerze).
- Punkt odniesienia: reguła firmy „górne 35% score_polityki” (wynik 1 / 0, próg = kwantyl 0,65 na części
  treningowej). Dodatkowo `score_polityki` jako ranking ciągły.
- Miary na teście (evals/metryki_uplift.py): krzywa Qini, AUUC, AUUC − losowo, uplift w górnych 20% i 35%;
  95% przedziały z bootstrapu wierszy testu (2 000 losowań, te same dla wszystkich rankingów) i różnice par.
Zapis: versions/v3_uplift_tlearner/{model.joblib, metryki.json}, evals/wyniki/v3_uplift_tlearner.parquet,
docs/img/uplift_qini.png, docs/img/uplift_kwintyle.png, MLflow (`najemcy`). Raport: evals/uplift.md.
"""

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.churn_model.evals.metryki_uplift import bootstrap_miar, krzywa_qini, miary
from api.ai.churn_model.evals.przezycie import KATALOG_REPO, SIATKA, TLO, TUSZ, TUSZ_DRUGI
from api.ai.churn_model.versions.v3_uplift_tlearner.model import PARAMETRY, ModelUpliftT, liczba_drzew, macierz
from api.ai.features.najemcy.zbior import FRAKCJA_TRENINGU_UPLIFT, OKRES_UPLIFT, podziel_uplift, wczytaj_zbior
from causalml.inference.meta import BaseSClassifier
from lightgbm import LGBMClassifier

EKSPERYMENT_MLFLOW = "najemcy"
KATALOG_WERSJI = Path(__file__).resolve().parents[1] / "versions" / ModelUpliftT.wersja
SCIEZKA_PREDYKCJI = Path(__file__).with_name("wyniki") / "v3_uplift_tlearner.parquet"
SCIEZKA_QINI = KATALOG_REPO / "docs" / "img" / "uplift_qini.png"
SCIEZKA_KWINTYLI = KATALOG_REPO / "docs" / "img" / "uplift_kwintyle.png"
FRAKCJA_REGULY = 0.35
KWINTYLE = 5

T = ModelUpliftT.wersja
S = "s_learner_causalml"
REGULA = "regula_gorne_35_score"
SCORE = "score_polityki_ciagly"
# Paleta referencyjna skilla dataviz (tryb jasny), sloty 1–3 w stałej kolejności; losowo = tusz drugorzędny.
KOLORY = {T: "#2a78d6", S: "#eb6834", REGULA: "#1baf7a"}
STYLE = {T: "-", S: "--", REGULA: "-."}
OPISY = {
    T: "T-learner (v3)",
    S: "S-learner (causalml)",
    REGULA: "Reguła: górne 35% score_polityki",
    SCORE: "score_polityki (ranking ciągły)",
}


def parametry_sklearn(parametry: dict = PARAMETRY) -> dict:
    """Te same parametry LightGBM w nazwach interfejsu sklearn (LGBMClassifier)."""
    return {
        "learning_rate": parametry["learning_rate"],
        "num_leaves": parametry["num_leaves"],
        "min_child_samples": parametry["min_child_samples"],
        "colsample_bytree": parametry["feature_fraction"],
        "subsample": parametry["bagging_fraction"],
        "subsample_freq": parametry["bagging_freq"],
        "reg_lambda": parametry["lambda_l2"],
        "random_state": parametry["seed"],
        "deterministic": parametry["deterministic"],
        "force_row_wise": parametry["force_row_wise"],
        "n_jobs": parametry["num_threads"],
        "verbose": parametry["verbose"],
    }


def s_learner(trening: pd.DataFrame, w: np.ndarray, y: np.ndarray) -> tuple[BaseSClassifier, int]:
    X = macierz(trening)
    n_drzew = liczba_drzew(pd.concat([pd.Series(w.astype(float), index=X.index, name="oferta"), X], axis=1), y)
    model = BaseSClassifier(learner=LGBMClassifier(n_estimators=n_drzew, **parametry_sklearn()), control_name=0)
    model.fit(X, w.astype(int), y)
    return model, n_drzew


def kwintyle(y, w, wynik, opis: str) -> pd.DataFrame:
    """Obserwowany uplift (p_o − p_k, 95% Wald) i średni przewidywany uplift w kwintylach wyniku (1 = najwyższy)."""
    df = pd.DataFrame({"y": y, "w": w, "wynik": wynik})
    df["kwintyl"] = KWINTYLE - pd.qcut(df["wynik"].rank(method="first"), KWINTYLE, labels=False)
    wiersze = []
    for k, g in df.groupby("kwintyl"):
        o, c = g.loc[g["w"] == 1, "y"], g.loc[g["w"] == 0, "y"]
        se = np.sqrt(o.mean() * (1 - o.mean()) / len(o) + c.mean() * (1 - c.mean()) / len(c))
        u = o.mean() - c.mean()
        wiersze.append(
            {"ranking": opis, "kwintyl": int(k), "n_oferta": len(o), "n_kontrola": len(c),
             "uplift_przewidywany": float(g["wynik"].mean()), "uplift_obserwowany": float(u),
             "ci95_od": float(u - 1.96 * se), "ci95_do": float(u + 1.96 * se)}  # fmt: skip
        )
    return pd.DataFrame(wiersze)


# --- wykresy -----------------------------------------------------------------------------------------------------


def _os(ax) -> None:
    ax.set_facecolor(TLO)
    ax.grid(axis="y", color=SIATKA, lw=0.8)
    ax.grid(axis="x", visible=False)
    ax.tick_params(colors=TUSZ_DRUGI, length=0, labelsize=9)
    for bok in ("top", "right", "left"):
        ax.spines[bok].set_visible(False)
    ax.spines["bottom"].set_color(SIATKA)


def rysuj_qini(y, w, wyniki: dict[str, np.ndarray], sciezka: Path) -> None:
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150, facecolor=TLO)
    _os(ax)
    ate = None
    for nazwa in (T, S, REGULA):
        k = krzywa_qini(y, w, wyniki[nazwa])
        ate = k["qini"].iloc[-1]
        ax.plot(k["frakcja"], 100 * k["qini"], color=KOLORY[nazwa], lw=2, ls=STYLE[nazwa], label=OPISY[nazwa], zorder=3)
    ax.plot([0, 1], [0, 100 * ate], color=TUSZ_DRUGI, lw=1, ls=":", label="Losowa kolejność", zorder=2)
    for x in (0.20, FRAKCJA_REGULY):
        ax.axvline(x, color=SIATKA, lw=1, zorder=1)
        ax.text(x + 0.006, 0.97, f"{x:.0%}", transform=ax.get_xaxis_transform(), fontsize=8, color=TUSZ_DRUGI)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0f} p.p.".replace("+0", "0")))
    ax.set_xlabel("Umowy z ofertą: odsetek z góry listy", color=TUSZ_DRUGI, fontsize=10)
    ax.set_ylabel("Przyrost odsetka przedłużeń w całej grupie", color=TUSZ_DRUGI, fontsize=10)
    ax.set_title(
        f"Krzywe Qini: część testowa {OKRES_UPLIFT} ({len(y)} umów, 30% według id_umowy)",
        fontsize=11, color=TUSZ, loc="left",
    )  # fmt: skip
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    fig.savefig(sciezka, facecolor=TLO, bbox_inches="tight")
    plt.close(fig)


def rysuj_kwintyle(tabela: pd.DataFrame, sciezka: Path) -> None:
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5.0), dpi=150, facecolor=TLO)
    _os(ax)
    szer = 0.36
    for i, nazwa in enumerate((T, S)):
        t = tabela[tabela["ranking"] == nazwa]
        x = t["kwintyl"].to_numpy() + (i - 0.5) * (szer + 0.04)
        u = 100 * t["uplift_obserwowany"].to_numpy()
        ax.bar(x, u, width=szer, color=KOLORY[nazwa], label=OPISY[nazwa], zorder=3)
        ax.errorbar(
            x, u, yerr=[u - 100 * t["ci95_od"], 100 * t["ci95_do"] - u],
            fmt="none", ecolor=TUSZ_DRUGI, elinewidth=1, capsize=3, zorder=4,
        )  # fmt: skip
    ax.axhline(0, color=TUSZ_DRUGI, lw=1, zorder=2)
    ax.set_xticks(
        range(1, KWINTYLE + 1), [f"{k}." + (" (najwyższy)" if k == 1 else "") for k in range(1, KWINTYLE + 1)]
    )
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f} p.p."))
    ax.set_xlabel("Kwintyl przewidywanego upliftu (część testowa)", color=TUSZ_DRUGI, fontsize=10)
    ax.set_ylabel("Obserwowany uplift: oferta − kontrola", color=TUSZ_DRUGI, fontsize=10)
    ax.set_title("Obserwowany efekt oferty w kwintylach modeli (95% przedział)", fontsize=11, color=TUSZ, loc="left")
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    fig.savefig(sciezka, facecolor=TLO, bbox_inches="tight")
    plt.close(fig)


# --- główna ------------------------------------------------------------------------------------------------------


def main(z_mlflow: bool = True) -> dict:
    with polacz() as con:
        zbiory = podziel_uplift(wczytaj_zbior(con))
    trening, test = zbiory["trening"], zbiory["test"]
    w_tr = (trening["grupa"] == "oferta").to_numpy()
    y_tr = 1 - trening["odejdzie"].to_numpy(dtype=int)
    w_te = (test["grupa"] == "oferta").to_numpy().astype(int)
    y_te = 1 - test["odejdzie"].to_numpy(dtype=int)

    model_t = ModelUpliftT().fit(trening, w_tr, y_tr)
    model_s, drzewa_s = s_learner(trening, w_tr, y_tr)
    prog = float(np.quantile(trening["score_polityki"], 1 - FRAKCJA_REGULY))
    p_o, p_k = model_t.predict_skladowe(test)
    wyniki = {
        T: p_o - p_k,
        S: model_s.predict(macierz(test))[:, 0],
        REGULA: (test["score_polityki"] >= prog).to_numpy(dtype=float),
        SCORE: test["score_polityki"].to_numpy(dtype=float),
    }

    na_tescie = {n: miary(y_te, w_te, wynik) for n, wynik in wyniki.items()}
    boot = bootstrap_miar(y_te, w_te, wyniki, pary=[(T, REGULA), (S, REGULA), (T, S), (T, SCORE)])
    tab_kw = pd.concat([kwintyle(y_te, w_te, wyniki[n], n) for n in (T, S)], ignore_index=True)
    korelacje = pd.DataFrame(wyniki).corr(method="spearman").round(4).to_dict()

    opis_czesci = {}
    for nazwa, czesc, w, y in (("trening", trening, w_tr, y_tr), ("test", test, w_te, y_te)):
        w = np.asarray(w, dtype=bool)
        opis_czesci[nazwa] = {
            "umowy": int(len(czesc)),
            "oferta": int(w.sum()),
            "kontrola": int((~w).sum()),
            "przedluzenia_oferta": float(y[w].mean()),
            "przedluzenia_kontrola": float(y[~w].mean()),
            "ate": float(y[w].mean() - y[~w].mean()),
            "b2b": float((czesc["linia_umowy"] == "B2B").mean()),
            "data_konca_od": str(czesc["data_do"].min().date()),
            "data_konca_do": str(czesc["data_do"].max().date()),
        }

    metryki = {
        "wersja": T,
        "dane": {
            "okres": OKRES_UPLIFT,
            "podzial": f"{FRAKCJA_TRENINGU_UPLIFT:.0%} trening według md5(id_umowy), reszta test",
            "czesci": opis_czesci,
        },
        "cechy": list(model_t.cechy),
        "parametry": PARAMETRY,
        "liczba_drzew": {"T_oferta": model_t.liczba_drzew_["oferta"], "T_kontrola": model_t.liczba_drzew_["kontrola"],
                         "S": drzewa_s},  # fmt: skip
        "prog_reguly_score": prog,
        "regula_udzial_na_tescie": float(wyniki[REGULA].mean()),
        "test": na_tescie,
        "bootstrap": boot,
        "kwintyle": tab_kw.to_dict("records"),
        "korelacje_spearmana_test": korelacje,
        "przewidywany_uplift_test": {
            n: {"srednia": float(np.mean(wyniki[n])), "p10": float(np.percentile(wyniki[n], 10)),
                "p90": float(np.percentile(wyniki[n], 90)), "udzial_ujemnych": float(np.mean(wyniki[n] < 0))}
            for n in (T, S)
        },  # fmt: skip
        "waznosc_cech_T": model_t.waznosc_cech().head(10).to_dict("records"),
    }
    KATALOG_WERSJI.mkdir(parents=True, exist_ok=True)
    model_t.zapisz(KATALOG_WERSJI / "model.joblib")
    sciezka_metryk = KATALOG_WERSJI / "metryki.json"
    sciezka_metryk.write_text(json.dumps(metryki, ensure_ascii=False, indent=2), encoding="utf-8")

    pred = test[["id_umowy", "data_do", "linia_umowy", "grupa", "odejdzie", "score_polityki"]].copy()
    pred["przedluzona"] = y_te
    pred["p_oferta_T"], pred["p_kontrola_T"] = p_o, p_k
    for n in (T, S, REGULA):
        pred[f"wynik_{n}"] = wyniki[n]
    SCIEZKA_PREDYKCJI.parent.mkdir(exist_ok=True)
    pred.to_parquet(SCIEZKA_PREDYKCJI, index=False)

    SCIEZKA_QINI.parent.mkdir(parents=True, exist_ok=True)
    rysuj_qini(y_te, w_te, wyniki, SCIEZKA_QINI)
    rysuj_kwintyle(tab_kw, SCIEZKA_KWINTYLI)

    if z_mlflow:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        role = {T: "model", S: "model_porownawczy", REGULA: "baseline", SCORE: "ranking_dodatkowy"}
        for nazwa in (T, S, REGULA, SCORE):
            m = na_tescie[nazwa]
            zapisz_run(
                nazwa,
                parametry={"zbior": f"{OKRES_UPLIFT}, test 30% według id_umowy", "opis": OPISY[nazwa]}
                | (
                    {
                        "liczba_drzew_oferta": model_t.liczba_drzew_["oferta"],
                        "liczba_drzew_kontrola": model_t.liczba_drzew_["kontrola"],
                        **PARAMETRY,
                    }
                    if nazwa == T
                    else {}
                )
                | ({"liczba_drzew": drzewa_s} if nazwa == S else {})
                | ({"prog_score": prog} if nazwa == REGULA else {}),  # fmt: skip
                metryki={f"test_{k}": v for k, v in m.items()},
                tagi={"model": "churn_model", "rola": role[nazwa], "typ": "uplift"},
                artefakty=[sciezka_metryk, SCIEZKA_PREDYKCJI, SCIEZKA_QINI, SCIEZKA_KWINTYLI],
            )
    return metryki


if __name__ == "__main__":
    wynik = main(z_mlflow="--bez-mlflow" not in sys.argv)
    print(json.dumps(wynik["dane"], ensure_ascii=False, indent=2))
    print("drzewa:", wynik["liczba_drzew"], "| próg reguły:", round(wynik["prog_reguly_score"], 5),
          "| udział reguły na teście:", round(wynik["regula_udzial_na_tescie"], 4))  # fmt: skip
    print(pd.DataFrame(wynik["test"]).T.round(4).to_string())
    for n, d in wynik["bootstrap"]["przedzialy"].items():
        print(n, {k: [round(a, 4) for a in v] for k, v in d.items()})
    for n, d in wynik["bootstrap"]["roznice"].items():
        print(n, {k: [round(a, 4) for a in v] for k, v in d.items()})
    print(pd.DataFrame(wynik["kwintyle"]).round(4).to_string(index=False))
    print(json.dumps(wynik["przewidywany_uplift_test"], indent=1))
    print(pd.DataFrame(wynik["korelacje_spearmana_test"]))
    print(pd.DataFrame(wynik["waznosc_cech_T"]).round(3).to_string(index=False))
