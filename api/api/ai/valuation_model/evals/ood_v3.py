"""Detektor danych spoza zakresu (versions/v3_przedzialy/ood.py): krzywa pokrycie–ryzyko i odsetek odmów
(docs/b1_ood.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.ood_v3

Detektor uczy się wyłącznie na zbiorze `trening` (zakresy, liczności, standaryzacja, kNN, Isolation Forest, progi
domyślne = kwantyl 0,99 wyników treningu). Próg proponujemy na `walidacja`; `test` (już otwarty dla v2_lgbm_geo i
v2_lgbm_geo_cqr) tylko pokazuje krzywą i odsetek odmów przy zaproponowanym progu. Błąd = |P50 − cena| / cena, gdzie
P50 = wycena zapisanego v2_lgbm_geo (bez ponownego uczenia).
Zapisuje: versions/v3_przedzialy/ood.joblib, versions/v3_przedzialy/ood_metryki.json, docs/img/b1_ood_*.png.
"""

import json
from datetime import date

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from api.adapters.duckdb_baza import KATALOG_REPO, polacz  # noqa: E402
from api.ai.features.wycena.geo import cechy_geo  # noqa: E402
from api.ai.features.wycena.sasiedztwo import cechy_sasiedztwa_punktow  # noqa: E402
from api.ai.features.wycena.zbior import wczytaj_transakcje_z_cechami  # noqa: E402
from api.ai.valuation_model.base import ModelWyceny  # noqa: E402
from api.ai.valuation_model.evals.analiza_bledow_v2 import SQL_OFERTY, _f  # noqa: E402
from api.ai.valuation_model.evals.ewaluacja import KATALOG_WERSJI, _md  # noqa: E402
from api.ai.valuation_model.versions.v3_przedzialy.ood import KODY, DetektorOOD  # noqa: E402

KATALOG = KATALOG_WERSJI / "v3_przedzialy"
KATALOG_WYKRESOW = KATALOG_REPO / "docs" / "img"
DZIEN_WYCENY_DOMILO = "2026-10-01"  # pierwszy dzień po eksporcie: znane są transakcje opublikowane do 2026-09-30
KWANTYLE_PROGU = (0.95, 0.98, 0.99, 0.995, 0.999)
PROG_MAPE_BANKU = 8.0  # warunek banku: MAPE ≤ 8% (evals/porownanie.md)

OPISY_KODOW = {
    "miasto": "miasto < 80 transakcji",
    "dzielnica": "dzielnica < 80 transakcji",
    "metraz": "metraż poza p0,5–p99,5",
    "rok_budowy": "rok budowy poza p0,5–p99,5 / brak",
    "typ_lokalu": "nietypowy typ lokalu (pokoje × metraż)",
    "knn": "daleko od 10 najbliższych (kNN)",
    "isolation_forest": "Isolation Forest",
}

SQL_BUDYNKI = f"""
SELECT id_budynku AS id_transakcji, miasto, dzielnica, lat, lon, DATE '{DZIEN_WYCENY_DOMILO}' AS dzien_wyceny
FROM pms_budynki
"""
SQL_LOKALE = """
SELECT l.id_lokalu, l.id_budynku, b.nazwa, b.miasto, b.dzielnica, l.metraz, l.pokoje, l.pietro,
       b.rok_oddania AS rok_budowy, b.typ AS typ_budynku_pms, b.segment
FROM pms_lokale l JOIN pms_budynki b USING (id_budynku)
"""

# Styl wykresów: paleta referencyjna skilla dataviz, tryb jasny; walidacja #2a78d6,#eb6834,#1baf7a,#eda100 — PASS,
# kontrast < 3:1 dla #1baf7a i #eda100, dlatego etykiety bezpośrednio przy liniach i tabela w raporcie.
POWIERZCHNIA, TEKST, TEKST_2, SIATKA = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
KOLORY = {"laczny": "#2a78d6", "knn": "#eb6834", "if": "#1baf7a", "szerokosc": "#eda100"}
ETYKIETY = {
    "laczny": "detektor łączny (reguły + kNN + IF)",
    "knn": "odległość kNN",
    "if": "Isolation Forest",
    "szerokosc": "szerokość przedziału CQR (porównanie)",
    "wyrocznia": "wyrocznia: odrzuca największe błędy (granica)",
}


# --- dane ----------------------------------------------------------------------------------------------------------


def wczytaj_lokale_domilo(con) -> pd.DataFrame:
    """7 200 lokali Domilo z cechami jak w modelu: położenie budynku, sąsiedzi znani w dniu wyceny."""
    lokale = con.execute(SQL_LOKALE).df()
    geo = cechy_geo(con, f"SELECT id_transakcji, miasto, dzielnica, lat, lon FROM ({SQL_BUDYNKI})")
    sas = cechy_sasiedztwa_punktow(con, SQL_BUDYNKI)
    budynki = geo.merge(sas, on="id_transakcji", validate="one_to_one").rename(columns={"id_transakcji": "id_budynku"})
    wynik = lokale.merge(budynki, on="id_budynku", how="left", validate="many_to_one")
    if len(wynik) != len(lokale):
        raise ValueError("Złączenie cech budynków zmieniło liczbę lokali")
    return wynik


def wczytaj_oferty(con) -> pd.DataFrame:
    """Oferty 2026-06 – 2026-09 (jak w b1_bledy.md) z cechami na dzień wyceny."""
    oferty = con.execute(SQL_OFERTY).df()
    geo_sql = f"SELECT id_transakcji, miasto, dzielnica, lat, lon FROM ({SQL_OFERTY})"
    sas_sql = f"SELECT id_transakcji, miasto, lat, lon, dzien_wyceny FROM ({SQL_OFERTY})"
    oferty = oferty.merge(cechy_geo(con, geo_sql), on="id_transakcji", how="left", validate="one_to_one")
    return oferty.merge(cechy_sasiedztwa_punktow(con, sas_sql), on="id_transakcji", how="left", validate="one_to_one")


# --- krzywa pokrycie–ryzyko ----------------------------------------------------------------------------------------


def wynik_laczny(ocena: pd.DataFrame, prog_knn: float, prog_if: float) -> np.ndarray:
    """Jedna liczba do sortowania: reguła = +∞, inaczej max(odl_knn / prog_knn, wynik_if / prog_if); > 1 = odmowa."""
    regula = ocena[[f"powod_{k}" for k in KODY if k not in ("knn", "isolation_forest")]].any(axis=1).to_numpy()
    w = np.maximum(ocena["odl_knn"].to_numpy() / prog_knn, ocena["wynik_if"].to_numpy() / prog_if)
    return np.where(regula, np.inf, w)


def krzywa(wynik: np.ndarray, blad: np.ndarray, przyjete: np.ndarray) -> np.ndarray:
    """MAPE (%) na przyjętych, gdy przyjmujemy ułamek `przyjete` lokali o najniższym wyniku (stabilnie)."""
    kolejnosc = np.argsort(wynik, kind="stable")
    skumulowany = np.cumsum(blad[kolejnosc])
    n = np.maximum(1, np.round(przyjete * len(blad)).astype(int))
    return 100 * skumulowany[n - 1] / n


def rysuj(krzywe: dict[str, np.ndarray], przyjete: np.ndarray, punkty: list[tuple[str, float, float]],
          mape_wszystkie: float, tytul: str, stopka: str, plik) -> None:  # fmt: skip
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=150)
    fig.patch.set_facecolor(POWIERZCHNIA)
    ax.set_facecolor(POWIERZCHNIA)
    ax.grid(True, color=SIATKA, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(SIATKA)
    ax.tick_params(colors=TEKST_2, labelsize=9)
    x = 100 * przyjete
    ax.axhline(mape_wszystkie, color=TEKST_2, linewidth=1, linestyle=":")
    ax.annotate(f"bez odmów: {_f(mape_wszystkie, 2)}%", (x[0] + 0.45 * (x[-1] - x[0]), mape_wszystkie),
                xytext=(0, -12), textcoords="offset points", ha="center", color=TEKST_2, fontsize=8.5)  # fmt: skip
    ax.axhline(PROG_MAPE_BANKU, color=TEKST_2, linewidth=1, linestyle="-.")
    ax.annotate(f"warunek banku: MAPE ≤ {_f(PROG_MAPE_BANKU, 0)}%", (x[0], PROG_MAPE_BANKU), xytext=(4, -11),
                textcoords="offset points", color=TEKST_2, fontsize=8.5)  # fmt: skip
    ax.plot(x, krzywe["wyrocznia"], color=TEKST_2, linewidth=1.5, linestyle="--", label=ETYKIETY["wyrocznia"])
    for k in ("szerokosc", "if", "knn", "laczny"):
        ax.plot(x, krzywe[k], color=KOLORY[k], linewidth=2, label=ETYKIETY[k])
    # Trzy linie OOD prawie się pokrywają: jeden podpis grupy nad nimi, kolory rozróżnia legenda.
    gora = max(krzywe[k].max() for k in ("knn", "if", "laczny"))
    ax.annotate("sygnały OOD: kNN, Isolation Forest, detektor łączny", (x[0], gora), xytext=(x[0] + 0.5, gora + 0.12),
                color=TEKST, fontsize=8.5, va="bottom")  # fmt: skip
    ax.annotate(ETYKIETY["szerokosc"].split(" (")[0], (x[0], krzywe["szerokosc"][0]), xytext=(4, -12),
                textcoords="offset points", color=TEKST, fontsize=8.5)  # fmt: skip
    ax.annotate("wyrocznia", (x[0], krzywe["wyrocznia"][0]), xytext=(14, -12), textcoords="offset points",
                color=TEKST_2, fontsize=8.5)  # fmt: skip
    for etykieta, px, py in punkty:
        ax.plot([px], [py], marker="o", markersize=8, color=KOLORY["laczny"], markeredgecolor=POWIERZCHNIA,
                markeredgewidth=2, zorder=5)  # fmt: skip
        # podpis w wolnym pasie między wyrocznią a krzywą szerokości (x od 58 do 82%), połączony z punktem linią
        pas = (x >= x[0] + 8) & (x <= x[0] + 32)
        y_pod = (krzywe["wyrocznia"][pas].max() + krzywe["szerokosc"][pas].min()) / 2
        ax.annotate(etykieta, (px, py), xytext=(x[0] + 20, y_pod), ha="center", va="center", color=TEKST,
                    fontsize=8.5, arrowprops={"arrowstyle": "-", "color": TEKST_2, "linewidth": 0.8})  # fmt: skip
    ax.set_ylim(min(krzywe["wyrocznia"].min(), PROG_MAPE_BANKU) - 0.3, gora + 0.6)
    ax.set_xlim(x[0], x[-1] + 0.5)
    ax.set_xlabel("Odsetek przyjętych lokali (%)", color=TEKST_2, fontsize=10)
    ax.set_ylabel("MAPE na przyjętych (%)", color=TEKST_2, fontsize=10)
    ax.set_title(tytul, color=TEKST, fontsize=12, loc="left")
    leg = ax.legend(loc="lower right", fontsize=8, frameon=False)
    for t in leg.get_texts():
        t.set_color(TEKST)
    ax.text(1.0, -0.14, stopka, transform=ax.transAxes, ha="right", color=TEKST_2, fontsize=8)
    fig.tight_layout()
    plik.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plik, facecolor=POWIERZCHNIA)
    plt.close(fig)


# --- tabele odmów -------------------------------------------------------------------------------------------------


def rozbicie(nazwa: str, ocena: pd.DataFrame) -> dict:
    """Odsetek odmów i każdego powodu (lokal może mieć kilka), a także „tylko ten powód”."""
    flagi = ocena[[f"powod_{k}" for k in KODY]].to_numpy()
    jedyny = flagi.sum(axis=1) == 1
    w = {"zbior": nazwa, "lokale": int(len(ocena)), "odmowy_proc": _f(100 * ocena["odmowa"].mean(), 1)}
    for i, k in enumerate(KODY):
        w[k] = f"{_f(100 * flagi[:, i].mean(), 1)} ({_f(100 * (flagi[:, i] & jedyny).mean(), 1)})"
    return w


def blad_wg_powodu(ocena: pd.DataFrame, blad: np.ndarray) -> pd.DataFrame:
    wiersze = [
        {
            "grupa": "przyjęte",
            "lokale": int((~ocena["odmowa"]).sum()),
            "MAPE": _f(100 * blad[~ocena["odmowa"].to_numpy()].mean(), 2),
        }
    ]
    wiersze.append(
        {"grupa": "odrzucone", "lokale": int(ocena["odmowa"].sum()), "MAPE": _f(100 * blad[ocena["odmowa"]].mean(), 2)}
    )
    for k in KODY:
        m = ocena[f"powod_{k}"].to_numpy()
        if m.any():
            wiersze.append(
                {"grupa": f"powód: {OPISY_KODOW[k]}", "lokale": int(m.sum()), "MAPE": _f(100 * blad[m].mean(), 2)}
            )
    return pd.DataFrame(wiersze)


def progi_wg_kwantyla(det: DetektorOOD, tr: pd.DataFrame) -> dict[float, tuple[float, float]]:
    w = det.wyniki(tr, bez_siebie=True)
    return {q: (float(np.quantile(w["odl_knn"], q)), float(np.quantile(w["wynik_if"], q))) for q in KWANTYLE_PROGU}


# --- przebieg -----------------------------------------------------------------------------------------------------


def main() -> None:
    con = polacz()
    df = wczytaj_transakcje_z_cechami(con)
    typ = con.execute("SELECT id_transakcji, typ_budynku FROM rcn_transakcje").df()
    df = df.merge(typ, on="id_transakcji", how="left", validate="one_to_one")
    zb = {z: df[df["zbior"] == z].reset_index(drop=True) for z in ("trening", "walidacja", "test")}
    det = DetektorOOD().fit(zb["trening"])
    print(f"### Detektor (trening: {det.n_treningu_} transakcji)\n")
    print(f"- zakresy p0,5–p99,5: {det.zakresy_}")
    print(f"- metraż wg liczby pokoi: {det.zakresy_metrazu_pokoje_}")
    print(f"- liczba transakcji wg liczby pokoi: {det.liczba_pokoje_}")
    print(
        f"- dzielnice < 80 transakcji: {{{', '.join(f'{k}: {v}' for k, v in det.liczba_dzielnica_.items() if v < 80)}}}"
    )
    print(f"- progi domyślne (kwantyl 0,99 treningu): kNN {det.prog_knn_:.4f}, IF {det.prog_if_:.4f}\n")

    geo = ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lgbm_geo" / "model.joblib")
    cqr = ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lgbm_geo_cqr" / "model.joblib")
    oferty = wczytaj_oferty(con)
    kat = oferty[oferty["miasto"] == "Katowice"].reset_index(drop=True)
    znane = oferty[oferty["miasto"] != "Katowice"].reset_index(drop=True)
    domilo = wczytaj_lokale_domilo(con)
    braki = domilo[list(det.kolumny)].isna().sum()
    print(f"### Lokale Domilo: braki w cechach przestrzeni\n\n{_md(braki[braki > 0].rename('braki').reset_index())}\n")

    # 1. Progi: kwantyle wyników treningu, ocenione na walidacji (+ Katowice i Domilo, które nie mają cen RCN).
    progi = progi_wg_kwantyla(det, zb["trening"])
    wal = zb["walidacja"]
    blad_wal = np.abs(geo.predict(wal) / wal["cena_pln"].to_numpy() - 1)
    wiersze = []
    for q, (pk, pi) in progi.items():
        o = det.ocen(wal, prog_knn=pk, prog_if=pi)
        wiersze.append(
            {
                "kwantyl_treningu": _f(q, 3),
                "prog_knn": _f(pk, 3),
                "prog_IF": _f(pi, 4),
                "walidacja_odmowy_proc": _f(100 * o["odmowa"].mean(), 1),
                "walidacja_MAPE_przyjetych": _f(100 * blad_wal[~o["odmowa"].to_numpy()].mean(), 2),
                "walidacja_MAPE_odrzuconych": _f(100 * blad_wal[o["odmowa"].to_numpy()].mean(), 2),
                "Katowice_odmowy_proc": _f(100 * det.ocen(kat, prog_knn=pk, prog_if=pi)["odmowa"].mean(), 1),
                "Domilo_odmowy_proc": _f(100 * det.ocen(domilo, prog_knn=pk, prog_if=pi)["odmowa"].mean(), 1),
            }
        )
    print(
        "### Progi kNN / IF jako kwantyl wyników treningu (walidacja, Katowice, Domilo)\n\n"
        f"{_md(pd.DataFrame(wiersze))}\n"
    )

    # 2. Krzywe pokrycie–ryzyko na walidacji i teście.
    przyjete = np.round(np.arange(0.5, 1.0001, 0.005), 3)
    wyniki_krzywych, punkty_proponowane = {}, {}
    for z in ("walidacja", "test"):
        d = zb[z]
        o = det.ocen(d)
        blad = np.abs(geo.predict(d) / d["cena_pln"].to_numpy() - 1)
        p = cqr.predict_interval(d)
        szer = ((p["p90"] - p["p10"]) / p["p50"]).to_numpy()
        kr = {
            "laczny": krzywa(wynik_laczny(o, det.prog_knn_, det.prog_if_), blad, przyjete),
            "knn": krzywa(o["odl_knn"].to_numpy(), blad, przyjete),
            "if": krzywa(o["wynik_if"].to_numpy(), blad, przyjete),
            "szerokosc": krzywa(szer, blad, przyjete),
            "wyrocznia": krzywa(blad, blad, przyjete),
        }
        wyniki_krzywych[z] = {"ocena": o, "blad": blad, "szerokosc": szer, "krzywe": kr}
        przyj = 1 - o["odmowa"].mean()
        mape_przyj = 100 * blad[~o["odmowa"].to_numpy()].mean()
        punkty_proponowane[z] = (100 * przyj, mape_przyj)
        tab = pd.DataFrame({"przyjete_proc": [_f(100 * x, 0) for x in przyjete[::10]]})
        for k, v in kr.items():
            tab[k] = [_f(x, 2) for x in v[::10]]
        print(f"### Krzywa pokrycie–ryzyko, {z} (MAPE % na przyjętych)\n\n{_md(tab)}\n")
        print(f"{z}: proponowany próg → przyjęte {_f(100 * przyj, 1)}%, MAPE przyjętych {_f(mape_przyj, 2)}%, "
              f"MAPE wszystkich {_f(100 * blad.mean(), 2)}%\n")  # fmt: skip
        # Ile trzeba odrzucić, by MAPE na przyjętych ≤ 8% (każdy wynik osobno)
        wiersze = []
        for k, v in kr.items():
            ok = np.where(v <= PROG_MAPE_BANKU)[0]
            wiersze.append(
                {
                    "wynik": ETYKIETY.get(k, k),
                    "max_przyjetych_przy_MAPE_le_8_proc": _f(100 * przyjete[ok[-1]], 1) if len(ok) else "nie osiąga",
                }
            )
        print(f"### {z}: największy odsetek przyjętych z MAPE ≤ 8%\n\n{_md(pd.DataFrame(wiersze))}\n")

    # Porównanie: próg szerokości przedziału CQR wybrany na walidacji (największy odsetek przyjętych z MAPE ≤ 8%),
    # przeniesiony na test jako wartość szerokości (nie jako odsetek).
    w_wal = wyniki_krzywych["walidacja"]
    ok = np.where(w_wal["krzywe"]["szerokosc"] <= PROG_MAPE_BANKU)[0]
    prog_szer = float(np.sort(w_wal["szerokosc"])[int(round(przyjete[ok[-1]] * len(w_wal["szerokosc"]))) - 1])
    wiersze = []
    for z in ("walidacja", "test"):
        w = wyniki_krzywych[z]
        przyj = w["szerokosc"] <= prog_szer
        wiersze.append(
            {
                "zbior": z,
                "prog_szerokosci_proc": _f(100 * prog_szer, 1),
                "przyjete_proc": _f(100 * przyj.mean(), 1),
                "MAPE_przyjetych": _f(100 * w["blad"][przyj].mean(), 2),
                "MAPE_odrzuconych": _f(100 * w["blad"][~przyj].mean(), 2),
            }
        )
    print(f"### Porównanie: odmowa przy szerokim przedziale CQR (próg z walidacji)\n\n{_md(pd.DataFrame(wiersze))}\n")

    for z, plik in (("test", "b1_ood_pokrycie_ryzyko_test.png"), ("walidacja", "b1_ood_pokrycie_ryzyko_walidacja.png")):
        n = len(zb[z])
        okres = "akty 2026-01 – 2026-06" if z == "test" else "akty 2025-07 – 2025-12"
        px, py = punkty_proponowane[z]
        rysuj(
            wyniki_krzywych[z]["krzywe"],
            przyjete,
            [(f"proponowany próg: {_f(px, 1)}% przyjętych, MAPE {_f(py, 2)}%", px, py)],
            100 * wyniki_krzywych[z]["blad"].mean(),
            f"Pokrycie a ryzyko: MAPE v2_lgbm_geo na przyjętych lokalach ({z})",
            f"{z.capitalize()}: {okres}, {n} transakcji. Lokale sortowane od najniższego wyniku; "
            "detektor łączny: reguły zawsze odrzucane.",
            KATALOG_WYKRESOW / plik,
        )

    # 3. Odmowy z rozbiciem na powody.
    oceny = {
        "walidacja (RCN 2025-H2)": wyniki_krzywych["walidacja"]["ocena"],
        "test (RCN 2026-H1)": wyniki_krzywych["test"]["ocena"],
        "oferty z Katowic": det.ocen(kat),
        "oferty z 6 miast z treningu": det.ocen(znane),
        "lokale Domilo": det.ocen(domilo),
    }
    print("### Odmowy i powody (% lokali; w nawiasie: tylko ten jeden powód)\n")
    print(_md(pd.DataFrame([rozbicie(k, v) for k, v in oceny.items()])) + "\n")
    print(
        "### Test: MAPE przyjętych, odrzuconych i według powodu\n\n"
        f"{_md(blad_wg_powodu(oceny['test (RCN 2026-H1)'], wyniki_krzywych['test']['blad']))}\n"
    )
    print(
        "### Walidacja: MAPE według powodu\n\n"
        f"{_md(blad_wg_powodu(oceny['walidacja (RCN 2025-H2)'], wyniki_krzywych['walidacja']['blad']))}\n"
    )

    # Test: rok budowy poza zakresem a rynek
    t = zb["test"].assign(odmowa_rok=oceny["test (RCN 2026-H1)"]["powod_rok_budowy"].to_numpy())
    print(
        "### Test: rok budowy poza zakresem\n\n"
        f"{_md(t[t.odmowa_rok].groupby(['rok_budowy', 'rynek']).size().rename('transakcje').reset_index())}\n"
    )

    # Katowice: 40 operatów due diligence
    ok = oceny["oferty z Katowic"]
    dd = kat["id_operatu"].notna().to_numpy()
    print(f"Katowice: operaty due diligence {int(dd.sum())}, odmowy {int(ok['odmowa'].to_numpy()[dd].sum())}\n")

    # Domilo: według budynku
    od = oceny["lokale Domilo"]
    dom = domilo.rename(columns={"rok_budowy": "rok_oddania"}).assign(
        odmowa=od["odmowa"].to_numpy(), **{f"p_{k}": od[f"powod_{k}"].to_numpy() for k in KODY}
    )
    wg_budynku = (
        dom.groupby(["id_budynku", "nazwa", "miasto", "dzielnica", "rok_oddania", "typ_budynku_pms", "segment"])
        .agg(lokale=("id_lokalu", "size"), odmowy=("odmowa", "sum"), **{f"n_{k}": (f"p_{k}", "sum") for k in KODY})
        .reset_index()
    )
    wg_budynku = wg_budynku[wg_budynku["odmowy"] > 0].sort_values("odmowy", ascending=False)
    print(f"### Domilo: budynki z odmowami\n\n{_md(wg_budynku)}\n")
    nietypowe = (
        dom[dom.p_typ_lokalu | dom.p_metraz]
        .groupby("pokoje")
        .agg(lokale=("id_lokalu", "size"), metraz_min=("metraz", "min"), metraz_max=("metraz", "max"))
        .reset_index()
    )
    print(f"### Domilo: liczba pokoi i metraż lokali z odmową „typ lokalu” albo „metraż”\n\n"
          f"{_md(nietypowe)}\n")  # fmt: skip

    # Przykłady powodów słowami (pierwszy lokal z danym powodem w każdym zbiorze)
    przyklady = []
    for nazwa, (dane, o) in {
        "test": (zb["test"], oceny["test (RCN 2026-H1)"]),
        "Katowice": (kat, oceny["oferty z Katowic"]),
        "Domilo": (domilo, oceny["lokale Domilo"]),
    }.items():
        ident = dane["id_lokalu"] if "id_lokalu" in dane else dane["id_transakcji"]
        for k in KODY:
            m = o[f"powod_{k}"].to_numpy()
            if m.any():
                i = int(np.argmax(m))
                przyklady.append(
                    {"zbior": nazwa, "powod": k, "id": ident.iloc[i], "powody_slowami": o["powody"].iloc[i]}
                )
    print(f"### Przykłady powodów słowami\n\n{_md(pd.DataFrame(przyklady))}\n")

    # 4. Zapis detektora i metryk.
    KATALOG.mkdir(parents=True, exist_ok=True)
    joblib.dump(det, KATALOG / "ood.joblib")
    metryki = {
        "uczony_na": "trening (rcn_transakcje, data_aktu 2023-01-01 – 2025-06-30, podzial.sql)",
        "policzono": date.today().isoformat(),
        "progi": {"knn": det.prog_knn_, "isolation_forest": det.prog_if_, "kwantyl_treningu": det.kwantyl_progu},
        "zakresy": det.zakresy_,
        "zakresy_metrazu_wg_pokoi": {str(k): v for k, v in det.zakresy_metrazu_pokoje_.items()},
        "odmowy": {
            k: {
                "lokale": int(len(v)),
                "odmowy_proc": float(100 * v["odmowa"].mean()),
                **{f"{kod}_proc": float(100 * v[f"powod_{kod}"].mean()) for kod in KODY},
            }
            for k, v in oceny.items()
        },
        "punkt_proponowany": {
            z: {"przyjete_proc": p[0], "mape_przyjetych_proc": p[1]} for z, p in punkty_proponowane.items()
        },
    }
    (KATALOG / "ood_metryki.json").write_text(
        json.dumps(metryki, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Zapisano versions/v3_przedzialy/ood.joblib, ood_metryki.json i wykresy w docs/img/.")


if __name__ == "__main__":
    main()
