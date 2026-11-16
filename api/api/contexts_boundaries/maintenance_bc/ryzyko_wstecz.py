"""Symulacja wstecz zadań `cechy-wind` + `ryzyko-wind` dla zakresu dni (dane historyczne dla panelu technicznego).

Dla każdego dnia od `od` do `do` po kolei: te same kroki co funkcje Inngest (maintenance_bc/cechy_dzienne.py,
ryzyko_dzienne.py), z `id_przebiegu = symulacja_wstecz:<dzien>`. Zapis do tabel ryzyko_wind i alarmy_wind w
domilo.duckdb (zastępuje dzień ryzyka; alarmy: pierwsza decyzja dnia zostaje), przerwa 7 dni liczona z alarmów
zapisanych w poprzednich dniach. Zgłoszenia alertów idą do Serwisownika (SERWISOWNIK_URL, domyślnie atrapa
`pypyr serwisownik_mock`), chyba że `--bez-serwisownika` (wtedy kroki `serwisownik-<id_windy>` są pomijane i alarmy
nie mają `id_zgloszenia`).

Ręcznie: `pypyr ryzyko_wind_wstecz [od=RRRR-MM-DD] [do=RRRR-MM-DD]` albo
`cd api && poetry run python -m api.contexts_boundaries.maintenance_bc.ryzyko_wstecz OD DO [--bez-serwisownika]`.
Domyślny zakres (OD_DOMYSLNIE – DO_DOMYSLNIE): 8 pełnych tygodni alertów przed końcem danych + tydzień na przerwę.
"""

import json
import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from api.adapters.duckdb_baza import SCIEZKA_BAZY
from api.contexts_boundaries.maintenance_bc import cechy_dzienne, ryzyko_dzienne

OD_DOMYSLNIE = date(2026, 7, 27)  # poniedziałek; tydzień przed 8 tygodniami alertów
DO_DOMYSLNIE = date(2026, 9, 30)  # dzień eksportu (CLAUDE.md)
PRZEBIEG = "symulacja_wstecz"


def krok_z_pominieciem(pomijaj_serwisownik: bool) -> Callable:
    def krok(id_kroku: str, handler: Callable, *args):
        if pomijaj_serwisownik and id_kroku.startswith("serwisownik-"):
            return {"pominieto": True}
        return json.loads(json.dumps(handler(*args), default=str))

    return krok


def wykonaj(
    od: date,
    do: date,
    pomijaj_serwisownik: bool = False,
    sciezka: Path = SCIEZKA_BAZY,
    katalog: Path = cechy_dzienne.KATALOG_DZIENNY,
    katalog_magazynu: str | None = None,
    klient=None,
) -> list[dict]:
    krok = krok_z_pominieciem(pomijaj_serwisownik)
    wyniki = []
    dzien = od
    while dzien <= do:
        d = dzien.isoformat()
        cechy_dzienne.wykonaj_cechy_wind(krok, d, katalog_magazynu, sciezka, katalog)
        r = ryzyko_dzienne.wykonaj_ryzyko_wind(krok, f"{PRZEBIEG}:{d}", d, sciezka, katalog, klient)
        wyniki.append(
            {
                "dzien": d,
                "windy": r["ryzyko"]["windy"],
                "zapasowa": r["ryzyko"]["zapasowa"],
                "alarmy": [(a["id_windy"], a["tryb_oceny"]) for a in r["alarmy"]["alarmy"]],
            }
        )
        print(json.dumps(wyniki[-1], ensure_ascii=False), flush=True)
        dzien += timedelta(days=1)
    return wyniki


if __name__ == "__main__":
    argumenty = [a for a in sys.argv[1:] if a and not a.startswith("--")]
    od = date.fromisoformat(argumenty[0]) if argumenty else OD_DOMYSLNIE
    do = date.fromisoformat(argumenty[1]) if len(argumenty) > 1 else DO_DOMYSLNIE
    wykonaj(od, do, pomijaj_serwisownik="--bez-serwisownika" in sys.argv)
