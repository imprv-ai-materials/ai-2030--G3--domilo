"""Przygotowanie i sprawdzenie Grafany z tablicą wind (dev/grafana/, docs/b4_panel_techniczny.md).

Kroki (`pypyr grafana` wywołuje je po zbudowaniu danych, przed i po `docker compose up`):
- `--przygotuj`: pobiera wtyczkę motherduck-duckdb-datasource (WERSJA_WTYCZKI) do plugins/ (gdy jej nie ma), zakłada
  .env z losowym hasłem administratora (gdy go nie ma) i generuje dashboards/windy.json z windy.szablon.json:
  zakres czasu = 30 dni przed dniem oceny … dzień oceny + 1 (dane/panel_info.parquet), granica kolorów ryzyka = próg
  opłacalności wizyty p* (panel_info.prog_oplacalnosci_proc).
- `--sprawdz`: czeka na Grafanę (http://127.0.0.1:3400), sprawdza wtyczkę i źródło danych, wykonuje zapytanie każdego
  panelu i zmiennej przez /api/ds/query (zmienne: pierwsza winda i pierwszy sygnał) i wypisuje liczby wierszy.
  Kończy się błędem, gdy któreś zapytanie się nie uda albo panel z danymi zwróci 0 wierszy.
"""

import json
import os
import re
import secrets
import sys
import time
import urllib.request
import zipfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd

KATALOG = Path(__file__).resolve().parent
WERSJA_WTYCZKI = "0.4.6"
NAZWA_WTYCZKI = "motherduck-duckdb-datasource"
URL_WTYCZKI = (
    f"https://github.com/motherduckdb/grafana-duckdb-datasource/releases/download/v{WERSJA_WTYCZKI}/"
    f"{NAZWA_WTYCZKI}-{WERSJA_WTYCZKI}.zip"
)
URL_GRAFANY = "http://127.0.0.1:3400"
DS = {"type": NAZWA_WTYCZKI, "uid": "duckdb-windy"}


def pobierz_wtyczke() -> Path:
    cel = KATALOG / "plugins" / NAZWA_WTYCZKI
    if (cel / "plugin.json").exists():
        return cel
    with urllib.request.urlopen(URL_WTYCZKI, timeout=120) as odp:
        dane = odp.read()
    cel.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(dane)) as z:
        z.extractall(cel.parent)
    if not (cel / "plugin.json").exists():
        raise FileNotFoundError(f"W archiwum {URL_WTYCZKI} nie ma {NAZWA_WTYCZKI}/plugin.json")
    for plik in cel.glob("gpx_*"):
        plik.chmod(0o755)
    return cel


def zaloz_env() -> None:
    plik = KATALOG / ".env"
    if not plik.exists():
        plik.write_text(f"GRAFANA_HASLO_ADMINA={secrets.token_urlsafe(18)}\n", encoding="utf-8")
        plik.chmod(0o600)


def generuj_tablice() -> dict:
    info = pd.read_parquet(KATALOG / "dane" / "panel_info.parquet").iloc[0]
    dzien = pd.Timestamp(info["dzien_oceny"])
    od, do = (dzien - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00.000+02:00"), (dzien + timedelta(days=1)).strftime(
        "%Y-%m-%dT00:00:00.000+02:00"
    )
    tekst = (KATALOG / "windy.szablon.json").read_text(encoding="utf-8")
    tekst = tekst.replace('"__OD__"', json.dumps(od)).replace('"__DO__"', json.dumps(do))
    tekst = tekst.replace('"__PROG__"', json.dumps(float(info["prog_oplacalnosci_proc"])))
    tablica = json.loads(tekst)
    (KATALOG / "dashboards").mkdir(exist_ok=True)
    (KATALOG / "dashboards" / "windy.json").write_text(
        json.dumps(tablica, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {"od": od, "do": do, "prog": float(info["prog_oplacalnosci_proc"])}


def _zadanie(sciezka: str, dane: dict | None = None) -> dict:
    zadanie = urllib.request.Request(
        f"{URL_GRAFANY}{sciezka}",
        data=json.dumps(dane).encode() if dane is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(zadanie, timeout=60) as odp:
        return json.loads(odp.read())


def zapytaj(sql: str, od: str, do: str) -> list[dict]:
    """Wynik zapytania SQL przez źródło danych Grafany: lista ramek {kolumny, wiersze}."""
    wynik = _zadanie(
        "/api/ds/query",
        {
            "from": str(int(pd.Timestamp(od).timestamp() * 1000)),
            "to": str(int(pd.Timestamp(do).timestamp() * 1000)),
            "queries": [{"refId": "A", "datasource": DS, "rawSql": sql, "format": 1, "rawQuery": True}],
        },
    )["results"]["A"]
    if "error" in wynik:
        raise RuntimeError(wynik["error"])
    return [
        {
            "kolumny": [f["name"] for f in r["schema"]["fields"]],
            "wiersze": len(r["data"]["values"][0]) if r["data"]["values"] else 0,
        }
        for r in wynik.get("frames", [])
    ]


def sprawdz() -> None:
    for _ in range(60):
        try:
            if _zadanie("/api/health").get("database") == "ok":
                break
        except OSError:
            pass
        time.sleep(2)
    else:
        raise TimeoutError("Grafana nie odpowiada na /api/health")
    wtyczka = _zadanie(f"/api/plugins/{NAZWA_WTYCZKI}/settings")
    print(f"wtyczka: {wtyczka['id']} {wtyczka['info']['version']}")
    tablica = json.loads((KATALOG / "dashboards" / "windy.json").read_text(encoding="utf-8"))
    od, do = tablica["time"]["from"], tablica["time"]["to"]
    zmienne = {}
    for v in tablica["templating"]["list"]:
        ramki = zapytaj(v["query"], od, do)
        wartosci = _zadanie(
            "/api/ds/query",
            {"queries": [{"refId": "A", "datasource": DS, "rawSql": v["query"], "format": 1, "rawQuery": True}]},
        )["results"]["A"]["frames"][0]["data"]["values"][0]
        zmienne[v["name"]] = wartosci[0]
        print(f"zmienna ${v['name']}: {ramki[0]['wiersze']} wartości, pierwsza: {wartosci[0]}")
    bledy = []
    for p in tablica["panels"]:
        for t in p.get("targets", []):
            sql = re.sub(
                r"\$\{(\w+):sqlstring\}",
                lambda m: "'" + str(zmienne[m.group(1)]).replace("'", "''") + "'",
                t["rawSql"],
            )
            try:
                ramki = zapytaj(sql, od, do)
                wiersze = sum(r["wiersze"] for r in ramki)
                print(f"panel „{p['title']}”: {wiersze} wierszy, kolumny {ramki[0]['kolumny'] if ramki else []}")
                if wiersze == 0:
                    bledy.append(f"{p['title']}: 0 wierszy")
            except Exception as e:  # noqa: BLE001 — zbieramy wszystkie błędy paneli
                bledy.append(f"{p['title']}: {e}")
    if bledy:
        raise SystemExit("Błędy paneli:\n" + "\n".join(bledy))
    print(
        f"Tablica: {URL_GRAFANY}/d/{tablica['uid']} "
        "(widz bez logowania; administrator: admin, hasło w dev/grafana/.env)"
    )


if __name__ == "__main__":
    if "--przygotuj" in sys.argv:
        print("wtyczka:", pobierz_wtyczke())
        zaloz_env()
        print("tablica:", generuj_tablice())
    if "--sprawdz" in sys.argv:
        os.environ.setdefault("NO_PROXY", "127.0.0.1")
        sprawdz()
