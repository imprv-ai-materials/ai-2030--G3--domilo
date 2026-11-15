"""Kalibracja izotoniczna v2b_lgbm_ipw i oceny 1–10 z LLM v1 (raport: evals/kalibracja.md).

Uruchomienie (po `pypyr baza`; odpowiedzi v1 muszą być w ai/llm/cache, skrypt nie woła API):
    cd api && poetry run python -m api.ai.lead_model.evals.kalibracja [--bez-mlflow]

Zbiory (features/leady/podzial_v2.py, czas warszawski):
- Zapisany v2b (versions/v2b_lgbm_ipw/model.joblib) uczył się na zapytaniach 2023-01 – 2026-02, więc walidacja
  2025-07 – 2026-02 jest w jego zbiorze uczącym. Dlatego v2b uczymy od nowa tym samym kodem (`ModelLGBMIPW`, te same
  parametry i cechy) na `trening` z utworzeniem przed 2025-07-01 (`v2b_do_2025_06`).
- Walidacja (tylko do kalibracji): `trening` z utworzeniem 2025-07-01 – 2026-02-28. Zbiór testowy nie bierze udziału
  w kalibracji.
- Ocena: okno migracji (każde zapytanie obsłużone) i, dla porządku, test 2026-03 – 2026-06.

Kalibracja (sklearn `IsotonicRegression`, `out_of_bounds="clip"`), dwa warianty:
- `kontakt` (główny): tylko obsłużone zapytania walidacji, waga IPW min(1 / P(obsłużony), 10) z modelu skłonności
  `v2b_do_2025_06`. Daje szansę na umowę *po kontakcie*, czyli to, co przewiduje v2b i co mierzy okno migracji.
- `wszystkie`: wszystkie zapytania walidacji bez wag. Daje szansę na umowę przy obecnym sposobie oddzwaniania
  (część zapytań bez kontaktu).
v1: wynik = ocena / 10 (tak jak v1_llm_zero_shot) i ta sama kalibracja. Baseline: v0_regula_zrodla uczona na tym
samym treningu (nieobsłużone = 0, jak w ewaluacja_v2b.py), surowa i po tej samej kalibracji, oraz stała.

Miary: ECE z 10 równych przedziałów [0; 0,1), …, [0,9; 1] (średnia |średni wynik − konwersja| ważona liczbą zapytań
w przedziale), ECE z 10 przedziałów o równej liczności (decyle wyniku), Brier, AUC, lift@10%, precision@k, liczba
różnych wartości wyniku. 95% CI dla ECE z bootstrapu (1 000 losowań).
Zapis: evals/wyniki/{kalibracja.json, kalibracja.parquet, kalibracja_okno.png}, MLflow (`leady`).
"""

import json
import sys

import matplotlib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.llm_client import KATALOG_CACHE
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.leady.podzial_v2 import STREFA
from api.ai.features.leady.sygnaly_v1 import _plik_cache
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_MODELU, KATALOG_WYNIKOW
from api.ai.lead_model.evals.ewaluacja_v2 import _json, przygotuj, target_treningu
from api.ai.lead_model.evals.metryki import dzienna_liczba_zapytan, lift_at, precision_at_k
from api.ai.lead_model.versions.v0_regula_zrodla.model import ModelRegulaZrodla
from api.ai.lead_model.versions.v1_llm_zero_shot.model import SKALA
from api.ai.lead_model.versions.v2b_lgbm_ipw.model import ModelLGBMIPW
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

KONIEC_TRENINGU = pd.Timestamp("2025-07-01", tz=STREFA)  # walidacja: od tej chwili do końca `trening` (2026-02-28)
PRZEDZIALY = 10
MIN_ZAPYTAN_NA_WYKRESIE = 30  # tylko wykres; ECE liczymy ze wszystkich przedziałów
LOSOWANIA_ECE = 1000
WARIANTY = ("kontakt", "wszystkie")
KOLOR_PRZED, KOLOR_PO, KOLOR_SIATKI, KOLOR_TEKSTU = "#2a78d6", "#eb6834", "#d9d8d2", "#3b3b38"


# --- miary kalibracji -------------------------------------------------------------------------------------------


def _krawedzie(p: np.ndarray, rowna_licznosc: bool) -> np.ndarray:
    if rowna_licznosc:
        return np.unique(np.quantile(p, np.linspace(0, 1, PRZEDZIALY + 1)))
    return np.round(np.linspace(0, 1, PRZEDZIALY + 1), 10)  # bez zaokrąglenia 0,3 wpadałoby do [0,2; 0,3)


def przedzialy(y, p, rowna_licznosc: bool = False) -> pd.DataFrame:
    """Tabela przedziałów: od, do, n, średni wynik, konwersja (ostatni przedział domknięty z prawej)."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    kr = _krawedzie(p, rowna_licznosc)
    nr = np.clip(np.searchsorted(kr, p, side="right") - 1, 0, len(kr) - 2)
    df = pd.DataFrame({"nr": nr, "p": p, "y": y})
    g = df.groupby("nr").agg(n=("y", "size"), sredni_wynik=("p", "mean"), konwersja=("y", "mean")).reset_index()
    g["od"], g["do"] = kr[g["nr"]], kr[g["nr"] + 1]
    return g[["od", "do", "n", "sredni_wynik", "konwersja"]]


def ece(y, p, rowna_licznosc: bool = False) -> float:
    t = przedzialy(y, p, rowna_licznosc)
    return float((t["n"] * (t["sredni_wynik"] - t["konwersja"]).abs()).sum() / t["n"].sum())


def ece_ci(y, p, ziarno: int = 42) -> list[float]:
    y, p = np.asarray(y), np.asarray(p)
    rng = np.random.default_rng(ziarno)
    proby = [ece(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(LOSOWANIA_ECE))]
    return [float(np.percentile(proby, 2.5)), float(np.percentile(proby, 97.5))]


def miary(y, p, k: int, z_ci: bool = False) -> dict:
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    wynik = {
        "n": int(len(y)),
        "umowy": int(y.sum()),
        "konwersja": float(y.mean()),
        "sredni_wynik": float(p.mean()),
        "ece_10_rowne": ece(y, p),
        "ece_10_decyle": ece(y, p, rowna_licznosc=True),
        "brier": float(np.mean((p - y) ** 2)),
        "auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None,
        "lift_10": lift_at(y, p) if p.std() > 0 else 1.0,
        "k": int(k),
        "precision_k": precision_at_k(y, p, k),
        "rozne_wartosci": int(len(np.unique(p))),
    }
    if z_ci:
        wynik["ece_10_rowne_ci95"] = ece_ci(y, p)
    return wynik


# --- dane --------------------------------------------------------------------------------------------------------


def oceny_v1(leady: pd.DataFrame) -> np.ndarray:
    """Ocena v1 (1–10) / 10 z ai/llm/cache (ten sam klucz co v1_llm_zero_shot); bez wywołań API."""
    oceny = []
    for lead in leady.to_dict("records"):
        plik = _plik_cache(lead, KATALOG_CACHE)
        if not plik.exists():
            raise RuntimeError(f"v1: brak odpowiedzi w cache dla {lead['id_leada']} (uruchom sygnaly_v1)")
        oceny.append(json.loads(plik.read_text(encoding="utf-8"))["odpowiedz"]["ocena"])
    return np.asarray(oceny, dtype=float) / SKALA


def kalibruj(p_wal, y_wal, wagi=None) -> IsotonicRegression:
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p_wal, y_wal, sample_weight=wagi)


def mapa(kal: IsotonicRegression) -> list[dict]:
    """Punkty schodków funkcji izotonicznej (wynik przed → po)."""
    return [{"przed": float(a), "po": float(b)} for a, b in zip(kal.X_thresholds_, kal.y_thresholds_)]


def _liczebnosc(wynik_v1: np.ndarray) -> dict[str, int]:
    """Liczba zapytań z każdą oceną v1 (1–10)."""
    oceny, n = np.unique(np.rint(wynik_v1 * SKALA).astype(int), return_counts=True)
    return {str(o): int(c) for o, c in zip(oceny, n)}


SQL_KONWERSJA_MIESIECZNA = """
SELECT strftime(date_trunc('month', l.utworzono), '%Y-%m') AS miesiac,
       count(*) FILTER (WHERE c.obsluzony) AS obsluzone,
       avg(c.umowa_45d::INT) FILTER (WHERE c.obsluzony) AS konwersja_obsluzonych,
       count(*) FILTER (WHERE c.okno_migracji) AS w_oknie_migracji
FROM crm_leady AS l JOIN leady_cel AS c USING (id_leada)
WHERE c.umowa_45d IS NOT NULL AND NOT c.cenzurowany
  AND l.utworzono >= TIMESTAMPTZ '2024-01-01 00:00 Europe/Warsaw'
  AND l.utworzono <  TIMESTAMPTZ '2026-07-01 00:00 Europe/Warsaw'
GROUP BY 1 ORDER BY 1
"""


SQL_OKNO_A_RESZTA_MIESIECY = """
SELECT c.okno_migracji, count(*) AS obsluzone, avg(c.umowa_45d::INT) AS konwersja_obsluzonych
FROM crm_leady AS l JOIN leady_cel AS c USING (id_leada)
WHERE c.obsluzony AND c.umowa_45d IS NOT NULL AND NOT c.cenzurowany
  AND l.utworzono >= TIMESTAMPTZ '2025-03-01 00:00 Europe/Warsaw'
  AND l.utworzono <  TIMESTAMPTZ '2025-05-01 00:00 Europe/Warsaw'
GROUP BY 1 ORDER BY 1
"""


def konwersja_miesieczna(con) -> dict:
    """Konwersja obsłużonych zapytań w każdym miesiącu 2024-01 – 2026-06 oraz w marcu–kwietniu 2025 w oknie migracji
    i poza nim (czy okno odstaje od reszty okresu)."""
    return {
        "miesiace": con.execute(SQL_KONWERSJA_MIESIECZNA).df().to_dict("records"),
        "marzec_kwiecien_2025_okno_a_reszta": con.execute(SQL_OKNO_A_RESZTA_MIESIECY).df().to_dict("records"),
    }


# --- wykres ------------------------------------------------------------------------------------------------------


def wykres(y, panele: list[tuple[str, np.ndarray, np.ndarray]], sciezka) -> None:
    """Krzywa kalibracji w oknie migracji: 10 równych przedziałów (te same co ECE), przed i po kalibracji."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tekst = ("text.color", "axes.labelcolor", "xtick.color", "ytick.color")
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": KOLOR_SIATKI} | {k: KOLOR_TEKSTU for k in tekst})
    fig, osie = plt.subplots(1, len(panele), figsize=(6 * len(panele), 5.4), dpi=150)
    for os_, (tytul, przed, po) in zip(osie, panele):
        gora, pominiete = 0.0, []
        for nazwa, p, kolor, znacznik in (("przed", przed, KOLOR_PRZED, "o"), ("po kalibracji", po, KOLOR_PO, "s")):
            t = przedzialy(y, p)
            male = t["n"] < MIN_ZAPYTAN_NA_WYKRESIE
            pominiete.append(f"{nazwa}: {int(male.sum())} przedz., {int(t.loc[male, 'n'].sum())} zapytań")
            t = t[~male]
            gora = max(gora, t["sredni_wynik"].max(), t["konwersja"].max())
            os_.plot(t["sredni_wynik"], t["konwersja"], color=kolor, lw=2, zorder=3,
                     label=f"{nazwa} (ECE {ece(y, p) * 100:.1f} pp)".replace(".", ","))  # fmt: skip
            os_.scatter(t["sredni_wynik"], t["konwersja"], s=np.clip(t["n"] / 6, 30, 300), color=kolor,
                        marker=znacznik, edgecolor="white", linewidth=2, zorder=4)  # fmt: skip
        gora = min(1.0, gora * 1.08)
        os_.plot([0, gora], [0, gora], color="#8a8983", lw=1, ls=(0, (4, 3)), zorder=1, label="idealna kalibracja")
        os_.set_xlim(0, gora)
        os_.set_ylim(0, gora)
        os_.set_aspect("equal")
        os_.grid(color=KOLOR_SIATKI, lw=0.6)
        os_.set_axisbelow(True)
        for bok in ("top", "right"):
            os_.spines[bok].set_visible(False)
        os_.set_title(tytul, loc="left", fontsize=11, fontweight="bold")
        os_.set_xlabel("średni wynik modelu w przedziale")
        os_.set_ylabel("odsetek zapytań z umową w 45 dni")
        procent = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%")
        os_.xaxis.set_major_formatter(procent)
        os_.yaxis.set_major_formatter(procent)
        os_.legend(frameon=False, loc="upper left")
        os_.text(0.03, 0.78, f"bez przedziałów < {MIN_ZAPYTAN_NA_WYKRESIE} zapytań\n" + "\n".join(pominiete),
                 transform=os_.transAxes, ha="left", va="top", fontsize=8, color="#6b6a64")  # fmt: skip
    fig.suptitle(f"Okno migracji CRM ({len(y):_} zapytań): 10 równych przedziałów wyniku, przed i po kalibracji; "
                 "wielkość punktu = liczba zapytań".replace("_", " "), x=0.01, ha="left", fontsize=11)  # fmt: skip
    fig.tight_layout()
    fig.savefig(sciezka, facecolor="white")
    plt.close(fig)


# --- główny przebieg ---------------------------------------------------------------------------------------------


def main(mlflow_wlaczony: bool = True) -> None:
    con = polacz()
    zbiory, cechy = przygotuj(con)
    pelny = zbiory["trening"]
    uczacy = (pelny["utworzono"] < KONIEC_TRENINGU).to_numpy()
    trening, walid = pelny[uczacy].reset_index(drop=True), pelny[~uczacy].reset_index(drop=True)
    X_tr = cechy["trening"][uczacy].reset_index(drop=True).assign(obsluzony=trening["obsluzony"].to_numpy())
    X_wal = cechy["trening"][~uczacy].reset_index(drop=True)
    y_tr = trening["umowa_45d"].astype(int).to_numpy()

    v2b = ModelLGBMIPW().fit(X_tr, y_tr)
    v2b_zapisany = ModelLeadow.wczytaj(KATALOG_MODELU / "versions" / "v2b_lgbm_ipw" / "model.joblib")
    v0 = ModelRegulaZrodla().fit(trening, target_treningu(trening))

    def wyniki_surowe(zbior: pd.DataFrame, X: pd.DataFrame) -> dict[str, np.ndarray]:
        return {"v2b": v2b.predict(X), "v1": oceny_v1(zbior), "v0": v0.predict(zbior)}

    # kalibracja na walidacji
    y_wal = walid["umowa_45d"].astype(int).to_numpy()
    obsl_wal = walid["obsluzony"].to_numpy(dtype=bool)
    wagi_wal = v2b.wagi(X_wal[obsl_wal])
    surowe_wal = wyniki_surowe(walid, X_wal)
    kalibratory = {(m, "kontakt"): kalibruj(surowe_wal[m][obsl_wal], y_wal[obsl_wal], wagi_wal) for m in surowe_wal} | {
        (m, "wszystkie"): kalibruj(surowe_wal[m], y_wal) for m in surowe_wal
    }
    stale = {
        "kontakt": float(np.average(y_wal[obsl_wal], weights=wagi_wal)),
        "wszystkie": float(y_wal.mean()),
    }

    metryki = {
        "opis": {
            "trening": "zamknięte, niecenzurowane zapytania 2023-01-01 – 2025-06-30 bez okna migracji",
            "walidacja": "zamknięte, niecenzurowane zapytania 2025-07-01 – 2026-02-28 (tylko kalibracja)",
            "kalibracja_kontakt": "obsłużone zapytania walidacji, waga min(1/P(obsłużony), 10), izotoniczna",
            "kalibracja_wszystkie": "wszystkie zapytania walidacji bez wag, izotoniczna",
            "ece": f"{PRZEDZIALY} równych przedziałów [0;1] oraz {PRZEDZIALY} decyli wyniku",
        },
        "trening": {
            "n": len(trening),
            "n_obsluzonych": int(trening["obsluzony"].sum()),
            "liczba_drzew": v2b.liczba_drzew_,
            "auc_walidacji_w_czasie_wazone": v2b.auc_walidacji_,
            "walidacja_wczesnego_zatrzymania_od": v2b.granica_walidacji_,
            "liczba_drzew_v2b_zapisanego": v2b_zapisany.liczba_drzew_,
        },
        "zbior_walidacyjny": {
            "n": len(walid),
            "umowy": int(y_wal.sum()),
            "n_obsluzonych": int(obsl_wal.sum()),
            "umowy_obsluzonych": int(y_wal[obsl_wal].sum()),
            "konwersja_obsluzonych_wazona_ipw": stale["kontakt"],
            "konwersja_wszystkich": stale["wszystkie"],
            "suma_wag": float(wagi_wal.sum()),
            "wagi_przyciete": int((1 / v2b.sklonnosc(X_wal[obsl_wal]) > v2b.maks_waga).sum()),
            "oceny_v1_obsluzone": _liczebnosc(surowe_wal["v1"][obsl_wal]),
            "oceny_v1_wszystkie": _liczebnosc(surowe_wal["v1"]),
        },
        "konwersja_miesieczna": konwersja_miesieczna(con),
        "mapy": {f"{m}_{w}": mapa(kal) for (m, w), kal in kalibratory.items()},
    }

    con.close()

    wiersze = []
    oceny = {"okno_migracji": zbiory["okno_migracji"], "test": zbiory["test"], "walidacja": walid}
    X_oceny = {"okno_migracji": cechy["okno_migracji"], "test": cechy["test"], "walidacja": X_wal}
    wykres_dane = None
    for nazwa, zbior in oceny.items():
        X = X_oceny[nazwa]
        y = zbior["umowa_45d"].astype(int).to_numpy()
        obsl = zbior["obsluzony"].to_numpy(dtype=bool)
        k = dzienna_liczba_zapytan(zbior["utworzono"])
        surowe = wyniki_surowe(zbior, X)
        surowe["v2b_zapisany"] = v2b_zapisany.predict(X)
        wyniki = dict(surowe)
        for (m, w), kal in kalibratory.items():
            wyniki[f"{m}_{w}"] = kal.predict(surowe[m])
        for w, c in stale.items():
            wyniki[f"stala_{w}"] = np.full(len(y), c)
        ci = nazwa == "okno_migracji"
        metryki[nazwa] = {
            "wszystkie": {m: miary(y, p, k, z_ci=ci) for m, p in wyniki.items()},
            "obsluzone": {m: miary(y[obsl], p[obsl], k) for m, p in wyniki.items()} if obsl.sum() < len(y) else None,
            "przedzialy": {
                m: przedzialy(y, wyniki[m]).to_dict("records")
                for m in ("v2b", "v2b_kontakt", "v2b_wszystkie", "v1", "v1_kontakt", "v1_wszystkie", "v0", "v0_kontakt")
            },
        }
        wiersze.append(
            zbior[["id_leada", "utworzono", "zrodlo", "obsluzony", "umowa_45d"]].assign(
                zbior=nazwa, **{f"wynik_{m}": p for m, p in wyniki.items()}
            )
        )
        if nazwa == "okno_migracji":
            wykres_dane = (y, wyniki)

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    y_okna, w_okna = wykres_dane
    sciezka_wykresu = KATALOG_WYNIKOW / "kalibracja_okno.png"
    wykres(
        y_okna,
        [
            ("v2b_lgbm_ipw (uczony do 2025-06), izotoniczna „kontakt”", w_okna["v2b"], w_okna["v2b_kontakt"]),
            ("v1_llm_zero_shot: ocena / 10, izotoniczna „kontakt”", w_okna["v1"], w_okna["v1_kontakt"]),
        ],
        sciezka_wykresu,
    )
    sciezka_json = KATALOG_WYNIKOW / "kalibracja.json"
    sciezka_json.write_text(json.dumps(metryki, ensure_ascii=False, indent=2, default=_json), "utf-8")
    pd.concat(wiersze, ignore_index=True).to_parquet(KATALOG_WYNIKOW / "kalibracja.parquet", index=False)

    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        plaskie = {
            f"{z}_{m}_{miara}": metryki[z]["wszystkie"][m][miara]
            for z in ("okno_migracji", "test")
            for m in ("v2b", "v2b_kontakt", "v2b_wszystkie", "v1", "v1_kontakt", "v1_wszystkie", "v0", "v0_kontakt")
            for miara in ("ece_10_rowne", "ece_10_decyle", "brier", "auc")
        }
        run = zapisz_run(
            "v2b_lgbm_ipw_izotoniczna",
            parametry={
                "model": "v2b_lgbm_ipw uczony od nowa na 2023-01 – 2025-06",
                "kalibracja": "IsotonicRegression, walidacja 2025-07 – 2026-02",
                "liczba_drzew": v2b.liczba_drzew_,
                "przedzialy_ece": PRZEDZIALY,
            },
            metryki=plaskie,
            tagi={"zbior_oceny": "okno migracji + test 2026-03 – 2026-06", "target": "leady_cel.umowa_45d"},
            artefakty=[sciezka_json, sciezka_wykresu],
        )
        print(f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run v2b_lgbm_ipw_izotoniczna = {run}")
    for z in ("okno_migracji", "test"):
        for m, r in metryki[z]["wszystkie"].items():
            pokaz = ("sredni_wynik", "konwersja", "ece_10_rowne", "ece_10_decyle", "brier", "auc")
            print(z, m, {x: round(r[x], 4) if isinstance(r[x], float) else r[x] for x in pokaz})


if __name__ == "__main__":
    main(mlflow_wlaczony="--bez-mlflow" not in sys.argv[1:])
