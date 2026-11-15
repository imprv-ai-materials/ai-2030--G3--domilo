"""Słownik powodów pominięcia pozycji kolejki przez doradcę (pole „powód pominięcia” w CRM).

Kody podał użytkownik (czat 2026-11-15): znam_klienta, brak_lokalu, duplikat, inne. Opisy są tylko etykietami
w panelu. Ten słownik jest jedynym źródłem kodów dla tabeli `kolejka_pominiecia` (CHECK), API (`POST /leads/skips`)
i panelu; atrapa CRM (dev/mock_lejek/app.py) ma własną kopię, a test pilnuje zgodności.
"""

POWODY_POMINIECIA: dict[str, str] = {
    "znam_klienta": "znam klienta (kontakt poza kolejką)",
    "brak_lokalu": "brak pasującego lokalu",
    "duplikat": "duplikat innego zapytania",
    "inne": "inny powód (opis w komentarzu)",
}
# Dla „inne” komentarz jest wymagany: bez niego kierownik nie wie, co się stało.
POWODY_Z_KOMENTARZEM = ("inne",)
