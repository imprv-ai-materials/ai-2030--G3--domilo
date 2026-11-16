"""Losowy test rabatu `test_2025` (retencja_decyzje): czy losowanie się udało i ile rabat zmienia przedłużenia.

Uruchomienie (wymaga domilo.duckdb z migawki_najemcy i cechy_najemcy: `pypyr baza`):
    cd api && poetry run python -m api.ai.churn_model.evals.eksperyment_rabatu_2025

- Populacja: wszystkie umowy z `retencja_decyzje.okres = 'test_2025'` (końce umów 2025-07 – 2026-03), przydział
  oferty losowy 50/50 (`grupa` = oferta / kontrola). Wynik: przedłużenie = 1 − `migawki_najemcy.odejdzie`.
- Balans: 10 cech o największej ważności (gain) w v1_ryzyko (`versions/v1_ryzyko/metryki.json`), wartości na dzień
  migawki z `cechy_najemcy`. Dla każdej: średnia (dla `linia` udział B2B) w obu grupach, standaryzowana różnica
  średnich (SMD), udział braków i p z testu Welcha (dla `linia` test z dwóch proporcji). Test łączny: regresja
  logistyczna `grupa ~ 10 cech` (braki: średnia + wskaźnik braku) wobec modelu pustego, test ilorazu wiarygodności.
- Efekt (ATE, intention-to-treat): odsetek przedłużeń oferta − kontrola, 95% przedział Walda (normalny, wariancje
  osobno w grupach). Segmenty: górne 35% i dolne 65% `score_polityki` w całym `test_2025` (próg = kwantyl 0,65).
  Różnica efektów góra − dół z przedziałem (segmenty rozłączne, więc wariancje się sumują).
- Sprawdzenia: przedział z bootstrapu po najemcach (najemca może mieć kilka umów, np. umowa ramowa B2B), podział
  według flagi firmy `kwalifikuje` zamiast progu z całego okresu, efekt w liniach B2C / B2B (analiza dodatkowa).
Zapis: evals/wyniki/eksperyment_rabatu_2025.json. Raport: docs/test_rabatu_2025.md.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from scipy import stats

KATALOG_MODELU = Path(__file__).resolve().parents[1]
SCIEZKA_METRYK_V1 = KATALOG_MODELU / "versions" / "v1_ryzyko" / "metryki.json"
SCIEZKA_WYNIKOW = Path(__file__).with_name("wyniki") / "eksperyment_rabatu_2025.json"
OKRES = "test_2025"
LICZBA_CECH = 10
FRAKCJA_GORY = 0.35
Z95 = float(stats.norm.ppf(0.975))
DNI_OFERTY = 45  # data_oferty = data_konca − 45 dni w całym test_2025 (sprawdza main: dni_oferty_przed_koncem)
N_BOOTSTRAP = 2000
ZIARNO = 42


def cechy_balansu(sciezka: Path = SCIEZKA_METRYK_V1, liczba: int = LICZBA_CECH) -> list[str]:
    """`liczba` cech v1_ryzyko o największym gain (kolejność jak w metryki.json, malejąco)."""
    metryki = json.loads(Path(sciezka).read_text(encoding="utf-8"))
    return [w["cecha"] for w in metryki["waznosc_cech"][:liczba]]


def sql_testu(cechy: list[str]) -> str:
    kolumny = ", ".join(f"c.{k}" for k in cechy if k != "linia")
    return f"""
SELECT r.id_umowy, r.data_konca, r.score_polityki, r.kwalifikuje, r.grupa, r.data_oferty, r.czy_otwarta,
       m.id_najemcy, m.id_umowy_ramowej, m.linia, m.wypowiedzenie_przed_migawka,
       coalesce(m.wypowiedzenie_data < m.data_do - INTERVAL {DNI_OFERTY} DAY, false) AS wypowiedzenie_przed_oferta,
       m.odejdzie, 1 - m.odejdzie AS przedluzona,
       f.id_umowy IS NOT NULL AS rabat_w_nastepnej, f.kwota_rabatu, {kolumny}
FROM retencja_decyzje AS r
JOIN migawki_najemcy AS m USING (id_umowy)
JOIN cechy_najemcy AS c USING (id_umowy)
LEFT JOIN (SELECT id_umowy, max(kwota_rabatu) AS kwota_rabatu FROM fk_rabaty GROUP BY id_umowy) AS f
    ON f.id_umowy = m.id_umowy_nastepnej
WHERE r.okres = '{OKRES}'
"""


# --- statystyka ------------------------------------------------------------------------------------------------


def efekt(y, oferta) -> dict:
    """Odsetek przedłużeń w obu grupach, ATE = oferta − kontrola, błąd standardowy i 95% przedział Walda."""
    y = np.asarray(y, dtype=float)
    oferta = np.asarray(oferta, dtype=bool)
    yt, yc = y[oferta], y[~oferta]
    pt, pc = yt.mean(), yc.mean()
    se = float(np.sqrt(pt * (1 - pt) / len(yt) + pc * (1 - pc) / len(yc)))
    ate = float(pt - pc)
    return {
        "n_oferta": int(len(yt)),
        "n_kontrola": int(len(yc)),
        "przedluzone_oferta": int(yt.sum()),
        "przedluzone_kontrola": int(yc.sum()),
        "odsetek_oferta": float(pt),
        "odsetek_kontrola": float(pc),
        "ate": ate,
        "se": se,
        "ci95": [ate - Z95 * se, ate + Z95 * se],
        "p": float(2 * stats.norm.sf(abs(ate / se))) if se > 0 else None,
    }


def efekt_stratyfikowany(y, oferta, warstwa) -> dict:
    """ATE ważony udziałem warstw (post-stratyfikacja), SE = sqrt(sum w^2 se^2), 95% przedział normalny."""
    y = np.asarray(y, dtype=float)
    oferta = np.asarray(oferta, dtype=bool)
    warstwa = np.asarray(warstwa)
    ate, wariancja = 0.0, 0.0
    for w in np.unique(warstwa):
        m = warstwa == w
        e = efekt(y[m], oferta[m])
        ate += m.mean() * e["ate"]
        wariancja += m.mean() ** 2 * e["se"] ** 2
    se = float(np.sqrt(wariancja))
    return {"ate": float(ate), "se": se, "ci95": [ate - Z95 * se, ate + Z95 * se]}


def roznica_efektow(a: dict, b: dict) -> dict:
    """Różnica ATE dwóch rozłącznych segmentów (a − b) z 95% przedziałem."""
    roznica = a["ate"] - b["ate"]
    se = float(np.sqrt(a["se"] ** 2 + b["se"] ** 2))
    return {
        "roznica": float(roznica),
        "se": se,
        "ci95": [roznica - Z95 * se, roznica + Z95 * se],
        "p": float(2 * stats.norm.sf(abs(roznica / se))),
    }


def ate_bootstrap_klastrow(y, oferta, klastry, n_prob: int = N_BOOTSTRAP, ziarno: int = ZIARNO) -> list[float]:
    """95% przedział percentylowy ATE z losowania klastrów (najemców) ze zwracaniem."""
    y = np.asarray(y, dtype=float)
    oferta = np.asarray(oferta, dtype=bool)
    kody, klastry_idx = np.unique(np.asarray(klastry), return_inverse=True)
    porzadek = np.argsort(klastry_idx, kind="stable")
    granice = np.r_[0, np.cumsum(np.bincount(klastry_idx, minlength=len(kody)))]
    rng = np.random.default_rng(ziarno)
    wyniki = []
    for _ in range(n_prob):
        wybrane = rng.integers(0, len(kody), len(kody))
        i = np.concatenate([porzadek[granice[k] : granice[k + 1]] for k in wybrane])
        t = oferta[i]
        wyniki.append(y[i][t].mean() - y[i][~t].mean())
    return [float(np.percentile(wyniki, 2.5)), float(np.percentile(wyniki, 97.5))]


def gorne_35(score: pd.Series, frakcja: float = FRAKCJA_GORY) -> pd.Series:
    """True dla umów ze score >= kwantyl (1 − frakcja), liczonego interpolacją liniową (jak quantile_cont)."""
    prog = float(np.quantile(score.to_numpy(dtype=float), 1 - frakcja))
    return score >= prog


def _smd(xt: np.ndarray, xc: np.ndarray, binarna: bool) -> float:
    if binarna:
        pt, pc = xt.mean(), xc.mean()
        mianownik = np.sqrt((pt * (1 - pt) + pc * (1 - pc)) / 2)
    else:
        mianownik = np.sqrt((xt.var(ddof=1) + xc.var(ddof=1)) / 2)
    return float((xt.mean() - xc.mean()) / mianownik) if mianownik > 0 else 0.0


def balans_cechy(x: pd.Series, oferta, nazwa: str) -> dict:
    """Średnia w grupach (dla `linia`: udział B2B), SMD, udział braków, p (Welch / test dwóch proporcji)."""
    oferta = np.asarray(oferta, dtype=bool)
    binarna = nazwa == "linia"
    if binarna:
        x = (x == "B2B").astype(float).where(x.notna())
    x = x.to_numpy(dtype=float)
    braki = np.isnan(x)
    xt, xc = x[oferta & ~braki], x[~oferta & ~braki]
    if binarna:
        p_wsp = np.r_[xt, xc].mean()
        se = np.sqrt(p_wsp * (1 - p_wsp) * (1 / len(xt) + 1 / len(xc)))
        p = float(2 * stats.norm.sf(abs(xt.mean() - xc.mean()) / se)) if se > 0 else 1.0
    else:
        p = float(stats.ttest_ind(xt, xc, equal_var=False).pvalue)
    return {
        "cecha": "linia (udział B2B)" if binarna else nazwa,
        "oferta": float(xt.mean()),
        "kontrola": float(xc.mean()),
        "smd": _smd(xt, xc, binarna),
        "braki_oferta": float(braki[oferta].mean()),
        "braki_kontrola": float(braki[~oferta].mean()),
        "p": p,
    }


def _macierz(df: pd.DataFrame, cechy: list[str]) -> np.ndarray:
    """Cechy liczbowe (brak = średnia) + wskaźniki braku (jeden na wzór braków, np. dwie cechy ankiety mają ten sam),
    `linia` jako 0/1 B2B; kolumny standaryzowane."""
    kolumny, wzory_brakow = [], []
    for k in cechy:
        if k == "linia":
            kolumny.append((df[k] == "B2B").to_numpy(dtype=float))
            continue
        x = df[k].to_numpy(dtype=float)
        braki = np.isnan(x)
        kolumny.append(np.where(braki, np.nanmean(x), x))
        if braki.any() and not any(np.array_equal(braki, w) for w in wzory_brakow):
            wzory_brakow.append(braki)
            kolumny.append(braki.astype(float))
    X = np.column_stack(kolumny)
    sd = X.std(axis=0)
    return (X - X.mean(axis=0)) / np.where(sd > 0, sd, 1.0)


def _logit_loglik(X: np.ndarray, y: np.ndarray, iteracje: int = 50) -> float:
    """Log-wiarygodność regresji logistycznej (z wyrazem wolnym) dopasowanej metodą Newtona."""
    X = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(X.shape[1])
    for _ in range(iteracje):
        p = 1 / (1 + np.exp(-X @ beta))
        hesjan = X.T @ (X * (p * (1 - p))[:, None])
        krok = np.linalg.solve(hesjan, X.T @ (y - p))
        beta += krok
        if np.max(np.abs(krok)) < 1e-10:
            break
    p = np.clip(1 / (1 + np.exp(-X @ beta)), 1e-12, 1 - 1e-12)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def laczny_test_balansu(df: pd.DataFrame, oferta, cechy: list[str]) -> dict:
    """Test ilorazu wiarygodności: czy cechy razem przewidują grupę (oferta) lepiej niż model pusty."""
    y = np.asarray(oferta, dtype=float)
    X = _macierz(df, cechy)
    ll_pelny = _logit_loglik(X, y)
    p0 = y.mean()
    ll_pusty = float(len(y) * (p0 * np.log(p0) + (1 - p0) * np.log(1 - p0)))
    lr = 2 * (ll_pelny - ll_pusty)
    return {"statystyka_lr": float(lr), "stopnie_swobody": int(X.shape[1]), "p": float(stats.chi2.sf(lr, X.shape[1]))}


# --- analiza ---------------------------------------------------------------------------------------------------


def wczytaj(con, cechy: list[str]) -> pd.DataFrame:
    df = con.execute(sql_testu(cechy)).df()
    n_okresu = con.execute(f"SELECT count(*) FROM retencja_decyzje WHERE okres = '{OKRES}'").fetchone()[0]
    if len(df) != n_okresu:
        raise ValueError(f"{OKRES}: złączenie z migawki_najemcy / cechy_najemcy gubi umowy ({len(df)} z {n_okresu})")
    if set(df["grupa"]) != {"oferta", "kontrola"}:
        raise ValueError(f"{OKRES}: nieoczekiwane grupy {sorted(set(df['grupa']))}")
    df["oferta"] = df["grupa"] == "oferta"
    df["gorne_35"] = gorne_35(df["score_polityki"])
    df["miesiac_konca"] = pd.to_datetime(df["data_konca"]).dt.strftime("%Y-%m")
    return df


def balans(df: pd.DataFrame, cechy: list[str]) -> dict:
    oferta = df["oferta"].to_numpy()
    n_oferta = int(oferta.sum())
    miesiace = pd.crosstab(df["miesiac_konca"], df["grupa"])
    segmenty = {"gorne_35": df["gorne_35"].to_numpy(), "dolne_65": ~df["gorne_35"].to_numpy()}
    return {
        "liczebnosc": {
            "n": int(len(df)),
            "oferta": n_oferta,
            "kontrola": int(len(df) - n_oferta),
            "udzial_oferty": n_oferta / len(df),
            "p_dwumianowy_50_50": float(stats.binomtest(n_oferta, len(df), 0.5).pvalue),
        },
        "cechy": [balans_cechy(df[k], oferta, k) for k in cechy],
        "laczny": laczny_test_balansu(df, oferta, cechy),
        "dodatkowe": [
            balans_cechy(df["score_polityki"], oferta, "score_polityki"),
            balans_cechy(df["wypowiedzenie_przed_migawka"].astype(float), oferta, "wypowiedzenie_przed_migawka"),
        ],
        "miesiace": {
            "tabela": miesiace.reset_index().to_dict("records"),
            "p_chi2": float(stats.chi2_contingency(miesiace.to_numpy())[1]),
        },
        "segmenty": {
            nazwa: {
                "n": int(m.sum()),
                "oferta": int((oferta & m).sum()),
                "p_dwumianowy_50_50": float(stats.binomtest(int((oferta & m).sum()), int(m.sum()), 0.5).pvalue),
                "cechy": [balans_cechy(df.loc[m, k], oferta[m], k) for k in cechy],
                "laczny": laczny_test_balansu(df.loc[m].reset_index(drop=True), oferta[m], cechy),
            }
            for nazwa, m in segmenty.items()
        },
    }


def efekty(df: pd.DataFrame, maski: dict[str, np.ndarray], z_bootstrapem: bool = True) -> dict:
    wynik = {}
    for nazwa, m in maski.items():
        seg = df.loc[m]
        e = efekt(seg["przedluzona"], seg["oferta"])
        e["score_od"] = float(seg["score_polityki"].min())
        e["score_do"] = float(seg["score_polityki"].max())
        e["udzial_b2b"] = float((seg["linia"] == "B2B").mean())
        e["otwarte_oferty"] = float(seg.loc[seg["oferta"], "czy_otwarta"].astype(float).mean())
        if z_bootstrapem:
            e["ci95_bootstrap_najemcy"] = ate_bootstrap_klastrow(seg["przedluzona"], seg["oferta"], seg["id_najemcy"])
        wynik[nazwa] = e
    return wynik


def wypowiedzenia(df: pd.DataFrame, maski: dict[str, np.ndarray]) -> dict:
    """Wypowiedzenia złożone przed migawką i przed ofertą w obu grupach (zdarzenia sprzed dnia oferty)."""
    wynik = {}
    for nazwa, m in maski.items():
        seg = df.loc[m]
        o = seg["oferta"].to_numpy()
        odch = seg["odejdzie"] == 1
        wynik[nazwa] = {
            k: balans_cechy(seg[k].astype(float), o, k)
            for k in ("wypowiedzenie_przed_migawka", "wypowiedzenie_przed_oferta")
        } | {
            "odchodzacy_z_wyp_przed_oferta": {
                "oferta": float(seg.loc[odch & seg["oferta"], "wypowiedzenie_przed_oferta"].mean()),
                "kontrola": float(seg.loc[odch & ~seg["oferta"], "wypowiedzenie_przed_oferta"].mean()),
            }
        }
    return wynik


def wrazliwosc(df: pd.DataFrame, maski: dict[str, np.ndarray]) -> dict:
    """ATE bez umów z wypowiedzeniem przed migawką oraz ATE stratyfikowany po tej fladze."""
    wynik = {}
    for nazwa, m in maski.items():
        seg = df.loc[m]
        bez = seg.loc[~seg["wypowiedzenie_przed_migawka"]]
        wynik[nazwa] = {
            "bez_wyp_przed_migawka": efekt(bez["przedluzona"], bez["oferta"]),
            "stratyfikowany_wyp_przed_migawka": efekt_stratyfikowany(
                seg["przedluzona"], seg["oferta"], seg["wypowiedzenie_przed_migawka"]
            ),
        }
    return wynik


def rabaty(df: pd.DataFrame, maski: dict[str, np.ndarray]) -> dict:
    """Przedłużenia z rabatem w następnej umowie (fk_rabaty) w obu grupach."""
    wynik = {}
    for nazwa, m in maski.items():
        seg = df.loc[m & (df["przedluzona"] == 1).to_numpy()]
        wynik[nazwa] = {
            g: {
                "przedluzone": int((seg["grupa"] == g).sum()),
                "z_rabatem": int(seg.loc[seg["grupa"] == g, "rabat_w_nastepnej"].sum()),
                "kwoty_rabatu": sorted(
                    seg.loc[seg["grupa"] == g, "kwota_rabatu"].dropna().astype(int).unique().tolist()
                ),
            }
            for g in ("oferta", "kontrola")
        }
    return wynik


def main() -> dict:
    cechy = cechy_balansu()
    with polacz() as con:
        df = wczytaj(con, cechy)
    gora = df["gorne_35"].to_numpy()
    kwal = df["kwalifikuje"].to_numpy(dtype=bool)
    b2b = (df["linia"] == "B2B").to_numpy()

    segmenty = {"wszystkie": np.ones(len(df), dtype=bool), "gorne_35": gora, "dolne_65": ~gora}
    glowne = efekty(df, segmenty)
    wg_kwalifikuje = efekty(df, {"kwalifikuje": kwal, "nie_kwalifikuje": ~kwal}, z_bootstrapem=False)
    wg_linii = efekty(
        df,
        {
            "B2C": ~b2b,
            "B2B": b2b,
            "B2C_gorne_35": ~b2b & gora,
            "B2C_dolne_65": ~b2b & ~gora,
            "B2B_gorne_35": b2b & gora,
            "B2B_dolne_65": b2b & ~gora,
        },
        z_bootstrapem=False,
    )
    wyniki = {
        "okres": OKRES,
        "data_konca_od": str(pd.to_datetime(df["data_konca"]).min().date()),
        "data_konca_do": str(pd.to_datetime(df["data_konca"]).max().date()),
        "dni_oferty_przed_koncem": sorted(
            (pd.to_datetime(df["data_konca"]) - pd.to_datetime(df["data_oferty"])).dt.days.dropna().unique().tolist()
        ),
        "cechy_balansu": cechy,
        "prog_gornych_35": float(np.quantile(df["score_polityki"], 1 - FRAKCJA_GORY)),
        "zgodnosc_gorne_35_z_kwalifikuje": pd.crosstab(df["gorne_35"], df["kwalifikuje"])
        .rename_axis(index="gorne_35", columns="kwalifikuje")
        .stack()
        .rename("umowy")
        .reset_index()
        .to_dict("records"),
        "balans": balans(df, cechy),
        "efekty": glowne,
        "roznica_gorne_minus_dolne": roznica_efektow(glowne["gorne_35"], glowne["dolne_65"]),
        "wypowiedzenia": wypowiedzenia(df, segmenty),
        "wrazliwosc": wrazliwosc(df, segmenty),
        "rabaty": rabaty(df, segmenty),
        "efekty_wg_kwalifikuje": wg_kwalifikuje,
        "roznica_kwalifikuje_minus_nie": roznica_efektow(
            wg_kwalifikuje["kwalifikuje"], wg_kwalifikuje["nie_kwalifikuje"]
        ),
        "efekty_wg_linii": wg_linii,
        "roznica_B2C_minus_B2B": roznica_efektow(wg_linii["B2C"], wg_linii["B2B"]),
    }
    SCIEZKA_WYNIKOW.parent.mkdir(exist_ok=True)
    SCIEZKA_WYNIKOW.write_text(json.dumps(wyniki, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return wyniki


if __name__ == "__main__":
    w = main()
    b = w["balans"]
    print("Liczebność:", b["liczebnosc"])
    print(
        "Próg górnych 35%:",
        round(w["prog_gornych_35"], 5),
        "| zgodność z kwalifikuje:",
        w["zgodnosc_gorne_35_z_kwalifikuje"],
    )
    print("\n## Balans (10 cech v1)")
    print(pd.DataFrame(b["cechy"] + b["dodatkowe"]).round(4).to_string(index=False))
    print("Łącznie:", b["laczny"], "| miesiące p_chi2:", round(b["miesiace"]["p_chi2"], 4))
    for seg, s in b["segmenty"].items():
        print(f"\n## Balans w segmencie {seg}: n={s['n']}, oferta={s['oferta']}, p50/50={s['p_dwumianowy_50_50']:.4f}")
        print(pd.DataFrame(s["cechy"])[["cecha", "oferta", "kontrola", "smd", "p"]].round(4).to_string(index=False))
        print("Łącznie:", s["laczny"])
    print("dni oferty przed końcem:", w["dni_oferty_przed_koncem"])
    for seg, s in w["wypowiedzenia"].items():
        print(f"\n## Wypowiedzenia {seg}")
        print(
            pd.DataFrame([s["wypowiedzenie_przed_migawka"], s["wypowiedzenie_przed_oferta"]])
            .round(4)
            .to_string(index=False)
        )
        print("odchodzący z wypowiedzeniem przed ofertą:", s["odchodzacy_z_wyp_przed_oferta"])
    for seg, s in w["wrazliwosc"].items():
        print(f"\n## Wrażliwość {seg}")
        print(pd.DataFrame(s).T.to_string())
    print("\n## Rabaty", json.dumps(w["rabaty"], ensure_ascii=False))
    for klucz in ("efekty", "efekty_wg_kwalifikuje", "efekty_wg_linii"):
        print(f"\n## {klucz}")
        print(pd.DataFrame(w[klucz]).T.to_string())
    for klucz in ("roznica_gorne_minus_dolne", "roznica_kwalifikuje_minus_nie", "roznica_B2C_minus_B2B"):
        print(klucz, w[klucz])
