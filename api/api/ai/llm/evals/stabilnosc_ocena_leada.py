"""Stabilność oceny zapytań przez LLM: ten sam prompt na tych samych zapytaniach, dwa przebiegi.

Opis i wyniki: docs/llm_ocena_leada_v1.md. Uruchomienie (wymaga domilo.duckdb: `pypyr baza` i klucza w środowisku):
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.llm.evals.stabilnosc_ocena_leada

Losuje `N_LEADOW` zapytań z `crm_leady` (ziarno `ZIARNO`) i wysyła każde `N_PRZEBIEGOW` razy, za każdym razem
z pominięciem cache (inaczej przebieg 2 byłby kopią pierwszego). Odpowiedzi z przebiegu 1 trafiają do ai/llm/cache/.
Wszystkie odpowiedzi i wejścia zapisuje w evals/wyniki/stabilnosc_<wersja>.parquet.
"""

import json
import sys
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.llm_client import KlientLLM
from api.ai.features.leady.ocena_llm import losuj_leady, opis_leada
from api.ai.llm.evals.stabilnosc_cechy_lokalu import _markdown
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.ocena_leada import OcenaLeada

NAZWA_PROMPTU = "ocena_leada_v1"
N_LEADOW = 500
N_PRZEBIEGOW = 2
ZIARNO = 42
WATKI = 8
KATALOG_WYNIKOW = Path(__file__).with_name("wyniki")


def _zgodnosc(pary: list[tuple], zgodne: Callable[[object, object], bool]) -> dict:
    identyczne = sum(a is not None and b is not None and zgodne(a, b) for a, b in pary)
    return {"identyczne": identyczne, "leadow": len(pary), "odsetek": identyczne / len(pary)}


def zgodnosc_dwoch_przebiegow(
    przebieg_1: Mapping[str, dict | None], przebieg_2: Mapping[str, dict | None]
) -> dict[str, dict]:
    """Ile zapytań ma tę samą odpowiedź w obu przebiegach: cała odpowiedź, ocena (dokładnie i ±1), każde pole.

    Odpowiedź None (błąd wywołania) jest niezgodna z każdą inną, więc zapytanie z błędem nie jest „identyczne”.
    """
    pary = [(przebieg_1[k], przebieg_2.get(k)) for k in przebieg_1]

    def pole(nazwa):
        return [(a[nazwa] if a else None, b[nazwa] if b else None) for a, b in pary]

    return {
        "calosc": _zgodnosc(pary, lambda a, b: a == b),
        "ocena": _zgodnosc(pole("ocena"), lambda a, b: a == b),
        "ocena_roznica_do_1": _zgodnosc(pole("ocena"), lambda a, b: abs(a - b) <= 1),
        "sygnaly": _zgodnosc(pole("sygnaly"), lambda a, b: a == b),
        "uzasadnienie": _zgodnosc(pole("uzasadnienie"), lambda a, b: a == b),
    }


def uruchom_przebiegi(klient: KlientLLM, leady: pd.DataFrame, n_przebiegow: int = N_PRZEBIEGOW) -> pd.DataFrame:
    prompt = wczytaj_prompt(NAZWA_PROMPTU)
    wejscia = [opis_leada(r) for r in leady.to_dict("records")]
    wiersze = []
    for przebieg in range(1, n_przebiegow + 1):

        def jeden(wejscie: str, przebieg=przebieg) -> dict:
            try:
                w = klient.zapytaj(wejscie, prompt, OcenaLeada, czytaj_cache=False, zapisuj_cache=(przebieg == 1))
                return {
                    "dane": w.dane,
                    "surowy_tekst": w.surowy_tekst,
                    "tokeny_wejscia": w.tokeny_wejscia,
                    "tokeny_wyjscia": w.tokeny_wyjscia,
                    "blad": None,
                }
            except Exception as e:  # noqa: BLE001 — błąd jednego zapytania nie przerywa przebiegu; liczony w raporcie
                return {
                    "dane": None,
                    "surowy_tekst": None,
                    "tokeny_wejscia": None,
                    "tokeny_wyjscia": None,
                    "blad": f"{type(e).__name__}: {e}"[:500],
                }

        with ThreadPoolExecutor(max_workers=WATKI) as pula:
            odpowiedzi = list(pula.map(jeden, wejscia))
        for id_leada, wejscie, o in zip(leady["id_leada"], wejscia, odpowiedzi):
            wiersze.append({"przebieg": przebieg, "id_leada": id_leada, "wejscie": wejscie, **o})
        print(f"przebieg {przebieg}: błędów {sum(o['blad'] is not None for o in odpowiedzi)}", file=sys.stderr)
    return pd.DataFrame(wiersze)


def tabela_zgodnosci(wyniki: pd.DataFrame) -> pd.DataFrame:
    przebiegi = {p: dict(zip(g["id_leada"], g["dane"])) for p, g in wyniki.groupby("przebieg")}
    teksty = {p: dict(zip(g["id_leada"], g["surowy_tekst"])) for p, g in wyniki.groupby("przebieg")}
    z = zgodnosc_dwoch_przebiegow(przebiegi[1], przebiegi[2])
    z["surowy_tekst_json"] = _zgodnosc([(teksty[1][k], teksty[2].get(k)) for k in teksty[1]], lambda a, b: a == b)
    return pd.DataFrame([{"zakres": k, **v} for k, v in z.items()])


def main() -> None:
    con = polacz()
    leady = losuj_leady(con, N_LEADOW, ZIARNO)
    con.close()
    wyniki = uruchom_przebiegi(KlientLLM(), leady)

    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    zapis = wyniki.assign(dane=wyniki["dane"].map(lambda d: json.dumps(d, ensure_ascii=False) if d else None))
    zapis.to_parquet(KATALOG_WYNIKOW / f"stabilnosc_{NAZWA_PROMPTU}.parquet", index=False)

    print(_markdown(tabela_zgodnosci(wyniki)))
    print(f"\nbłędne wywołania: {wyniki['blad'].notna().sum()} z {len(wyniki)}")
    print(f"tokeny wejścia: {wyniki['tokeny_wejscia'].sum():.0f}, wyjścia: {wyniki['tokeny_wyjscia'].sum():.0f}")


if __name__ == "__main__":
    main()
