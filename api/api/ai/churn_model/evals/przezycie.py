"""Czas najmu: odsetek cenzurowanych i trzy sposoby liczenia typowego czasu najmu (docs/przezycie.md).

Uruchomienie (wymaga domilo.duckdb z tabelą czas_najmu: `pypyr baza`):
    cd api && poetry run python -m api.ai.churn_model.evals.przezycie

Porównujemy na tabeli czas_najmu (features/najemcy/czas_najmu.sql):
- średnią tylko z zakończonych najmów (aktywne pominięte),
- średnią, w której aktywny najem dostaje dzisiejszy staż (do 2026-09-30) jako czas trwania,
- medianę z krzywej Kaplana-Meiera (lifelines), która aktywne najmy traktuje jako cenzurowane.
Dla porównania tej samej statystyki podajemy też mediany dwóch pierwszych podejść, przedział 95% mediany KM
odsetek najmów trwających dłużej niż 12 / 24 / 36 / 48 miesięcy według KM (także tuż przed 12 i 24) oraz średnią
z KM ograniczoną do 48 miesięcy (RMST), żeby średnią porównać ze średnią, a medianę z medianą.

lifelines 0.30.3 deklaruje pandas < 3, a projekt ma pandas 3.1; instalacja bez zależności (`pypyr install`,
`pip install --no-deps lifelines==0.30.3`). Test api/tests/test_czas_najmu.py porównuje krzywą z liczeniem ręcznym.
Zapis: evals/wyniki/przezycie.json, docs/img/przezycie_km.png.
"""

import json
from pathlib import Path

import matplotlib
import pandas as pd
from lifelines import KaplanMeierFitter
from lifelines.utils import median_survival_times, restricted_mean_survival_time

KATALOG_REPO = Path(__file__).resolve().parents[5]
SCIEZKA_WYNIKOW = Path(__file__).with_name("wyniki") / "przezycie.json"
SCIEZKA_WYKRESU = KATALOG_REPO / "docs" / "img" / "przezycie_km.png"
PROGI_MIESIECY = (12, 24, 36, 48)
HORYZONT_RMST = 48  # średnia z KM ograniczona do 4 lat: przy 48 mies. w ryzyku są jeszcze setki najmów

# Paleta referencyjna skilla dataviz (tryb jasny): cały portfel w tuszu, linie w stałej kolejności slotów.
KOLORY = {"wszystkie": "#52514e", "B2C": "#2a78d6", "B2B": "#eb6834"}
TUSZ = "#0b0b0b"
TUSZ_DRUGI = "#52514e"
SIATKA = "#e4e3df"
TLO = "#fcfcfb"


def krzywa_km(czasy: pd.DataFrame, etykieta: str = "KM") -> KaplanMeierFitter:
    """Kaplan-Meier na kolumnach miesiace (czas) i zdarzenie (1 = koniec najmu, 0 = cenzura)."""
    return KaplanMeierFitter(label=etykieta).fit(czasy["miesiace"], event_observed=czasy["zdarzenie"])


def _liczba(x) -> float | None:
    x = float(x)
    return None if x == float("inf") else x


def przezycie_po(km: KaplanMeierFitter, miesiace: float, scisle: bool = False) -> float | None:
    """S(t) z KM: odsetek najmów trwających dłużej niż t (scisle=True: tuż przed t); None, gdy t poza danymi."""
    s = km.survival_function_.iloc[:, 0]
    if s.index.max() < miesiace:
        return None
    return float(s[s.index < miesiace].iloc[-1] if scisle else s[s.index <= miesiace].iloc[-1])


def _srednie_ograniczone(czasy: pd.DataFrame, horyzont: float) -> tuple[float, float]:
    """Średnie dwóch naiwnych podejść z czasem uciętym do horyzontu (porównywalne z RMST)."""
    uciete = czasy["miesiace"].clip(upper=horyzont)
    return float(uciete[czasy["zdarzenie"] == 1].mean()), float(uciete.mean())


def podsumowanie_przezycia(czasy: pd.DataFrame, horyzont_rmst: float = HORYZONT_RMST) -> dict:
    """Odsetek cenzurowanych, średnie / mediany trzech podejść, mediana KM z przedziałem 95% i RMST."""
    zakonczone = czasy.loc[czasy["zdarzenie"] == 1, "miesiace"]
    km = krzywa_km(czasy)
    przedzial = median_survival_times(km.confidence_interval_)
    zak_ograniczona, staz_ograniczona = _srednie_ograniczone(czasy, horyzont_rmst)
    return {
        "najmy": int(len(czasy)),
        "zakonczone": int(len(zakonczone)),
        "cenzurowane": int((czasy["zdarzenie"] == 0).sum()),
        "odsetek_cenzurowanych": float((czasy["zdarzenie"] == 0).mean()),
        "srednia_zakonczone": float(zakonczone.mean()),
        "mediana_zakonczone": float(zakonczone.median()),
        "srednia_staz_jako_koniec": float(czasy["miesiace"].mean()),
        "mediana_staz_jako_koniec": float(czasy["miesiace"].median()),
        "mediana_km": _liczba(km.median_survival_time_),
        "mediana_km_95_od": _liczba(przedzial.iloc[0, 0]),
        "mediana_km_95_do": _liczba(przedzial.iloc[0, 1]),
        "km_trwa_dluzej_niz": {str(m): przezycie_po(km, m) for m in PROGI_MIESIECY},
        "km_tuz_przed": {str(m): przezycie_po(km, m, scisle=True) for m in (12, 24)},
        "horyzont_rmst": horyzont_rmst,
        "rmst_km": float(restricted_mean_survival_time(km, t=horyzont_rmst)),
        "srednia_zakonczone_do_horyzontu": zak_ograniczona,
        "srednia_staz_jako_koniec_do_horyzontu": staz_ograniczona,
        "najdluzsza_obserwacja_miesiace": float(czasy["miesiace"].max()),
    }


def cenzura_wg_roku(czasy: pd.DataFrame) -> list[dict]:
    """Rok wprowadzenia: najmy, odsetek aktywnych (cenzurowanych), średnia z zakończonych i KM po 12 / 24 mies."""
    tabela = czasy.groupby("rok_wprowadzenia").agg(
        najmy=("zdarzenie", "size"),
        cenzurowane=("zdarzenie", lambda z: int((z == 0).sum())),
        srednia_zakonczone=("miesiace", lambda m: float(m[czasy.loc[m.index, "zdarzenie"] == 1].mean())),
    )
    tabela["odsetek_cenzurowanych"] = tabela["cenzurowane"] / tabela["najmy"]
    wynik = []
    for rok, wiersz in tabela.to_dict("index").items():
        km = krzywa_km(czasy[czasy["rok_wprowadzenia"] == rok])
        wynik.append(
            {
                "rok_wprowadzenia": int(rok),
                **wiersz,
                "km_po_12": przezycie_po(km, 12),
                "km_po_24": przezycie_po(km, 24),
                "mediana_km": _liczba(km.median_survival_time_),
            }
        )
    return wynik


def wykres(czasy: pd.DataFrame, wyniki: dict, sciezka: Path = SCIEZKA_WYKRESU) -> None:
    """Krzywe KM: cały portfel, B2C, B2B (95% przedział), linia 50% i mediany."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150, facecolor=TLO)
    ax.set_facecolor(TLO)
    nazwy = {"wszystkie": "cały portfel", "B2C": "B2C", "B2B": "B2B"}
    uchwyty, opisy = [], []
    for nazwa in ("wszystkie", "B2C", "B2B"):
        km = krzywa_km(czasy if nazwa == "wszystkie" else czasy[czasy["linia"] == nazwa], nazwa)
        s = km.survival_function_.iloc[:, 0]
        ci = km.confidence_interval_
        kolor, styl = KOLORY[nazwa], "--" if nazwa == "wszystkie" else "-"
        if nazwa != "wszystkie":
            ax.fill_between(ci.index, ci.iloc[:, 0], ci.iloc[:, 1], step="post", color=kolor, alpha=0.15, lw=0)
        (linia,) = ax.step(s.index, s.values, where="post", color=kolor, lw=2, ls=styl, zorder=3)
        mediana = wyniki[nazwa]["mediana_km"]
        if mediana is not None:
            ax.plot([mediana], [0.5], "o", ms=8, color=kolor, mec=TLO, mew=2, zorder=5)
        uchwyty.append(linia)
        opisy.append(f"{nazwy[nazwa]}: mediana {mediana:.0f} mies." if mediana is not None else nazwy[nazwa])
    ax.axhline(0.5, color=TUSZ_DRUGI, lw=1, ls=":", zorder=2)
    ax.text(95, 0.515, "połowa najmów jeszcze trwa", fontsize=8, color=TUSZ_DRUGI, ha="right")
    ax.set_xlim(0, 96)
    ax.set_xticks(range(0, 97, 12))
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
    ax.set_xlabel("Miesiące od wprowadzenia", color=TUSZ_DRUGI)
    ax.set_ylabel("Najmy, które trwają dłużej", color=TUSZ_DRUGI)
    ax.set_title("Najmy roczne: ile trwa dłużej niż t miesięcy (Kaplan-Meier)", fontsize=11, color=TUSZ, loc="left")
    ax.grid(axis="y", color=SIATKA, lw=0.8)
    ax.tick_params(colors=TUSZ_DRUGI, length=0)
    for bok in ("top", "right", "left"):
        ax.spines[bok].set_visible(False)
    ax.spines["bottom"].set_color(SIATKA)
    ax.legend(uchwyty, opisy, frameon=False, loc="upper right", fontsize=9)
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(sciezka, facecolor=TLO, bbox_inches="tight")
    plt.close(fig)


def main() -> dict:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    czasy = con.execute("SELECT linia, miesiace, zdarzenie, rok_wprowadzenia FROM czas_najmu").df()
    con.close()
    wyniki = {
        "wszystkie": podsumowanie_przezycia(czasy),
        "B2C": podsumowanie_przezycia(czasy[czasy["linia"] == "B2C"]),
        "B2B": podsumowanie_przezycia(czasy[czasy["linia"] == "B2B"]),
        "cenzura_wg_roku": cenzura_wg_roku(czasy),
    }
    SCIEZKA_WYNIKOW.parent.mkdir(parents=True, exist_ok=True)
    SCIEZKA_WYNIKOW.write_text(json.dumps(wyniki, ensure_ascii=False, indent=2), encoding="utf-8")
    wykres(czasy, wyniki)
    return wyniki


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
