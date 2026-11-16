"""Kampania retencyjna Q3 2026: czy oferta (rabat 150 zł / mies.) zarabia, mierzone na losowej grupie kontrolnej.

Uruchomienie (wymaga domilo.duckdb z migawki_najemcy: `pypyr baza`):
    cd api && poetry run python -m api.contexts_boundaries.retention_bc.kampania_2026q3

- Populacja: `retencja_decyzje.okres = 'kampania_2026q3'` (końce umów 2026-07 – 2026-09), umowy kwalifikujące się
  według starej reguły (górne 35% `score_polityki`, flaga `kwalifikuje`). Około 20% z nich losowo nie dostało
  oferty (`grupa = 'kontrola'`), reszta dostała (`grupa = 'oferta'`). Umowy `brak_oferty` (nie kwalifikują się)
  są poza porównaniem.
- Wynik: przedłużenie = 1 − `migawki_najemcy.odejdzie` (kolejny okres umowy albo przeprowadzka do innego lokalu
  Domilo; dla końców umów do 2026-09-30 wynik jest znany: docs/target_najemcy.md).
- Rabat: przedłużenie z ofertą, którego następna umowa ma pozycje w `fk_rabaty` (rabat faktycznie przyznany).
- Wynik netto kampanii (założenia R, D, k z retention_bc/zalozenia.yaml, podane przez użytkownika):
      dodatkowe przedłużenia = (p_oferta − p_kontrola) × liczba ofert
      wynik netto = dodatkowe przedłużenia × R − rabaty × D − oferty × k
      ROI = wynik netto / (rabaty × D + oferty × k)
  D to roczny koszt rabatu, więc „wypłacone rabaty” to rabaty za cały rok nowej umowy (FK zaksięgowało do dnia
  eksportu tylko ich część, podajemy ją osobno).
- 95% przedziały: bootstrap percentylowy, 1 000 losowań, ziarno 42, umowy losowane ze zwracaniem osobno w grupie
  oferta i kontrola (przydział był losowy na poziomie umowy, liczebności grup stałe). Sprawdzenie: bootstrap po
  najemcach (najemca z kilkoma umowami losowany w całości). Dla ATE także przedział Walda.
- Wrażliwość: k = 0 (k = 60 zł to szacunek), D = 1 950 zł (tyle księguje FK za pełny rok: 13 pozycji × 150 zł,
  docs/polityka_rabatow.md) oraz efekt z losowego testu 2025 w grupie `kwalifikuje`
  (churn_model/evals/wyniki/eksperyment_rabatu_2025.json) zamiast efektu z kampanii.
Zapis: retention_bc/wyniki/kampania_2026q3.json. Raport: docs/kampania_2026q3.md.
"""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.contexts_boundaries.retention_bc.zalozenia import ZalozeniaOferty, zalozenia_oferty
from scipy import stats

OKRES = "kampania_2026q3"
N_BOOTSTRAP = 1000
ZIARNO = 42
Z95 = float(stats.norm.ppf(0.975))
UDZIAL_KONTROLI = 0.20  # z opisu kampanii (polecenie użytkownika); sprawdzamy test dwumianowy
D_Z_FK = 1950.0  # fk_rabaty: 13 pozycji × 150 PLN za pełny rok (polityka_rabatow.SQL_D_Z_FK); tylko wrażliwość
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")
SCIEZKA_TESTU_2025 = (
    Path(__file__).resolve().parents[2] / "ai" / "churn_model" / "evals" / "wyniki" / "eksperyment_rabatu_2025.json"
)

SQL_KAMPANII = f"""
SELECT r.id_umowy, r.data_konca::DATE AS data_konca, date_trunc('month', r.data_konca)::DATE AS miesiac_konca,
       r.score_polityki, r.kwalifikuje, r.grupa, r.grupa = 'oferta' AS oferta, r.data_oferty::DATE AS data_oferty,
       r.czy_otwarta, m.id_najemcy, m.linia, m.wypowiedzenie_przed_migawka, m.przeprowadzka,
       1 - m.odejdzie AS przedluzona,
       f.id_umowy IS NOT NULL AS rabat,
       coalesce(f.pozycje, 0) AS rabat_pozycje_do_eksportu,
       coalesce(f.suma, 0) AS rabat_zaksiegowany_pln
FROM retencja_decyzje AS r
JOIN migawki_najemcy AS m USING (id_umowy)
LEFT JOIN (SELECT id_umowy, count(*) AS pozycje, sum(kwota_rabatu) AS suma FROM fk_rabaty GROUP BY id_umowy) AS f
    ON f.id_umowy = m.id_umowy_nastepnej
WHERE r.okres = '{OKRES}' AND r.grupa IN ('oferta', 'kontrola')
ORDER BY r.id_umowy
"""

SQL_GRUPY = f"""
SELECT grupa, kwalifikuje, count(*) AS umowy, min(data_konca)::DATE AS od, max(data_konca)::DATE AS do_,
       count(data_oferty) AS z_data_oferty, min(score_polityki) AS score_min, max(score_polityki) AS score_max
FROM retencja_decyzje WHERE okres = '{OKRES}' GROUP BY ALL ORDER BY ALL
"""

SQL_DNI_OFERTY = f"""
SELECT date_diff('day', data_oferty, data_konca) AS dni, count(*) AS umowy
FROM retencja_decyzje WHERE okres = '{OKRES}' AND grupa = 'oferta' GROUP BY 1 ORDER BY 1
"""

SQL_FK_DO = "SELECT max(miesiac) AS ostatni_miesiac FROM fk_rabaty"


# --- obliczenia ------------------------------------------------------------------------------------------------


def wynik_kampanii(df: pd.DataFrame, z: ZalozeniaOferty) -> dict:
    """Odsetki przedłużeń, dodatkowe przedłużenia, koszty, wynik netto i ROI (kolumny: oferta, przedluzona, rabat)."""
    oferta = df["oferta"].to_numpy(dtype=bool)
    y = df["przedluzona"].to_numpy(dtype=float)
    rabat = df["rabat"].to_numpy(dtype=bool)
    n_o, n_k = int(oferta.sum()), int((~oferta).sum())
    p_o, p_k = float(y[oferta].mean()), float(y[~oferta].mean())
    ate = p_o - p_k
    dodatkowe = ate * n_o
    rabaty_szt = int((rabat & oferta).sum())
    koszt_rabatow = rabaty_szt * z.D
    koszt_kontaktu = n_o * z.k
    koszt = koszt_rabatow + koszt_kontaktu
    korzysc = dodatkowe * z.R
    netto = korzysc - koszt
    return {
        "n_oferta": n_o,
        "n_kontrola": n_k,
        "przedluzone_oferta": int(y[oferta].sum()),
        "przedluzone_kontrola": int(y[~oferta].sum()),
        "odsetek_oferta": p_o,
        "odsetek_kontrola": p_k,
        "ate": ate,
        "dodatkowe_przedluzenia": dodatkowe,
        "rabaty_szt": rabaty_szt,
        "korzysc": korzysc,
        "koszt_rabatow": koszt_rabatow,
        "koszt_kontaktu": koszt_kontaktu,
        "koszt": koszt,
        "wynik_netto": netto,
        "roi": netto / koszt,
        # ATE, przy którym wynik netto = 0, przy tych samych kosztach (rabaty i kontakty) kampanii
        "ate_prog_zera": koszt / z.R / n_o,
        "koszt_na_dodatkowe_przedluzenie": koszt / dodatkowe if dodatkowe > 0 else None,
    }


def ate_wald(w: dict) -> list[float]:
    """95% przedział Walda dla ATE (wariancje osobno w grupach)."""
    p_o, p_k = w["odsetek_oferta"], w["odsetek_kontrola"]
    se = np.sqrt(p_o * (1 - p_o) / w["n_oferta"] + p_k * (1 - p_k) / w["n_kontrola"])
    return [w["ate"] - Z95 * se, w["ate"] + Z95 * se]


def bootstrap_wyniku(
    df: pd.DataFrame,
    z: ZalozeniaOferty,
    n_prob: int = N_BOOTSTRAP,
    ziarno: int = ZIARNO,
    klastry: str | None = None,
) -> pd.DataFrame:
    """`n_prob` wyników kampanii na próbach bootstrap.

    Bez `klastry`: umowy losowane ze zwracaniem osobno w grupie oferta i kontrola (stałe liczebności grup).
    Z `klastry` (np. "id_najemcy"): losowani są najemcy ze wszystkimi swoimi umowami.
    """
    rng = np.random.default_rng(ziarno)
    df = df.reset_index(drop=True)
    wyniki = []
    if klastry is None:
        idx_o = np.flatnonzero(df["oferta"].to_numpy(dtype=bool))
        idx_k = np.flatnonzero(~df["oferta"].to_numpy(dtype=bool))
        for _ in range(n_prob):
            idx = np.r_[rng.choice(idx_o, len(idx_o)), rng.choice(idx_k, len(idx_k))]
            wyniki.append(wynik_kampanii(df.iloc[idx], z))
    else:
        grupy = df.groupby(klastry, sort=True).indices
        listy = list(grupy.values())
        for _ in range(n_prob):
            wyb = rng.integers(0, len(listy), len(listy))
            idx = np.concatenate([listy[i] for i in wyb])
            wyniki.append(wynik_kampanii(df.iloc[idx], z))
    return pd.DataFrame(wyniki)


def przedzial(s: pd.Series) -> list[float]:
    """Percentylowy 95% przedział (2,5 i 97,5 percentyl)."""
    return [float(s.quantile(0.025)), float(s.quantile(0.975))]


def podsumowanie(df: pd.DataFrame, z: ZalozeniaOferty, klastry: str | None = None) -> dict:
    """Wynik punktowy, przedziały z bootstrapu i odsetek losowań z dodatnim wynikiem netto."""
    w = wynik_kampanii(df, z)
    b = bootstrap_wyniku(df, z, klastry=klastry)
    pola = ("odsetek_oferta", "odsetek_kontrola", "ate", "dodatkowe_przedluzenia", "wynik_netto", "roi", "koszt")
    w["ci95_bootstrap"] = {p: przedzial(b[p]) for p in pola}
    w["udzial_losowan_netto_dodatni"] = float((b["wynik_netto"] > 0).mean())
    w["ci95_ate_wald"] = ate_wald(w)
    return w


def wynik_przy_ate(w: dict, ate: float, z: ZalozeniaOferty) -> dict:
    """Wynik netto kampanii, gdyby efekt oferty wynosił `ate` (te same oferty i rabaty co w kampanii)."""
    dodatkowe = ate * w["n_oferta"]
    netto = dodatkowe * z.R - w["rabaty_szt"] * z.D - w["n_oferta"] * z.k
    return {"ate": ate, "dodatkowe_przedluzenia": dodatkowe, "wynik_netto": netto, "roi": netto / w["koszt"]}


# --- opis populacji --------------------------------------------------------------------------------------------


def balans(df: pd.DataFrame) -> dict:
    """Czy grupa kontrolna przypomina grupę z ofertą (to, co znane przed ofertą) i czy jej udział to 20%."""
    o = df["oferta"].to_numpy(dtype=bool)
    n = len(df)
    test_udzialu = stats.binomtest(int((~o).sum()), n, UDZIAL_KONTROLI)
    s_o, s_k = df.loc[o, "score_polityki"], df.loc[~o, "score_polityki"]
    b2b = (df["linia"] == "B2B").to_numpy()
    wyp = df["wypowiedzenie_przed_migawka"].to_numpy(dtype=bool)

    def proporcje(x: np.ndarray) -> dict:
        tab = [[int(x[o].sum()), int((~x[o]).sum())], [int(x[~o].sum()), int((~x[~o]).sum())]]
        return {"oferta": float(x[o].mean()), "kontrola": float(x[~o].mean()), "p": float(stats.fisher_exact(tab)[1])}

    miesiace = pd.crosstab(df["miesiac_konca"].astype(str), df["grupa"])
    return {
        "umowy": n,
        "udzial_kontroli": float((~o).mean()),
        "p_udzial_20": float(test_udzialu.pvalue),
        "score_polityki": {
            "oferta": float(s_o.mean()),
            "kontrola": float(s_k.mean()),
            "p": float(stats.ttest_ind(s_o, s_k, equal_var=False).pvalue),
        },
        "udzial_b2b": proporcje(b2b),
        "wypowiedzenie_przed_migawka": proporcje(wyp),
        "miesiace": {m: {g: int(v) for g, v in r.items()} for m, r in miesiace.iterrows()},
        "p_miesiac_x_grupa": float(stats.chi2_contingency(miesiace.to_numpy())[1]),
        "najemcy": int(df["id_najemcy"].nunique()),
        "najemcy_w_obu_grupach": int((df.groupby("id_najemcy")["grupa"].nunique() > 1).sum()),
    }


def segmenty(df: pd.DataFrame, z: ZalozeniaOferty) -> dict:
    """Odsetki i ATE (Wald) w miesiącach końca umowy i liniach; liczebności małe, więc to tylko opis."""
    out = {}
    for kol in ("miesiac_konca", "linia"):
        for wartosc, seg in df.groupby(kol, sort=True):
            w = wynik_kampanii(seg, z)
            etykieta = str(wartosc)[:7] if kol == "miesiac_konca" else str(wartosc)
            out[f"{kol}={etykieta}"] = {
                k: w[k] for k in ("n_oferta", "n_kontrola", "odsetek_oferta", "odsetek_kontrola", "ate", "wynik_netto")
            } | {"ci95_ate_wald": ate_wald(w)}
    return out


def rabaty_fk(df: pd.DataFrame) -> dict:
    """Co FK zaksięgowało do dnia eksportu dla przedłużeń z ofertą (rabat roczny jest dopiero w trakcie)."""
    o = df["oferta"].to_numpy(dtype=bool)
    prz = df["przedluzona"].to_numpy(dtype=bool)
    rab = df["rabat"].to_numpy(dtype=bool)
    return {
        "przedluzenia_oferta": int((o & prz).sum()),
        "z_rabatem": int((o & rab).sum()),
        "bez_rabatu": int((o & prz & ~rab).sum()),
        "rabat_w_kontroli": int((~o & rab).sum()),
        "pozycje_do_eksportu": int(df.loc[o, "rabat_pozycje_do_eksportu"].sum()),
        "zaksiegowano_pln": float(df.loc[o, "rabat_zaksiegowany_pln"].sum()),
        "oferty_otwarte": int(df.loc[o, "czy_otwarta"].fillna(False).astype(bool).sum()),
    }


# --- uruchomienie ----------------------------------------------------------------------------------------------


def main() -> dict:
    z = zalozenia_oferty()
    with polacz() as con:
        df = con.execute(SQL_KAMPANII).df()
        grupy = con.execute(SQL_GRUPY).df()
        dni = con.execute(SQL_DNI_OFERTY).df()
        fk_do = con.execute(SQL_FK_DO).fetchone()[0]
    n_retencja = int(grupy.loc[grupy["grupa"].isin(["oferta", "kontrola"]), "umowy"].sum())
    if len(df) != n_retencja:
        raise ValueError(f"Złączenie z migawki_najemcy zgubiło umowy: {len(df)} z {n_retencja}")
    df["oferta"] = df["oferta"].astype(bool)
    df["rabat"] = df["rabat"].astype(bool)

    glowny = podsumowanie(df, z)
    klastry = podsumowanie(df, z, klastry="id_najemcy")
    z_fk = replace(z, D=D_Z_FK)
    wrazliwosc_d = podsumowanie(df, z_fk)
    wrazliwosc_k = podsumowanie(df, replace(z, k=0.0))  # k = 60 zł to szacunek; k = 0: kontakt bez kosztu

    test_2025 = json.loads(SCIEZKA_TESTU_2025.read_text(encoding="utf-8"))["efekty_wg_kwalifikuje"]["kwalifikuje"]
    efekt_2025 = {
        "ate": test_2025["ate"],
        "ci95": test_2025["ci95"],
        "przy_ate": wynik_przy_ate(glowny, test_2025["ate"], z),
        "przy_dolnej_granicy": wynik_przy_ate(glowny, test_2025["ci95"][0], z),
        "przy_gornej_granicy": wynik_przy_ate(glowny, test_2025["ci95"][1], z),
    }

    wyniki = {
        "okres": OKRES,
        "zalozenia": {"R": z.R, "D": z.D, "k": z.k},
        "n_bootstrap": N_BOOTSTRAP,
        "ziarno": ZIARNO,
        "grupy_retencja_decyzje": grupy.astype({"od": str, "do_": str}).to_dict(orient="records"),
        "dni_oferty_przed_koncem": dni.to_dict(orient="records"),
        "fk_rabaty_ostatni_miesiac": fk_do,
        "balans": balans(df),
        "rabaty_fk": rabaty_fk(df),
        "glowny": glowny,
        "bootstrap_po_najemcach": klastry,
        "wrazliwosc_D_1950": wrazliwosc_d,
        "wrazliwosc_k_0": wrazliwosc_k,
        "efekt_z_testu_2025_kwalifikuje": efekt_2025,
        "segmenty": segmenty(df, z),
    }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    (KATALOG_WYNIKOW / "kampania_2026q3.json").write_text(
        json.dumps(wyniki, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return wyniki


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2, default=str))
