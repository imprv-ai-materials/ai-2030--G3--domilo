"""Krzywe Kaplana-Meiera w grupach: B2C / B2B i indeksacja przy ostatnim przedłużeniu (<= 6% / > 6%).

Uruchomienie (wymaga domilo.duckdb z tabelą czas_najmu: `pypyr baza`):
    cd api && poetry run python -m api.ai.churn_model.evals.przezycie_grupy

Dla każdej grupy: S(12), S(24), mediana KM (95% przedział) i RMST do 60 miesięcy (pole pod krzywą = średni czas
najmu w ciągu pierwszych 5 lat). Grupy indeksacji: features/najemcy/indeksacja_ostatnia.sql (czas od wprowadzenia).
Kontrola: features/najemcy/okresy_przedluzen.sql, czas od początku przedłużenia, grupa = indeksacja tego
przedłużenia; tylko przedłużenia zaczęte w latach 2022–2023, kiedy obie grupy indeksacji są liczne.
Na koniec porównanie RMST z naiwnymi średnimi `czas_najmu_mies` z leasing_bc/zalozenia.yaml.
Zapis: evals/wyniki/przezycie_grupy.json, docs/img/przezycie_km_grupy.png.
"""

import json
from pathlib import Path

import matplotlib
import pandas as pd
from api.ai.churn_model.evals.przezycie import (
    KATALOG_REPO,
    SIATKA,
    TLO,
    TUSZ,
    TUSZ_DRUGI,
    _liczba,
    krzywa_km,
    przezycie_po,
)
from api.contexts_boundaries.leasing_bc.zalozenia import wczytaj_zalozenia
from lifelines.utils import median_survival_times, restricted_mean_survival_time

KATALOG_SQL = KATALOG_REPO / "api" / "api" / "ai" / "features" / "najemcy"
SQL_INDEKSACJA = KATALOG_SQL / "indeksacja_ostatnia.sql"
SQL_OKRESY = KATALOG_SQL / "okresy_przedluzen.sql"
SCIEZKA_WYNIKOW = Path(__file__).with_name("wyniki") / "przezycie_grupy.json"
SCIEZKA_WYKRESU = KATALOG_REPO / "docs" / "img" / "przezycie_km_grupy.png"
HORYZONT_RMST = 60
LATA_KONTROLI = (2022, 2023)

# Paleta referencyjna skilla dataviz (tryb jasny): linie = sloty 1–2 (jak w przezycie_km.png), indeksacja = sloty 3–4.
KOLORY = {"B2C": "#2a78d6", "B2B": "#eb6834", "<= 6%": "#1baf7a", "> 6%": "#eda100"}


def sql(sciezka: Path) -> str:
    return sciezka.read_text(encoding="utf-8").strip().rstrip(";")


def metryki_km(czasy: pd.DataFrame, horyzont: float = HORYZONT_RMST) -> dict:
    """S(12), S(24), mediana KM z 95% przedziałem, RMST do horyzontu; liczności i najkrótszy czas w grupie."""
    km = krzywa_km(czasy)
    przedzial = median_survival_times(km.confidence_interval_)
    return {
        "najmy": int(len(czasy)),
        "cenzurowane": int((czasy["zdarzenie"] == 0).sum()),
        "najkrotszy_czas_miesiace": float(czasy["miesiace"].min()),
        "S_12": przezycie_po(km, 12),
        "S_24": przezycie_po(km, 24),
        "mediana_km": _liczba(km.median_survival_time_),
        "mediana_km_95_od": _liczba(przedzial.iloc[0, 0]),
        "mediana_km_95_do": _liczba(przedzial.iloc[0, 1]),
        "horyzont_rmst": horyzont,
        "rmst_km": float(restricted_mean_survival_time(km, t=horyzont)),
    }


def roznice_z_zalozeniami(wyniki_linii: dict, zalozenia: dict) -> dict:
    """Naiwna średnia czas_najmu_mies (leasing_bc/zalozenia.yaml) wobec RMST: różnica w miesiącach i w %."""
    naiwne = zalozenia["czas_najmu_mies"]["wartosc"]
    wynik = {}
    for linia, metryki in wyniki_linii.items():
        rmst = metryki["rmst_km"]
        wynik[linia] = {
            "naiwna_srednia": float(naiwne[linia]),
            "rmst_km": rmst,
            "roznica_miesiace": rmst - float(naiwne[linia]),
            "roznica_proc_naiwnej": (rmst - float(naiwne[linia])) / float(naiwne[linia]),
        }
    return wynik


def _krzywa(ax, czasy: pd.DataFrame, etykieta: str, kolor: str) -> None:
    km = krzywa_km(czasy, etykieta)
    s = km.survival_function_.iloc[:, 0]
    ci = km.confidence_interval_
    ax.fill_between(ci.index, ci.iloc[:, 0], ci.iloc[:, 1], step="post", color=kolor, alpha=0.15, lw=0)
    mediana = _liczba(km.median_survival_time_)
    opis = f"{etykieta} (n = {len(czasy):,}".replace(",", " ")
    opis += f"; mediana {mediana:.0f} mies.)" if mediana is not None else "; mediana poza danymi)"
    ax.step(s.index, s.values, where="post", color=kolor, lw=2, label=opis, zorder=3)
    if mediana is not None:
        ax.plot([mediana], [0.5], "o", ms=8, color=kolor, mec=TLO, mew=2, zorder=5)


def wykres(panele: list[tuple[str, str, list[tuple[str, pd.DataFrame]]]], sciezka: Path = SCIEZKA_WYKRESU) -> None:
    """Małe wielokrotności: jeden panel na podział, wspólna oś Y; linia 50% i RMST-owy horyzont 60 mies."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, osie = plt.subplots(1, len(panele), figsize=(5.2 * len(panele), 5.2), dpi=150, sharey=True, facecolor=TLO)
    for ax, (tytul, os_x, grupy) in zip(osie, panele):
        ax.set_facecolor(TLO)
        for etykieta, czasy in grupy:
            _krzywa(ax, czasy, etykieta, KOLORY[etykieta])
        ax.axhline(0.5, color=TUSZ_DRUGI, lw=1, ls=":", zorder=2)
        ax.axvline(HORYZONT_RMST, color=SIATKA, lw=1, zorder=1)
        ax.set_xlim(0, 90)
        ax.set_xticks(range(0, 91, 12))
        ax.set_ylim(0, 1.02)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
        ax.set_title(tytul, fontsize=10, color=TUSZ, loc="left")
        ax.set_xlabel(os_x, color=TUSZ_DRUGI, fontsize=9)
        ax.grid(axis="y", color=SIATKA, lw=0.8)
        ax.tick_params(colors=TUSZ_DRUGI, length=0, labelsize=8)
        for bok in ("top", "right", "left"):
            ax.spines[bok].set_visible(False)
        ax.spines["bottom"].set_color(SIATKA)
        ax.legend(frameon=False, loc="upper right", fontsize=8)
    osie[0].set_ylabel("Najmy, które trwają dłużej", color=TUSZ_DRUGI)
    fig.suptitle(
        "Kaplan-Meier: odsetek najmów trwających dłużej niż t miesięcy (kropka = mediana, pionowa linia = 60 mies.)",
        fontsize=11,
        color=TUSZ,
        x=0.01,
        ha="left",
    )
    fig.tight_layout()
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(sciezka, facecolor=TLO, bbox_inches="tight")
    plt.close(fig)


def main() -> dict:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    najmy = con.execute(sql(SQL_INDEKSACJA)).df()
    okresy = con.execute(sql(SQL_OKRESY)).df()
    con.close()
    kontrola = okresy[okresy["rok_przedluzenia"].isin(LATA_KONTROLI)]

    grupy = {
        "linia": {linia: najmy[najmy["linia"] == linia] for linia in ("B2C", "B2B")},
        "indeksacja_ostatnia": {
            g: najmy[najmy["grupa_indeksacji"] == g] for g in ("<= 6%", "> 6%", "bez przedłużenia")
        },
        "indeksacja_ostatnia_B2C": {
            g: najmy[(najmy["grupa_indeksacji"] == g) & (najmy["linia"] == "B2C")] for g in ("<= 6%", "> 6%")
        },
        "indeksacja_ostatnia_B2B": {
            g: najmy[(najmy["grupa_indeksacji"] == g) & (najmy["linia"] == "B2B")] for g in ("<= 6%", "> 6%")
        },
        "kontrola_od_przedluzenia_2022_2023": {
            g: kontrola[kontrola["grupa_indeksacji"] == g] for g in ("<= 6%", "> 6%")
        },
    }
    for rok in LATA_KONTROLI:
        for linia in ("B2C", "B2B"):
            grupy[f"kontrola_{rok}_{linia}"] = {
                g: kontrola[
                    (kontrola["rok_przedluzenia"] == rok)
                    & (kontrola["linia"] == linia)
                    & (kontrola["grupa_indeksacji"] == g)
                ]
                for g in ("<= 6%", "> 6%")
            }
    wyniki = {podzial: {g: metryki_km(d) for g, d in gr.items()} for podzial, gr in grupy.items()}
    wyniki["ostatnie_przedluzenie_wg_roku"] = (
        najmy[najmy["przedluzenia"] > 0]
        .assign(rok=lambda d: pd.to_datetime(d["data_od_ostatniego"]).dt.year)
        .groupby(["rok", "grupa_indeksacji"])
        .size()
        .unstack(fill_value=0)
        .to_dict("index")
    )
    wyniki["ostatnie_przedluzenie_wg_roku"] = {str(k): v for k, v in wyniki["ostatnie_przedluzenie_wg_roku"].items()}
    wyniki["kontrola_przedluzenia_na_najem"] = float(len(kontrola) / kontrola["id_najmu"].nunique())
    wyniki["zalozenia_vs_rmst"] = roznice_z_zalozeniami(wyniki["linia"], wczytaj_zalozenia())

    SCIEZKA_WYNIKOW.parent.mkdir(parents=True, exist_ok=True)
    SCIEZKA_WYNIKOW.write_text(json.dumps(wyniki, ensure_ascii=False, indent=2), encoding="utf-8")
    wykres(
        [
            ("Linia klienta", "Miesiące od wprowadzenia", list(grupy["linia"].items())),
            (
                "Indeksacja przy ostatnim przedłużeniu",
                "Miesiące od wprowadzenia",
                [(g, grupy["indeksacja_ostatnia"][g]) for g in ("<= 6%", "> 6%")],
            ),
            (
                "Kontrola: przedłużenia 2022–2023",
                "Miesiące od początku przedłużenia",
                list(grupy["kontrola_od_przedluzenia_2022_2023"].items()),
            ),
        ]
    )
    return wyniki


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
