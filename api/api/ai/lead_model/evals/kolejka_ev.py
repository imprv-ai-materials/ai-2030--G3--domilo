"""Kolejka według pieniędzy w oknie migracji: od najnowszego vs według p vs według EV (docs/kolejka_ev.md).

Uruchomienie (po `pypyr baza` i `python -m api.ai.lead_model.evals.kalibracja`, które zapisuje p w
evals/wyniki/kalibracja.parquet):
    cd api && poetry run python -m api.ai.lead_model.evals.kolejka_ev [--bez-mlflow]

- Zbiór: wszystkie 5 320 zapytań z okna migracji CRM (2025-03-03 – 2025-04-13; każde obsłużone przez call center).
- p: v2b_lgbm_ipw uczony do 2025-06 po kalibracji izotonicznej „kontakt” (`wynik_v2b_kontakt`), czyli szansa na
  umowę w 45 dni po kontakcie. Remisy p (59 poziomów) rozstrzyga wynik przed kalibracją (ta sama kolejność co v2b).
- EV (leasing_bc/wartosc.py) = p × mediana czynszu linii w mieście × średni czas najmu linii × liczba lokali.
- Wartość podpisanych umów: Σ czynsz z umowy × czas najmu linii najmu, z całą umową ramową; 0 bez umowy w 45 dni.
- Kolejka dzienna: każdego dnia (data utworzenia, czas warszawski) zapytania z tego dnia w danej kolejności; „górne
  10%” = pierwsze 10% zapytań każdego dnia (część ułamkowa zapytania liczona proporcjonalnie). Krzywa gain: udział
  wartości podpisanych umów w pierwszych x% zapytań każdego dnia. Kolejności: od najnowszego (malejąco `utworzono`),
  według p, według EV. Dla porównania z lift@10% z porownanie.md: górne 10% całego okna naraz (tylko p i EV).
- Miara kontrolna bez założeń: wpłaty (`pms_platnosci.kwota_zaplacona`) ze wszystkich umów najmów powstałych
  z zapytania (z przedłużeniami) do dnia eksportu. Główna miara używa tego samego czasu najmu linii co EV, więc
  sama z siebie sprzyja kolejności według EV; wpłaty tego nie robią, ale są ucięte na 2026-09 (ok. 1,5 roku).
- 95% CI z bootstrapu dni (2 000 losowań 42 dni ze zwracaniem, te same losowania dla wszystkich kolejności).
Zapis: evals/wyniki/{kolejka_ev.json, kolejka_ev.parquet}, docs/img/kolejka_ev_gain.png, MLflow (`leady`, run
`kolejka_ev`).
"""

import json
import sys

import matplotlib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import KATALOG_REPO, polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.lead_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_WYNIKOW
from api.ai.lead_model.evals.ewaluacja_v2 import _json
from api.contexts_boundaries.leasing_bc.wartosc import czynsz_i_czas, umowy_zapytan, wartosc_oczekiwana, wartosc_umow
from api.contexts_boundaries.leasing_bc.zalozenia import wczytaj_zalozenia

STREFA = "Europe/Warsaw"
CZOLOWKA = 0.10
LOSOWANIA = 2000
FRAKCJE = np.linspace(0, 1, 201)
KOLEJNOSCI = {  # nazwa -> (kolumny sortowania, malejąco)
    "od_najnowszego": (["utworzono"], [False]),
    "wedlug_p": (["p", "p_przed_kalibracja"], [False, False]),
    "wedlug_ev": (["ev", "p_przed_kalibracja"], [False, False]),
}
ETYKIETY = {"od_najnowszego": "od najnowszego", "wedlug_p": "według p", "wedlug_ev": "według EV"}
KOLORY = {"od_najnowszego": "#2a78d6", "wedlug_p": "#eb6834", "wedlug_ev": "#1baf7a"}
SCIEZKA_WYKRESU = KATALOG_REPO / "docs" / "img" / "kolejka_ev_gain.png"

SQL_OKNO = """
SELECT l.id_leada, l.utworzono, l.miasto, l.linia_pref, l.liczba_lokali, c.umowa_45d, c.id_umowy
FROM crm_leady AS l JOIN leady_cel AS c USING (id_leada)
WHERE c.okno_migracji
ORDER BY l.id_leada
"""

SQL_WPLATY = """
WITH n AS (SELECT unnest(?) AS id_leada, unnest(?) AS id_najmu)
SELECT n.id_leada, count(DISTINCT u.id_umowy) AS umowy_najmow, sum(p.kwota_zaplacona) AS wplaty,
       sum(p.kwota_nalezna) AS nalezne, max(p.miesiac) AS ostatni_miesiac
FROM (SELECT DISTINCT id_leada, id_najmu FROM n) AS n
JOIN pms_umowy AS u USING (id_najmu)
JOIN pms_platnosci AS p USING (id_umowy)
GROUP BY n.id_leada
"""


# --- krzywe gain ----------------------------------------------------------------------------------------------------


def _sortuj(g: pd.DataFrame, kolejnosc: str) -> pd.DataFrame:
    kolumny, rosnaco = KOLEJNOSCI[kolejnosc]
    return g.sort_values(kolumny, ascending=rosnaco, kind="mergesort")


def zebrane_w_dniu(g: pd.DataFrame, kolejnosc: str, kolumna: str, frakcje: np.ndarray) -> np.ndarray:
    """Suma `kolumna` w pierwszych frakcja × n zapytaniach dnia (interpolacja liniowa wewnątrz zapytania)."""
    narastajaco = np.concatenate([[0.0], np.cumsum(_sortuj(g, kolejnosc)[kolumna].to_numpy(dtype=float))])
    return np.interp(frakcje * len(g), np.arange(len(g) + 1), narastajaco)


def tabela_dzienna(df: pd.DataFrame, kolumna: str, frakcje: np.ndarray) -> dict[str, np.ndarray]:
    """kolejność -> macierz [dzień × frakcja] zebranej sumy `kolumna`; plus 'suma' -> suma dnia."""
    dni = [g for _, g in df.groupby("dzien", sort=True)]
    wynik = {k: np.vstack([zebrane_w_dniu(g, k, kolumna, frakcje) for g in dni]) for k in KOLEJNOSCI}
    wynik["suma"] = np.array([g[kolumna].sum() for g in dni], dtype=float)
    return wynik


def zebrane_calosc(df: pd.DataFrame, kolejnosc: str, kolumna: str, frakcja: float) -> float:
    """Udział sumy `kolumna` w pierwszych frakcja × N zapytaniach całego okna (jedna kolejka)."""
    return float(zebrane_w_dniu(df, kolejnosc, kolumna, np.array([frakcja]))[0] / df[kolumna].sum())


def bootstrap_dni(tab: dict[str, np.ndarray], i_frakcji: int, ziarno: int = 42) -> dict:
    rng = np.random.default_rng(ziarno)
    n = len(tab["suma"])
    proby = {k: [] for k in KOLEJNOSCI}
    for _ in range(LOSOWANIA):
        i = rng.integers(0, n, n)
        for k in KOLEJNOSCI:
            proby[k].append(tab[k][i, i_frakcji].sum() / tab["suma"][i].sum())
    p = {k: np.asarray(v) for k, v in proby.items()}
    pary = {
        "ev_minus_p": p["wedlug_ev"] - p["wedlug_p"],
        "ev_minus_najnowsze": p["wedlug_ev"] - p["od_najnowszego"],
        "p_minus_najnowsze": p["wedlug_p"] - p["od_najnowszego"],
    }
    ci = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]  # noqa: E731
    return {k: ci(v) for k, v in p.items()} | {k: ci(v) for k, v in pary.items()}


def sklad_czolowki(df: pd.DataFrame) -> dict:
    """Pierwsze round(10% × n) zapytań każdego dnia: skład według linii i wkład w wartość."""
    wynik = {}
    for k in KOLEJNOSCI:
        czolo = pd.concat(
            [_sortuj(g, k).head(max(1, round(CZOLOWKA * len(g)))) for _, g in df.groupby("dzien", sort=True)]
        )
        po_linii = czolo.groupby("linia_pref").agg(
            zapytania=("id_leada", "size"), umowy=("umowa_45d", "sum"), wartosc=("wartosc", "sum")
        )
        wynik[k] = {
            "zapytania": int(len(czolo)),
            "umowy": int(czolo["umowa_45d"].sum()),
            "wartosc_pln": float(czolo["wartosc"].sum()),
            "srednie_p": float(czolo["p"].mean()),
            "sredni_ev_pln": float(czolo["ev"].mean()),
            "zapytania_z_wieloma_lokalami": int((czolo["lokale"] > 1).sum()),
            "po_linii": po_linii.reset_index().to_dict("records"),
        }
    return wynik


# --- wykres ---------------------------------------------------------------------------------------------------------


def wykres(krzywe: dict[str, np.ndarray], udzialy_10: dict[str, float], sciezka) -> None:
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    szary, tekst = "#d9d8d2", "#3b3b38"
    kolory_tekstu = ("text.color", "axes.labelcolor", "xtick.color", "ytick.color")
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": szary} | {k: tekst for k in kolory_tekstu})
    fig, osie = plt.subplots(1, 2, figsize=(12, 5.2), dpi=150)
    for os_, gora_x, tytul in ((osie[0], 1.0, "Cała kolejka"), (osie[1], 0.3, "Początek kolejki (0–30%)")):
        os_.plot([0, gora_x], [0, gora_x], color="#8a8983", lw=1, ls=(0, (4, 3)), label="losowa kolejność")
        for k in KOLEJNOSCI:
            etykieta = f"{ETYKIETY[k]} (górne 10%: {udzialy_10[k] * 100:.1f}%)".replace(".", ",")
            os_.plot(FRAKCJE, krzywe[k], color=KOLORY[k], lw=2, label=etykieta)
        os_.axvline(CZOLOWKA, color=szary, lw=1, zorder=0)
        maks_y = 1.0 if gora_x == 1.0 else min(1.0, max(float(np.interp(gora_x, FRAKCJE, krzywe[k])) for k in krzywe))
        os_.set_xlim(0, gora_x)
        os_.set_ylim(0, maks_y * 1.05 if gora_x < 1 else 1.0)
        os_.grid(color=szary, lw=0.6)
        os_.set_axisbelow(True)
        for bok in ("top", "right"):
            os_.spines[bok].set_visible(False)
        procent = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%")
        os_.xaxis.set_major_formatter(procent)
        os_.yaxis.set_major_formatter(procent)
        os_.set_xlabel("odsetek zapytań obsłużonych w kolejności (każdego dnia)")
        os_.set_ylabel("udział wartości podpisanych umów")
        os_.set_title(tytul, loc="left", fontsize=11, fontweight="bold")
    osie[1].legend(frameon=False, loc="upper left")
    fig.suptitle("Okno migracji CRM (5 320 zapytań, 42 dni): krzywe gain wartości umów dla trzech kolejności",
                 x=0.01, ha="left", fontsize=11)  # fmt: skip
    fig.tight_layout()
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(sciezka, facecolor="white")
    plt.close(fig)


# --- główny przebieg ------------------------------------------------------------------------------------------------


def main(mlflow_wlaczony: bool = True) -> None:
    zalozenia = wczytaj_zalozenia()
    con = polacz()
    df = con.execute(SQL_OKNO).df()
    wyniki_kal = pd.read_parquet(KATALOG_WYNIKOW / "kalibracja.parquet")
    p = wyniki_kal.loc[wyniki_kal["zbior"] == "okno_migracji", ["id_leada", "wynik_v2b", "wynik_v2b_kontakt"]]
    df = df.merge(p, on="id_leada", how="left", validate="1:1").rename(
        columns={"wynik_v2b_kontakt": "p", "wynik_v2b": "p_przed_kalibracja"}
    )
    if df["p"].isna().any():
        raise RuntimeError("Brak p dla części zapytań okna: uruchom evals/kalibracja.py")
    umowy = umowy_zapytan(con, df.loc[df["umowa_45d"] == 1, "id_leada"])
    wplaty = con.execute(SQL_WPLATY, [umowy["id_leada"].tolist(), umowy["id_najmu"].tolist()]).df()
    con.close()

    # kontrola umów ramowych: czy dwa zapytania nie dzielą jednej umowy ramowej (podwójne liczenie)
    ramowe = umowy.dropna(subset=["id_umowy_ramowej"]).groupby("id_umowy_ramowej")["id_leada"].nunique()
    umowy_dzielone = int(umowy.duplicated("id_umowy").sum())
    rozrzut = umowy.dropna(subset=["id_umowy_ramowej"]).groupby("id_leada")["data_podpisania"].agg(["min", "max"])
    rozrzut_dni = (rozrzut["max"] - rozrzut["min"]).dt.days

    df = df.join(czynsz_i_czas(df, zalozenia))
    df["ev"] = wartosc_oczekiwana(df["p"], df, zalozenia)
    df = df.merge(wartosc_umow(umowy, zalozenia), on="id_leada", how="left")
    df["umowy"] = df["umowy"].fillna(0).astype(int)
    df["wartosc"] = df["wartosc_umow"].fillna(0.0)
    df = df.merge(wplaty[["id_leada", "wplaty"]], on="id_leada", how="left")
    df["wplaty"] = df["wplaty"].fillna(0.0).astype(float)
    df["dzien"] = pd.to_datetime(df["utworzono"], utc=True).dt.tz_convert(STREFA).dt.date

    i10 = int(np.argmin(np.abs(FRAKCJE - CZOLOWKA)))
    tab_wartosc = tabela_dzienna(df, "wartosc", FRAKCJE)
    tab_umowy = tabela_dzienna(df, "umowa_45d", FRAKCJE)
    tab_wplaty = tabela_dzienna(df, "wplaty", FRAKCJE)
    krzywe = {k: tab_wartosc[k].sum(axis=0) / tab_wartosc["suma"].sum() for k in KOLEJNOSCI}
    udzialy = {k: float(krzywe[k][i10]) for k in KOLEJNOSCI}
    po_linii = df.groupby("linia_pref").agg(
        zapytania=("id_leada", "size"),
        umowy_45d=("umowa_45d", "sum"),
        lokale_podpisane=("umowy", "sum"),
        lokale_deklarowane_u_podpisanych=("lokale", lambda s: float(s[df.loc[s.index, "umowa_45d"] == 1].sum())),
        suma_ev=("ev", "sum"),
        wartosc_umow=("wartosc", "sum"),
        srednie_p=("p", "mean"),
    )
    wynik = {
        "zbior": "okno migracji 2025-03-03 – 2025-04-13",
        "n": len(df),
        "dni": len(tab_wartosc["suma"]),
        "umowy_45d": int(df["umowa_45d"].sum()),
        "lokale_podpisane": int(df["umowy"].sum()),
        "wartosc_umow_pln": float(df["wartosc"].sum()),
        "suma_ev_pln": float(df["ev"].sum()),
        "kontrola_umow_ramowych": {
            "umowy_ramowe": int(len(ramowe)),
            "ramowe_wspolne_dla_wielu_zapytan": int((ramowe > 1).sum()),
            "umowy_przypisane_wielu_zapytaniom": umowy_dzielone,
            "maks_dni_miedzy_podpisaniami_w_ramowej": int(rozrzut_dni.max()) if len(rozrzut_dni) else None,
        },
        "czolowka_10_dziennie": {
            k: {
                "udzial_wartosci": udzialy[k],
                "wartosc_pln": float(tab_wartosc[k][:, i10].sum()),
                "udzial_umow": float(tab_umowy[k][:, i10].sum() / tab_umowy["suma"].sum()),
                "umowy": float(tab_umowy[k][:, i10].sum()),
            }
            for k in KOLEJNOSCI
        },
        "czolowka_10_dziennie_ci95": bootstrap_dni(tab_wartosc, i10),
        "czolowka_10_dziennie_umowy_ci95": bootstrap_dni(tab_umowy, i10),
        "wplaty_do_eksportu": {
            "suma_pln": float(df["wplaty"].sum()),
            "zapytania_z_wplatami": int((df["wplaty"] > 0).sum()),
            "ostatni_miesiac": str(wplaty["ostatni_miesiac"].max()),
            "czolowka_10_dziennie": {
                k: {"udzial": float(tab_wplaty[k][:, i10].sum() / tab_wplaty["suma"].sum()),
                    "wplaty_pln": float(tab_wplaty[k][:, i10].sum())}  # fmt: skip
                for k in KOLEJNOSCI
            },
            "czolowka_10_dziennie_ci95": bootstrap_dni(tab_wplaty, i10),
            "po_linii": df.groupby("linia_pref")["wplaty"].sum().to_dict(),
        },
        "czolowka_10_cale_okno": {
            k: {
                "udzial_wartosci": zebrane_calosc(df, k, "wartosc", CZOLOWKA),
                "udzial_umow": zebrane_calosc(df, k, "umowa_45d", CZOLOWKA),
            }
            for k in ("wedlug_p", "wedlug_ev")
        },
        "sklad_czolowki_10": sklad_czolowki(df),
        "po_linii": po_linii.reset_index().to_dict("records"),
        "krzywe": {"frakcje": FRAKCJE.tolist(), **{k: v.tolist() for k, v in krzywe.items()}},
        "zalozenia": {k: zalozenia[k]["wartosc"] for k in ("czas_najmu_mies", "czynsz_mediana_pln")}
        | {"zastepstwo": zalozenia["czynsz_mediana_pln"].get("zastepstwo")},
    }

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    sciezka_json = KATALOG_WYNIKOW / "kolejka_ev.json"
    sciezka_json.write_text(json.dumps(wynik, ensure_ascii=False, indent=2, default=_json), "utf-8")
    kolumny = ["id_leada", "utworzono", "dzien", "miasto", "linia_pref", "linia_wyceny", "lokale", "czynsz",
               "czas_najmu_mies", "p", "p_przed_kalibracja", "ev", "umowa_45d", "umowy", "wartosc",
               "wplaty"]  # fmt: skip
    df[kolumny].to_parquet(KATALOG_WYNIKOW / "kolejka_ev.parquet", index=False)
    wykres(krzywe, udzialy, SCIEZKA_WYKRESU)

    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        metryki = {f"okno_czolowka10_udzial_wartosci_{k}": v for k, v in udzialy.items()}
        metryki |= {
            f"okno_czolowka10_udzial_umow_{k}": v["udzial_umow"] for k, v in wynik["czolowka_10_dziennie"].items()
        }
        metryki |= {
            f"okno_czolowka10_udzial_wplat_{k}": v["udzial"]
            for k, v in wynik["wplaty_do_eksportu"]["czolowka_10_dziennie"].items()
        }
        run = zapisz_run(
            "kolejka_ev",
            parametry={"p": "v2b_lgbm_ipw do 2025-06 + izotoniczna kontakt", "kolejka": "dzienna, górne 10%",
                       "ev": "p × mediana czynszu (linia, miasto) × czas najmu linii × liczba lokali"},  # fmt: skip
            metryki=metryki,
            tagi={"zbior_oceny": "okno migracji", "miara": "udział wartości podpisanych umów"},
            artefakty=[sciezka_json, SCIEZKA_WYKRESU],
        )
        print(f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run kolejka_ev = {run}")
    pokaz = ("czolowka_10_dziennie", "czolowka_10_dziennie_ci95", "czolowka_10_cale_okno", "kontrola_umow_ramowych",
             "wplaty_do_eksportu")  # fmt: skip
    print(json.dumps({k: wynik[k] for k in pokaz}, indent=1, default=_json))


if __name__ == "__main__":
    main(mlflow_wlaczony="--bez-mlflow" not in sys.argv[1:])
