"""Ewaluacja v0 (baseline) i v1 (regresja liniowa) na podziale czasowym RCN (docs/b2_wycena_v0_v1.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`):
    cd api && poetry run python -m api.ai.valuation_model.evals.ewaluacja
Oba modele uczą się wyłącznie na zbiorze `trening`. Postać metrażu w v1 (ln albo m²) wybieramy na `walidacja`;
`test` służy tylko do raportu. Zapisuje versions/<wersja>/model.joblib i versions/<wersja>/metryki.json oraz
wypisuje tabele Markdown.
"""

import json
from pathlib import Path

import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.podzial import ZBIORY
from api.ai.features.wycena.zbior import wczytaj_transakcje
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.metryki import metryki
from api.ai.valuation_model.versions.v0_mediana_dzielnicy.model import ModelMedianaDzielnicy
from api.ai.valuation_model.versions.v1_liniowa.model import ModelLiniowy

KATALOG_WERSJI = Path(__file__).resolve().parents[1] / "versions"


def _md(df: pd.DataFrame) -> str:
    def komorka(x):
        if isinstance(x, float):
            return f"{x:,.1f}".replace(",", " ").replace(".", ",")
        if isinstance(x, int):
            return f"{x:,}".replace(",", " ")
        return str(x)

    linie = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    linie += ["| " + " | ".join(komorka(x) for x in w) + " |" for w in df.itertuples(index=False)]
    return "\n".join(linie)


def _wiersz(wersja: str, zbior: str, grupa: str, m: dict) -> dict:
    return {
        "wersja": wersja,
        "zbior": zbior,
        "grupa": grupa,
        "n": m["n"],
        "MAE_pln": round(m["mae"]),
        "RMSE_pln": round(m["rmse"]),
        "MAPE_proc": round(m["mape"], 2),
        "MdAPE_proc": round(m["mdape"], 2),
        "mediana_bledu_proc": round(m["mediana_bledu_proc"], 2),
    }


def main() -> None:
    con = polacz()
    df = wczytaj_transakcje(con)
    zbiory = {z: df[df["zbior"] == z] for z in ZBIORY}
    tr = zbiory["trening"]
    X_tr, y_tr = tr[list(KOLUMNY_CECH)], tr["cena_pln"]

    # 1. Wybór postaci metrażu w v1 na zbiorze walidacyjnym.
    wybor = []
    for metraz_log in (True, False):
        m = ModelLiniowy(metraz_log=metraz_log).fit(X_tr, y_tr)
        wal = zbiory["walidacja"]
        wynik = metryki(wal["cena_pln"], m.predict(wal[list(KOLUMNY_CECH)]))
        wybor.append(_wiersz("v1_liniowa", "walidacja", "ln(metraż)" if metraz_log else "metraż [m²]", wynik))
    wybor = pd.DataFrame(wybor)
    metraz_log = bool(wybor.loc[wybor["MAPE_proc"].idxmin(), "grupa"] == "ln(metraż)")
    print(f"### Wybór postaci metrażu w v1 (walidacja)\n\n{_md(wybor)}\n\nWybrano metraz_log={metraz_log}\n")

    # 2. Modele końcowe na zbiorze treningowym.
    modele: list[ModelWyceny] = [
        ModelMedianaDzielnicy().fit(X_tr, y_tr),
        ModelLiniowy(metraz_log=metraz_log).fit(X_tr, y_tr),
    ]

    wiersze, wiersze_grup = [], []
    for model in modele:
        wyniki_wersji = {}
        for zbior, d in zbiory.items():
            pred = model.predict(d[list(KOLUMNY_CECH)])
            wyniki_wersji[zbior] = metryki(d["cena_pln"], pred)
            wiersze.append(_wiersz(model.wersja, zbior, "wszystkie", wyniki_wersji[zbior]))
            if zbior == "test":
                d = d.assign(pred=pred)
                for kol in ("miasto", "rynek"):
                    for wartosc, g in d.groupby(kol):
                        wiersze_grup.append(
                            _wiersz(model.wersja, zbior, f"{kol}={wartosc}", metryki(g["cena_pln"], g["pred"]))
                        )
        katalog = KATALOG_WERSJI / model.wersja
        model.zapisz(katalog / "model.joblib")
        parametry = (
            {"metraz_log": model.metraz_log, "min_transakcji_dzielnicy": model.min_transakcji_dzielnicy}
            if isinstance(model, ModelLiniowy)
            else {}
        )
        (katalog / "metryki.json").write_text(
            json.dumps(
                {
                    "wersja": model.wersja,
                    "uczony_na": "trening (rcn_transakcje, data_aktu 2023-01-01 – 2025-06-30, podzial.sql)",
                    "transakcje_treningowe": int(len(tr)),
                    "parametry": parametry,
                    "metryki": wyniki_wersji,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(f"### Metryki: wszystkie transakcje\n\n{_md(pd.DataFrame(wiersze))}\n")
    print(f"### Metryki na teście: miasta i rynek\n\n{_md(pd.DataFrame(wiersze_grup))}\n")

    # 3. Opis v1: dzielnice połączone, kategorie zastępcze na walidacji i teście, współczynniki.
    v1 = modele[1]
    pol = pd.DataFrame(
        [
            {"miasto": m, "dzielnica": d, "transakcje_trening": n, "kategoria_w_modelu": f"{m} | reszta miasta"}
            for (m, d), n in v1.dzielnice_polaczone_.items()
        ]
    )
    print(f"### v1: dzielnice połączone w „resztę miasta”\n\n{_md(pol)}\n")
    print(f"Kategorie dzielnic w v1: {len(v1.kategorie_dzielnic_)}\n")
    zast = []
    for zbior, d in zbiory.items():
        dz = v1.explain(d[list(KOLUMNY_CECH)])["dzielnica_w_modelu"]
        zast.append(
            {
                "zbior": zbior,
                "transakcje": int(len(d)),
                "reszta_miasta": int(dz.str.endswith("reszta miasta").sum()),
                "srednia_miasta": int(dz.str.endswith("średnia miasta").sum()),
            }
        )
    print(f"### v1: transakcje wyceniane przez kategorię zastępczą\n\n{_md(pd.DataFrame(zast))}\n")
    wsp = v1.wspolczynniki_
    nie_dzielnice = wsp[~wsp.index.str.startswith("dzielnica=")]
    tab = pd.DataFrame(
        {"cecha": nie_dzielnice.index, "wspolczynnik_ln": [f"{x:.4f}".replace(".", ",") for x in nie_dzielnice]}
    )
    print(f"### v1: współczynniki (poza dzielnicami)\n\n{_md(tab)}\n")


if __name__ == "__main__":
    main()
