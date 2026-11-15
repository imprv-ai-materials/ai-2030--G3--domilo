"""Stabilność odpowiedzi LLM: ten sam prompt na tych samych opisach, kilka przebiegów (docs/llm_cechy_lokalu_v1.md).

Uruchomienie (wymaga domilo.duckdb: `pypyr baza` i klucza w środowisku):
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.llm.evals.stabilnosc_cechy_lokalu

Losuje `N_OPISOW` opisów z `radar_oferty` (ziarno `ZIARNO`) i wysyła każdy `N_PRZEBIEGOW` razy, za każdym razem
z pominięciem cache (inaczej przebiegi 2–5 byłyby kopią pierwszego). Odpowiedzi z przebiegu 1 trafiają do
ai/llm/cache/. Wszystkie odpowiedzi zapisuje w evals/wyniki/stabilnosc_<wersja>.parquet.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.llm_client import KlientLLM
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.cechy_lokalu import CechyLokalu

NAZWA_PROMPTU = "cechy_lokalu_v1"
N_OPISOW = 200
N_PRZEBIEGOW = 5
ZIARNO = 42
WATKI = 8
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")
POLA = list(CechyLokalu.model_fields)


def losuj_opisy(con: duckdb.DuckDBPyConnection, n: int = N_OPISOW, ziarno: int = ZIARNO) -> pd.DataFrame:
    """n różnych ofert (id_oferty, opis), losowanie bez zwracania, powtarzalne dla tego samego ziarna."""
    oferty = con.execute("SELECT id_oferty, opis FROM radar_oferty ORDER BY id_oferty").df()
    wybrane = np.random.default_rng(ziarno).choice(len(oferty), size=n, replace=False)
    return oferty.iloc[wybrane].reset_index(drop=True)


def _zgodnosc(wartosci: list[list]) -> dict:
    identyczne = sum(all(w == p[0] for w in p) for p in wartosci)
    return {"identyczne": identyczne, "opisow": len(wartosci), "odsetek": identyczne / len(wartosci)}


def zgodnosc_przebiegow(przebiegi: dict[str, list[dict | None]]) -> dict[str, dict]:
    """Dla całej odpowiedzi i każdego pola: ile opisów ma identyczną wartość we wszystkich przebiegach.

    Odpowiedź None (błąd wywołania) liczy się jako różna od każdej innej, więc opis z błędem nie jest „identyczny”.
    """
    lista = list(przebiegi.values())
    pola = sorted({k for p in lista for odp in p if odp for k in odp})
    wynik = {"calosc": _zgodnosc([[json.dumps(o, sort_keys=True) if o else object() for o in p] for p in lista])}
    for pole in pola:
        wynik[pole] = _zgodnosc([[o[pole] if o else object() for o in p] for p in lista])
    return wynik


def uruchom_przebiegi(klient: KlientLLM, opisy: pd.DataFrame, n_przebiegow: int = N_PRZEBIEGOW) -> pd.DataFrame:
    prompt = wczytaj_prompt(NAZWA_PROMPTU)
    wiersze = []
    for przebieg in range(1, n_przebiegow + 1):

        def jeden(rekord, przebieg=przebieg):
            try:
                w = klient.zapytaj(rekord.opis, prompt, CechyLokalu, czytaj_cache=False, zapisuj_cache=(przebieg == 1))
                return {
                    "dane": w.dane,
                    "surowy_tekst": w.surowy_tekst,
                    "tokeny_wejscia": w.tokeny_wejscia,
                    "tokeny_wyjscia": w.tokeny_wyjscia,
                    "blad": None,
                }
            except Exception as e:  # noqa: BLE001 — błąd jednego opisu nie przerywa przebiegu; liczony w raporcie
                return {
                    "dane": None,
                    "surowy_tekst": None,
                    "tokeny_wejscia": None,
                    "tokeny_wyjscia": None,
                    "blad": f"{type(e).__name__}: {e}"[:500],
                }

        with ThreadPoolExecutor(max_workers=WATKI) as pula:
            odpowiedzi = list(pula.map(jeden, opisy.itertuples()))
        for rekord, o in zip(opisy.itertuples(), odpowiedzi):
            wiersze.append({"przebieg": przebieg, "id_oferty": rekord.id_oferty, **o})
        print(f"przebieg {przebieg}: błędów {sum(o['blad'] is not None for o in odpowiedzi)}", file=sys.stderr)
    return pd.DataFrame(wiersze)


def tabela_zgodnosci(wyniki: pd.DataFrame) -> pd.DataFrame:
    przebiegi = {id_: list(g.sort_values("przebieg")["dane"]) for id_, g in wyniki.groupby("id_oferty", sort=False)}
    teksty = [list(g.sort_values("przebieg")["surowy_tekst"]) for _, g in wyniki.groupby("id_oferty", sort=False)]
    z = zgodnosc_przebiegow(przebiegi)
    z["surowy_tekst_json"] = _zgodnosc([[t if t is not None else object() for t in p] for p in teksty])
    return pd.DataFrame([{"zakres": k, **v} for k, v in z.items()])


def main() -> None:
    con = polacz()
    opisy = losuj_opisy(con)
    con.close()
    wyniki = uruchom_przebiegi(KlientLLM(), opisy)

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    zapis = wyniki.assign(dane=wyniki["dane"].map(lambda d: json.dumps(d, ensure_ascii=False) if d else None))
    zapis.to_parquet(KATALOG_WYNIKOW / f"stabilnosc_{NAZWA_PROMPTU}.parquet", index=False)

    print(_markdown(tabela_zgodnosci(wyniki)))
    print(f"\nbłędne wywołania: {wyniki['blad'].notna().sum()} z {len(wyniki)}")
    print(f"tokeny wejścia: {wyniki['tokeny_wejscia'].sum():.0f}, wyjścia: {wyniki['tokeny_wyjscia'].sum():.0f}")


def _markdown(df: pd.DataFrame) -> str:
    wiersze = [[f"{v:.3f}" if isinstance(v, float) else str(v) for v in r] for r in df.itertuples(index=False)]
    return "\n".join(
        ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
        + ["| " + " | ".join(w) + " |" for w in wiersze]
    )


if __name__ == "__main__":
    main()
