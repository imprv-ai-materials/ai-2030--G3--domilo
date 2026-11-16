"""Atrapa Serwisownika: przyjmuje zgłoszenia z alarmów o ryzyku awarii wind (api/api/adapters/serwisownik_alarmy.py).

Uruchomienie: `pypyr mock_serwisownik` (port 8103) albo
    poetry run uvicorn app:app --app-dir dev/mock_serwisownik --port 8103
Stan w pliku JSON (`MOCK_SERWISOWNIK_STAN`, domyślnie dev/mock_serwisownik/stan.json, poza gitem).

- `POST /api/zgloszenia`: zgłoszenie z `klucz_idempotencji`. Nowy klucz: nowe zgłoszenie `A000001`, `A000002`, …
  (200, `utworzono = true`). Ten sam klucz i ta sama treść: 200 z tym samym id, `utworzono = false`. Ten sam klucz
  i inna treść: 409, nic nie zapisane.
- `GET /api/zgloszenia`: wszystkie zgłoszenia po kluczu; `DELETE /api/zgloszenia`: czyści stan.
"""

import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException

SCIEZKA_DOMYSLNA = Path(__file__).resolve().with_name("stan.json")
WYMAGANE = ("klucz_idempotencji", "id_budynku", "id_urzadzenia", "typ_urzadzenia", "kategoria", "alarm")


def _kanoniczny(obiekt) -> str:
    return json.dumps(obiekt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utworz_aplikacje(sciezka: Path | None = None) -> FastAPI:
    plik = Path(sciezka or os.environ.get("MOCK_SERWISOWNIK_STAN", SCIEZKA_DOMYSLNA))
    blokada = threading.Lock()
    aplikacja = FastAPI(title="Atrapa Serwisownika: zgłoszenia z alarmów wind", version="1.0")

    def wczytaj() -> dict[str, dict]:
        return json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else {}

    def zapisz(stan: dict[str, dict]) -> None:
        plik.parent.mkdir(parents=True, exist_ok=True)
        tymczasowy = plik.with_suffix(".tmp")
        tymczasowy.write_text(json.dumps(stan, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
        os.replace(tymczasowy, plik)

    @aplikacja.post("/api/zgloszenia")
    def przyjmij(zgloszenie: dict):
        brak = [k for k in WYMAGANE if k not in zgloszenie]
        if brak:
            raise HTTPException(422, f"brak pól: {', '.join(brak)}")
        klucz = zgloszenie["klucz_idempotencji"]
        with blokada:
            stan = wczytaj()
            znane = stan.get(klucz)
            if znane is not None:
                if _kanoniczny(znane["tresc"]) != _kanoniczny(zgloszenie):
                    raise HTTPException(409, f"klucz {klucz} ma już zgłoszenie {znane['id_zgloszenia']} z inną treścią")
                return {"id_zgloszenia": znane["id_zgloszenia"], "utworzono": False}
            id_zgloszenia = f"A{len(stan) + 1:06d}"
            stan[klucz] = {"id_zgloszenia": id_zgloszenia, "tresc": zgloszenie}
            zapisz(stan)
        return {"id_zgloszenia": id_zgloszenia, "utworzono": True}

    @aplikacja.get("/api/zgloszenia")
    def lista():
        stan = wczytaj()
        return {"liczba": len(stan), "zgloszenia": dict(sorted(stan.items()))}

    @aplikacja.delete("/api/zgloszenia")
    def wyczysc():
        with blokada:
            plik.unlink(missing_ok=True)
        return {"liczba": 0}

    return aplikacja


app = utworz_aplikacje()
