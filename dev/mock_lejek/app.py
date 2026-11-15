"""Atrapa CRM (lejek sprzedaży) dla webhooka kolejek doradców (api/api/adapters/crm_lejek.py).

Uruchomienie: `pypyr mock_lejek` (port 8102) albo
    poetry run uvicorn app:app --app-dir dev/mock_lejek --port 8102
Stan trzymamy w pliku JSON (`MOCK_LEJEK_STAN`, domyślnie dev/mock_lejek/stan.json, poza gitem), żeby przetrwał
restart i dało się go porównać między przebiegami.

- `POST /webhook/kolejka-doradcy` `{"pozycje": [...]}`: każda pozycja ma `klucz_idempotencji` = `id_leada:data_kolejki`.
  Nowy klucz: zapis. Ten sam klucz i ta sama treść: powtórzenie, stan bez zmian. Ten sam klucz i inna treść:
  409 dla całej paczki, nic nie zapisane.
- `GET /stan`: wszystkie pozycje po kluczu + `skrot` (SHA-256 z kanonicznego JSON-u pozycji).
- `GET /statystyki`: liczba żądań, zapisów, powtórzeń i konfliktów od startu procesu (nie jest częścią stanu).
- `DELETE /stan`: czyści stan (do testów i pokazu).
"""

import hashlib
import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

SCIEZKA_DOMYSLNA = Path(__file__).resolve().with_name("stan.json")
WYMAGANE = ("klucz_idempotencji", "id_leada", "data_kolejki", "id_doradcy", "pozycja")


class Paczka(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pozycje: list[dict]


def _kanoniczny(obiekt) -> str:
    return json.dumps(obiekt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _skrot(pozycje: dict[str, dict]) -> str:
    return hashlib.sha256(_kanoniczny(pozycje).encode("utf-8")).hexdigest()


class Magazyn:
    """Stan atrapy: klucz idempotencji -> pozycja (dokładnie ta treść, którą CRM przyjął jako pierwszą)."""

    def __init__(self, sciezka: Path):
        self.sciezka = Path(sciezka)
        self.blokada = threading.Lock()
        self.statystyki = {"zadania": 0, "utworzono": 0, "powtorzenia": 0, "konflikty": 0}

    def wczytaj(self) -> dict[str, dict]:
        if not self.sciezka.exists():
            return {}
        return json.loads(self.sciezka.read_text(encoding="utf-8"))

    def zapisz(self, pozycje: dict[str, dict]) -> None:
        self.sciezka.parent.mkdir(parents=True, exist_ok=True)
        tymczasowy = self.sciezka.with_suffix(".tmp")
        tymczasowy.write_text(json.dumps(pozycje, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
        os.replace(tymczasowy, self.sciezka)

    def przyjmij(self, pozycje: list[dict]) -> tuple[int, dict]:
        with self.blokada:
            self.statystyki["zadania"] += 1
            stan = self.wczytaj()
            nowe, powtorzenia, konflikty = {}, 0, []
            for p in pozycje:
                brak = [k for k in WYMAGANE if k not in p]
                if brak:
                    return 422, {"detail": f"brak pól: {', '.join(brak)}"}
                klucz = p["klucz_idempotencji"]
                if klucz != f"{p['id_leada']}:{p['data_kolejki']}":
                    return 422, {"detail": f"klucz {klucz} nie pasuje do id_leada:data_kolejki"}
                znana = stan.get(klucz, nowe.get(klucz))
                if znana is None:
                    nowe[klucz] = p
                elif _kanoniczny(znana) == _kanoniczny(p):
                    powtorzenia += 1
                else:
                    konflikty.append(klucz)
            if konflikty:
                self.statystyki["konflikty"] += len(konflikty)
                return 409, {"detail": "ten sam klucz z inną treścią", "klucze": konflikty[:20]}
            if nowe:
                self.zapisz({**stan, **nowe})
            self.statystyki["utworzono"] += len(nowe)
            self.statystyki["powtorzenia"] += powtorzenia
            return 200, {"utworzono": len(nowe), "powtorzenia": powtorzenia}

    def wyczysc(self) -> None:
        with self.blokada:
            self.sciezka.unlink(missing_ok=True)


def utworz_aplikacje(sciezka: Path | None = None) -> FastAPI:
    magazyn = Magazyn(sciezka or Path(os.environ.get("MOCK_LEJEK_STAN", SCIEZKA_DOMYSLNA)))
    aplikacja = FastAPI(title="Atrapa CRM: lejek i kolejki doradców", version="1.0")
    aplikacja.state.magazyn = magazyn

    @aplikacja.post("/webhook/kolejka-doradcy")
    def webhook(paczka: Paczka):
        kod, tresc = magazyn.przyjmij(paczka.pozycje)
        if kod == 422:
            raise HTTPException(422, tresc["detail"])
        return JSONResponse(tresc, status_code=kod)

    @aplikacja.get("/stan")
    def stan():
        pozycje = dict(sorted(magazyn.wczytaj().items()))
        return {"liczba": len(pozycje), "skrot": _skrot(pozycje), "pozycje": pozycje}

    @aplikacja.get("/statystyki")
    def statystyki():
        return magazyn.statystyki

    @aplikacja.delete("/stan")
    def wyczysc():
        magazyn.wyczysc()
        return {"liczba": 0}

    return aplikacja


app = utworz_aplikacje()
