"""Liczby do docs/b1_v1.md: efekty v1 w % ceny, podział losowy 85/15 vs czasowy, miesięczna mediana ceny m² i trend.

Uruchomienie (wymaga domilo.duckdb i nauczonego v1: `python -m api.ai.valuation_model.evals.ewaluacja`):
    cd api && poetry run python -m api.ai.valuation_model.evals.analiza_v1
"""

from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.podzial import sql_podzialu
from api.ai.features.wycena.zbior import wczytaj_transakcje
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.metryki import metryki
from api.ai.valuation_model.versions.v0_mediana_dzielnicy.model import ModelMedianaDzielnicy
from api.ai.valuation_model.versions.v1_liniowa.model import ModelLiniowy
from sklearn.model_selection import train_test_split

SCIEZKA_V1 = Path(__file__).resolve().parents[1] / "versions" / "v1_liniowa" / "model.joblib"
ZIARNA = (1, 2, 3, 4, 5)
CECHY = list(KOLUMNY_CECH)

SQL_MEDIANA_MIESIECZNA = """
-- Miesięczna mediana ceny m² (transakcje z podziału, czyli znane w dniu eksportu), razem i w miastach
SELECT strftime(t.data_aktu, '%Y-%m') AS miesiac,
       count(*) AS transakcje,
       median(t.cena_m2) AS razem,
       median(t.cena_m2) FILTER (t.miasto = 'Warszawa') AS warszawa,
       median(t.cena_m2) FILTER (t.miasto = 'Kraków') AS krakow,
       median(t.cena_m2) FILTER (t.miasto = 'Wrocław') AS wroclaw,
       median(t.cena_m2) FILTER (t.miasto = 'Poznań') AS poznan,
       median(t.cena_m2) FILTER (t.miasto = 'Gdańsk') AS gdansk,
       median(t.cena_m2) FILTER (t.miasto = 'Łódź') AS lodz
FROM rcn_transakcje t JOIN ({podzial}) p USING (id_transakcji)
GROUP BY ALL ORDER BY miesiac
"""

SQL_MEDIANA_ROCZNA = """
SELECT CASE WHEN year(t.data_aktu) = 2026 THEN '2026 (I–VI)' ELSE CAST(year(t.data_aktu) AS VARCHAR) END AS okres,
       count(*) AS transakcje, median(t.cena_m2) AS mediana_ceny_m2
FROM rcn_transakcje t JOIN ({podzial}) p USING (id_transakcji)
GROUP BY ALL ORDER BY okres
"""


def _fmt(x, miejsca=1):
    if x is None or x is pd.NA:
        return ""
    if isinstance(x, (int, np.integer)):
        return f"{x:,}".replace(",", " ")
    if isinstance(x, (float, np.floating)):
        if np.isnan(x):
            return ""
        return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")
    return str(x).replace("|", "\\|")


def _md(df: pd.DataFrame, miejsca=1) -> str:
    linie = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    linie += ["| " + " | ".join(_fmt(x, miejsca) for x in w) + " |" for w in df.itertuples(index=False)]
    return "\n".join(linie)


def trend(seria: pd.Series) -> tuple[float, float]:
    """Trend log-liniowy ln(y) = a + b·t (t = numer miesiąca): (% na miesiąc, % na rok = 100·(e^(12b) − 1))."""
    t = np.arange(len(seria), dtype=float)
    b = np.polyfit(t, np.log(seria.to_numpy(dtype=float)), 1)[0]
    return 100 * (np.exp(b) - 1), 100 * (np.exp(12 * b) - 1)


def efekty(df: pd.DataFrame) -> None:
    v1 = ModelWyceny.wczytaj(SCIEZKA_V1)
    ef = v1.efekty_procentowe()
    # Surowa różnica ceny m² dzielnicy vs miasta w treningu (bez wyrównania cech), do porównania z efektem modelu.
    tr = df[df["zbior"] == "trening"]
    med_miasta = tr.groupby("miasto")["cena_m2"].median()
    dz = v1.explain(tr[CECHY])["dzielnica_w_modelu"]
    med_kat = tr.assign(kat=dz).groupby(["miasto", "kat"])["cena_m2"].median()
    surowo = {f"dzielnica: {k}": 100 * (v / med_miasta[m] - 1) for (m, k), v in med_kat.items()}
    ef["surowa_roznica_m2_proc"] = ef["cecha"].map(surowo)
    ef["transakcje_trening"] = ef["transakcje_trening"].astype("Int64")
    ranking = ef[ef["typ"] != "metraz"].assign(abs_efekt=lambda d: d["efekt_proc"].abs())
    top = ranking.sort_values("abs_efekt", ascending=False).head(10)
    kol = ["cecha", "b", "efekt_proc", "odniesienie", "transakcje_trening", "surowa_roznica_m2_proc"]
    print(f"### 1a. Top 10 efektów v1 wg |e^b − 1|\n\n{_md(top[kol], 4)}\n")
    reszta = ef[ef["typ"] != "dzielnica"]
    print(
        f"### 1b. Efekty cech innych niż dzielnica\n\n{_md(reszta[['cecha', 'b', 'efekt_proc', 'odniesienie']], 4)}\n"
    )
    d = ef[ef["typ"] == "dzielnica"]
    print(
        f"Dzielnice: {len(d)} kategorii, efekt od {d['efekt_proc'].min():.1f}% do {d['efekt_proc'].max():.1f}%, "
        f"|efekt| > 20%: {(d['efekt_proc'].abs() > 20).sum()}\n"
    )
    return v1


def _ogon(y, pred, nazwa: str) -> dict:
    """Wpływ bardzo dużych błędów: udział |błąd| > 50% i MAPE bez nich."""
    ape = 100 * np.abs(np.asarray(pred) / np.asarray(y, dtype=float) - 1)
    duze = ape > 50
    return {"wariant": nazwa, "n": int(len(ape)), "mape": ape.mean(), "mdape": float(np.median(ape)),
            "bledy_ponad_50_proc": int(duze.sum()), "udzial_proc": 100 * duze.mean(),
            "mape_bez_nich": ape[~duze].mean(), "max_ape": ape.max()}  # fmt: skip


def podzial_losowy(df: pd.DataFrame) -> None:
    wiersze, ogony = [], []
    tr, te = df[df["zbior"] == "trening"], df[df["zbior"] == "test"]
    for klasa in (ModelMedianaDzielnicy, ModelLiniowy):
        m = klasa().fit(tr[CECHY], tr["cena_pln"])
        w = metryki(te["cena_pln"], m.predict(te[CECHY]))
        wiersze.append({"podzial": "czasowy (trening → test 2026-I–VI)", "ziarno": "", "wersja": m.wersja, **w})
        if klasa is ModelLiniowy:
            ogony.append(_ogon(te["cena_pln"], m.predict(te[CECHY]), "v1, podział czasowy, test"))
    for ziarno in ZIARNA:
        ucz, test = train_test_split(df, test_size=0.15, random_state=ziarno)
        for klasa in (ModelMedianaDzielnicy, ModelLiniowy):
            m = klasa().fit(ucz[CECHY], ucz["cena_pln"])
            pred = pd.Series(m.predict(test[CECHY]), index=test.index)
            w = metryki(test["cena_pln"], pred)
            if klasa is ModelLiniowy and ziarno == ZIARNA[0]:
                ogony.append(_ogon(test["cena_pln"], pred, f"v1, podział losowy (ziarno {ziarno}), 15%"))
            maska = test["data_aktu"] >= pd.Timestamp("2026-01-01")
            w26 = metryki(test.loc[maska, "cena_pln"], pred[maska])
            wiersze.append(
                {"podzial": "losowy 85/15", "ziarno": ziarno, "wersja": m.wersja, **w,
                 "n_2026": w26["n"], "mape_2026": w26["mape"], "mediana_bledu_2026": w26["mediana_bledu_proc"]}
            )  # fmt: skip
    wyn = pd.DataFrame(wiersze)
    kol = ["podzial", "ziarno", "wersja", "n", "mae", "rmse", "mape", "mdape", "mediana_bledu_proc"]
    kol += ["n_2026", "mape_2026", "mediana_bledu_2026"]
    print(f"### 2a. Podział losowy 85/15 vs czasowy\n\n{_md(wyn[kol], 2)}\n")
    los = wyn[wyn["podzial"] == "losowy 85/15"]
    sr = los.groupby("wersja")[["n", "mae", "rmse", "mape", "mdape", "mediana_bledu_proc", "mape_2026"]].agg(
        ["mean", "min", "max"]
    )
    sr.columns = [f"{a}_{b}" for a, b in sr.columns]
    print(f"### 2b. Losowy 85/15: średnia, min, max z {len(ZIARNA)} ziaren\n\n{_md(sr.reset_index(), 2)}\n")
    print(f"### 2c. Bardzo duże błędy (> 50%) a MAPE\n\n{_md(pd.DataFrame(ogony), 2)}\n")


def mediana_miesieczna(con, df: pd.DataFrame, v1: ModelWyceny) -> None:
    mies = con.execute(SQL_MEDIANA_MIESIECZNA.format(podzial=sql_podzialu())).df()
    # Indeks „stałej jakości”: mediana (cena / wycena v1 − 1) w miesiącu, v1 uczony na treningu (bez czasu).
    reszty = df.assign(r=df["cena_pln"] / v1.predict(df[CECHY]) - 1, miesiac=df["data_aktu"].dt.strftime("%Y-%m"))
    mies = mies.merge(
        reszty.groupby("miesiac")["r"].median().mul(100).rename("cena_vs_wycena_v1_proc").reset_index(), on="miesiac"
    )
    print(f"### 3a. Miesięczna mediana ceny m² (zł)\n\n{_md(mies, 1)}\n")
    roczna = con.execute(SQL_MEDIANA_ROCZNA.format(podzial=sql_podzialu())).df()
    roczna["zmiana_rdr_proc"] = 100 * roczna["mediana_ceny_m2"].pct_change()
    print(f"### 3b. Mediana ceny m² w latach\n\n{_md(roczna, 1)}\n")
    wiersze = []
    for kol in ("razem", "warszawa", "krakow", "wroclaw", "poznan", "gdansk", "lodz"):
        mies_proc, rok_proc = trend(mies[kol])
        pierwsze, ostatnie = mies[kol].iloc[:6].median(), mies[kol].iloc[-6:].median()
        wiersze.append(
            {"seria": kol, "trend_proc_mies": mies_proc, "trend_proc_rok": rok_proc,
             "mediana_6_pierwszych_mies": pierwsze, "mediana_6_ostatnich_mies": ostatnie,
             "zmiana_proc": 100 * (ostatnie / pierwsze - 1)}
        )  # fmt: skip
    ind = 1 + mies["cena_vs_wycena_v1_proc"] / 100
    mies_proc, rok_proc = trend(ind)
    wiersze.append(
        {"seria": "stała jakość: cena / wycena v1", "trend_proc_mies": mies_proc, "trend_proc_rok": rok_proc,
         "mediana_6_pierwszych_mies": ind.iloc[:6].median(), "mediana_6_ostatnich_mies": ind.iloc[-6:].median(),
         "zmiana_proc": 100 * (ind.iloc[-6:].median() / ind.iloc[:6].median() - 1)}
    )  # fmt: skip
    print(f"### 3c. Trend (log-liniowy, 42 miesiące 2023-01 – 2026-06)\n\n{_md(pd.DataFrame(wiersze), 2)}\n")


def main() -> None:
    con = polacz()
    df = wczytaj_transakcje(con)
    v1 = efekty(df)
    podzial_losowy(df)
    mediana_miesieczna(con, df, v1)


if __name__ == "__main__":
    main()
