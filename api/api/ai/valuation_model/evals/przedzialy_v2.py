"""Przedział 80% (P10–P90) dla v2_lgbm_geo: modele kwantylowe LightGBM i kalibracja CQR (docs/b1_przedzialy.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.przedzialy_v2                 # uczenie + walidacja
    poetry run python -m api.ai.valuation_model.evals.przedzialy_v2 --otworz-test   # jednorazowo: także test

Kto czego używa:
- P50: zapisany model punktowy versions/v2_lgbm_geo/model.joblib (bez ponownego uczenia);
- modele kwantylowe (alpha 0,1 i 0,9): liczba drzew z wczesnego zatrzymania na trening 2025-01 – 2025-06
  (część odłożona), potem uczenie na całym treningu 2023-01 – 2025-06 z tą liczbą drzew;
- kalibracja CQR i punkt odniesienia (stały przedział względny): walidacja 2025-07 – 2025-12;
- test 2026-01 – 2026-06: tylko pomiar. Metodę główną (CQR symetryczny) wybraliśmy przed otwarciem testu.
Skrypt odmawia ponownego otwarcia testu, jeśli versions/v2_lgbm_geo_cqr/metryki.json ma już wynik testu.
Bez `--otworz-test` nic nie jest zapisywane.
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.wycena.geo import SCIEZKA_GEO, cechy_geo
from api.ai.features.wycena.podzial import SCIEZKA_PODZIALU
from api.ai.features.wycena.sasiedztwo import SCIEZKA_SASIEDZTWA, cechy_sasiedztwa_punktow
from api.ai.features.wycena.zbior import wczytaj_transakcje_z_cechami
from api.ai.valuation_model.base import ModelWyceny
from api.ai.valuation_model.evals.analiza_bledow_v2 import ETYKIETY_CENY, PROGI_CENY, SQL_OFERTY, _f
from api.ai.valuation_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_WERSJI, OPIS_PODZIALU, _md
from api.ai.valuation_model.versions.v2_lgbm_geo_cqr.model import (
    POZIOM,
    ModelPrzedzialuCQR,
    kwantyl_konformalny,
)

KATALOG = KATALOG_WERSJI / ModelPrzedzialuCQR.wersja
RAPORT = "docs/b1_przedzialy.md"
POCZATEK_ODLOZONEJ = pd.Timestamp("2025-01-01")  # trening od tego dnia = część odłożona do wyboru liczby drzew
NORMA_BANKU = (77.0, 83.0)  # pokrycie przedziału 80% wymagane przez bank, w %

# Nazwa metody -> etykieta w tabelach. „staly” = punkt odniesienia.
METODY = {
    "staly": "stały ±% (odniesienie)",
    "surowy": "kwantylowe, przed kalibracją",
    "cqr": "CQR (główna)",
    "cqr_asymetryczny": "CQR asymetryczny",
}


# --- punkt odniesienia: stały przedział względny wokół wyceny -------------------------------------------------


def granice_stale(p50_kal: np.ndarray, y_kal: np.ndarray, poziom: float = POZIOM) -> tuple[float, float]:
    """(dół, góra) w ln: P10 = P50·exp(dół), P90 = P50·exp(góra), z błędów ln(y/P50) na zbiorze kalibracyjnym.

    Ten sam kwantyl konformalny co w CQR, osobno dla każdego ogona (po (1 − poziom)/2).
    """
    r = np.log(np.asarray(y_kal, dtype=float) / np.asarray(p50_kal, dtype=float))
    poziom_ogona = 1 - (1 - poziom) / 2
    return -kwantyl_konformalny(-r, poziom_ogona), kwantyl_konformalny(r, poziom_ogona)


def przedzial_staly(p50: np.ndarray, granice: tuple[float, float]) -> pd.DataFrame:
    return pd.DataFrame({"p10": p50 * np.exp(granice[0]), "p50": p50, "p90": p50 * np.exp(granice[1])})


# --- metryki przedziału ------------------------------------------------------------------------------------------


def metryki_przedzialu(y, p10, p50, p90) -> dict[str, float]:
    """Pokrycie i ogony w %, szerokość względna (P90 − P10) / P50 w %."""
    y, p10, p50, p90 = (np.asarray(a, dtype=float) for a in (y, p10, p50, p90))
    szer = (p90 - p10) / p50
    return {
        "n": int(len(y)),
        "pokrycie": float(100 * np.mean((y >= p10) & (y <= p90))),
        "ponizej_p10": float(100 * np.mean(y < p10)),
        "powyzej_p90": float(100 * np.mean(y > p90)),
        "mediana_szerokosci": float(100 * np.median(szer)),
        "srednia_szerokosci": float(100 * np.mean(szer)),
    }


def _w_normie(pokrycie: float) -> str:
    return "tak" if NORMA_BANKU[0] <= pokrycie <= NORMA_BANKU[1] else "**nie**"


def _przedzialy(model: ModelPrzedzialuCQR, granice: tuple[float, float], d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    wyj = {m: model.predict_interval(d, metoda=m).reset_index(drop=True) for m in METODY if m != "staly"}
    wyj["staly"] = przedzial_staly(wyj["cqr"]["p50"].to_numpy(), granice)
    return {m: wyj[m] for m in METODY}


def tabela_ogolem(d: pd.DataFrame, przedzialy: dict[str, pd.DataFrame], zbior: str) -> pd.DataFrame:
    wiersze = []
    for m, p in przedzialy.items():
        mm = metryki_przedzialu(d["cena_pln"], p["p10"], p["p50"], p["p90"])
        wiersze.append(
            {
                "zbior": zbior,
                "przedzial": METODY[m],
                "n": mm["n"],
                "pokrycie_proc": _f(mm["pokrycie"], 1),
                "w_normie_77_83": _w_normie(mm["pokrycie"]),
                "ponizej_P10_proc": _f(mm["ponizej_p10"], 1),
                "powyzej_P90_proc": _f(mm["powyzej_p90"], 1),
                "mediana_szerokosci_proc": _f(mm["mediana_szerokosci"], 1),
                "srednia_szerokosci_proc": _f(mm["srednia_szerokosci"], 1),
            }
        )
    return pd.DataFrame(wiersze)


def tabela_segmentow(d: pd.DataFrame, przedzialy: dict[str, pd.DataFrame], kolumna: str) -> pd.DataFrame:
    """Jeden wiersz na segment: pokrycie przed/po kalibracji i odniesienie, ogony i szerokość CQR."""
    wiersze = []
    grupy = list(d.reset_index(drop=True).groupby(kolumna, observed=True, sort=True))
    grupy.append(("wszystkie", d.reset_index(drop=True)))
    for wartosc, g in grupy:
        idx = g.index
        mm = {m: metryki_przedzialu(g["cena_pln"], *(p.loc[idx, k] for k in ("p10", "p50", "p90")))
              for m, p in przedzialy.items()}  # fmt: skip
        wiersze.append(
            {
                "segment": str(wartosc),
                "n": int(len(g)),
                "pokrycie_przed": _f(mm["surowy"]["pokrycie"], 1),
                "pokrycie_CQR": _f(mm["cqr"]["pokrycie"], 1),
                "w_normie_77_83": _w_normie(mm["cqr"]["pokrycie"]),
                "ponizej_P10_CQR": _f(mm["cqr"]["ponizej_p10"], 1),
                "powyzej_P90_CQR": _f(mm["cqr"]["powyzej_p90"], 1),
                "pokrycie_CQR_asym": _f(mm["cqr_asymetryczny"]["pokrycie"], 1),
                "pokrycie_staly": _f(mm["staly"]["pokrycie"], 1),
                "szerokosc_przed": _f(mm["surowy"]["mediana_szerokosci"], 1),
                "szerokosc_CQR": _f(mm["cqr"]["mediana_szerokosci"], 1),
                "szerokosc_staly": _f(mm["staly"]["mediana_szerokosci"], 1),
            }
        )
    return pd.DataFrame(wiersze)


def _segmenty(d: pd.DataFrame, p50: np.ndarray) -> pd.DataFrame:
    d = d.reset_index(drop=True).copy()
    d["segment_ceny"] = pd.cut(d["cena_pln"], PROGI_CENY, labels=ETYKIETY_CENY, right=False)
    d["segment_wyceny"] = pd.cut(p50, PROGI_CENY, labels=ETYKIETY_CENY, right=False)
    d["metraz_grupa"] = np.where(d["metraz"] < 30, "< 30 m²", "≥ 30 m²")
    d["miesiac_aktu"] = d["data_aktu"].dt.strftime("%Y-%m")
    return d


# --- Katowice: przedział dla ofert z miasta spoza treningu -----------------------------------------------------


def przedzialy_ofert(con, model: ModelPrzedzialuCQR) -> None:
    """Oferty 2026-06 – 2026-09 (jak w b1_bledy.md, tabela 7–8): szerokość przedziału i pokrycie 40 operatów DD."""
    oferty = con.execute(SQL_OFERTY).df()
    geo_sql = f"SELECT id_transakcji, miasto, dzielnica, lat, lon FROM ({SQL_OFERTY})"
    sas_sql = f"SELECT id_transakcji, miasto, lat, lon, dzien_wyceny FROM ({SQL_OFERTY})"
    oferty = oferty.merge(cechy_geo(con, geo_sql), on="id_transakcji", how="left", validate="one_to_one")
    oferty = oferty.merge(cechy_sasiedztwa_punktow(con, sas_sql), on="id_transakcji", how="left", validate="one_to_one")
    p = model.predict_interval(oferty)
    oferty = oferty.join(p)
    oferty["szerokosc"] = 100 * (oferty["p90"] - oferty["p10"]) / oferty["p50"]
    oferty["znane"] = np.where(oferty["miasto"] == "Katowice", "Katowice (spoza treningu)", "6 miast z treningu")
    wiersze = []
    for nazwa, g in oferty.groupby("znane"):
        wiersze.append(
            {
                "oferty": nazwa,
                "n": int(len(g)),
                "mediana_szerokosci_CQR_proc": _f(g["szerokosc"].median(), 1),
                "P90_szerokosci_CQR_proc": _f(g["szerokosc"].quantile(0.9), 1),
                "max_szerokosci_CQR_proc": _f(g["szerokosc"].max(), 1),
            }
        )
    print(f"### Oferty 2026-06 – 2026-09: szerokość przedziału CQR\n\n{_md(pd.DataFrame(wiersze))}\n")
    dd = oferty[oferty["id_operatu"].notna()]
    w = dd["wartosc_operatu"]
    tab = pd.DataFrame(
        [
            {
                "operaty_DD": int(len(dd)),
                "operat_w_P10_P90": int(((w >= dd["p10"]) & (w <= dd["p90"])).sum()),
                "operat_ponizej_P10": int((w < dd["p10"]).sum()),
                "operat_powyzej_P90": int((w > dd["p90"]).sum()),
                "mediana_szerokosci_proc": _f(dd["szerokosc"].median(), 1),
                "mediana_P10_do_operatu_proc": _f(100 * (dd["p10"] / w - 1).median(), 1),
            }
        ]
    )
    print(f"### Katowice: 40 operatów due diligence a przedział CQR\n\n{_md(tab)}\n")


# --- przebieg ------------------------------------------------------------------------------------------------------


def _test_juz_otwarty() -> bool:
    plik = KATALOG / "metryki.json"
    return plik.exists() and "test" in json.loads(plik.read_text(encoding="utf-8"))["metryki"]


def main(otworz_test: bool = False, mlflow_wlaczony: bool = True) -> None:
    if otworz_test and _test_juz_otwarty():
        raise SystemExit(f"Zbiór testowy dla {ModelPrzedzialuCQR.wersja} był już otwarty ({KATALOG / 'metryki.json'}).")
    con = polacz()
    df = wczytaj_transakcje_z_cechami(con)
    typ = con.execute("SELECT id_transakcji, typ_budynku FROM rcn_transakcje").df()
    df = df.merge(typ, on="id_transakcji", how="left", validate="one_to_one")
    tr, wal = df[df["zbior"] == "trening"], df[df["zbior"] == "walidacja"]
    tr_ucz, tr_odl = tr[tr["data_aktu"] < POCZATEK_ODLOZONEJ], tr[tr["data_aktu"] >= POCZATEK_ODLOZONEJ]
    print(
        f"Trening: {len(tr)} (uczenie do wyboru drzew {len(tr_ucz)}, odłożone 2025-H1 {len(tr_odl)}), "
        f"walidacja/kalibracja: {len(wal)}\n"
    )

    punktowy = ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lgbm_geo" / "model.joblib")
    model = ModelPrzedzialuCQR(punktowy).fit(tr_ucz, tr_ucz["cena_pln"], tr_odl, tr_odl["cena_pln"])
    model.kalibruj(wal, wal["cena_pln"])
    granice = granice_stale(punktowy.predict(wal), wal["cena_pln"].to_numpy())
    parametry = {
        "drzewa_p10": model.drzewa_["p10"],
        "drzewa_p90": model.drzewa_["p90"],
        "korekta_cqr_ln": model.korekta_,
        "korekta_cqr_asym_dol_ln": model.korekta_asym_[0],
        "korekta_cqr_asym_gora_ln": model.korekta_asym_[1],
        "n_kalibracji": model.n_kalibracji_,
        "staly_dol_ln": granice[0],
        "staly_gora_ln": granice[1],
    }
    print(
        "### Parametry\n\n"
        + _md(pd.DataFrame([{k: (_f(v, 4) if isinstance(v, float) else v) for k, v in parametry.items()}]))
        + f"\n\nCQR: granice × exp(∓{model.korekta_:.4f}) = dolna × {np.exp(-model.korekta_):.4f}, "
        f"górna × {np.exp(model.korekta_):.4f}. Stały: P10 = P50 × {np.exp(granice[0]):.4f}, "
        f"P90 = P50 × {np.exp(granice[1]):.4f}\n"
    )

    przedzialy_ofert(con, model)

    oceniane = {"trening": tr, "walidacja": wal}
    if otworz_test:
        oceniane["test"] = df[df["zbior"] == "test"]
    wyniki: dict[str, dict] = {}
    ogolem = []
    for z, d in oceniane.items():
        p = _przedzialy(model, granice, d)
        ogolem.append(tabela_ogolem(d, p, z))
        wyniki[z] = {m: metryki_przedzialu(d["cena_pln"], pp["p10"], pp["p50"], pp["p90"]) for m, pp in p.items()}
        if z == "trening":
            continue
        s = _segmenty(d, p["cqr"]["p50"].to_numpy())
        for kol, tytul in (
            ("segment_ceny", "segment ceny transakcyjnej"),
            ("segment_wyceny", "segment wyceny (P50)"),
            ("miasto", "miasto"),
            ("typ_budynku", "typ budynku"),
            ("metraz_grupa", "metraż"),
            ("miesiac_aktu", "miesiąc aktu"),
        ):
            print(f"### {z}: {tytul}\n\n{_md(tabela_segmentow(s, p, kol))}\n")
        if z == "test":
            male = s[s["metraz"] < 30]
            pm = {m: pp.loc[male.index].reset_index(drop=True) for m, pp in p.items()}
            print(f"### test: lokale < 30 m² według miasta\n\n{_md(tabela_segmentow(male, pm, 'miasto'))}\n")
    print(f"### Ogółem\n\n{_md(pd.concat(ogolem, ignore_index=True))}\n")

    if not otworz_test:
        print("Przebieg roboczy (bez testu): model i metryki nie zostały zapisane.")
        return

    KATALOG.mkdir(parents=True, exist_ok=True)
    model.zapisz(KATALOG / "model.joblib")
    opis = {
        "wersja": model.wersja,
        "p50": "versions/v2_lgbm_geo/model.joblib (bez ponownego uczenia)",
        "modele_kwantylowe": "LightGBM objective=quantile, alpha 0,1 i 0,9, cechy i hiperparametry jak v2_lgbm_geo",
        "wybor_liczby_drzew": "wczesne zatrzymanie na trening 2025-01-01 – 2025-06-30 (uczenie na 2023-01 – 2024-12), "
        "potem uczenie na całym treningu",
        "kalibracja": "CQR symetryczny w ln(ceny) na walidacji 2025-07-01 – 2025-12-31 (metoda główna, wybrana "
        "przed otwarciem testu); obok CQR asymetryczny i stały przedział względny (odniesienie)",
        "test_otwarty": date.today().isoformat(),
        "parametry": parametry,
        "metryki": wyniki,
    }
    (KATALOG / "metryki.json").write_text(json.dumps(opis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        run_id = zapisz_run(
            model.wersja,
            parametry={"wersja": model.wersja, **parametry},
            metryki={f"{z}_{m}_{k}": v for z, mm in wyniki.items() for m, d in mm.items() for k, v in d.items()},
            tagi={
                "podzial": "czasowy (podzial.sql, data_aktu)",
                "podzial_opis": OPIS_PODZIALU,
                "target": "rcn_transakcje.cena_pln; przedział 80% P10–P90, kalibracja CQR na walidacji",
                "raport": RAPORT,
            },
            artefakty=[
                KATALOG / "model.joblib",
                KATALOG / "metryki.json",
                KATALOG / "model.py",
                SCIEZKA_PODZIALU,
                SCIEZKA_GEO,
                SCIEZKA_SASIEDZTWA,
                Path(__file__),
            ],
        )
        print(f"MLflow: run {model.wersja} = {run_id}")


if __name__ == "__main__":
    argumenty = sys.argv[1:]
    main(otworz_test="--otworz-test" in argumenty, mlflow_wlaczony="--bez-mlflow" not in argumenty)
