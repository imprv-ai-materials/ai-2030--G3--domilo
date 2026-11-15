"""Webhook do CRM: dzienne kolejki doradców (lejek sprzedaży). Atrapa CRM: dev/mock_lejek/ (`pypyr mock_lejek`).

Kontrakt (atrapa dev/mock_lejek/app.py zachowuje się tak samo):
- `POST {CRM_LEJEK_URL}/webhook/kolejka-doradcy` z ciałem `{"pozycje": [...]}`, każda pozycja z polem
  `klucz_idempotencji` = `"{id_leada}:{data_kolejki}"`.
- CRM zapisuje pozycję tylko przy pierwszym kluczu. Ten sam klucz z tą samą treścią to powtórzenie: odpowiedź 200,
  stan się nie zmienia. Ten sam klucz z inną treścią to konflikt: 409 dla całej paczki i nic nie jest zapisane.
- Odpowiedź 200: `{"utworzono": n, "powtorzenia": n}`.
Konflikt zgłaszamy jako `KonfliktIdempotencji` (ponowienie nic nie da: trzeba sprawdzić, co zmieniło kolejkę).
Inne błędy HTTP i sieci przechodzą dalej jako wyjątki httpx, więc Inngest ponawia krok webhooka.

Adres: zmienna `CRM_LEJEK_URL` (domyślnie atrapa http://127.0.0.1:8102); opcjonalny token `CRM_LEJEK_TOKEN`
(nagłówek Authorization: Bearer).
"""

import os
from collections.abc import Iterable

import httpx

URL_DOMYSLNY = "http://127.0.0.1:8102"
SCIEZKA_WEBHOOKA = "/webhook/kolejka-doradcy"
LIMIT_CZASU_S = 30.0


class KonfliktIdempotencji(RuntimeError):
    """CRM ma już pozycję z tym kluczem, ale z inną treścią."""


def klucz_idempotencji(id_leada: str, data_kolejki: str) -> str:
    return f"{id_leada}:{data_kolejki}"


class KlientLejka:
    def __init__(self, url: str | None = None, http: httpx.Client | None = None, token: str | None = None):
        self.url = (url or os.environ.get("CRM_LEJEK_URL") or URL_DOMYSLNY).rstrip("/")
        self._http = http
        self.token = token if token is not None else os.environ.get("CRM_LEJEK_TOKEN")

    def _klient(self) -> httpx.Client:
        return self._http or httpx.Client(timeout=LIMIT_CZASU_S)

    def wyslij_kolejke(self, pozycje: Iterable[dict]) -> dict:
        """Wysyła pozycje kolejki (pola z adapters/kolejka_doradcow.POLA_POZYCJI) z kluczami idempotencji."""
        tresc = [{**p, "klucz_idempotencji": klucz_idempotencji(p["id_leada"], p["data_kolejki"])} for p in pozycje]
        if not tresc:
            return {"utworzono": 0, "powtorzenia": 0}
        naglowki = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        klient = self._klient()
        try:
            odp = klient.post(f"{self.url}{SCIEZKA_WEBHOOKA}", json={"pozycje": tresc}, headers=naglowki)
        finally:
            if self._http is None:
                klient.close()
        if odp.status_code == 409:
            raise KonfliktIdempotencji(odp.text[:500])
        odp.raise_for_status()
        wynik = odp.json()
        return {"utworzono": int(wynik["utworzono"]), "powtorzenia": int(wynik["powtorzenia"])}
