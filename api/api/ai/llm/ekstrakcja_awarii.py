"""Ekstrakcja awarii wind z notatek konserwatorów przez LLM (prompt awaria_v1, schemat schemas/awaria.py).

Wejście LLM to jedno zgłoszenie ze wszystkimi notatkami (`opis_zgloszenia`): czas utworzenia, źródło i treść
zgłoszenia oraz notatki od najstarszej z czasem i autorem. Celowo bez kategorii, priorytetu, statusu i czasu
zamknięcia: kategoria „awaria” nie oznacza faktycznej awarii (docs/b4_historia_awarii.md), a model ma czytać notatki.
Bez numeru zgłoszenia, więc identyczne zgłoszenia mają ten sam klucz cache.

Klient: `api.adapters.llm_client.KlientLLM` (gpt-6-luna, reasoning effort none, temperatura 0). Odpowiedzi trafiają
do `ai/llm/cache/<sha256(wersja promptu + wejście)>.json`, więc ponowne uruchomienie nie płaci drugi raz.

Uruchomienie (wymaga domilo.duckdb i OPENAI_API_KEY w środowisku), z katalogu głównego repozytorium:
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.llm.ekstrakcja_awarii [--zbior zloty_zbior|windy] [--limit N]
Zbiory: `zloty_zbior` — 400 zgłoszeń z `serwis_zloty_zbior` (ręczne etykiety koordynatora); `windy` — wszystkie
zgłoszenia z `zgloszenia_wind`. `--limit N` bierze N zgłoszeń w stałej kolejności md5(id_zgloszenia).
Wynik: `ai/features/windy/awarie_llm/<wersja>_<zbior>[_N].parquet` (pola schematu, tokeny, z_cache, blad).
"""

import argparse
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
from api.adapters.llm_client import KlientLLM, klucz_cache
from api.ai.llm.prompty import Prompt, wczytaj_prompt
from api.ai.llm.schemas.awaria import Awaria

PROMPT = "awaria_v1"
POLA = tuple(Awaria.model_fields)
KOLUMNY_TOKENOW = ("tokeny_wejscia", "tokeny_wyjscia", "tokeny_wejscia_z_cache")
KATALOG_WYNIKOW = Path(__file__).resolve().parents[1] / "features" / "windy" / "awarie_llm"
WATKI = 16
AUTORZY = {"KOORD": "koordynator"}  # pozostali autorzy (K01–K19) to konserwatorzy

SQL_ZBIORY = {
    "zloty_zbior": "SELECT id_zgloszenia FROM serwis_zloty_zbior",
    "windy": "SELECT id_zgloszenia FROM zgloszenia_wind",
}

SQL_ZGLOSZENIA = """
SELECT
    z.id_zgloszenia,
    z.utworzono,
    z.zrodlo,
    z.tresc_zgloszenia,
    list({'data_czas': n.data_czas, 'autor': n.autor, 'tresc': n.tresc} ORDER BY n.data_czas, n.id_notatki)
        FILTER (n.id_notatki IS NOT NULL) AS notatki
FROM serwis_zgloszenia AS z
LEFT JOIN serwis_notatki AS n USING (id_zgloszenia)
WHERE z.id_zgloszenia IN (SELECT id_zgloszenia FROM wybrane)
GROUP BY z.id_zgloszenia, z.utworzono, z.zrodlo, z.tresc_zgloszenia
ORDER BY md5(z.id_zgloszenia)
"""


def _czas(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M")


def _jedna_linia(tekst: str | None) -> str:
    # Notatki bywają łamane w środku zdania („Wym.\nrolek”): łączymy w jedną linię.
    return " ".join((tekst or "").split())


def opis_zgloszenia(utworzono: datetime, zrodlo: str | None, tresc: str | None, notatki: Sequence[dict]) -> str:
    """Tekst wejścia LLM: zgłoszenie i jego notatki od najstarszej (czas lokalny Serwisownika)."""
    linie = [
        f"Zgłoszenie utworzone: {_czas(utworzono)}",
        f"Źródło zgłoszenia: {zrodlo or 'brak'}",
        f"Treść zgłoszenia: {_jedna_linia(tresc) or 'brak'}",
    ]
    if not notatki:
        linie.append("Notatki: brak")
        return "\n".join(linie)
    linie.append("Notatki (od najstarszej, czas lokalny):")
    for n in sorted(notatki, key=lambda n: n["data_czas"]):
        autor = n["autor"] or "brak"
        rola = AUTORZY.get(autor, "konserwator")
        linie.append(f"[{_czas(n['data_czas'])}] {autor} ({rola}): {_jedna_linia(n['tresc'])}")
    return "\n".join(linie)


def zgloszenia(con: duckdb.DuckDBPyConnection, id_zgloszen: Sequence[str]) -> pd.DataFrame:
    """id_zgloszenia + `tekst` (wejście LLM) dla podanych zgłoszeń, w kolejności md5(id_zgloszenia)."""
    con.register("wybrane", pd.DataFrame({"id_zgloszenia": pd.Series(list(id_zgloszen), dtype="string")}))
    try:
        # fetchall, nie .df(): lista notatek wraca jako list[dict] z datetime, bez NA i typów pandas
        wiersze = con.execute(SQL_ZGLOSZENIA).fetchall()
    finally:
        con.unregister("wybrane")
    return pd.DataFrame(
        {
            "id_zgloszenia": [w[0] for w in wiersze],
            "tekst": [opis_zgloszenia(utw, zr, tr, notatki or []) for _, utw, zr, tr, notatki in wiersze],
        }
    )


def wyciagnij_awarie(
    klient: KlientLLM, rekordy: pd.DataFrame, prompt: Prompt, watki: int = WATKI, postep: int | None = None
) -> pd.DataFrame:
    """Jeden wiersz na zgłoszenie (kolejność wejścia): id_zgloszenia, pola schematu, klucz cache, tokeny, blad.

    Błąd jednego zgłoszenia (np. odpowiedź niespójna ze schematem albo wyczerpane ponowienia SDK) zapisujemy
    w `blad` i idziemy dalej.
    """
    zrobione = [0]

    def jedno(r) -> dict:
        wiersz = {"id_zgloszenia": r.id_zgloszenia, "klucz_cache": klucz_cache(r.tekst, prompt.wersja)}
        try:
            w = klient.zapytaj(r.tekst, prompt, Awaria)
            wiersz |= {**w.dane, "z_cache": w.z_cache, "blad": None}
            wiersz |= {k: getattr(w, k) for k in KOLUMNY_TOKENOW}
        except Exception as e:  # noqa: BLE001 — błąd jednego zgłoszenia nie przerywa ekstrakcji; liczony w wyniku
            wiersz |= {**{p: None for p in POLA}, "z_cache": False, "blad": f"{type(e).__name__}: {e}"[:500]}
            wiersz |= {k: None for k in KOLUMNY_TOKENOW}
        zrobione[0] += 1
        if postep and zrobione[0] % postep == 0:
            print(f"{prompt.wersja}: {zrobione[0]} / {len(rekordy)}", file=sys.stderr, flush=True)
        return wiersz

    with ThreadPoolExecutor(max_workers=watki) as pula:
        wiersze = list(pula.map(jedno, rekordy.itertuples(index=False)))
    wynik = pd.DataFrame(wiersze, columns=["id_zgloszenia", *POLA, "klucz_cache", "z_cache", *KOLUMNY_TOKENOW, "blad"])
    for k in (*KOLUMNY_TOKENOW, "czas_naprawy_h", "pewnosc"):
        wynik[k] = pd.to_numeric(wynik[k], errors="coerce")
    return wynik


def main(argv: Sequence[str] | None = None) -> Path:
    from api.adapters.duckdb_baza import polacz

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zbior", choices=sorted(SQL_ZBIORY), default="zloty_zbior")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--prompt", default=PROMPT)
    arg = parser.parse_args(argv)

    con = polacz()
    ids = [r[0] for r in con.execute(SQL_ZBIORY[arg.zbior]).fetchall()]
    rekordy = zgloszenia(con, ids)
    con.close()
    if arg.limit is not None:
        rekordy = rekordy.head(arg.limit)

    prompt = wczytaj_prompt(arg.prompt)
    print(f"{prompt.wersja}, zbiór {arg.zbior}: {len(rekordy)} zgłoszeń", file=sys.stderr, flush=True)
    wynik = wyciagnij_awarie(KlientLLM(), rekordy, prompt, postep=100)
    KATALOG_WYNIKOW.mkdir(parents=True, exist_ok=True)
    nazwa = f"{prompt.wersja}_{arg.zbior}" + (f"_{arg.limit}" if arg.limit is not None else "")
    plik = KATALOG_WYNIKOW / f"{nazwa}.parquet"
    wynik.to_parquet(plik, index=False)
    ok = wynik[wynik["blad"].isna()]
    print(
        f"zapisano {plik}: {len(wynik)} zgłoszeń, błędów {len(wynik) - len(ok)}, z cache {int(ok['z_cache'].sum())}, "
        f"czy_awaria = true: {int(ok['czy_awaria'].sum())}, tokeny wejścia / wyjścia: "
        f"{int(ok['tokeny_wejscia'].sum())} / {int(ok['tokeny_wyjscia'].sum())}",
        file=sys.stderr,
    )
    return plik


if __name__ == "__main__":
    main()
