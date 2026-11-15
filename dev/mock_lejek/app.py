"""Atrapa CRM (lejek sprzedaży) dla webhooka kolejek doradców (api/api/adapters/crm_lejek.py).

Uruchomienie: `pypyr mock_lejek` (port 8102) albo
    poetry run uvicorn app:app --app-dir dev/mock_lejek --port 8102
Stan trzymamy w pliku JSON (`MOCK_LEJEK_STAN`, domyślnie dev/mock_lejek/stan.json, poza gitem), żeby przetrwał
restart i dało się go porównać między przebiegami. Pominięcia są w osobnym pliku (`stan_pominiecia.json`), żeby
stan kolejek (`GET /stan`, skrót) nie zależał od pracy doradców.

- `POST /webhook/kolejka-doradcy` `{"pozycje": [...]}`: każda pozycja ma `klucz_idempotencji` = `id_leada:data_kolejki`.
  Nowy klucz: zapis. Ten sam klucz i ta sama treść: powtórzenie, stan bez zmian. Ten sam klucz i inna treść:
  409 dla całej paczki, nic nie zapisane.
- `GET /stan`: wszystkie pozycje po kluczu + `skrot` (SHA-256 z kanonicznego JSON-u pozycji).
- Pole „powód pominięcia”: `GET /doradca/{id_doradcy}` (strona z kolejką doradcy i wyborem powodu) oraz
  `POST /kolejka/pominiecie` `{"klucz_idempotencji", "powod", "komentarz"}`. Słownik powodów: POWODY_POMINIECIA
  (kopia api/api/contexts_boundaries/leasing_bc/pominiecia.py; zgodność pilnuje test). CRM przekazuje pominięcie do
  API Domilo (`POST {DOMILO_API_URL}/leads/skips`, domyślnie http://127.0.0.1:8101), które zapisuje je do tabeli
  `kolejka_pominiecia` w domilo.duckdb. Zapamiętujemy je u siebie dopiero, gdy Domilo je przyjmie; błąd Domilo
  przekazujemy dalej (404 pozycja spoza kolejki, 422 zły powód, 502 Domilo niedostępne).
- `GET /pominiecia`: pominięcia przyjęte przez Domilo; `GET /statystyki`: liczniki od startu procesu.
- `DELETE /stan`: czyści stan kolejek i pominięć (do testów i pokazu).
"""

import hashlib
import html
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

SCIEZKA_DOMYSLNA = Path(__file__).resolve().with_name("stan.json")
URL_DOMILO = "http://127.0.0.1:8101"
WYMAGANE = ("klucz_idempotencji", "id_leada", "data_kolejki", "id_doradcy", "pozycja")
POWODY_POMINIECIA = {
    "znam_klienta": "znam klienta (kontakt poza kolejką)",
    "brak_lokalu": "brak pasującego lokalu",
    "duplikat": "duplikat innego zapytania",
    "inne": "inny powód (opis w komentarzu)",
}


class Paczka(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pozycje: list[dict]


class Pominiecie(BaseModel):
    model_config = ConfigDict(extra="forbid")
    klucz_idempotencji: str
    powod: str
    komentarz: str | None = Field(default=None, max_length=500)


def _kanoniczny(obiekt) -> str:
    return json.dumps(obiekt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _skrot(pozycje: dict[str, dict]) -> str:
    return hashlib.sha256(_kanoniczny(pozycje).encode("utf-8")).hexdigest()


def _zapisz_json(sciezka: Path, dane: dict) -> None:
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = sciezka.with_suffix(".tmp")
    tymczasowy.write_text(json.dumps(dane, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    os.replace(tymczasowy, sciezka)


def _wczytaj_json(sciezka: Path) -> dict:
    return json.loads(sciezka.read_text(encoding="utf-8")) if sciezka.exists() else {}


class Magazyn:
    """Stan atrapy: klucz idempotencji -> pozycja (dokładnie ta treść, którą CRM przyjął jako pierwszą)."""

    def __init__(self, sciezka: Path):
        self.sciezka = Path(sciezka)
        self.sciezka_pominiec = self.sciezka.with_name(f"{self.sciezka.stem}_pominiecia.json")
        self.blokada = threading.Lock()
        self.statystyki = {"zadania": 0, "utworzono": 0, "powtorzenia": 0, "konflikty": 0, "pominiecia": 0}

    def wczytaj(self) -> dict[str, dict]:
        return _wczytaj_json(self.sciezka)

    def zapisz(self, pozycje: dict[str, dict]) -> None:
        _zapisz_json(self.sciezka, pozycje)

    def pominiecia(self) -> dict[str, dict]:
        return _wczytaj_json(self.sciezka_pominiec)

    def zapisz_pominiecie(self, klucz: str, pominiecie: dict) -> None:
        with self.blokada:
            _zapisz_json(self.sciezka_pominiec, {**self.pominiecia(), klucz: pominiecie})
            self.statystyki["pominiecia"] += 1

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
            self.sciezka_pominiec.unlink(missing_ok=True)


def _strona_doradcy(id_doradcy: str, data: str | None, pozycje: list[dict], pominiecia: dict[str, dict]) -> str:
    e = html.escape
    opcje = "".join(f'<option value="{e(k)}">{e(v)}</option>' for k, v in POWODY_POMINIECIA.items())
    wiersze = []
    for p in pozycje:
        klucz = p["klucz_idempotencji"]
        pom = pominiecia.get(klucz)
        stan = f"pominięte: {e(POWODY_POMINIECIA.get(pom['powod'], pom['powod']))}" if pom else ""
        wiersze.append(
            f"<tr><td>{p['pozycja']}</td><td>{e(p['id_leada'])}</td><td>{e(str(p.get('linia_pref') or ''))}</td>"
            f"<td>{p.get('ev_pln', 0):,.0f} zł</td><td>{e(str(p.get('uzasadnienie') or ''))}</td>"
            f'<td><select name="powod" data-klucz="{e(klucz)}"><option value="">powód pominięcia…</option>{opcje}'
            f'</select> <input name="komentarz" data-klucz="{e(klucz)}" placeholder="komentarz" size="16">'
            f' <button data-klucz="{e(klucz)}">Pomiń</button> <span data-stan="{e(klucz)}">{stan}</span></td></tr>'
        )
    return f"""<!doctype html><html lang="pl"><meta charset="utf-8">
<title>Atrapa CRM · kolejka {e(id_doradcy)}</title>
<style>body{{font:14px system-ui;margin:24px}}td,th{{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left;
vertical-align:top}}td:nth-child(5){{max-width:420px;color:#555}}</style>
<h1>Atrapa CRM · kolejka {e(id_doradcy)} · {e(data or "")}</h1>
<p>Pole „powód pominięcia”: wybierz powód i kliknij „Pomiń”. CRM przekaże je do Domilo (POST /leads/skips).</p>
<table><tr><th>Poz.</th><th>Zapytanie</th><th>Linia</th><th>EV</th><th>Uzasadnienie</th><th>Pominięcie</th></tr>
{"".join(wiersze)}</table>
<script>
document.querySelectorAll("button[data-klucz]").forEach((b) => b.addEventListener("click", async () => {{
  const k = b.dataset.klucz;
  const powod = document.querySelector(`select[data-klucz="${{k}}"]`).value;
  const komentarz = document.querySelector(`input[data-klucz="${{k}}"]`).value || null;
  const stan = document.querySelector(`span[data-stan="${{k}}"]`);
  if (!powod) {{ stan.textContent = "wybierz powód"; return; }}
  const odp = await fetch("/kolejka/pominiecie", {{method: "POST", headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{klucz_idempotencji: k, powod, komentarz}})}});
  const tresc = await odp.json();
  stan.textContent = odp.ok ? `zapisano (${{tresc.wynik}})` : `błąd ${{odp.status}}: ${{JSON.stringify(tresc.detail)}}`;
}}));
</script></html>"""


def utworz_aplikacje(
    sciezka: Path | None = None, api_domilo: httpx.Client | None = None, url_domilo: str | None = None
) -> FastAPI:
    """`api_domilo`: klient HTTP do API Domilo (w testach TestClient aplikacji api.main); domyślnie httpx."""
    magazyn = Magazyn(sciezka or Path(os.environ.get("MOCK_LEJEK_STAN", SCIEZKA_DOMYSLNA)))
    adres_domilo = (url_domilo or os.environ.get("DOMILO_API_URL") or URL_DOMILO).rstrip("/")
    aplikacja = FastAPI(title="Atrapa CRM: lejek i kolejki doradców", version="1.1")
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

    @aplikacja.post("/kolejka/pominiecie")
    def pominiecie(z: Pominiecie):
        pozycja = magazyn.wczytaj().get(z.klucz_idempotencji)
        if pozycja is None:
            raise HTTPException(404, f"Nie ma pozycji {z.klucz_idempotencji} w kolejkach CRM")
        if z.powod not in POWODY_POMINIECIA:
            raise HTTPException(422, f"Nieznany powód pominięcia: {z.powod}")
        zgloszenie = {
            "data_kolejki": pozycja["data_kolejki"],
            "id_leada": pozycja["id_leada"],
            "id_doradcy": pozycja["id_doradcy"],
            "powod": z.powod,
            "komentarz": z.komentarz,
            "zgloszono": datetime.now(timezone.utc).isoformat(),
        }
        klient = api_domilo or httpx.Client(timeout=30.0)
        try:
            odp = klient.post(f"{adres_domilo}/leads/skips", json=zgloszenie)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"API Domilo niedostępne ({adres_domilo}): {type(e).__name__}") from e
        finally:
            if api_domilo is None:
                klient.close()
        if odp.status_code != 200:
            szczegoly = (
                odp.json().get("detail")
                if odp.headers.get("content-type", "").startswith("application/json")
                else odp.text
            )
            raise HTTPException(odp.status_code, szczegoly)
        magazyn.zapisz_pominiecie(z.klucz_idempotencji, zgloszenie)
        return {"klucz_idempotencji": z.klucz_idempotencji, **odp.json()}

    @aplikacja.get("/pominiecia")
    def pominiecia():
        return dict(sorted(magazyn.pominiecia().items()))

    @aplikacja.get("/doradca/{id_doradcy}", response_class=HTMLResponse)
    def strona_doradcy(id_doradcy: str, data: str | None = None):
        pozycje = [p for p in magazyn.wczytaj().values() if p["id_doradcy"] == id_doradcy]
        dzien = data or max((p["data_kolejki"] for p in pozycje), default=None)
        pozycje = sorted((p for p in pozycje if p["data_kolejki"] == dzien), key=lambda p: p["pozycja"])
        return _strona_doradcy(id_doradcy, dzien, pozycje, magazyn.pominiecia())

    @aplikacja.get("/statystyki")
    def statystyki():
        return magazyn.statystyki

    @aplikacja.delete("/stan")
    def wyczysc():
        magazyn.wyczysc()
        return {"liczba": 0}

    return aplikacja


app = utworz_aplikacje()
