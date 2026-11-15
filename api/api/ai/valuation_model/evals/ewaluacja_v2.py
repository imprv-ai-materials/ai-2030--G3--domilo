"""Ewaluacja v2 (LightGBM na cechach v1) na podziale czasowym RCN (docs/b3_wycena_v2_geo.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2                 # trening + walidacja
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2 --otworz-test   # jednorazowo: także test

v2 uczy się wyłącznie na zbiorze `trening`; zbiór `walidacja` (akty 2025-07 – 2025-12) służy do wczesnego
zatrzymania (liczba drzew), więc metryki walidacyjne v2 są lekko optymistyczne. Zbiór `test` otwieramy raz:
skrypt odmawia ponownego liczenia testu, jeśli versions/v2_lightgbm/metryki.json już ma wynik testu.
Bez `--otworz-test` model i metryki nie są zapisywane (to przebieg roboczy na walidacji).
Porównanie z v1 (versions/v1_liniowa/model.joblib) na tych samych transakcjach. Run trafia do eksperymentu MLflow
`wycena` (wyłączenie: --bez-mlflow).
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.wycena.podzial import SCIEZKA_PODZIALU, ZBIORY
from api.ai.features.wycena.zbior import wczytaj_transakcje
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_WERSJI, OPIS_PODZIALU, _md, _wiersz
from api.ai.valuation_model.evals.metryki import metryki
from api.ai.valuation_model.versions.v2_lightgbm.model import ModelLightGBM

KATALOG_V2 = KATALOG_WERSJI / ModelLightGBM.wersja
RAPORT = "docs/b3_wycena_v2_geo.md"


def _test_juz_otwarty() -> bool:
    plik = KATALOG_V2 / "metryki.json"
    return plik.exists() and "test" in json.loads(plik.read_text(encoding="utf-8"))["metryki"]


def main(otworz_test: bool = False, mlflow_wlaczony: bool = True) -> None:
    if otworz_test and _test_juz_otwarty():
        raise SystemExit(f"Zbiór testowy dla {ModelLightGBM.wersja} był już otwarty ({KATALOG_V2 / 'metryki.json'}).")
    con = polacz()
    df = wczytaj_transakcje(con)
    oceniane = ZBIORY if otworz_test else ("trening", "walidacja")
    zbiory = {z: df[df["zbior"] == z] for z in oceniane}
    tr, wal = zbiory["trening"], zbiory["walidacja"]
    cechy = list(KOLUMNY_CECH)

    v2 = ModelLightGBM().fit(tr[cechy], tr["cena_pln"], wal[cechy], wal["cena_pln"])
    v1 = ModelWyceny.wczytaj(KATALOG_WERSJI / "v1_liniowa" / "model.joblib")
    print(
        f"### v2: wczesne zatrzymanie\n\nnajlepsza iteracja: {v2.najlepsza_iteracja_} (z max {v2.max_drzew}, "
        f"stop po {v2.stopping_rounds} rundach bez poprawy), l2 ln(ceny) na walidacji: {v2.l2_walidacja_:.5f}\n"
    )

    wiersze, wiersze_grup, wyniki_v2 = [], [], {}
    for zbior, d in zbiory.items():
        for model in (v1, v2):
            pred = model.predict(d[cechy])
            m = metryki(d["cena_pln"], pred)
            wiersze.append(_wiersz(model.wersja, zbior, "wszystkie", m))
            if model is v2:
                wyniki_v2[zbior] = m
            if zbior in ("walidacja", "test"):
                dd = d.assign(pred=pred)
                for kol in ("miasto", "rynek"):
                    for wartosc, g in dd.groupby(kol):
                        wiersze_grup.append(
                            _wiersz(model.wersja, zbior, f"{kol}={wartosc}", metryki(g["cena_pln"], g["pred"]))
                        )
    print(f"### Metryki: wszystkie transakcje\n\n{_md(pd.DataFrame(wiersze))}\n")
    print(f"### Metryki: miasta i rynek\n\n{_md(pd.DataFrame(wiersze_grup))}\n")

    nieznane = []
    for zbior, d in zbiory.items():
        klucz = d["miasto"].astype(str) + " | " + d["dzielnica"].astype(str)
        nieznane.append(
            {
                "zbior": zbior,
                "transakcje": int(len(d)),
                "dzielnica_nieznana_w_treningu": int((~klucz.isin(v2.kategorie_["dzielnica"])).sum()),
            }
        )
    print(f"### v2: dzielnice nieznane w treningu\n\n{_md(pd.DataFrame(nieznane))}\n")
    waz = v2.waznosc_cech().assign(udzial_proc=lambda x: x["udzial_proc"].round(1))[["cecha", "udzial_proc"]]
    print(f"### v2: ważność cech (gain, % sumy)\n\n{_md(waz)}\n")

    if not otworz_test:
        print("Przebieg roboczy (bez testu): model i metryki nie zostały zapisane.")
        return

    v2.zapisz(KATALOG_V2 / "model.joblib")
    parametry = {
        **v2.parametry,
        "max_drzew": v2.max_drzew,
        "stopping_rounds": v2.stopping_rounds,
        "najlepsza_iteracja": v2.najlepsza_iteracja_,
    }
    (KATALOG_V2 / "metryki.json").write_text(
        json.dumps(
            {
                "wersja": v2.wersja,
                "uczony_na": "trening (rcn_transakcje, data_aktu 2023-01-01 – 2025-06-30, podzial.sql)",
                "wczesne_zatrzymanie_na": "walidacja (data_aktu 2025-07-01 – 2025-12-31), l2 na ln(ceny)",
                "transakcje_treningowe": int(len(tr)),
                "test_otwarty": date.today().isoformat(),
                "parametry": parametry,
                "metryki": wyniki_v2,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        run_id = zapisz_run(
            v2.wersja,
            parametry={"wersja": v2.wersja, **parametry},
            metryki={f"{z}_{k}": v for z, m in wyniki_v2.items() for k, v in m.items()},
            tagi={
                "podzial": "czasowy (podzial.sql, data_aktu)",
                "podzial_opis": OPIS_PODZIALU,
                "target": "rcn_transakcje.cena_pln (cena transakcyjna), model na ln(ceny)",
                "wczesne_zatrzymanie": "walidacja",
                "raport": RAPORT,
            },
            artefakty=[
                KATALOG_V2 / "model.joblib",
                KATALOG_V2 / "metryki.json",
                KATALOG_V2 / "model.py",
                SCIEZKA_PODZIALU,
                Path(__file__),
            ],
        )
        print(f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run {v2.wersja} = {run_id}")


if __name__ == "__main__":
    argumenty = sys.argv[1:]
    main(otworz_test="--otworz-test" in argumenty, mlflow_wlaczony="--bez-mlflow" not in argumenty)
