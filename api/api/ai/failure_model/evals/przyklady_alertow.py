"""Alerty z okresu testowego: produkcyjne zadania `cechy-wind` + `ryzyko-wind` dla każdego poniedziałku testu
(2026-01-05 – 2026-09-21) na KOPII domilo.duckdb, alerty wysłane do atrapy Serwisownika (dev/serwisownik_mock/,
`pypyr serwisownik_mock`; adres SERWISOWNIK_URL albo domyślny http://127.0.0.1:8103).

Wynik (docs/b4_ryzyko_dzienne.md): zgłoszenia przyjęte przez atrapę (GET /api/zgloszenia) z wynikiem z `dni_wind`
(czy w 7 dni zaczęła się awaria, jej podzespół, godziny do startu) w pliku `--wyjscie` (JSON, poza gitem).
Przykłady do raportu wybiera reguła ustalona przed uruchomieniem: alert z pozycji 1 z trzech pierwszych poniedziałków.
Uruchomienie: `cd api && poetry run python -m api.ai.failure_model.evals.przyklady_alertow --wyjscie /tmp/alerty.json`.
"""

import argparse
import json
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd
from api.adapters import ryzyko_wind, serwisownik
from api.adapters.duckdb_baza import SCIEZKA_BAZY, polaczenie
from api.contexts_boundaries.maintenance_bc import cechy_dzienne, ryzyko_dzienne

PIERWSZY, OSTATNI = date(2026, 1, 5), date(2026, 9, 21)  # poniedziałki testu v2b (2026-01-01 – 2026-09-22)


def poniedzialki() -> list[date]:
    return [PIERWSZY + timedelta(weeks=i) for i in range((OSTATNI - PIERWSZY).days // 7 + 1)]


def uruchom(katalog: Path) -> None:
    baza = katalog / "domilo.duckdb"
    shutil.copy(SCIEZKA_BAZY, baza)
    with polaczenie(tylko_odczyt=False, sciezka=baza) as con:  # kopia ma zacząć bez historii ocen i alarmów
        ryzyko_wind.wyczysc(con)
    krok = lambda _id, h, *a: h(*a)  # noqa: E731
    klient = serwisownik.KlientSerwisownika()
    for d in poniedzialki():
        cechy_dzienne.wykonaj_cechy_wind(krok, d.isoformat(), str(katalog / "magazyn"), baza, katalog / "dzienne")
        ryzyko_dzienne.wykonaj_ryzyko_wind(krok, "test", d.isoformat(), baza, katalog / "dzienne", klient)


def z_wynikiem(zgloszenia: dict) -> list[dict]:
    with polaczenie() as con:
        cel = con.execute("SELECT id_windy, dzien, awaria_7d, podzespol, godziny_do_startu FROM dni_wind").df()
    cel["dzien"] = pd.to_datetime(cel["dzien"]).dt.date.astype(str)
    cel = cel.set_index(["id_windy", "dzien"])
    wyniki = []
    for klucz, z in sorted(
        zgloszenia.items(), key=lambda kv: (kv[1]["tresc"]["alarm"]["dzien"], kv[1]["tresc"]["alarm"]["pozycja"])
    ):
        t, a = z["tresc"], z["tresc"]["alarm"]
        fakt = cel.loc[(a["id_windy"], a["dzien"])] if (a["id_windy"], a["dzien"]) in cel.index else None
        wyniki.append(
            {
                "id_zgloszenia": z["id_zgloszenia"],
                "klucz_idempotencji": klucz,
                "zgloszenie": t,
                "awaria_7d": None if fakt is None else int(fakt["awaria_7d"]),
                "podzespol_awarii": None if fakt is None or pd.isna(fakt["podzespol"]) else fakt["podzespol"],
                "godziny_do_startu": (
                    None
                    if fakt is None or pd.isna(fakt["godziny_do_startu"])
                    else round(float(fakt["godziny_do_startu"]), 1)
                ),
            }
        )
    return wyniki


if __name__ == "__main__":
    arg = argparse.ArgumentParser()
    arg.add_argument("--wyjscie", required=True)
    wyjscie = Path(arg.parse_args().wyjscie)
    url = serwisownik.KlientSerwisownika().url
    with tempfile.TemporaryDirectory() as tmp:
        uruchom(Path(tmp))
    stan = httpx.get(f"{url}{serwisownik.SCIEZKA_ZGLOSZEN}", timeout=30).json()["zgloszenia"]
    wyniki = z_wynikiem(stan)
    wyjscie.write_text(json.dumps(wyniki, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"zgłoszenia: {len(wyniki)}, plik: {wyjscie}")
