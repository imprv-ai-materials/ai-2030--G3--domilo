"""Alarm o ryzyku awarii windy -> zgłoszenie w Serwisowniku. Atrapa: dev/mock_serwisownik/ (`pypyr mock_serwisownik`).

Kontrakt (przyjęty w tej pracy, do potwierdzenia z zespołem Serwisownika; atrapa zachowuje się tak samo):
- `POST {SERWISOWNIK_URL}/api/zgloszenia` z ciałem zgłoszenia: pola jak w serwis_zgloszenia (`id_budynku`,
  `id_urzadzenia` = id windy, `typ_urzadzenia` = `winda`, `zrodlo` = `model_awarii`, `kategoria` = `przegląd`,
  `priorytet` = `normalny`, `tresc_zgloszenia`, `firma_serwisowa`) + `klucz_idempotencji` i `alarm` (szczegóły
  alarmu: dzień, pozycja, ryzyko, sygnały, podzespoły, wersja modelu).
- `klucz_idempotencji` = `alarm-windy:{id_windy}:{dzien_alarmu}`. Serwisownik zakłada zgłoszenie tylko przy
  pierwszym kluczu. Ten sam klucz i ta sama treść: 200 z tym samym `id_zgloszenia` i `utworzono = false`.
  Ten sam klucz i inna treść: 409 (zgłaszamy jako `KonfliktIdempotencji`; ponowienie nic nie da).
- Odpowiedź 200: `{"id_zgloszenia": "...", "utworzono": true|false}`.
Inne błędy HTTP i sieci przechodzą dalej jako wyjątki httpx, więc Inngest ponawia krok wysyłki.

Adres: `SERWISOWNIK_URL` (domyślnie atrapa http://127.0.0.1:8103); opcjonalny `SERWISOWNIK_TOKEN` (Bearer).
"""

import os

import httpx

URL_DOMYSLNY = "http://127.0.0.1:8103"
SCIEZKA = "/api/zgloszenia"
LIMIT_CZASU_S = 30.0


class KonfliktIdempotencji(RuntimeError):
    """Serwisownik ma już zgłoszenie z tym kluczem, ale z inną treścią."""


def klucz_idempotencji(id_windy: str, dzien_alarmu: str) -> str:
    return f"alarm-windy:{id_windy}:{dzien_alarmu}"


class KlientSerwisownika:
    def __init__(self, url: str | None = None, http: httpx.Client | None = None, token: str | None = None):
        self.url = (url or os.environ.get("SERWISOWNIK_URL") or URL_DOMYSLNY).rstrip("/")
        self._http = http
        self.token = token if token is not None else os.environ.get("SERWISOWNIK_TOKEN")

    def zglos_alarm(self, zgloszenie: dict) -> dict:
        """Wysyła zgłoszenie (pola w opisie modułu, z `alarm.id_windy` i `alarm.dzien`); zwraca odpowiedź 200."""
        alarm = zgloszenie["alarm"]
        tresc = {**zgloszenie, "klucz_idempotencji": klucz_idempotencji(alarm["id_windy"], alarm["dzien"])}
        naglowki = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        klient = self._http or httpx.Client(timeout=LIMIT_CZASU_S)
        try:
            odp = klient.post(f"{self.url}{SCIEZKA}", json=tresc, headers=naglowki)
        finally:
            if self._http is None:
                klient.close()
        if odp.status_code == 409:
            raise KonfliktIdempotencji(odp.text[:500])
        odp.raise_for_status()
        wynik = odp.json()
        return {"id_zgloszenia": str(wynik["id_zgloszenia"]), "utworzono": bool(wynik["utworzono"])}
