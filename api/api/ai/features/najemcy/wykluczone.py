"""Pola wykluczone z cech najemców (lista i uzasadnienie: wykluczone.yaml obok) i pola zakazane w SQL cech."""

import re
from collections.abc import Iterable
from pathlib import Path

import yaml

SCIEZKA_WYKLUCZONYCH = Path(__file__).with_name("wykluczone.yaml")


def wczytaj_wykluczone(sciezka: Path = SCIEZKA_WYKLUCZONYCH) -> dict[str, dict]:
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))


WYKLUCZONE: frozenset[str] = frozenset(wczytaj_wykluczone())

# Kolumny, których SQL cech nie może czytać (poza komentarzami): wynik po migawce z migawki_najemcy, stan na dzień
# eksportu (pms_lokale.status, czynsz_katalogowy, status zgłoszeń) i dane osobowe najemcy. Opis:
# docs/przecieki_najemcy.md.
ZAKAZANE_W_SQL: frozenset[str] = WYKLUCZONE | {
    "odejdzie",
    "id_umowy_nastepnej",
    "przeprowadzka",
    "id_najmu_przeprowadzki",
    "data_wyprowadzenia",
    "powod_odejscia",
    "wypowiedzenie_data",
    "wypowiedzenie_przed_migawka",
    "czynsz_katalogowy",
    "status",
    "pms_najemcy",
    "retencja_decyzje",
}


class CechaWykluczona(ValueError):
    pass


def sprawdz_brak_wykluczonych(kolumny: Iterable[str], gdzie: str) -> None:
    """Błąd, gdy którakolwiek kolumna jest wykluczona: dokładnie albo z przedrostkiem/przyrostkiem."""
    zle = sorted(
        str(k)
        for k in kolumny
        if any(str(k) == w or str(k).endswith(f"_{w}") or str(k).startswith(f"{w}_") for w in WYKLUCZONE)
    )
    if zle:
        raise CechaWykluczona(f"{gdzie}: cechy wykluczone (features/najemcy/wykluczone.yaml): {', '.join(zle)}")


def zakazane_w_sql(sql: str) -> list[str]:
    """Zakazane identyfikatory użyte w SQL (komentarze `--` pomijamy)."""
    bez_komentarzy = "\n".join(linia.split("--", 1)[0] for linia in sql.splitlines())
    slowa = set(re.findall(r"[a-z_][a-z0-9_]*", bez_komentarzy.lower()))
    return sorted(slowa & ZAKAZANE_W_SQL)
