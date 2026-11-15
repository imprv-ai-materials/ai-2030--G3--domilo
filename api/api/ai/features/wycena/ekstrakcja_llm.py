"""Ekstrakcja cech lokalu przez LLM: opisy dopasowanych ofert, opisy Domilo, zdjęcia (docs/b1_v4_llm_cechy.md).

Uruchomienie (wymaga domilo.duckdb i klucza w środowisku), z katalogu głównego repozytorium:
    set -a && . ./.env && set +a
    cd api && poetry run python -m api.ai.features.wycena.ekstrakcja_llm

Zbiory:
- opisy_ofert:   20 500 ofert z radar_dopasowania, opis bez kwot (bez_kwot), prompt cechy_lokalu_v1;
- opisy_domilo:  7 200 lokali z lokale_domilo_opisy, opis bez czynszu (bez_kwot), prompt cechy_lokalu_v1;
- zdjecia_ofert: oferty ze zdjęciami, których dopasowana transakcja ma akt od 2026-01-01 (okres testu),
                 4 zdjęcia na ofertę, prompt cechy_lokalu_zdjecia_v1;
- zdjecia_domilo: lokale Domilo ze zdjęciami (300 lokali z operatem kontrolnym), jak wyżej.
Wyniki: cechy_llm/<zbior>.parquet (surowe odpowiedzi + tokeny + błąd). Ponowne uruchomienie czyta cache klienta.
"""

import sys
import time
from pathlib import Path

import pandas as pd
from api.adapters.duckdb_baza import KATALOG_DANYCH, polacz
from api.adapters.llm_client import MODEL, KlientLLM
from api.ai.features.wycena.cechy_llm import POLA, wyciagnij
from api.ai.features.wycena.ceny_w_opisie import bez_kwot
from api.ai.llm.prompty import wczytaj_prompt

KATALOG_WYNIKOW = Path(__file__).with_name("cechy_llm")
PROMPT_OPISU = "cechy_lokalu_v1"
PROMPT_ZDJEC = "cechy_lokalu_zdjecia_v1"
POCZATEK_TESTU = "2026-01-01"
WATKI = 16

SQL_OPISY_OFERT = """
SELECT o.id_oferty AS id, o.opis AS tekst FROM radar_dopasowania d JOIN radar_oferty o USING (id_oferty)
ORDER BY o.id_oferty
"""
SQL_OPISY_DOMILO = "SELECT id_lokalu AS id, opis_marketingowy AS tekst FROM lokale_domilo_opisy ORDER BY id_lokalu"
SQL_ZDJECIA_OFERT = f"""
SELECT m.id_oferty AS id, list(m.pomieszczenie ORDER BY m.sciezka) AS pomieszczenia,
       list(m.sciezka ORDER BY m.sciezka) AS sciezki
FROM metadane m
JOIN radar_dopasowania d USING (id_oferty)
JOIN rcn_transakcje t USING (id_transakcji)
WHERE t.data_aktu >= TIMESTAMP '{POCZATEK_TESTU}'
GROUP BY m.id_oferty ORDER BY m.id_oferty
"""
SQL_ZDJECIA_DOMILO = """
SELECT id_lokalu AS id, list(pomieszczenie ORDER BY sciezka) AS pomieszczenia, list(sciezka ORDER BY sciezka) AS sciezki
FROM metadane WHERE id_lokalu IS NOT NULL GROUP BY id_lokalu ORDER BY id_lokalu
"""


def rekordy_opisow(con, sql: str) -> pd.DataFrame:
    df = con.execute(sql).df()
    return df.assign(tekst=df["tekst"].map(bez_kwot))


def rekordy_zdjec(con, sql: str) -> pd.DataFrame:
    df = con.execute(sql).df()
    katalog_radaru = KATALOG_DANYCH / "radar"
    return pd.DataFrame(
        {
            "id": df["id"],
            "tekst": df["pomieszczenia"].map(lambda p: ", ".join(p)),
            "obrazy": df["sciezki"].map(lambda s: [katalog_radaru / x for x in s]),
        }
    )


def _f(x: float, miejsca: int = 0) -> str:
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def podsumowanie(nazwa: str, wynik: pd.DataFrame, sekundy: float, prompt: str) -> dict:
    ok = wynik[wynik["blad"].isna()]
    n = len(ok)
    return {
        "zbior": nazwa,
        "prompt": prompt,
        "rekordy": len(wynik),
        "bledy": int(wynik["blad"].notna().sum()),
        "z_cache_klienta": int(wynik["z_cache"].sum()),
        "tokeny_wejscia": int(ok["tokeny_wejscia"].sum()),
        "w_tym_z_cache_OpenAI": int(ok["tokeny_wejscia_z_cache"].sum()),
        "tokeny_wyjscia": int(ok["tokeny_wyjscia"].sum()),
        "wejscie_na_1000": _f(1000 * ok["tokeny_wejscia"].sum() / n),
        "z_cache_OpenAI_na_1000": _f(1000 * ok["tokeny_wejscia_z_cache"].sum() / n),
        "wyjscie_na_1000": _f(1000 * ok["tokeny_wyjscia"].sum() / n),
        "czas_s": _f(sekundy, 1),
    }


def main(tylko: set[str] | None = None) -> None:
    con = polacz()
    zbiory = {
        "opisy_ofert": (rekordy_opisow(con, SQL_OPISY_OFERT), PROMPT_OPISU),
        "opisy_domilo": (rekordy_opisow(con, SQL_OPISY_DOMILO), PROMPT_OPISU),
        "zdjecia_ofert": (rekordy_zdjec(con, SQL_ZDJECIA_OFERT), PROMPT_ZDJEC),
        "zdjecia_domilo": (rekordy_zdjec(con, SQL_ZDJECIA_DOMILO), PROMPT_ZDJEC),
    }
    con.close()
    klient = KlientLLM()
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    wiersze = []
    for nazwa, (rekordy, nazwa_promptu) in zbiory.items():
        if tylko and nazwa not in tylko:
            continue
        print(f"{nazwa}: {len(rekordy)} rekordów", file=sys.stderr, flush=True)
        start = time.monotonic()
        wynik = wyciagnij(klient, rekordy, wczytaj_prompt(nazwa_promptu), watki=WATKI, postep=1000)
        sekundy = time.monotonic() - start
        wynik.to_parquet(KATALOG_WYNIKOW / f"{nazwa}.parquet", index=False)
        wiersze.append(podsumowanie(nazwa, wynik, sekundy, nazwa_promptu))
        print(f"{nazwa}: gotowe, błędów {wiersze[-1]['bledy']}, {sekundy:.0f} s", file=sys.stderr, flush=True)

    tab = pd.DataFrame(wiersze)
    print(f"Model: {MODEL}\n")
    print("| " + " | ".join(tab.columns) + " |\n|" + "---|" * len(tab.columns))
    for w in tab.itertuples(index=False):
        print("| " + " | ".join(str(x) for x in w) + " |")
    print(f"\nPola schematu: {', '.join(POLA)}")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
