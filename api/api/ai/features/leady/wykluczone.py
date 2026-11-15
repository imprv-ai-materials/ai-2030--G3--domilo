"""Cechy wykluczone z modelu kolejki i z promptów (lista i uzasadnienie: wykluczone.yaml obok)."""

from collections.abc import Iterable
from pathlib import Path

import yaml

SCIEZKA_WYKLUCZONYCH = Path(__file__).with_name("wykluczone.yaml")


def wczytaj_wykluczone(sciezka: Path = SCIEZKA_WYKLUCZONYCH) -> dict[str, dict]:
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))


WYKLUCZONE: frozenset[str] = frozenset(wczytaj_wykluczone())


class CechaWykluczona(ValueError):
    pass


def sprawdz_brak_wykluczonych(kolumny: Iterable[str], gdzie: str) -> None:
    """Błąd, gdy którakolwiek kolumna jest wykluczona: dokładnie albo z przedrostkiem/przyrostkiem (`wklad_jezyk`)."""
    zle = sorted(
        str(k)
        for k in kolumny
        if any(str(k) == w or str(k).endswith(f"_{w}") or str(k).startswith(f"{w}_") for w in WYKLUCZONE)
    )
    if zle:
        raise CechaWykluczona(f"{gdzie}: cechy wykluczone (features/leady/wykluczone.yaml): {', '.join(zle)}")
