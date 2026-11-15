"""Podział zapytań dla modeli kolejki uczonych na historii (v2 i dalej).

- trening: zamknięte, niecenzurowane zapytania utworzone 2023-01-01 – 2026-02-28 (czas warszawski), bez okna
  migracji CRM (2025-03-03 – 2025-04-13). Zamknięte = `leady_cel.zamkniety` (umowa albo utrata wg historii statusów).
- test: wszystkie niecenzurowane zapytania utworzone 2026-03-01 – 2026-06-30 („zwykły” test: wynik zależy też od
  tego, do kogo doradcy oddzwonili).
- okno_migracji: wszystkie 5 320 zapytań z okna (każde obsłużone przez call center).

Test i okno obejmują wszystkie niecenzurowane zapytania (także niezamknięte), tak jak ocena v0/v1.
"""

import pandas as pd

STREFA = "Europe/Warsaw"
TRENING_OD, TRENING_DO = pd.Timestamp("2023-01-01", tz=STREFA), pd.Timestamp("2026-03-01", tz=STREFA)
TEST_OD, TEST_DO = pd.Timestamp("2026-03-01", tz=STREFA), pd.Timestamp("2026-07-01", tz=STREFA)
OPIS = {
    "trening": "zamknięte, niecenzurowane zapytania 2023-01-01 – 2026-02-28 bez okna migracji",
    "test": "wszystkie niecenzurowane zapytania 2026-03-01 – 2026-06-30",
    "okno_migracji": "wszystkie zapytania z okna migracji 2025-03-03 – 2025-04-13",
}


def podziel(zbior: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Zbiór z `wczytaj_zbior` (wymaga kolumny `zamkniety`) -> {trening, test, okno_migracji} (indeks od 0)."""
    t = zbior["utworzono"]
    znany = zbior["umowa_45d"].notna() & ~zbior["cenzurowany"]
    maski = {
        "trening": znany & zbior["zamkniety"] & ~zbior["okno_migracji"] & (t >= TRENING_OD) & (t < TRENING_DO),
        "test": znany & (t >= TEST_OD) & (t < TEST_DO),
        "okno_migracji": znany & zbior["okno_migracji"],
    }
    return {nazwa: zbior[m].reset_index(drop=True) for nazwa, m in maski.items()}
