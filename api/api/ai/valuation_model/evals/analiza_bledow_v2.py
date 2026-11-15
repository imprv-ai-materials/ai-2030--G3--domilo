"""Analiza błędów v2 na zbiorze testowym i wycena ofert z Katowic (docs/b1_bledy.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.analiza_bledow_v2
Wypisuje tabele Markdown i zapisuje wykresy w docs/img/. Niczego nie uczy: używa zapisanych modeli
versions/v2_lgbm_geo, v2_lightgbm, v1_liniowa. Zbiór testowy był już otwarty przy ewaluacji (2026-11-15),
tu tylko opisujemy jego błędy; wniosków z tej analizy nie wolno sprawdzać na tym samym teście.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from api.adapters.duckdb_baza import KATALOG_REPO, polacz  # noqa: E402
from api.ai.features.wycena.geo import cechy_geo  # noqa: E402
from api.ai.features.wycena.sasiedztwo import cechy_sasiedztwa_punktow  # noqa: E402
from api.ai.features.wycena.zbior import wczytaj_transakcje_z_cechami  # noqa: E402
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny  # noqa: E402
from api.ai.valuation_model.evals.ewaluacja import KATALOG_WERSJI, _md  # noqa: E402

KATALOG_WYKRESOW = KATALOG_REPO / "docs" / "img"
PROGI_CENY = [0, 300_000, 600_000, 1_000_000, np.inf]
ETYKIETY_CENY = ["< 300 tys.", "300–600 tys.", "600 tys. – 1 mln", "≥ 1 mln"]

# Styl wykresów (paleta referencyjna skilla dataviz, tryb jasny; walidacja: #2a78d6,#eb6834 — wszystkie testy PASS).
POWIERZCHNIA, TEKST, TEKST_2, SIATKA, PUNKTY = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#a3a29c"
SERIA_1, SERIA_2 = "#2a78d6", "#eb6834"


def _wczytaj(nazwa: str) -> ModelWyceny:
    return ModelWyceny.wczytaj(KATALOG_WERSJI / nazwa / "model.joblib")


def _f(x: float, miejsca: int = 1) -> str:
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def _metryki_grupy(g: pd.DataFrame) -> dict:
    e = g["geo"] - g["cena_pln"]
    ew = e / g["cena_pln"]
    return {
        "transakcje": int(len(g)),
        "MAE_geo": _f(np.mean(np.abs(e)), 0),
        "MAPE_geo": _f(100 * np.mean(np.abs(ew)), 2),
        "MdAPE_geo": _f(100 * np.median(np.abs(ew)), 2),
        "mediana_bledu_geo": _f(100 * np.median(ew), 2),
        "MAPE_lightgbm": _f(100 * np.mean(np.abs(g["lgbm"] / g["cena_pln"] - 1)), 2),
        "MAPE_v1": _f(100 * np.mean(np.abs(g["v1"] / g["cena_pln"] - 1)), 2),
    }


def _segmenty(df: pd.DataFrame, kolumna: str) -> pd.DataFrame:
    wiersze = [{"grupa": str(k), **_metryki_grupy(g)} for k, g in df.groupby(kolumna, observed=True, sort=False)]
    wiersze.append({"grupa": "wszystkie", **_metryki_grupy(df)})
    return pd.DataFrame(wiersze)


def _os(ax, tytul: str, opis_y: str) -> None:
    ax.set_facecolor(POWIERZCHNIA)
    ax.set_xscale("log")
    ax.grid(True, color=SIATKA, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(SIATKA)
    ax.tick_params(colors=TEKST_2, labelsize=9)
    ax.set_xlabel("Cena transakcyjna (zł, skala logarytmiczna)", color=TEKST_2, fontsize=10)
    ax.set_ylabel(opis_y, color=TEKST_2, fontsize=10)
    ax.set_title(tytul, color=TEKST, fontsize=12, loc="left")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: _f(x / 1000, 0) + " tys."))
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())


def _wykres(df: pd.DataFrame, przedzialy: pd.DataFrame, kolumna_pkt: str, kol_geo: str, kol_v1: str,
            tytul: str, opis_y: str, plik: Path, zakres_y: tuple[float, float], zero: bool) -> int:  # fmt: skip
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    fig.patch.set_facecolor(POWIERZCHNIA)
    _os(ax, tytul, opis_y)
    y = df[kolumna_pkt]
    poza = int(((y < zakres_y[0]) | (y > zakres_y[1])).sum())
    ax.scatter(df["cena_pln"], y.clip(*zakres_y), s=4, color=PUNKTY, alpha=0.35, linewidths=0,
               label="pojedyncze transakcje (v2_lgbm_geo)")  # fmt: skip
    if zero:
        ax.axhline(0, color=TEKST_2, linewidth=1)
    ostatni = przedzialy.iloc[-1]
    wyzsza = kol_geo if ostatni[kol_geo] >= ostatni[kol_v1] else kol_v1
    for kol, kolor, etykieta in ((kol_geo, SERIA_1, "v2_lgbm_geo"), (kol_v1, SERIA_2, "v1_liniowa")):
        ax.plot(przedzialy["cena_mediana"], przedzialy[kol], color=kolor, linewidth=2, marker="o", markersize=5,
                markeredgecolor=POWIERZCHNIA, markeredgewidth=1.5,
                label=f"{etykieta}: mediana w 20 przedziałach ceny")  # fmt: skip
        ax.annotate(etykieta, (ostatni["cena_mediana"], ostatni[kol]), xytext=(8, 7 if kol == wyzsza else -7),
                    textcoords="offset points", color=TEKST, fontsize=9, va="center")  # fmt: skip
    ax.set_ylim(*zakres_y)
    if not zero:
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _f(v / 1000, 0) + " tys."))
    leg = ax.legend(loc="upper left", fontsize=8.5, frameon=False)
    for t in leg.get_texts():
        t.set_color(TEKST)
    ax.text(1.0, -0.16, f"Test: akty 2026-01 – 2026-06, {len(df)} transakcji; poza zakresem osi (na krawędzi): {poza}",
            transform=ax.transAxes, ha="right", color=TEKST_2, fontsize=8)  # fmt: skip
    fig.tight_layout()
    plik.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plik, facecolor=POWIERZCHNIA)
    plt.close(fig)
    return poza


def analiza_testu(con) -> None:
    df = wczytaj_transakcje_z_cechami(con)
    df = df[df["zbior"] == "test"].copy()
    typ = con.execute("SELECT id_transakcji, typ_budynku FROM rcn_transakcje").df()
    df = df.merge(typ, on="id_transakcji", how="left", validate="one_to_one")
    geo, lgbm, v1 = _wczytaj("v2_lgbm_geo"), _wczytaj("v2_lightgbm"), _wczytaj("v1_liniowa")
    df["geo"] = geo.predict(df)
    df["lgbm"] = lgbm.predict(df[list(KOLUMNY_CECH)])
    df["v1"] = v1.predict(df[list(KOLUMNY_CECH)])

    df["segment_ceny"] = pd.cut(df["cena_pln"], PROGI_CENY, labels=ETYKIETY_CENY, right=False)
    df["segment_wyceny"] = pd.cut(df["geo"], PROGI_CENY, labels=ETYKIETY_CENY, right=False)
    df["metraz_grupa"] = np.where(df["metraz"] < 30, "< 30 m²", "≥ 30 m²")
    for kol, tytul in (
        ("segment_ceny", "Segment ceny transakcyjnej"),
        ("segment_wyceny", "Segment wyceny v2_lgbm_geo"),
        ("miasto", "Miasto"),
        ("typ_budynku", "Typ budynku"),
        ("metraz_grupa", "Metraż"),
        ("rynek", "Rynek"),
    ):
        tab = _segmenty(
            df.sort_values(kol) if kol not in ("segment_ceny", "segment_wyceny") else df.sort_values(kol), kol
        )
        print(f"### Test: {tytul}\n\n{_md(tab)}\n")

    male = df[df["metraz"] < 30]
    print(f"### Test: lokale < 30 m² według miasta\n\n{_md(_segmenty(male.sort_values('miasto'), 'miasto'))}\n")
    opis_male = pd.DataFrame(
        [
            {
                "grupa": g,
                "transakcje": int(len(d)),
                "mediana_metrazu": _f(d["metraz"].median(), 1),
                "mediana_ceny_m2": _f(d["cena_m2"].median(), 0),
                "mediana_wyceny_m2_geo": _f((d["geo"] / d["metraz"]).median(), 0),
            }
            for g, d in (("< 30 m²", male), ("≥ 30 m²", df[df["metraz"] >= 30]))
        ]
    )
    print(f"### Test: małe lokale — ceny m²\n\n{_md(opis_male)}\n")

    # Krzyżowo: segment ceny × typ budynku (MAPE geo, liczba transakcji)
    krzyz = df.groupby(["segment_ceny", "typ_budynku"], observed=True).apply(
        lambda g: pd.Series({"n": len(g), "MAPE": 100 * np.mean(np.abs(g["geo"] / g["cena_pln"] - 1))}),
        include_groups=False,
    )
    krzyz = krzyz.reset_index()
    krzyz["n"] = krzyz["n"].astype(int)
    krzyz["MAPE"] = krzyz["MAPE"].map(lambda x: _f(x, 2))
    print(f"### Test: segment ceny × typ budynku (v2_lgbm_geo)\n\n{_md(krzyz)}\n")

    # Wykresy: 20 przedziałów ceny o równej liczności.
    df["e_geo"] = df["geo"] - df["cena_pln"]
    df["e_v1"] = df["v1"] - df["cena_pln"]
    df["ew_geo"] = 100 * df["e_geo"] / df["cena_pln"]
    df["ew_v1"] = 100 * df["e_v1"] / df["cena_pln"]
    df["przedzial"] = pd.qcut(df["cena_pln"], 20, labels=False)
    przedzialy = df.groupby("przedzial").agg(
        cena_od=("cena_pln", "min"),
        cena_do=("cena_pln", "max"),
        cena_mediana=("cena_pln", "median"),
        transakcje=("cena_pln", "size"),
        abs_geo=("e_geo", lambda x: np.median(np.abs(x))),
        abs_v1=("e_v1", lambda x: np.median(np.abs(x))),
        wzgl_geo=("ew_geo", "median"),
        wzgl_v1=("ew_v1", "median"),
        absw_geo=("ew_geo", lambda x: np.median(np.abs(x))),
    )
    df["abs_geo_pkt"] = df["e_geo"].abs()
    zakres_abs = (0, float(np.percentile(df["abs_geo_pkt"], 99)))
    poza_abs = _wykres(df, przedzialy, "abs_geo_pkt", "abs_geo", "abs_v1",
                       "Błąd bezwzględny wyceny a cena transakcji", "|wycena − cena| (zł)",
                       KATALOG_WYKRESOW / "b1_bledy_bezwzgledny.png", zakres_abs, zero=False)  # fmt: skip
    poza_wzgl = _wykres(df, przedzialy, "ew_geo", "wzgl_geo", "wzgl_v1",
                        "Błąd względny wyceny a cena transakcji (> 0 = zawyża, < 0 = zaniża)",
                        "(wycena − cena) / cena (%)",
                        KATALOG_WYKRESOW / "b1_bledy_wzgledny.png", (-60.0, 60.0), zero=True)  # fmt: skip
    print(f"Wykresy: zakres osi Y błędu bezwzględnego 0–{_f(zakres_abs[1], 0)} zł (P99), poza: {poza_abs}; "
          f"względnego ±60%, poza: {poza_wzgl}\n")  # fmt: skip
    tab = pd.DataFrame(
        {
            "przedzial": [
                f"{_f(a / 1000, 0)}–{_f(b / 1000, 0)} tys."
                for a, b in zip(przedzialy["cena_od"], przedzialy["cena_do"])
            ],
            "transakcje": przedzialy["transakcje"].astype(int),
            "mediana_|bledu|_geo_zl": przedzialy["abs_geo"].map(lambda x: _f(x, 0)),
            "mediana_|bledu|_v1_zl": przedzialy["abs_v1"].map(lambda x: _f(x, 0)),
            "mediana_|bledu|_geo_proc": przedzialy["absw_geo"].map(lambda x: _f(x, 1)),
            "mediana_bledu_geo_proc": przedzialy["wzgl_geo"].map(lambda x: _f(x, 1)),
            "mediana_bledu_v1_proc": przedzialy["wzgl_v1"].map(lambda x: _f(x, 1)),
        }
    )
    print(f"### Dane do wykresów (20 przedziałów ceny o równej liczności)\n\n{_md(tab)}\n")


# --- Katowice ---------------------------------------------------------------------------------------------------

SQL_OFERTY = """
SELECT r.id_oferty AS id_transakcji, r.miasto, r.dzielnica, r.lat, r.lon, r.metraz, r.pokoje, r.pietro,
       r.rok_budowy, r.rynek, r.typ_budynku, r.cena_ofertowa, r.id_pakietu,
       coalesce(o.data_wyceny, r.data_publikacji)::DATE AS dzien_wyceny,
       o.id_operatu, o.wartosc_pln AS wartosc_operatu
FROM radar_oferty r
LEFT JOIN operaty o ON o.id_oferty = r.id_oferty AND o.typ = 'due_diligence'
WHERE r.data_publikacji >= TIMESTAMP '2026-06-01' AND r.data_publikacji < TIMESTAMP '2026-10-01'
"""


def wycena_ofert(con) -> None:
    oferty = con.execute(SQL_OFERTY).df()
    geo_sql = f"SELECT id_transakcji, miasto, dzielnica, lat, lon FROM ({SQL_OFERTY})"
    sas_sql = f"SELECT id_transakcji, miasto, lat, lon, dzien_wyceny FROM ({SQL_OFERTY})"
    oferty = oferty.merge(cechy_geo(con, geo_sql), on="id_transakcji", how="left", validate="one_to_one")
    oferty = oferty.merge(cechy_sasiedztwa_punktow(con, sas_sql), on="id_transakcji", how="left", validate="one_to_one")
    geo, lgbm, v1 = _wczytaj("v2_lgbm_geo"), _wczytaj("v2_lightgbm"), _wczytaj("v1_liniowa")
    oferty["geo"] = geo.predict(oferty)
    oferty["lgbm"] = lgbm.predict(oferty[list(KOLUMNY_CECH)])
    kat = oferty[oferty["miasto"] == "Katowice"].copy()

    # v1 na Katowicach
    try:
        v1.predict(kat[list(KOLUMNY_CECH)])
        v1_wynik = "v1 wyceniła oferty bez błędu"
    except ValueError as blad:
        v1_wynik = f"v1 odmówiła wyceny: ValueError: {blad}"
    print(f"### v1 na ofertach z Katowic\n\n{v1_wynik}\n")

    # Sygnały „poza danymi treningowymi”
    sygnaly = pd.DataFrame(
        [
            {
                "miasto": m,
                "oferty": int(len(d)),
                "miasto_nieznane_w_treningu": int((~d["miasto"].isin(geo.kategorie_["miasto"])).sum()),
                "dzielnica_nieznana_w_treningu": int(
                    (~(d["miasto"] + " | " + d["dzielnica"]).isin(geo.kategorie_["dzielnica"])).sum()
                ),
                "bez_sasiadow_RCN": int((d["sasiedzi_liczba"] == 0).sum()),
                "brak_rok_budowy": int(d["rok_budowy"].isna().sum()),
            }
            for m, d in oferty.groupby("miasto")
        ]
    )
    print(f"### Oferty 2026-06 – 2026-09: czy model zna miejsce?\n\n{_md(sygnaly)}\n")

    tr = wczytaj_transakcje_z_cechami(con)
    tr = tr[tr["zbior"] == "trening"]
    bez = tr[tr["sasiedzi_liczba"] == 0]
    print(
        "### Trening: transakcje bez sąsiadów (jedyne przykłady „brak sąsiedztwa”, z których model się uczył)\n\n"
        + _md(
            pd.DataFrame(
                [
                    {
                        "transakcje": int(len(bez)),
                        "miasta": ", ".join(f"{k} {v}" for k, v in bez["miasto"].value_counts().items()),
                        "data_aktu_od": str(bez["data_aktu"].min().date()),
                        "data_aktu_do": str(bez["data_aktu"].max().date()),
                        "udzial_w_treningu_proc": _f(100 * len(bez) / len(tr), 3),
                    }
                ]
            )
        )
        + "\n"
    )

    # Wycena vs operat due diligence (40)
    dd = kat[kat["id_operatu"].notna()].copy()
    wiersze = []
    for nazwa, kol in (
        ("v2_lgbm_geo", "geo"),
        ("v2_lightgbm", "lgbm"),
        ("cena ofertowa (punkt odniesienia)", "cena_ofertowa"),
    ):
        b = dd[kol] / dd["wartosc_operatu"] - 1
        wiersze.append(
            {
                "wycena": nazwa,
                "operaty": int(len(dd)),
                "mediana_bledu_proc": _f(100 * b.median(), 1),
                "MAPE": _f(100 * b.abs().mean(), 1),
                "MdAPE": _f(100 * b.abs().median(), 1),
                "min_bledu_proc": _f(100 * b.min(), 1),
                "max_bledu_proc": _f(100 * b.max(), 1),
                "wycen_ponizej_operatu": int((b < 0).sum()),
                "suma_wycen_mln_zl": _f(dd[kol].sum() / 1e6, 2),
            }
        )
    print(f"### Katowice: wycena a 40 operatów due diligence\n\n{_md(pd.DataFrame(wiersze))}\n")
    print(f"Suma wartości 40 operatów: {_f(dd['wartosc_operatu'].sum() / 1e6, 2)} mln zł\n")
    opis_dd = dd.agg(
        metraz_med=("metraz", "median"),
        rok_min=("rok_budowy", "min"),
        rok_max=("rok_budowy", "max"),
    )
    print(f"### Katowice DD: opis\n\n{opis_dd.to_string()}\nrynek: {dd['rynek'].value_counts().to_dict()}, "
          f"typ: {dd['typ_budynku'].value_counts().to_dict()}, dzielnica: {dd['dzielnica'].value_counts().to_dict()}, "
          f"pakiet: {dd['id_pakietu'].value_counts().to_dict()}\n")  # fmt: skip

    # Ceny m²: co „myśli” model a co mówią operaty i oferty
    m2 = pd.DataFrame(
        [
            {
                "co": "operat DD (40)",
                "mediana_zl_m2": _f((dd["wartosc_operatu"] / dd["metraz"]).median(), 0),
            },
            {"co": "wycena v2_lgbm_geo, oferty DD (40)", "mediana_zl_m2": _f((dd["geo"] / dd["metraz"]).median(), 0)},
            {"co": "wycena v2_lightgbm, oferty DD (40)", "mediana_zl_m2": _f((dd["lgbm"] / dd["metraz"]).median(), 0)},
            {
                "co": "cena ofertowa, oferty DD (40)",
                "mediana_zl_m2": _f((dd["cena_ofertowa"] / dd["metraz"]).median(), 0),
            },
            {
                "co": "cena ofertowa, wszystkie oferty Katowic (cena > 0)",
                "mediana_zl_m2": _f((kat.loc[kat["cena_ofertowa"] > 0, "cena_ofertowa"] / kat["metraz"]).median(), 0),
            },
            {
                "co": "wycena v2_lgbm_geo, wszystkie oferty Katowic",
                "mediana_zl_m2": _f((kat["geo"] / kat["metraz"]).median(), 0),
            },
        ]
        + [{"co": f"RCN trening: {m}", "mediana_zl_m2": _f(g["cena_m2"].median(), 0)} for m, g in tr.groupby("miasto")]
    )
    print(f"### Ceny za m²\n\n{_md(m2)}\n")

    # Wycena vs cena ofertowa: Katowice a pozostałe miasta (ten sam okres)
    ofe = oferty[oferty["cena_ofertowa"] > 0]
    por = pd.DataFrame(
        [
            {
                "miasto": m,
                "oferty": int(len(d)),
                "mediana_wycena_do_ceny_ofertowej_proc_geo": _f(100 * (d["geo"] / d["cena_ofertowa"] - 1).median(), 1),
                "MdAPE_wzgl_ceny_ofertowej_geo": _f(100 * (d["geo"] / d["cena_ofertowa"] - 1).abs().median(), 1),
                "mediana_wycena_do_ceny_ofertowej_proc_lgbm": _f(
                    100 * (d["lgbm"] / d["cena_ofertowa"] - 1).median(), 1
                ),
            }
            for m, d in ofe.groupby("miasto")
        ]
    )
    print(f"### Wycena a cena ofertowa, oferty 2026-06 – 2026-09 (cena > 0)\n\n{_md(por)}\n")

    # Z czego model złożył wycenę Katowic (SHAP, ln zł) — porównanie z ofertami z innych miast
    wkl = geo.explain(oferty)
    wkl["grupa"] = np.where(oferty["miasto"] == "Katowice", "Katowice", "pozostałe miasta")
    kol = [k for k in wkl.columns if k.startswith("wklad_")]
    srednie = wkl.groupby("grupa")[kol].mean().T
    srednie = srednie.reindex(srednie.abs().max(axis=1).sort_values(ascending=False).index).head(8)
    srednie = srednie.map(lambda x: _f(x, 3)).reset_index().rename(columns={"index": "skladnik_ln_wyceny"})
    print(f"### Średnie wkłady do ln(wyceny) v2_lgbm_geo (SHAP)\n\n{_md(srednie)}\n")

    # Czy model w ogóle ma jak ostrzec?
    try:
        geo.predict_interval(kat.head(1))
        przedzial = "jest"
    except NotImplementedError as blad:
        przedzial = f"NotImplementedError: {blad}"
    print(f"### predict_interval v2_lgbm_geo\n\n{przedzial}\n")


def main() -> None:
    con = polacz()
    analiza_testu(con)
    wycena_ofert(con)


if __name__ == "__main__":
    main()
