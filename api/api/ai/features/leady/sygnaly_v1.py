"""Sygnały z oceny LLM v1 (prompt `ocena_leada_v1`) jako cecha modelu kolejki: rodzina `tekst`.

`sygnaly` to lista z zamkniętego słownika (`Sygnal` w ai/llm/schemas/ocena_leada.py), którą v1 zwraca dla każdego
zapytania. Wejście LLM (`opis_leada`) zawiera tylko pola znane przy utworzeniu zapytania, więc sygnały też są znane
w chwili utworzenia (pomijając czas odpowiedzi API).

- `wczytaj_sygnaly(leady)`: tylko odczyt z ai/llm/cache/ (bez API). Brak odpowiedzi w cache = NULL w `sygnaly`
  (wtedy cechy sygnałów są NaN, nie „brak sygnału”).
- `python -m api.ai.features.leady.sygnaly_v1 [--limit N] [--watki 32]`: uzupełnia cache dla zapytań, które
  wchodzą do uczenia i ocen v2 (zbiory z `podzial_v2`): najpierw test, potem okno migracji, potem trening
  w losowej kolejności. Wymaga OPENAI_API_KEY (`set -a && . ./.env && set +a`).
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from api.adapters.llm_client import KATALOG_CACHE, KlientLLM, klucz_cache
from api.ai.features.leady.ocena_llm import opis_leada
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.llm.schemas.ocena_leada import OcenaLeada, Sygnal

WERSJA_PROMPTU = "ocena_leada_v1"
SYGNALY = tuple(s.value for s in Sygnal)


def _plik_cache(lead: dict, katalog: Path) -> Path:
    return katalog / f"{klucz_cache(opis_leada(lead), WERSJA_PROMPTU)}.json"


def wczytaj_sygnaly(leady: pd.DataFrame, katalog_cache: Path = KATALOG_CACHE) -> pd.DataFrame:
    """id_leada, sygnaly (tekst „a,b” w kolejności słownika; '' = brak sygnałów; NULL = brak odpowiedzi w cache)."""
    wiersze = []
    for lead in leady.to_dict("records"):
        plik = _plik_cache(lead, Path(katalog_cache))
        sygnaly = None
        if plik.exists():
            sygnaly = ",".join(json.loads(plik.read_text(encoding="utf-8"))["odpowiedz"]["sygnaly"])
        wiersze.append({"id_leada": lead["id_leada"], "sygnaly": sygnaly})
    return pd.DataFrame(wiersze, columns=["id_leada", "sygnaly"]).astype({"sygnaly": "string"})


def uzupelnij_cache(leady: pd.DataFrame, watki: int = 32, klient: KlientLLM | None = None) -> dict:
    """Woła API dla zapytań bez odpowiedzi w cache (kolejność jak w `leady`). Zwraca liczniki."""
    prompt = wczytaj_prompt(WERSJA_PROMPTU)
    klient = klient or KlientLLM()
    rekordy = [r for r in leady.to_dict("records") if not _plik_cache(r, klient.katalog_cache).exists()]
    licznik = {"do_wywolania": len(rekordy), "ok": 0, "bledy": 0}
    start = time.monotonic()

    def jeden(lead: dict) -> bool:
        try:
            klient.zapytaj(opis_leada(lead), prompt, OcenaLeada)
            return True
        except (
            Exception
        ) as e:  # noqa: BLE001 — błąd jednego zapytania nie przerywa reszty; ponowne uruchomienie dokończy
            print(f"{lead['id_leada']}: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
            return False

    with ThreadPoolExecutor(max_workers=watki) as pula:
        for i, ok in enumerate(as_completed([pula.submit(jeden, r) for r in rekordy]), start=1):
            licznik["ok" if ok.result() else "bledy"] += 1
            if i % 500 == 0 or i == len(rekordy):
                tempo = i / (time.monotonic() - start)
                print(f"{i}/{len(rekordy)} ({tempo:.1f}/s, błędy {licznik['bledy']})", flush=True)
    return licznik


def _kolejnosc_uzupelniania(zbiory: dict[str, pd.DataFrame], ziarno: int = 42) -> pd.DataFrame:
    trening = zbiory["trening"].sample(frac=1.0, random_state=ziarno)
    return pd.concat([zbiory["test"], zbiory["okno_migracji"], trening], ignore_index=True)


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polacz
    from api.ai.features.leady.podzial_v2 import podziel
    from api.ai.features.leady.zbior import wczytaj_zbior

    argumenty = sys.argv[1:]
    limit = int(argumenty[argumenty.index("--limit") + 1]) if "--limit" in argumenty else None
    watki = int(argumenty[argumenty.index("--watki") + 1]) if "--watki" in argumenty else 32
    con = polacz()
    kolejka = _kolejnosc_uzupelniania(podziel(wczytaj_zbior(con)))
    con.close()
    if limit is not None:
        kolejka = kolejka.iloc[:limit]
    print(json.dumps(uzupelnij_cache(kolejka, watki=watki), ensure_ascii=False), flush=True)
