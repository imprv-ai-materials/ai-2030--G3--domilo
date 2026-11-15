"""v4_llm_cechy: uczenie, porównanie z v2/v3 na testowych dopasowaniach i 300 operatach kontrolnych, koszt ekstrakcji
(docs/b1_v4_llm_cechy.md).

Uruchomienie (wymaga domilo.duckdb i wyników ekstrakcji w features/wycena/cechy_llm/*.parquet), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v4

v4 = ModelWycenyV4.fit na tym samym podziale co v3 (trening; walidacja do wczesnego zatrzymania P50 i kalibracji CQR;
część treningu od 2025-01-01 do wyboru liczby drzew P10/P90), z detektorem versions/v3_przedzialy/ood.joblib.
Cechy LLM z opisu dopasowanej oferty (bez kwot). Wariant „+ zdjęcia”: llm_standard zastąpiony standardem odczytanym
ze zdjęć tam, gdzie zdjęcia są (model uczył się tylko na standardzie z opisu, więc to sprawdzian, nie wersja).
Reguła decyzji (ustalona przed uruchomieniem): REGULA. Zapisuje versions/v4_llm_cechy/model.joblib i metryki.json.
"""

import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.cechy_llm import KOLUMNY_LLM, LLM_KATEGORII, cechy_do_modelu
from api.ai.features.wycena.zbior import wczytaj_transakcje_z_cechami
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.analiza_bledow_v2 import _f
from api.ai.valuation_model.evals.ewaluacja import KATALOG_WERSJI, _md
from api.ai.valuation_model.evals.ewaluacja_v3 import POCZATEK_ODLOZONEJ, metryki_v3
from api.ai.valuation_model.evals.ood_v3 import wczytaj_lokale_domilo
from api.ai.valuation_model.versions.v4_llm_cechy.model import ModelWycenyV4

KATALOG = KATALOG_WERSJI / ModelWycenyV4.wersja
KATALOG_CECH = Path(__file__).resolve().parents[2] / "features" / "wycena" / "cechy_llm"
# Wersja z current.yaml w chwili ustalenia reguły (przed v4). Stała, żeby ponowne uruchomienie po zmianie
# current.yaml na v4 nadal porównywało z tą samą wersją odniesienia.
WERSJA_ODNIESIENIA = "v1_liniowa"
REGULA = (
    "v4 trafia do current.yaml, jeśli MAPE jej P50 (bez odmów) na 300 operatach kontrolnych jest niższe niż MAPE "
    "wersji z current.yaml (v1_liniowa) na tych samych 300 lokalach"
)
N_BOOTSTRAP = 2000

SQL_OPERATY_KONTROLNE = "SELECT id_lokalu, id_operatu, data_wyceny, wartosc_pln FROM operaty WHERE typ = 'kontrolny'"


# --- dane ----------------------------------------------------------------------------------------------------------


def cechy(nazwa: str) -> pd.DataFrame:
    return cechy_do_modelu(pd.read_parquet(KATALOG_CECH / f"{nazwa}.parquet"))


def standard_ze_zdjec(nazwa: str) -> pd.DataFrame:
    return cechy(nazwa)[["id", "llm_standard"]].rename(columns={"llm_standard": "zdj_standard"})


def wczytaj_dane(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = wczytaj_transakcje_z_cechami(con)
    dop = con.execute("SELECT id_transakcji, id_oferty FROM radar_dopasowania").df()
    df = df.merge(dop, on="id_transakcji", how="left", validate="one_to_one")
    df = df.merge(cechy("opisy_ofert").rename(columns={"id": "id_oferty"}), on="id_oferty", how="left",
                  validate="many_to_one")  # fmt: skip
    df = df.merge(standard_ze_zdjec("zdjecia_ofert").rename(columns={"id": "id_oferty"}), on="id_oferty",
                  how="left", validate="many_to_one")  # fmt: skip
    df["z_dopasowaniem"] = df["id_oferty"].notna()

    op = con.execute(SQL_OPERATY_KONTROLNE).df()
    dom = wczytaj_lokale_domilo(con).merge(op, on="id_lokalu", how="inner", validate="one_to_one")
    dom = dom.merge(cechy("opisy_domilo").rename(columns={"id": "id_lokalu"}), on="id_lokalu", how="left",
                    validate="one_to_one")  # fmt: skip
    dom = dom.merge(standard_ze_zdjec("zdjecia_domilo").rename(columns={"id": "id_lokalu"}), on="id_lokalu",
                    how="left", validate="one_to_one")  # fmt: skip
    dom["cena_pln"] = dom["wartosc_pln"]
    if len(dom) != len(op):
        raise ValueError("Nie każdy operat kontrolny ma lokal z cechami")
    return df, dom.reset_index(drop=True)


def ze_zdjeciami(d: pd.DataFrame) -> pd.DataFrame:
    """llm_standard ze zdjęć tam, gdzie jest; inaczej z opisu."""
    return d.assign(llm_standard=d["zdj_standard"].where(d["zdj_standard"].notna(), d["llm_standard"]))


# --- metryki -------------------------------------------------------------------------------------------------------


def _punktowe(p50: np.ndarray, index) -> pd.DataFrame:
    return pd.DataFrame({"p10": np.nan, "p50": p50, "p90": np.nan, "odmowa": False}, index=index)


def _wiersz(model: str, zbior: str, m: dict, przedzial: bool) -> dict:
    return {
        "model": model,
        "zbior": zbior,
        "n": m["n"],
        "odmowy_proc": _f(m["odmowy_proc"], 1),
        "MAPE": _f(m["mape"], 2),
        "MdAPE": _f(m["mdape"], 2),
        "mediana_bledu": _f(m["mediana_bledu_proc"], 2),
        "MAE_pln": _f(m["mae"], 0),
        "pokrycie_80": _f(m["pokrycie"], 1) if przedzial else "—",
        "szerokosc": _f(m["mediana_szerokosci"], 1) if przedzial else "—",
    }


def predykcje(modele: dict, d: pd.DataFrame, zdjecia: bool) -> dict[str, pd.DataFrame]:
    v0, v1, v2, v3, v4 = (modele[k] for k in ("v0", "v1", "v2", "v3", "v4"))
    wyj = {
        "v0_mediana_dzielnicy (baseline)": _punktowe(v0.predict(d[list(KOLUMNY_CECH)]), d.index),
        "v1_liniowa": _punktowe(v1.predict(d[list(KOLUMNY_CECH)]), d.index),
        "v2_lgbm_geo (= P50 v3)": _punktowe(v2.predict(d), d.index),
        "v3_przedzialy bez odmów": v3.przedzial.predict_interval(d).assign(odmowa=False),
        "v3_przedzialy": v3.predict_interval(d),
        "v4_llm_cechy bez odmów": v4.przedzial.predict_interval(d).assign(odmowa=False),
        "v4_llm_cechy": v4.predict_interval(d),
    }
    if zdjecia:
        dz = ze_zdjeciami(d)
        wyj["v4 + standard ze zdjęć, bez odmów"] = v4.przedzial.predict_interval(dz).assign(odmowa=False)
        wyj["v4 + standard ze zdjęć"] = v4.predict_interval(dz)
        # Ablacja: v4 bez cech LLM na wejściu (NaN, jak transakcja bez opisu): ile wnoszą odczyty LLM.
        bez_llm = d.assign(**{k: np.nan for k in KOLUMNY_LLM})
        wyj["v4 z cechami LLM = brak (ablacja), bez odmów"] = v4.przedzial.predict_interval(bez_llm).assign(
            odmowa=False
        )
    return wyj


def bootstrap_roznicy_mape(y, a, b, n: int = N_BOOTSTRAP, ziarno: int = 42) -> tuple[float, float, float]:
    """MAPE(a) − MAPE(b) w punktach procentowych i 95% przedział z bootstrapu par (te same lokale)."""
    y, a, b = (np.asarray(v, dtype=float) for v in (y, a, b))
    ea, eb = np.abs(a / y - 1), np.abs(b / y - 1)
    rng = np.random.default_rng(ziarno)
    idx = rng.integers(0, len(y), size=(n, len(y)))
    roz = 100 * (ea[idx].mean(axis=1) - eb[idx].mean(axis=1))
    return float(100 * (ea.mean() - eb.mean())), float(np.quantile(roz, 0.025)), float(np.quantile(roz, 0.975))


# --- opis cech -----------------------------------------------------------------------------------------------------


def pokrycie_cech(zbiory: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "zbior": nazwa,
                "lokale": len(d),
                "z_cechami_LLM_z_opisu": int(d["llm_ekspozycja"].notna().sum()),
                "standard_z_opisu": int(d["llm_standard"].notna().sum()),
                "standard_ze_zdjec": int(d["zdj_standard"].notna().sum()),
            }
            for nazwa, d in zbiory.items()
        ]
    )


def rozklady(zbiory: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Odsetek wartości każdej cechy LLM (wśród lokali z odczytem opisu) w kolejnych zbiorach."""
    wiersze = []
    for kol in ("llm_standard", "zdj_standard", *LLM_KATEGORII):
        for nazwa, d in zbiory.items():
            ma = d["llm_ekspozycja"].notna() if kol != "zdj_standard" else d["zdj_standard"].notna()
            if not ma.any():
                continue
            v = d.loc[ma, kol].astype(object).where(d.loc[ma, kol].notna(), "null")
            for wart, ile in v.value_counts().sort_index(key=lambda s: s.astype(str)).items():
                wiersze.append({"cecha": kol, "zbior": nazwa, "wartosc": str(wart), "proc": 100 * ile / ma.sum()})
    t = pd.DataFrame(wiersze).pivot_table(index=["cecha", "wartosc"], columns="zbior", values="proc", fill_value=0)
    t = t[[k for k in zbiory if k in t.columns]].reset_index()
    for k in t.columns[2:]:
        t[k] = t[k].map(lambda x: _f(x, 1))
    return t


def zgodnosc_standardu(nazwa: str, d: pd.DataFrame) -> dict:
    oba = d[d["llm_standard"].notna() & d["zdj_standard"].notna()]
    roz = oba["zdj_standard"] - oba["llm_standard"]
    return {
        "zbior": nazwa,
        "ze_zdjeciami": int(d["zdj_standard"].notna().sum()),
        "standard_w_obu": len(oba),
        "zgodne_proc": _f(100 * (roz == 0).mean(), 1),
        "roznica_do_1_proc": _f(100 * (roz.abs() <= 1).mean(), 1),
        "zdjecia_wyzej_proc": _f(100 * (roz > 0).mean(), 1),
        "zdjecia_nizej_proc": _f(100 * (roz < 0).mean(), 1),
        "srednia_opis": _f(oba["llm_standard"].mean(), 2),
        "srednia_zdjecia": _f(oba["zdj_standard"].mean(), 2),
    }


SQL_PMS = (
    "SELECT id_lokalu AS id, pakiet_wykonczenia, ekspozycja AS ekspozycja_pms, balkon AS balkon_pms FROM pms_lokale"
)


def porownanie_z_pms(con) -> dict[str, pd.DataFrame]:
    """Odczyty LLM z opisów i zdjęć Domilo a kolumny pms_lokale (7 200 lokali; zdjęcia: 300)."""
    pms = con.execute(SQL_PMS).df()
    d = cechy("opisy_domilo").merge(pms, on="id", validate="one_to_one")
    z = d.merge(standard_ze_zdjec("zdjecia_domilo"), on="id", how="inner", validate="one_to_one")

    def tab(a: pd.Series, b: pd.Series) -> pd.DataFrame:
        t = pd.crosstab(a, b.astype(object).where(b.notna(), "null"), margins=True, margins_name="razem")
        return t.reset_index().rename(columns=str)

    return {
        "pakiet_wykonczenia × standard z opisu": tab(d["pakiet_wykonczenia"], d["llm_standard"]),
        "balkon (PMS) × balkon z opisu": tab(d["balkon_pms"], d["llm_balkon"]),
        "ekspozycja (PMS) × ekspozycja z opisu": tab(d["ekspozycja_pms"], d["llm_ekspozycja"]),
        "pakiet_wykonczenia × standard ze zdjęć": tab(z["pakiet_wykonczenia"], z["zdj_standard"]),
    }


def koszt_ekstrakcji() -> pd.DataFrame:
    wiersze = []
    for nazwa in ("opisy_ofert", "opisy_domilo", "zdjecia_ofert", "zdjecia_domilo"):
        w = pd.read_parquet(KATALOG_CECH / f"{nazwa}.parquet")
        ok = w[w["blad"].isna()]
        wiersze.append(
            {
                "zbior": nazwa,
                "rekordy": len(w),
                "bledy": int(w["blad"].notna().sum()),
                "tokeny_wejscia": int(ok["tokeny_wejscia"].sum()),
                "w_tym_cache_OpenAI": int(ok["tokeny_wejscia_z_cache"].sum()),
                "tokeny_wyjscia": int(ok["tokeny_wyjscia"].sum()),
                "wejscie_na_1000": _f(1000 * ok["tokeny_wejscia"].mean(), 0),
                "cache_OpenAI_na_1000": _f(1000 * ok["tokeny_wejscia_z_cache"].mean(), 0),
                "wyjscie_na_1000": _f(1000 * ok["tokeny_wyjscia"].mean(), 0),
            }
        )
    return pd.DataFrame(wiersze)


# --- główny przebieg -----------------------------------------------------------------------------------------------


def main() -> None:
    con = polacz()
    df, dom = wczytaj_dane(con)
    pms = porownanie_z_pms(con)
    con.close()
    tr, wal, te = (df[df["zbior"] == z].reset_index(drop=True) for z in ("trening", "walidacja", "test"))

    detektor = joblib.load(KATALOG_WERSJI / "v3_przedzialy" / "ood.joblib")
    v4 = ModelWycenyV4(detektor=detektor).fit(
        tr, tr["cena_pln"], wal, wal["cena_pln"], poczatek_odlozonej=POCZATEK_ODLOZONEJ
    )
    modele = {
        "v0": ModelWyceny.wczytaj(KATALOG_WERSJI / "v0_mediana_dzielnicy" / "model.joblib"),
        "v1": ModelWyceny.wczytaj(KATALOG_WERSJI / "v1_liniowa" / "model.joblib"),
        "v2": ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lgbm_geo" / "model.joblib"),
        "v3": ModelWyceny.wczytaj(KATALOG_WERSJI / "v3_przedzialy" / "model.joblib"),
        "v4": v4,
    }
    print(
        f"v4: drzewa P50 {v4.przedzial.punktowy.najlepsza_iteracja_}, P10/P90 {v4.przedzial.drzewa_}, "
        f"korekta CQR {v4.przedzial.korekta_:.4f} (v3: {modele['v3'].przedzial.korekta_:.4f}); "
        f"detektor = ood.joblib v3: {v4.detektor is detektor}\n"
    )

    zbiory = {
        "trening: dopasowania": tr[tr["z_dopasowaniem"]],
        "test: dopasowania": te[te["z_dopasowaniem"]],
        "test: dopasowania ze zdjęciami": te[te["zdj_standard"].notna()],
        "operaty kontrolne (lokale Domilo)": dom,
    }
    print(f"### 1. Pokrycie cech LLM\n\n{_md(pokrycie_cech(zbiory))}\n")
    print(f"### 2. Rozkład odczytów LLM (% lokali z odczytem)\n\n{_md(rozklady(zbiory))}\n")
    for tytul, t in pms.items():
        print(f"### 2b. Domilo: {tytul}\n\n{_md(t)}\n")
    zg = [
        zgodnosc_standardu(n, zbiory[n])
        for n in ("test: dopasowania ze zdjęciami", "operaty kontrolne (lokale Domilo)")
    ]
    print(f"### 3. Standard z opisu a standard ze zdjęć\n\n{_md(pd.DataFrame(zg))}\n")

    oceniane = {
        "test: dopasowania": (te[te["z_dopasowaniem"]], False),
        "test: dopasowania ze zdjęciami": (te[te["zdj_standard"].notna()], True),
        "test: bez dopasowania": (te[~te["z_dopasowaniem"]], False),
        "test: wszystkie": (te, False),
        "operaty kontrolne": (dom, True),
    }
    wiersze, wyniki, p50 = [], {}, {}
    for zbior, (d, zdj) in oceniane.items():
        y = d["cena_pln"].to_numpy(dtype=float)
        for model, p in predykcje(modele, d, zdj).items():
            m = metryki_v3(y, p)
            wyniki.setdefault(zbior, {})[model] = m
            wiersze.append(_wiersz(model, zbior, m, przedzial=bool(p["p10"].notna().any())))
            p50[(zbior, model)] = p["p50"].to_numpy()
    print(f"### 4. Metryki (MAPE, pokrycie i szerokość na przyjętych)\n\n{_md(pd.DataFrame(wiersze))}\n")

    # 5. Różnice z bootstrapem par (te same lokale), P50 bez odmów.
    current = WERSJA_ODNIESIENIA
    nazwa_current = {"v1_liniowa": "v1_liniowa", "v3_przedzialy": "v3_przedzialy bez odmów"}.get(current, current)
    pary = [
        ("test: dopasowania", "v4_llm_cechy bez odmów", "v2_lgbm_geo (= P50 v3)"),
        ("test: wszystkie", "v4_llm_cechy bez odmów", "v2_lgbm_geo (= P50 v3)"),
        ("operaty kontrolne", "v4_llm_cechy bez odmów", "v2_lgbm_geo (= P50 v3)"),
        ("operaty kontrolne", "v4_llm_cechy bez odmów", nazwa_current),
        ("operaty kontrolne", "v4 + standard ze zdjęć, bez odmów", "v4_llm_cechy bez odmów"),
        ("test: dopasowania ze zdjęciami", "v4 + standard ze zdjęć, bez odmów", "v4_llm_cechy bez odmów"),
        ("operaty kontrolne", "v4_llm_cechy bez odmów", "v4 z cechami LLM = brak (ablacja), bez odmów"),
    ]
    boot = []
    for zbior, a, b in pary:
        y = oceniane[zbior][0]["cena_pln"].to_numpy(dtype=float)
        r, lo, hi = bootstrap_roznicy_mape(y, p50[(zbior, a)], p50[(zbior, b)])
        boot.append({"zbior": zbior, "model": a, "wzgledem": b, "roznica_MAPE_pp": _f(r, 2),
                     "CI95_od": _f(lo, 2), "CI95_do": _f(hi, 2)})  # fmt: skip
    print(f"### 5. Różnica MAPE (pkt proc.), bootstrap par, {N_BOOTSTRAP} prób\n\n{_md(pd.DataFrame(boot))}\n")

    # 6. Ważność cech v4 (P50).
    w = v4.przedzial.punktowy.waznosc_cech()
    w = w.assign(udzial_proc=w["udzial_proc"].map(lambda x: _f(x, 2))).drop(columns="zysk")
    print(f"### 6. Ważność cech v4 (P50, gain)\n\n{_md(w)}\n")

    # 7. Koszt ekstrakcji (tokeny).
    koszt = koszt_ekstrakcji()
    print(f"### 7. Tokeny ekstrakcji\n\n{_md(koszt)}\n")

    # 8. Decyzja według reguły.
    mape_v4 = wyniki["operaty kontrolne"]["v4_llm_cechy bez odmów"]["mape"]
    mape_cur = wyniki["operaty kontrolne"][nazwa_current]["mape"]
    wygrywa = mape_v4 < mape_cur
    print(
        f"### 8. Decyzja\n\nReguła: {REGULA}.\nOperaty kontrolne: v4 (P50) MAPE {_f(mape_v4, 2)}%, "
        f"{current} MAPE {_f(mape_cur, 2)}% -> {'v4 WYGRYWA' if wygrywa else 'v4 NIE wygrywa'}\n"
    )

    v4.zapisz(KATALOG / "model.joblib")
    opis = {
        "wersja": v4.wersja,
        "policzono": date.today().isoformat(),
        "skladniki": {
            "p50_p10_p90": "LightGBM (cechy v2_lgbm_geo + cechy LLM: "
            + ", ".join(KOLUMNY_LLM)
            + ") + CQR na walidacji",
            "odmowa": "versions/v3_przedzialy/ood.joblib (bez ponownego uczenia)",
            "cechy_llm": "features/wycena/cechy_llm/opisy_ofert.parquet, opisy_domilo.parquet (prompt cechy_lokalu_v1)",
        },
        "drzewa_p50": v4.przedzial.punktowy.najlepsza_iteracja_,
        "drzewa_p10_p90": v4.przedzial.drzewa_,
        "korekta_cqr": v4.przedzial.korekta_,
        "metryki": wyniki,
        "bootstrap": boot,
        "regula": REGULA,
        "decyzja": {"current": current, "mape_current": mape_cur, "mape_v4": mape_v4, "v4_wygrywa": wygrywa},
    }
    (KATALOG / "metryki.json").write_text(json.dumps(opis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Zapisano versions/v4_llm_cechy/model.joblib i metryki.json")


if __name__ == "__main__":
    main()
