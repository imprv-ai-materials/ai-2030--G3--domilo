"""Atrapa Serwisownika: przyjmuje zgłoszenia z alertów o ryzyku awarii wind (api/api/adapters/serwisownik.py,
`KlientSerwisownika`).

Uruchomienie: `pypyr serwisownik_mock` (port 8103) albo
    poetry run uvicorn app:app --app-dir dev/serwisownik_mock --port 8103
Stan w pliku JSON (`SERWISOWNIK_MOCK_STAN`, domyślnie dev/serwisownik_mock/stan.json, poza gitem).

- `POST /api/zgloszenia`: zgłoszenie z `klucz_idempotencji` = `{id_windy}:{data_alarmu}` (422, gdy klucz nie pasuje do
  `id_urzadzenia` i `alarm.dzien`). Nowy klucz: nowe zgłoszenie `A000001`, `A000002`, …
  (200, `utworzono = true`). Ten sam klucz i ta sama treść: 200 z tym samym id, `utworzono = false`. Ten sam klucz
  i inna treść: 409, nic nie zapisane.
- `GET /api/zgloszenia`: wszystkie zgłoszenia po kluczu; `DELETE /api/zgloszenia`: czyści stan.
- Pole oceny koordynatora: strona `GET /koordynator` (zgłoszenia z alertów, wybór „trafny” / „fałszywy”, faktyczny
  podzespół, komentarz) i `POST /api/zgloszenia/ocena` `{"klucz_idempotencji", "ocena", "podzespol", "komentarz",
  "oceniajacy"}`. Serwisownik przekazuje ocenę do API Domilo (`POST {DOMILO_API_URL}/lifts/alerts/feedback`,
  domyślnie http://127.0.0.1:8101), które zapisuje ją w tabeli `alerty_ocena` (etykiety do ponownego uczenia).
  Ocenę zapamiętujemy przy zgłoszeniu dopiero, gdy Domilo ją przyjmie; błąd Domilo przekazujemy dalej (404 alert
  nieznany w Domilo, 422 zła wartość, 502 Domilo niedostępne).
"""

import html
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

SCIEZKA_DOMYSLNA = Path(__file__).resolve().with_name("stan.json")
WYMAGANE = ("klucz_idempotencji", "id_budynku", "id_urzadzenia", "typ_urzadzenia", "kategoria", "alarm")
URL_DOMILO = "http://127.0.0.1:8101"
OCENY = {"trafny": "trafny (usterka / awaria potwierdzona)", "falszywy": "fałszywy (winda sprawna)"}
# kopia słownika z api/api/adapters/alerty_ocena.py (PODZESPOLY); zgodność pilnuje test
PODZESPOLY = {
    "drzwi": "drzwi",
    "naped": "napęd",
    "hamulec_liny": "hamulec i liny",
    "sterownik": "sterownik",
    "zewnetrzna": "przyczyna zewnętrzna",
    "brak": "nie dotyczy",
}


class OcenaZgloszenia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    klucz_idempotencji: str
    ocena: str
    podzespol: str | None = None
    komentarz: str | None = Field(default=None, max_length=500)
    oceniajacy: str | None = Field(default=None, max_length=100)


def _kanoniczny(obiekt) -> str:
    return json.dumps(obiekt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strona_koordynatora(stan: dict[str, dict]) -> str:
    e = html.escape
    opcje_oceny = "".join(f'<option value="{k}">{e(v)}</option>' for k, v in OCENY.items())
    opcje_podz = '<option value="">podzespół (opcjonalnie)</option>' + "".join(
        f'<option value="{k}">{e(v)}</option>' for k, v in PODZESPOLY.items()
    )
    wiersze = []
    for klucz, z in sorted(stan.items(), key=lambda kv: kv[1]["tresc"]["alarm"]["dzien"], reverse=True):
        t, ocena = z["tresc"], z.get("ocena")
        flaga = " · <b>reguła zapasowa</b>" if t["alarm"].get("tryb_oceny") == "zapasowa" else ""
        stan_oceny = f"{e(OCENY.get(ocena['ocena'], ocena['ocena']))}" if ocena else "—"
        if ocena and ocena.get("podzespol"):
            stan_oceny += f", {e(PODZESPOLY.get(ocena['podzespol'], ocena['podzespol']))}"
        k = e(klucz)
        wiersze.append(
            f"<tr><td>{e(z['id_zgloszenia'])}</td><td>{e(t['alarm']['dzien'])}</td><td>{e(t['id_urzadzenia'])}"
            f"{flaga}</td><td>{e(t.get('tresc_zgloszenia') or '')}</td><td data-stan=\"{k}\">{stan_oceny}</td>"
            f'<td><select name="ocena" data-klucz="{k}"><option value="">ocena…</option>{opcje_oceny}</select> '
            f'<select name="podzespol" data-klucz="{k}">{opcje_podz}</select> '
            f'<input name="komentarz" data-klucz="{k}" placeholder="komentarz" size="18"> '
            f'<button data-klucz="{k}">Zapisz</button></td></tr>'
        )
    return f"""<!doctype html><html lang="pl"><meta charset="utf-8">
<title>Atrapa Serwisownika · ocena alertów wind</title>
<style>body{{font:14px system-ui;margin:24px}}td,th{{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left;
vertical-align:top}}td:nth-child(4){{max-width:460px;color:#444}}</style>
<h1>Atrapa Serwisownika · ocena alertów wind (koordynator)</h1>
<p>Po wizycie technika oznacz alert jako trafny albo fałszywy (i faktyczny podzespół). Ocena trafia do Domilo
(tabela alerty_ocena) jako etykieta do ponownego uczenia modelu.</p>
<p>Oceniający: <input id="oceniajacy" placeholder="np. koordynator Warszawa" size="28"></p>
<table><tr><th>Zgłoszenie</th><th>Dzień alarmu</th><th>Winda</th><th>Treść</th><th>Ocena</th><th>Oceń</th></tr>
{"".join(wiersze)}</table>
<script>
document.querySelectorAll("button[data-klucz]").forEach((b) => b.addEventListener("click", async () => {{
  const k = b.dataset.klucz;
  const pole = (n) => document.querySelector(`[name="${{n}}"][data-klucz="${{k}}"]`).value || null;
  const stan = document.querySelector(`td[data-stan="${{k}}"]`);
  const ocena = pole("ocena");
  if (!ocena) {{ stan.textContent = "wybierz ocenę"; return; }}
  const odp = await fetch("/api/zgloszenia/ocena", {{method: "POST", headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{klucz_idempotencji: k, ocena, podzespol: pole("podzespol"), komentarz: pole("komentarz"),
      oceniajacy: document.getElementById("oceniajacy").value || null}})}});
  const tresc = await odp.json();
  stan.textContent = odp.ok ? `${{ocena}} (${{tresc.wynik}})`
    : `błąd ${{odp.status}}: ${{JSON.stringify(tresc.detail)}}`;
}}));
</script></html>"""


def utworz_aplikacje(
    sciezka: Path | None = None, api_domilo: httpx.Client | None = None, url_domilo: str | None = None
) -> FastAPI:
    """`api_domilo`: klient HTTP do API Domilo (w testach TestClient aplikacji api.main); domyślnie httpx."""
    plik = Path(sciezka or os.environ.get("SERWISOWNIK_MOCK_STAN", SCIEZKA_DOMYSLNA))
    adres_domilo = (url_domilo or os.environ.get("DOMILO_API_URL") or URL_DOMILO).rstrip("/")
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
        if klucz != f"{zgloszenie['id_urzadzenia']}:{zgloszenie['alarm'].get('dzien')}":
            raise HTTPException(422, f"klucz {klucz} nie pasuje do id_urzadzenia:alarm.dzien")
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

    @aplikacja.post("/api/zgloszenia/ocena")
    def ocen(o: OcenaZgloszenia):
        znane = wczytaj().get(o.klucz_idempotencji)
        if znane is None:
            raise HTTPException(404, f"Nie ma zgłoszenia z kluczem {o.klucz_idempotencji}")
        if o.ocena not in OCENY or (o.podzespol is not None and o.podzespol not in PODZESPOLY):
            raise HTTPException(422, f"Nieznana ocena albo podzespół: {o.ocena}, {o.podzespol}")
        tresc = {**o.model_dump(), "id_zgloszenia": znane["id_zgloszenia"]}
        klient = api_domilo or httpx.Client(timeout=30.0)
        try:
            odp = klient.post(f"{adres_domilo}/lifts/alerts/feedback", json=tresc)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"API Domilo niedostępne ({adres_domilo}): {type(e).__name__}") from e
        finally:
            if api_domilo is None:
                klient.close()
        if odp.status_code != 200:
            json_odp = odp.headers.get("content-type", "").startswith("application/json")
            raise HTTPException(odp.status_code, odp.json().get("detail") if json_odp else odp.text)
        with blokada:
            stan = wczytaj()
            stan[o.klucz_idempotencji]["ocena"] = {
                **o.model_dump(exclude={"klucz_idempotencji"}),
                "oceniono": datetime.now(timezone.utc).isoformat(),
            }
            zapisz(stan)
        return {"klucz_idempotencji": o.klucz_idempotencji, **odp.json()}

    @aplikacja.get("/koordynator", response_class=HTMLResponse)
    def strona_koordynatora():
        return _strona_koordynatora(wczytaj())

    @aplikacja.delete("/api/zgloszenia")
    def wyczysc():
        with blokada:
            plik.unlink(missing_ok=True)
        return {"liczba": 0}

    return aplikacja


app = utworz_aplikacje()
