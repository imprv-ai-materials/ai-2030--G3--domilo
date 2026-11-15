"""Ewaluacja v2_lgbm_geo (LightGBM + otoczenie + sąsiedztwo) i ablacja rodzin cech (docs/b4_wycena_v2_lgbm_geo.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/:
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2_geo                 # trening + walidacja
    poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2_geo --otworz-test   # jednorazowo: także test

Każdy wariant uczy się na `trening`, a `walidacja` wybiera liczbę drzew (wczesne zatrzymanie). Na walidacji
wybieramy też, czy geohash6 wchodzi jako kategoria (wariant pełny z geohash6 albo bez, niższy MAPE). Ablacje
usuwają rodzinę cech z wybranego wariantu pełnego. Test liczymy jednym przebiegiem dla wszystkich wariantów;
skrypt odmawia ponownego otwarcia, jeśli versions/v2_lgbm_geo/metryki.json ma już wynik testu.
Bez `--otworz-test` nic nie jest zapisywane.
"""

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.wycena.geo import SCIEZKA_GEO
from api.ai.features.wycena.podzial import SCIEZKA_PODZIALU, ZBIORY
from api.ai.features.wycena.sasiedztwo import SCIEZKA_SASIEDZTWA
from api.ai.features.wycena.zbior import (
    KATEGORIA_GEOHASH,
    RODZINA_GEO_BEZ_POI,
    RODZINA_POI,
    RODZINA_SASIEDZTWO,
    wczytaj_transakcje_z_cechami,
)
from api.ai.valuation_model.base import KOLUMNY_CECH, ModelWyceny
from api.ai.valuation_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_WERSJI, OPIS_PODZIALU, _md, _wiersz
from api.ai.valuation_model.evals.metryki import metryki
from api.ai.valuation_model.versions.v2_lgbm_geo.model import ModelLightGBMGeo

KATALOG = KATALOG_WERSJI / ModelLightGBMGeo.wersja
RAPORT = "docs/b4_wycena_v2_lgbm_geo.md"
PELNY = RODZINA_POI + RODZINA_GEO_BEZ_POI + RODZINA_SASIEDZTWO


@dataclass
class Wariant:
    nazwa: str
    opis: str
    cechy_liczbowe: tuple[str, ...]
    cechy_kategorii: tuple[str, ...] = ()
    sasiedzi_wg_publikacji: bool = False


def _bez(cechy: tuple[str, ...], usun: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(k for k in cechy if k not in usun)


def _ucz(w: Wariant, dane: dict[bool, dict[str, pd.DataFrame]]) -> ModelLightGBMGeo:
    zb = dane[w.sasiedzi_wg_publikacji]
    kol = list(KOLUMNY_CECH) + list(w.cechy_liczbowe) + list(w.cechy_kategorii)
    tr, wal = zb["trening"], zb["walidacja"]
    model = ModelLightGBMGeo(cechy_liczbowe=w.cechy_liczbowe, cechy_kategorii=w.cechy_kategorii)
    return model.fit(tr[kol], tr["cena_pln"], wal[kol], wal["cena_pln"])


def _test_juz_otwarty() -> bool:
    plik = KATALOG / "metryki.json"
    return plik.exists() and "test" in json.loads(plik.read_text(encoding="utf-8"))["metryki"]


def main(otworz_test: bool = False, mlflow_wlaczony: bool = True) -> None:
    if otworz_test and _test_juz_otwarty():
        raise SystemExit(f"Zbiór testowy dla {ModelLightGBMGeo.wersja} był już otwarty ({KATALOG / 'metryki.json'}).")
    con = polacz()
    oceniane = ZBIORY if otworz_test else ("trening", "walidacja")
    dane = {}
    for wg_pub in (False, True):
        df = wczytaj_transakcje_z_cechami(con, sasiedzi_wg_publikacji=wg_pub)
        dane[wg_pub] = {z: df[df["zbior"] == z] for z in oceniane}
    zb = dane[False]

    # 0. Pokrycie cech sąsiedztwa.
    pokrycie = []
    for wg_pub, opis in ((False, "wg daty aktu"), (True, "wg daty publikacji")):
        for z, d in dane[wg_pub].items():
            pokrycie.append(
                {
                    "sasiedzi": opis,
                    "zbior": z,
                    "transakcje": int(len(d)),
                    "bez_sasiadow": int((d["sasiedzi_liczba"] == 0).sum()),
                    "mniej_niz_20": int((d["sasiedzi_liczba"] < 20).sum()),
                }
            )
    print(f"### Pokrycie cech sąsiedztwa\n\n{_md(pd.DataFrame(pokrycie))}\n")

    # 1. Wybór geohash6 na walidacji.
    kandydaci = [
        Wariant("pelny", "wszystkie rodziny, bez geohash6", PELNY),
        Wariant("pelny_geohash6", "wszystkie rodziny + geohash6 (kategoria)", PELNY, (KATEGORIA_GEOHASH,)),
    ]
    wybor, modele = [], {}
    for w in kandydaci:
        m = _ucz(w, dane)
        modele[w.nazwa] = m
        wal = zb["walidacja"]
        wybor.append(
            {
                **_wiersz(w.nazwa, "walidacja", w.opis, metryki(wal["cena_pln"], m.predict(wal))),
                "drzewa": m.najlepsza_iteracja_,
            }
        )
    wybor = pd.DataFrame(wybor)
    nazwa_pelnego = str(wybor.loc[wybor["MAPE_proc"].idxmin(), "wersja"])
    pelny = next(w for w in kandydaci if w.nazwa == nazwa_pelnego)
    print(f"### Wybór geohash6 (walidacja)\n\n{_md(wybor)}\n\nWybrano: {nazwa_pelnego}\n")

    # 2. Ablacje względem wybranego wariantu pełnego.
    geo_wszystko = RODZINA_POI + RODZINA_GEO_BEZ_POI
    warianty = [
        pelny,
        Wariant(
            "bez_geo",
            "bez cech z geo.sql (POI, centrum, dzielnica GUS, geohash6)",
            _bez(pelny.cechy_liczbowe, geo_wszystko),
        ),
        Wariant(
            "bez_sasiedztwa",
            "bez mediany i liczby sąsiadów",
            _bez(pelny.cechy_liczbowe, RODZINA_SASIEDZTWO),
            pelny.cechy_kategorii,
        ),
        Wariant(
            "bez_poi",
            "bez odległości do POI i flag (zostaje centrum, GUS, geohash6)",
            _bez(pelny.cechy_liczbowe, RODZINA_POI),
            pelny.cechy_kategorii,
        ),
        Wariant(
            "sasiedzi_wg_publikacji",
            "jak pełny, sąsiedzi tylko opublikowani przed dniem aktu",
            pelny.cechy_liczbowe,
            pelny.cechy_kategorii,
            True,
        ),
    ]
    referencje = [
        ModelWyceny.wczytaj(KATALOG_WERSJI / "v1_liniowa" / "model.joblib"),
        ModelWyceny.wczytaj(KATALOG_WERSJI / "v2_lightgbm" / "model.joblib"),
    ]
    wyniki: dict[str, dict] = {}
    wiersze = []
    for model in referencje:
        for z, d in zb.items():
            wiersze.append(
                {
                    **_wiersz(
                        model.wersja, z, "referencja", metryki(d["cena_pln"], model.predict(d[list(KOLUMNY_CECH)]))
                    ),
                    "drzewa": None,
                }
            )
    for w in warianty:
        m = modele.get(w.nazwa) or _ucz(w, dane)
        modele[w.nazwa] = m
        wyniki[w.nazwa] = {}
        for z, d in dane[w.sasiedzi_wg_publikacji].items():
            wyniki[w.nazwa][z] = metryki(d["cena_pln"], m.predict(d))
            wiersze.append({**_wiersz(w.nazwa, z, w.opis, wyniki[w.nazwa][z]), "drzewa": m.najlepsza_iteracja_})
    print(f"### Ablacja: wszystkie zbiory\n\n{_md(pd.DataFrame(wiersze))}\n")

    glowny = modele[pelny.nazwa]
    grupy = []
    for z in oceniane[1:]:
        d = zb[z]
        for model, pred in ((referencje[0], referencje[0].predict(d[list(KOLUMNY_CECH)])), (glowny, glowny.predict(d))):
            dd = d.assign(pred=pred)
            for kol in ("miasto", "rynek"):
                for wartosc, g in dd.groupby(kol):
                    grupy.append(_wiersz(model.wersja, z, f"{kol}={wartosc}", metryki(g["cena_pln"], g["pred"])))
    print(f"### Główny wariant ({pelny.nazwa}) i v1: miasta i rynek\n\n{_md(pd.DataFrame(grupy))}\n")
    waz = glowny.waznosc_cech().assign(udzial_proc=lambda x: x["udzial_proc"].round(1))[["cecha", "udzial_proc"]]
    print(f"### Ważność cech wariantu głównego (gain, % sumy)\n\n{_md(waz)}\n")

    if not otworz_test:
        print("Przebieg roboczy (bez testu): modele i metryki nie zostały zapisane.")
        return

    KATALOG.mkdir(parents=True, exist_ok=True)
    glowny.zapisz(KATALOG / "model.joblib")
    parametry = {
        **glowny.parametry,
        "max_drzew": glowny.max_drzew,
        "stopping_rounds": glowny.stopping_rounds,
        "najlepsza_iteracja": glowny.najlepsza_iteracja_,
        "cechy_liczbowe": list(glowny.cechy_liczbowe),
        "cechy_kategorii": list(glowny.cechy_kategorii),
        "wariant": pelny.nazwa,
    }
    wspolne = {
        "uczony_na": "trening (rcn_transakcje, data_aktu 2023-01-01 – 2025-06-30, podzial.sql)",
        "wczesne_zatrzymanie_na": "walidacja (data_aktu 2025-07-01 – 2025-12-31), l2 na ln(ceny)",
        "sasiedztwo": "sasiedztwo.sql: 20 najbliższych z 12 mies. przed dniem aktu; trening out-of-fold (5 foldów)",
        "test_otwarty": date.today().isoformat(),
    }
    (KATALOG / "metryki.json").write_text(
        json.dumps(
            {"wersja": glowny.wersja, **wspolne, "parametry": parametry, "metryki": wyniki[pelny.nazwa]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ablacja = {
        w.nazwa: {
            "opis": w.opis,
            "cechy_liczbowe": list(w.cechy_liczbowe),
            "cechy_kategorii": list(w.cechy_kategorii),
            "sasiedzi_wg_publikacji": w.sasiedzi_wg_publikacji,
            "najlepsza_iteracja": modele[w.nazwa].najlepsza_iteracja_,
            "metryki": wyniki[w.nazwa],
        }
        for w in warianty
    }
    (KATALOG / "ablacja.json").write_text(
        json.dumps(
            {**wspolne, "wybor_geohash6_walidacja": wybor.to_dict(orient="records"), "warianty": ablacja},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        for w in warianty:
            m = modele[w.nazwa]
            nazwa_runu = glowny.wersja if w is pelny else f"{glowny.wersja}/{w.nazwa}"
            run_id = zapisz_run(
                nazwa_runu,
                parametry={
                    "wersja": glowny.wersja,
                    "wariant": w.nazwa,
                    "najlepsza_iteracja": m.najlepsza_iteracja_,
                    "cechy_liczbowe": ",".join(w.cechy_liczbowe),
                    "cechy_kategorii": ",".join(w.cechy_kategorii),
                    "sasiedzi_wg_publikacji": w.sasiedzi_wg_publikacji,
                },
                metryki={f"{z}_{k}": v for z, mm in wyniki[w.nazwa].items() for k, v in mm.items()},
                tagi={
                    "podzial": "czasowy (podzial.sql, data_aktu)",
                    "podzial_opis": OPIS_PODZIALU,
                    "target": "rcn_transakcje.cena_pln (cena transakcyjna), model na ln(ceny)",
                    "ablacja": "tak" if w is not pelny else "nie (wariant główny)",
                    "raport": RAPORT,
                },
                artefakty=(
                    [KATALOG / "model.joblib", KATALOG / "metryki.json", KATALOG / "ablacja.json", KATALOG / "model.py"]
                    if w is pelny
                    else []
                )
                + [SCIEZKA_PODZIALU, SCIEZKA_GEO, SCIEZKA_SASIEDZTWA, Path(__file__)],
            )
            print(f"MLflow: run {nazwa_runu} = {run_id}")


if __name__ == "__main__":
    argumenty = sys.argv[1:]
    main(otworz_test="--otworz-test" in argumenty, mlflow_wlaczony="--bez-mlflow" not in argumenty)
