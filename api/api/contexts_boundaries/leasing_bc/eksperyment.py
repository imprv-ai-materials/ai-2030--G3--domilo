"""Eksperyment switchback kolejki (docs/kolejka_eksperyment.md): plan tygodni, wariant dnia, ziarno części losowej.

- Warianty: `model` (kolejka według EV z modelu z current.yaml) i `od_najnowszego` (obecny sposób pracy: najnowsze
  zapytania najpierw). Wariant obowiązuje cały tydzień (poniedziałek 05:30 – następny poniedziałek 05:30) i wszystkich
  doradców.
- Plan: tygodnie w parach; w każdej parze jeden tydzień modelu i jeden kontrolny, kolejność w parze losowa
  (`wylosuj_plan`, ziarno zapisane w planie). Pary równoważą warianty w czasie (sezon, święta, urlopy) i dają równą
  liczbę tygodni w każdym wariancie także po wcześniejszym zakończeniu na granicy pary.
- Plan obowiązuje, gdy istnieje plik `eksperyment_plan.yaml` obok tego modułu. Bez planu (i poza tygodniami planu)
  zadanie układa kolejkę według modelu.
- Część losowa: w każdej kolejce doradcy UDZIAL_LOSOWYCH (5%) pozycji zajmują zapytania wylosowane z otwartych
  zapytań miasta, na losowych pozycjach, w obu wariantach i poza eksperymentem. Dają ocenę modelu wolną od tego, kogo
  model wybrał (prawdopodobieństwo wylosowania zapisujemy w kolejka_historia). Ziarno zależy tylko od dnia, miasta
  i wariantu, więc dwa przebiegi tego samego dnia dają tę samą kolejkę (idempotencja webhooka do CRM).
"""

import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

WARIANTY = ("model", "od_najnowszego")
WARIANT_DOMYSLNY = "model"
UDZIAL_LOSOWYCH = 0.05
SCIEZKA_PLANU = Path(__file__).with_name("eksperyment_plan.yaml")


def poniedzialek(dzien: date) -> date:
    return dzien - timedelta(days=dzien.weekday())


def wylosuj_plan(start: date, tygodnie: int, ziarno: int) -> dict:
    """Plan: `tygodnie` tygodni od poniedziałku `start`, w parach z losową kolejnością wariantów w parze."""
    if start.weekday() != 0:
        raise ValueError(f"Plan zaczyna się w poniedziałek, a {start} to nie poniedziałek")
    if tygodnie < 2 or tygodnie % 2:
        raise ValueError("Liczba tygodni musi być parzysta (pary tydzień modelu + tydzień kontrolny)")
    rng = np.random.default_rng(ziarno)
    plan = []
    for para in range(tygodnie // 2):
        kolejnosc = list(rng.permutation(WARIANTY))
        for i, wariant in enumerate(kolejnosc):
            tydzien = start + timedelta(weeks=2 * para + i)
            plan.append({"tydzien": tydzien.isoformat(), "para": para + 1, "wariant": str(wariant)})
    return {
        "start": start.isoformat(),
        "tygodnie": tygodnie,
        "ziarno": int(ziarno),
        "wylosowano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": plan,
    }


def wczytaj_plan(sciezka: Path = SCIEZKA_PLANU) -> dict | None:
    sciezka = Path(sciezka)
    if not sciezka.exists():
        return None
    plan = yaml.safe_load(sciezka.read_text(encoding="utf-8"))
    nieznane = {p["wariant"] for p in plan["plan"]} - set(WARIANTY)
    if nieznane:
        raise ValueError(f"{sciezka}: nieznane warianty {sorted(nieznane)}")
    return plan


def zapisz_plan(plan: dict, sciezka: Path = SCIEZKA_PLANU) -> None:
    if Path(sciezka).exists():
        raise FileExistsError(f"{sciezka} już istnieje: planu w trakcie eksperymentu nie losujemy ponownie")
    Path(sciezka).write_text(yaml.safe_dump(plan, allow_unicode=True, sort_keys=False), encoding="utf-8")


def wariant_dnia(dzien: date, plan: dict | None) -> str:
    """Wariant kolejki na dzień (tydzień planu, w którym leży dzień); poza planem WARIANT_DOMYSLNY."""
    if plan:
        tydzien = poniedzialek(dzien).isoformat()
        for p in plan["plan"]:
            if p["tydzien"] == tydzien:
                return p["wariant"]
    return WARIANT_DOMYSLNY


def ziarno(*czesci: str) -> int:
    """Ziarno losowania z napisów (np. dzień, miasto, wariant): to samo wejście = ta sama kolejka."""
    return int(hashlib.sha256(":".join(czesci).encode("utf-8")).hexdigest()[:16], 16)


def liczba_losowych(dlugosc_kolejki: int, udzial: float = UDZIAL_LOSOWYCH) -> int:
    """Pozycje losowe w kolejce doradcy: udział × długość, zaokrąglony połówkowo w górę (40 pozycji -> 2)."""
    return int(udzial * dlugosc_kolejki + 0.5)
