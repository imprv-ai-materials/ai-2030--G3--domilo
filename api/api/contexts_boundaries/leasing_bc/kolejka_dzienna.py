"""Dzienna kolejka doradców: otwarte zapytania -> cechy -> wynik modelu z current.yaml -> EV -> kolejki -> uzasadnienia
-> zapis (tabela kolejka_doradcow) -> webhook do CRM. Opis i wyniki: docs/kolejka_dzienna.md.

Funkcja Inngest `kolejka-doradcow` (inngest_app.py, codziennie 05:30 czasu warszawskiego) wywołuje
`wykonaj_kolejke_doradcow`, a każdy krok idzie przez `ctx.step.run`. Inngest zapamiętuje wynik udanego kroku, więc po
awarii ponawia tylko krok, który padł. Kroki przekazują sobie dane przez pliki Parquet w katalogu przebiegu
(`kolejka_dzienna/<data_kolejki>/<id_przebiegu>/`, poza gitem), a zwracają tylko krótkie podsumowanie (JSON).

- Dzień kolejki (`data_kolejki`): z wywołania albo dzisiejsza data w Europe/Warsaw (krok `parametry`, zapamiętany).
- Stan danych: chwila kolejki 05:30 tego dnia, ale nie później niż koniec eksportu (2026-10-01 00:00), bo
  późniejszych zdarzeń w danych nie ma. Kolejka na każdy dzień po eksporcie widzi więc stan z końca eksportu.
- Otwarte zapytanie: w chwili stanu ostatni status z `crm_historia_statusow` to `otwarty` albo `w_toku`, a zapytanie
  ma najwyżej 45 dni. Starsze pomijamy: model przewiduje umowę w 45 dni, a w danych żadna umowa nie powstała później
  niż 45 dni po zapytaniu (docs/kolejka_target.md, R5). `crm_leady.status` i `id_doradcy` (stan na dzień eksportu)
  nie są używane.
- Wynik: model z current.yaml (ai/lead_model/obecny.py, kontrakt base.ModelLeadow: `predict`, `explain`).
- EV = p × mediana czynszu × czas najmu × liczba lokali (leasing_bc/wartosc.py).
- Kolejki: aktywni doradcy (crm_doradcy: zatrudnieni w dniu kolejki, bez call center) i otwarte zapytania z ich
  miasta według EV malejąco (remis: id_leada). Gdy w mieście jest kilku doradców, zapytania rozdajemy po kolei
  (1. do pierwszego doradcy, 2. do drugiego, …), więc kolejki się nie pokrywają, a każdy doradca ma podobną mieszankę.
  Najwyżej 40 pozycji na doradcę. Zapytanie jest danego dnia najwyżej u jednego doradcy, zgodnie z kluczem
  idempotencji webhooka (id_leada, data_kolejki).
- Uzasadnienie (ai/lead_model/uzasadnienie.py): top 3 wkłady SHAP z `explain` -> fakty -> zdanie z LLM (cache
  odpowiedzi), a bez LLM zdanie z szablonu. Liczone tylko dla zapytań w kolejkach.
- LLM: sygnały v1 (cecha modelu) i zdania uzasadnień, gdy jest OPENAI_API_KEY i nie ustawiono KOLEJKA_LLM=0.
  Błąd wywołania LLM przerywa krok (Inngest go ponawia; udane odpowiedzi zostają w cache), żeby dwa przebiegi tego
  samego dnia dały ten sam wynik. Bez LLM sygnały są brakiem (NaN), a zdania pochodzą z szablonu.

Ręcznie (bez Inngest): `pypyr kolejka [data=RRRR-MM-DD]` albo
`cd api && poetry run python -m api.contexts_boundaries.leasing_bc.kolejka_dzienna [RRRR-MM-DD]`.
"""

import json
import os
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from api.adapters import kolejka_doradcow, kolejka_historia, kolejka_ranking
from api.adapters.crm_lejek import KlientLejka
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polaczenie
from api.adapters.llm_client import BrakKluczaAPI, KlientLLM
from api.ai.features.leady.cechy import zbuduj_cechy
from api.ai.features.leady.fakty import fakty_leada, kontekst_faktow
from api.ai.features.leady.sygnaly_v1 import uzupelnij_cache, wczytaj_sygnaly
from api.ai.lead_model.base import KOLUMNY_WEJSCIA
from api.ai.lead_model.obecny import wczytaj_obecny
from api.ai.lead_model.uzasadnienie import WERSJA_PROMPTU, top_wklady, uzasadnij
from api.ai.llm.prompty import wczytaj_prompt
from api.contexts_boundaries.leasing_bc.eksperyment import (
    UDZIAL_LOSOWYCH,
    WARIANT_DOMYSLNY,
    WARIANTY,
    liczba_losowych,
    wariant_dnia,
    wczytaj_plan,
    ziarno,
)
from api.contexts_boundaries.leasing_bc.wartosc import wartosc_oczekiwana

STREFA = ZoneInfo("Europe/Warsaw")
KONIEC_DANYCH = datetime(2026, 10, 1, 0, 0, tzinfo=STREFA)  # dzień eksportu 2026-09-30 23:59 (granica półotwarta)
GODZINA_KOLEJKI = time(5, 30)
WIEK_MAKS_DNI = 45
MAKS_POZYCJI = 40
KATALOG_PRZEBIEGOW = KATALOG_REPO / "kolejka_dzienna"
WATKI_LLM = 8
STATUSY_OTWARTE = ("otwarty", "w_toku")

Krok = Callable[..., Any]

# Status w chwili stanu: ostatnia zmiana przed chwilą stanu. Remis czasu rozstrzyga etap statusu, tak jak
# w leady_cel.sql (otwarty -> w_toku -> status końcowy).
SQL_OTWARTE = f"""
WITH status_w_chwili AS (
    SELECT id_leada, status_na
    FROM crm_historia_statusow
    WHERE data_czas < $stan
    QUALIFY row_number() OVER (
        PARTITION BY id_leada
        ORDER BY data_czas DESC,
                 CASE status_na WHEN 'otwarty' THEN 0 WHEN 'w_toku' THEN 1 ELSE 2 END DESC,
                 status_na DESC
    ) = 1
)
SELECT {", ".join(f"l.{k}" for k in KOLUMNY_WEJSCIA)}, s.status_na AS status_crm
FROM crm_leady AS l
JOIN status_w_chwili AS s USING (id_leada)
WHERE l.utworzono < $stan
  AND l.utworzono >= $stan - INTERVAL {WIEK_MAKS_DNI} DAY
  AND s.status_na IN {STATUSY_OTWARTE}
ORDER BY l.id_leada
"""

SQL_DORADCY = """
SELECT id_doradcy, miasto
FROM crm_doradcy
WHERE id_doradcy <> 'CC' AND miasto IS NOT NULL
  AND CAST(data_od AS DATE) <= $dzien
  AND (data_do IS NULL OR CAST(data_do AS DATE) >= $dzien)
ORDER BY miasto, id_doradcy
"""


# --- logika (bez plików i Inngest) ---------------------------------------------------------------------------------


def stan_danych_na(data_kolejki: date) -> datetime:
    """Chwila, według której liczymy otwarte zapytania: 05:30 dnia kolejki, najpóźniej koniec eksportu."""
    return min(datetime.combine(data_kolejki, GODZINA_KOLEJKI, tzinfo=STREFA), KONIEC_DANYCH)


def otwarte_zapytania(con, stan: datetime) -> pd.DataFrame:
    """KOLUMNY_WEJSCIA + status_crm dla zapytań otwartych w chwili `stan` i nie starszych niż 45 dni."""
    return con.execute(SQL_OTWARTE, {"stan": stan}).df()


def aktywni_doradcy(con, dzien: date) -> pd.DataFrame:
    return con.execute(SQL_DORADCY, {"dzien": dzien}).df()


KOLUMNY_RANKINGU = [
    "id_leada",
    "miasto",
    "ranga",
    "otwarte_w_miescie",
    "id_doradcy",
    "pozycja",
    "wariant",
    "losowa",
    "p_losowania",
    "pula_losowania",
    "ziarno",
]


def _kolejnosc_wariantu(z: pd.DataFrame, wariant: str) -> list[str]:
    """Kolejność zapytań miasta w kolejce: `model` = EV malejąco, `od_najnowszego` = utworzono malejąco (remis: id)."""
    if wariant == "model":
        return z.sort_values(["ev", "id_leada"], ascending=[False, True], kind="mergesort")["id_leada"].tolist()
    if wariant == "od_najnowszego":
        return z.sort_values(["utworzono", "id_leada"], ascending=[False, True], kind="mergesort")["id_leada"].tolist()
    raise ValueError(f"Nieznany wariant kolejki: {wariant} (dozwolone: {', '.join(WARIANTY)})")


def ranking_kolejki(
    ev: pd.DataFrame,
    doradcy: pd.DataFrame,
    maks: int = MAKS_POZYCJI,
    wariant: str = WARIANT_DOMYSLNY,
    udzial_losowych: float = UDZIAL_LOSOWYCH,
    ziarno_dnia: str = "",
) -> pd.DataFrame:
    """Pełny ranking dnia: każde otwarte zapytanie z EV, miejsce w mieście i (dla kolejek) doradca i pozycja.

    `ev`: id_leada, miasto, ev (NaN = poza rankingiem), a dla wariantu `od_najnowszego` także utworzono;
    `doradcy`: id_doradcy, miasto.
    - Ranga: zawsze EV malejąco w mieście (remis: id_leada), od 1, w obu wariantach (górny decyl znaczy to samo).
    - Kolejki: w mieście z k doradcami długość kolejki doradcy j to S div k (+1 dla j < S mod k), S = min(k × maks,
      liczba zapytań). W każdej kolejce `liczba_losowych(długość)` pozycji (5%, 40 -> 2), na losowych miejscach,
      zajmują zapytania wylosowane bez zwracania ze wszystkich otwartych zapytań miasta. Pozostałe miejsca
      wypełniamy po kolei w kolejności wariantu (`_kolejnosc_wariantu`): następne zapytanie dostaje następny doradca
      (po id) na swojej najbliższej wolnej pozycji. Bez części losowej to ta sama reguła co wcześniej: ranga r ->
      doradca (r − 1) mod k, pozycja (r − 1) div k + 1.
    - p_losowania = liczba pozycji losowych w mieście / liczba otwartych zapytań miasta (to samo dla każdego zapytania
      miasta tego dnia; potrzebne do wag w ocenie modelu); pula_losowania = liczba otwartych zapytań miasta.
    - Losowanie: numpy z ziarnem `ziarno(ziarno_dnia, miasto, wariant)`, więc ten sam dzień daje tę samą kolejkę.
    Miasto bez doradcy ma ranking bez kolejek (id_doradcy, pozycja = NA).
    """
    z = ev[ev["ev"].notna()].sort_values(["miasto", "ev", "id_leada"], ascending=[True, False, True], kind="mergesort")
    z = z.copy()
    z["ranga"] = z.groupby("miasto").cumcount() + 1
    z["otwarte_w_miescie"] = z.groupby("miasto")["id_leada"].transform("size")
    doradcy_miast = {m: sorted(d["id_doradcy"]) for m, d in doradcy.groupby("miasto")}
    przydzial: dict[str, tuple[str, int, bool]] = {}
    p_losowania: dict[str, float] = {}
    ziarna: dict[str, str] = {}
    for miasto, zm in z.groupby("miasto", sort=True):
        ids = doradcy_miast.get(miasto, [])
        n = len(zm)
        ziarna[miasto] = f"{ziarno_dnia}:{miasto}:{wariant}"
        if not ids:
            p_losowania[miasto] = 0.0
            continue
        k = len(ids)
        sloty = min(maks * k, n)
        dlugosci = [sloty // k + (1 if j < sloty % k else 0) for j in range(k)]
        losowych = [liczba_losowych(d, udzial_losowych) for d in dlugosci]
        rng = np.random.default_rng(ziarno(ziarno_dnia, str(miasto), wariant))
        pula = sorted(zm["id_leada"])
        wylosowane = [str(x) for x in rng.choice(pula, size=sum(losowych), replace=False)] if sum(losowych) else []
        p_losowania[miasto] = sum(losowych) / n
        wolne = []  # dla każdego doradcy: jego pozycje nielosowe rosnąco
        nr = 0
        for j, (dlugosc, r) in enumerate(zip(dlugosci, losowych)):
            miejsca_losowe = sorted(int(x) + 1 for x in rng.choice(dlugosc, size=r, replace=False)) if r else []
            for poz in miejsca_losowe:
                przydzial[wylosowane[nr]] = (ids[j], poz, True)
                nr += 1
            wolne.append([p for p in range(1, dlugosc + 1) if p not in set(miejsca_losowe)])
        reszta = (x for x in _kolejnosc_wariantu(zm, wariant) if x not in przydzial)
        j = 0
        while any(wolne):
            if wolne[j]:
                przydzial[next(reszta)] = (ids[j], wolne[j].pop(0), False)
            j = (j + 1) % k
    z["id_doradcy"] = pd.Series([przydzial.get(i, (None,))[0] for i in z["id_leada"]], index=z.index, dtype="object")
    z["pozycja"] = pd.array([przydzial[i][1] if i in przydzial else None for i in z["id_leada"]], dtype="Int64")
    z["losowa"] = [bool(przydzial[i][2]) if i in przydzial else False for i in z["id_leada"]]
    z["wariant"] = wariant
    z["p_losowania"] = z["miasto"].map(p_losowania).astype(float)
    z["pula_losowania"] = z["otwarte_w_miescie"].astype(int)
    z["ziarno"] = z["miasto"].map(ziarna)
    return z[KOLUMNY_RANKINGU].reset_index(drop=True)


def przydziel_kolejki(
    ev: pd.DataFrame,
    doradcy: pd.DataFrame,
    maks: int = MAKS_POZYCJI,
    wariant: str = WARIANT_DOMYSLNY,
    udzial_losowych: float = UDZIAL_LOSOWYCH,
    ziarno_dnia: str = "",
) -> pd.DataFrame:
    """Kolejki: id_doradcy, miasto, pozycja (od 1), id_leada; część `ranking_kolejki` z doradcą."""
    r = ranking_kolejki(ev, doradcy, maks, wariant, udzial_losowych, ziarno_dnia)
    k = r[r["id_doradcy"].notna()].copy()
    k["pozycja"] = k["pozycja"].astype(int)
    k = k.sort_values(["miasto", "pozycja", "id_doradcy"], kind="mergesort")
    return k[["id_doradcy", "miasto", "pozycja", "id_leada"]].reset_index(drop=True)


def uzyj_llm() -> bool:
    return os.environ.get("KOLEJKA_LLM", "1") != "0" and bool(os.environ.get("OPENAI_API_KEY"))


def _klient_llm(z_llm: bool | None) -> KlientLLM | None:
    if not (uzyj_llm() if z_llm is None else z_llm):
        return None
    try:
        return KlientLLM()
    except BrakKluczaAPI:
        return None


# --- kroki (każdy czyta pliki poprzednich kroków z katalogu przebiegu i zapisuje swój) ----------------------------


def _liczniki(s: pd.Series) -> dict[str, int]:
    """Liczności wartości jako czysty JSON (Inngest zapamiętuje wynik kroku jako JSON)."""
    return {str(k): int(v) for k, v in s.value_counts().sort_index().items()}


def _plik(katalog: str, nazwa: str) -> Path:
    return Path(katalog) / f"{nazwa}.parquet"


def krok_parametry(data_kolejki: str | None, id_przebiegu: str, katalog_bazowy: str) -> dict:
    dzien = date.fromisoformat(data_kolejki) if data_kolejki else datetime.now(STREFA).date()
    katalog = Path(katalog_bazowy) / dzien.isoformat() / id_przebiegu
    katalog.mkdir(parents=True, exist_ok=True)
    return {
        "data_kolejki": dzien.isoformat(),
        "stan_danych_na": stan_danych_na(dzien).isoformat(),
        "katalog": str(katalog),
        "id_przebiegu": id_przebiegu,
    }


def krok_otwarte(katalog: str, stan_iso: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    with polaczenie(sciezka=sciezka) as con:
        otwarte = otwarte_zapytania(con, datetime.fromisoformat(stan_iso))
    otwarte.to_parquet(_plik(katalog, "otwarte"), index=False)
    return {
        "zapytania": len(otwarte),
        "miasta": _liczniki(otwarte["miasto"]),
        "statusy": _liczniki(otwarte["status_crm"]),
    }


def krok_sygnaly(katalog: str, z_llm: bool | None = None) -> dict:
    """Sygnały v1 (cecha rodziny `tekst`): z cache, a brakujące z LLM. Błąd LLM przerywa krok (ponowienie)."""
    otwarte = pd.read_parquet(_plik(katalog, "otwarte"))
    przed = wczytaj_sygnaly(otwarte)
    brak = int(przed["sygnaly"].isna().sum())
    wywolania = {"do_wywolania": 0, "ok": 0, "bledy": 0}
    klient = _klient_llm(z_llm) if brak else None
    if klient is not None:
        do_uzupelnienia = otwarte[przed["sygnaly"].isna().to_numpy()]
        wywolania = uzupelnij_cache(do_uzupelnienia, watki=WATKI_LLM * 2, klient=klient)
        if wywolania["bledy"]:
            raise RuntimeError(f"Sygnały LLM: {wywolania['bledy']} błędów (udane odpowiedzi zostały w cache)")
    sygnaly = wczytaj_sygnaly(otwarte, katalog_cache=klient.katalog_cache) if klient else przed
    sygnaly.to_parquet(_plik(katalog, "sygnaly"), index=False)
    return {
        "zapytania": len(otwarte),
        "z_cache_przed": len(otwarte) - brak,
        "llm": wywolania,
        "bez_sygnalow": int(sygnaly["sygnaly"].isna().sum()),
    }


def krok_cechy(katalog: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    otwarte = pd.read_parquet(_plik(katalog, "otwarte"))
    sygnaly = pd.read_parquet(_plik(katalog, "sygnaly"))
    with polaczenie(sciezka=sciezka) as con:
        cechy = zbuduj_cechy(con, sygnaly)
    X = otwarte[["id_leada", "utworzono"]].merge(cechy, on="id_leada", how="left", validate="1:1")
    X.to_parquet(_plik(katalog, "cechy"), index=False)
    return {"zapytania": len(X), "kolumny": X.shape[1] - 2}


def krok_wynik_modelu(katalog: str) -> dict:
    """Wynik i wkłady (explain) obecnej wersji z current.yaml, przez kontrakt ModelLeadow."""
    obecny = wczytaj_obecny()
    X = pd.read_parquet(_plik(katalog, "cechy"))
    p = np.asarray(obecny.model.predict(X), dtype=float)
    wyj = obecny.model.explain(X).reset_index(drop=True)
    if not np.allclose(wyj["wynik"].to_numpy(dtype=float), p, equal_nan=True):
        raise ValueError(f"{obecny.wersja}: explain()['wynik'] różni się od predict()")
    wklady = [c for c in wyj.columns if c.startswith("wklad_")]
    wynik = pd.concat([X[["id_leada"]], pd.Series(p, name="p"), wyj[wklady]], axis=1)
    wynik.to_parquet(_plik(katalog, "wynik"), index=False)
    return {
        "wersja_modelu": obecny.wersja,
        "zapytania": len(wynik),
        "bez_wyniku": int(np.isnan(p).sum()),
        "p_srednie": float(np.nanmean(p)) if len(p) else None,
    }


def krok_ev(katalog: str) -> dict:
    otwarte = pd.read_parquet(_plik(katalog, "otwarte"))
    wynik = pd.read_parquet(_plik(katalog, "wynik"), columns=["id_leada", "p"])
    df = otwarte.merge(wynik, on="id_leada", how="left", validate="1:1")
    df["ev"] = wartosc_oczekiwana(df["p"], df)
    df[["id_leada", "miasto", "utworzono", "p", "ev"]].to_parquet(_plik(katalog, "ev"), index=False)
    return {"zapytania": len(df), "suma_ev_pln": round(float(np.nansum(df["ev"])), 2)}


def krok_kolejki(
    katalog: str, data_kolejki: str, sciezka: Path = SCIEZKA_BAZY, plan: dict | None | str = "z_pliku"
) -> dict:
    """Ranking i kolejki dnia w wariancie z planu eksperymentu (leasing_bc/eksperyment.py), z 5% pozycji losowych."""
    ev = pd.read_parquet(_plik(katalog, "ev"))
    dzien = date.fromisoformat(data_kolejki)
    with polaczenie(sciezka=sciezka) as con:
        doradcy = aktywni_doradcy(con, dzien)
    wariant = wariant_dnia(dzien, wczytaj_plan() if plan == "z_pliku" else plan)
    ranking = ranking_kolejki(ev, doradcy, wariant=wariant, ziarno_dnia=data_kolejki)
    ranking.to_parquet(_plik(katalog, "ranking"), index=False)
    kolejki = ranking[ranking["id_doradcy"].notna()].copy()
    kolejki["pozycja"] = kolejki["pozycja"].astype(int)
    kolejki = kolejki.sort_values(["miasto", "pozycja", "id_doradcy"], kind="mergesort")
    kolejki = kolejki[["id_doradcy", "miasto", "pozycja", "id_leada"]].reset_index(drop=True)
    kolejki.to_parquet(_plik(katalog, "kolejki"), index=False)
    miasta_bez_doradcy = sorted(set(ev["miasto"]) - set(doradcy["miasto"]))
    return {
        "wariant": wariant,
        "doradcy": [str(d) for d in sorted(doradcy["id_doradcy"])],
        "pozycje": len(kolejki),
        "pozycje_losowe": int(ranking["losowa"].sum()),
        "na_doradce": _liczniki(kolejki["id_doradcy"]),
        "miasta_bez_doradcy": [str(m) for m in miasta_bez_doradcy],
    }


def krok_uzasadnienia(katalog: str, sciezka: Path = SCIEZKA_BAZY, z_llm: bool | None = None) -> dict:
    """Zdanie dla każdego zapytania w kolejkach: top 3 SHAP -> fakty -> LLM (albo szablon bez LLM)."""
    kolejki = pd.read_parquet(_plik(katalog, "kolejki"))
    wynik = pd.read_parquet(_plik(katalog, "wynik")).set_index("id_leada")
    cechy = pd.read_parquet(_plik(katalog, "cechy")).set_index("id_leada")
    with polaczenie(sciezka=sciezka) as con:
        kontekst = kontekst_faktow(con).set_index("id_leada")
    kolumny_wkladow = [c for c in wynik.columns if c.startswith("wklad_")]
    cechy_modelu = tuple(c.removeprefix("wklad_") for c in kolumny_wkladow if c != "wklad_staly")
    fakty_top, fakty_poz = [], []
    for id_leada in kolejki["id_leada"]:
        wszystkie = fakty_leada(cechy.loc[id_leada].to_dict(), kontekst.loc[id_leada].to_dict(), cechy_modelu)
        top = [c for c, _ in top_wklady(wynik.loc[id_leada, kolumny_wkladow])]
        fakty_top.append([wszystkie[c] for c in top])
        fakty_poz.append([f for c, f in wszystkie.items() if c not in top])

    klient = _klient_llm(z_llm)
    prompt = wczytaj_prompt(WERSJA_PROMPTU) if klient else None
    with ThreadPoolExecutor(max_workers=WATKI_LLM) as pula:
        wyniki = list(pula.map(lambda i: uzasadnij(fakty_top[i], fakty_poz[i], klient, prompt), range(len(kolejki))))
    if klient is not None:
        bledy = [w for w in wyniki if w.zrodlo == "szablon" and w.zdanie_llm is None]
        if bledy:
            raise RuntimeError(f"Uzasadnienia LLM: {len(bledy)} wywołań nie powiodło się ({bledy[0].problemy_llm})")
    df = pd.DataFrame(
        {
            "id_leada": kolejki["id_leada"],
            "uzasadnienie": [w.zdanie for w in wyniki],
            "zrodlo_uzasadnienia": [w.zrodlo for w in wyniki],
            "fakty_top": [json.dumps([f.tekst for f in ft], ensure_ascii=False) for ft in fakty_top],
            "problemy_llm": ["; ".join(w.problemy_llm) or None for w in wyniki],
        }
    )
    df.to_parquet(_plik(katalog, "uzasadnienia"), index=False)
    return {
        "zapytania": len(df),
        "zrodlo": _liczniki(df["zrodlo_uzasadnienia"]),
        "z_cache": sum(bool(w.z_cache) for w in wyniki),
    }


def krok_zapis(
    katalog: str, data_kolejki: str, stan_iso: str, wersja_modelu: str, id_przebiegu: str, sciezka: Path = SCIEZKA_BAZY
) -> dict:
    """Kolejki dnia do tabeli kolejka_doradcow (zastępuje cały dzień). p i EV zaokrąglone, żeby treść była stała."""
    kolejki = pd.read_parquet(_plik(katalog, "kolejki"))
    kolumny_otwartych = ["id_leada", "utworzono", "status_crm", "zrodlo", "linia_pref", "liczba_lokali"]
    otwarte = pd.read_parquet(_plik(katalog, "otwarte"), columns=kolumny_otwartych)
    ev = pd.read_parquet(_plik(katalog, "ev"), columns=["id_leada", "p", "ev"])
    uz = pd.read_parquet(_plik(katalog, "uzasadnienia"), columns=["id_leada", "uzasadnienie", "zrodlo_uzasadnienia"])
    df = kolejki.merge(otwarte, on="id_leada", validate="1:1").merge(ev, on="id_leada", validate="1:1")
    df = df.merge(uz, on="id_leada", validate="1:1")
    dzien = date.fromisoformat(data_kolejki)
    df = df.assign(
        data_kolejki=dzien,
        liczba_lokali=pd.to_numeric(df["liczba_lokali"], errors="coerce").fillna(1).astype(float),
        p=df["p"].astype(float).round(6),
        ev_pln=df["ev"].astype(float).round(2),
        wersja_modelu=wersja_modelu,
        stan_danych_na=pd.Timestamp(stan_iso),
        id_przebiegu=id_przebiegu,
    ).sort_values(["id_doradcy", "pozycja"])
    ranking = pd.read_parquet(_plik(katalog, "ranking")).merge(ev, on="id_leada", validate="1:1")
    ranking = ranking.assign(
        data_kolejki=dzien,
        p=ranking["p"].astype(float).round(6),
        ev_pln=ranking["ev"].astype(float).round(2),
        wersja_modelu=wersja_modelu,
        zrodlo_kolejki="zadanie",
        stan_danych_na=pd.Timestamp(stan_iso),
        id_przebiegu=id_przebiegu,
    )
    historia = ranking[ranking["id_doradcy"].notna()].assign(
        ranga_ev=lambda r: r["ranga"],
        pozycja=lambda r: r["pozycja"].astype(int),
    )
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        n = kolejka_doradcow.zapisz(con, dzien, df)
        n_rankingu = kolejka_ranking.zapisz(con, ranking)
        n_historii = kolejka_historia.zapisz(con, dzien, historia)
    return {"pozycje": n, "ranking": n_rankingu, "historia": n_historii}


def krok_webhook(data_kolejki: str, id_doradcy: str, sciezka: Path = SCIEZKA_BAZY, klient: KlientLejka | None = None):
    """Kolejka doradcy z tabeli (ta sama, którą oddaje GET /leads/next) -> webhook do CRM."""
    with polaczenie(sciezka=sciezka) as con:
        pozycje = kolejka_doradcow.pozycje(con, id_doradcy, date.fromisoformat(data_kolejki))
    return {"pozycje": len(pozycje), **(klient or KlientLejka()).wyslij_kolejke(pozycje)}


# --- przebieg -------------------------------------------------------------------------------------------------------


def wykonaj_kolejke_doradcow(
    krok: Krok,
    id_przebiegu: str,
    data_kolejki: str | None = None,
    sciezka: Path = SCIEZKA_BAZY,
    katalog_bazowy: Path = KATALOG_PRZEBIEGOW,
    klient_lejka: KlientLejka | None = None,
    z_llm: bool | None = None,
    plan: dict | None | str = "z_pliku",
) -> dict:
    """Kolejność kroków; `krok(id, handler, *args)` = ctx.step.run w Inngest (w testach i CLI: wywołanie wprost)."""
    par = krok("parametry", krok_parametry, data_kolejki, id_przebiegu, str(katalog_bazowy))
    kat, dzien, stan = par["katalog"], par["data_kolejki"], par["stan_danych_na"]
    wynik = {"parametry": par}
    wynik["otwarte"] = krok("otwarte-zapytania", krok_otwarte, kat, stan, sciezka)
    wynik["sygnaly"] = krok("sygnaly-llm", krok_sygnaly, kat, z_llm)
    wynik["cechy"] = krok("cechy", krok_cechy, kat, sciezka)
    wynik["model"] = krok("wynik-modelu", krok_wynik_modelu, kat)
    wynik["ev"] = krok("ev", krok_ev, kat)
    wynik["kolejki"] = krok("kolejki", krok_kolejki, kat, dzien, sciezka, plan)
    wynik["uzasadnienia"] = krok("uzasadnienia", krok_uzasadnienia, kat, sciezka, z_llm)
    wersja = wynik["model"]["wersja_modelu"]
    wynik["zapis"] = krok("zapis-kolejki", krok_zapis, kat, dzien, stan, wersja, id_przebiegu, sciezka)
    wynik["webhook"] = {
        d: krok(f"webhook-crm-{d}", krok_webhook, dzien, d, sciezka, klient_lejka) for d in wynik["kolejki"]["doradcy"]
    }
    return wynik


def _krok_wprost(id_kroku: str, handler: Callable, *args):
    wynik = handler(*args)
    print(f"[{id_kroku}] {json.dumps(wynik, ensure_ascii=False, default=str)}", flush=True)
    return wynik


if __name__ == "__main__":
    argumenty = [a for a in sys.argv[1:] if a]
    przebieg = f"reczny-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}"
    wykonaj_kolejke_doradcow(_krok_wprost, przebieg, argumenty[0] if argumenty else None)
