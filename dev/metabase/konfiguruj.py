"""Konfiguracja Metabase dla panelu kampanii retencyjnej przez API (idempotentna: można uruchamiać wielokrotnie).

Kroki: sterownik DuckDB w plugins/ (pobranie i sprawdzenie sha256) -> czekanie na /api/health -> konto
administratora (pierwsze uruchomienie; hasło losowe w dev/metabase/.env, poza gitem) -> ustawienia (język polski,
liczby „1 000,5”, publiczne linki) -> baza „Domilo: panel kampanii” (DuckDB `:memory:`, Init SQL tworzy widok
`read_parquet('/dane/<tabela>.parquet')` dla każdego pliku z dane/, czyli tabel z retention_bc/panel_kampanii.py)
-> synchronizacja -> kolekcja, karty (SQL) i panel -> link publiczny. Na końcu wypisuje adresy.

Uruchomienie z katalogu głównego: `pypyr metabase` albo `poetry run python dev/metabase/konfiguruj.py`
(Metabase musi działać: `docker compose -f dev/metabase/compose.yaml up -d`). Opis: docs/panel_kampanii.md.
"""

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx

KATALOG = Path(__file__).resolve().parent
ADRES = os.environ.get("MB_ADRES", "http://localhost:3300")
PLIK_ENV = KATALOG / ".env"
STEROWNIK = KATALOG / "plugins" / "duckdb.metabase-driver.jar"
STEROWNIK_URL = (
    "https://github.com/motherduckdb/metabase_duckdb_driver/releases/download/1.5.6.0/duckdb.metabase-driver.jar"
)
STEROWNIK_SHA256 = "e95f49d5668a0e57c83d05533efa76fd8f37dde26db82dd07bb33cbfbe50a69b"
EMAIL_ADMINA = "admin@domilo.local"  # konto lokalne, adres fikcyjny (bez poczty)
NAZWA_BAZY = "Domilo: panel kampanii"
KATALOG_DANYCH = KATALOG / "dane"  # w kontenerze: /dane (compose.yaml)
NAZWA_KOLEKCJI = "Kampania retencyjna"
NAZWA_PANELU = "Kampania retencyjna: panel dla marketingu"
OPIS_PANELU = "Czy kampania retencyjna zarabia, czy oferta zatrzymuje najemców i lista na ten tydzień."


# --- formatowanie w SQL (tekst z liczbą po polsku: spacja tysięcy, przecinek dziesiętny, znak minus) -----------------


def zl(wyrazenie: str) -> str:
    return f"replace(replace(format('{{:,.0f}}', {wyrazenie}), ',', ' '), '-', '−') || ' zł'"


def proc(wyrazenie: str, miejsc: int = 1) -> str:
    return f"replace(replace(format('{{:.{miejsc}f}}', 100 * ({wyrazenie})), '.', ','), '-', '−') || '%'"


def kol(nazwa: str) -> str:
    return json.dumps(["name", nazwa], ensure_ascii=False)


ZL = {"suffix": " zł", "decimals": 0}
PROCENT = {"number_style": "percent", "decimals": 1}
PP = {"suffix": " p.p.", "decimals": 1}

# --- karty -----------------------------------------------------------------------------------------------------------

KARTY = {
    "czy_zarabia": {
        "name": "Czy kampania Q3 2026 zarabia?",
        "display": "table",
        "sql": 'SELECT czy_kampania_zarabia AS "Odpowiedź", kampania AS "Kampania" FROM kampania_podsumowanie',
        "viz": {"column_settings": {kol("Odpowiedź"): {"text_wrapping": True}}},
    },
    "wynik_netto": {
        "name": "Wynik netto kampanii Q3 2026",
        "display": "scalar",
        "sql": 'SELECT wynik_netto_zl AS "Wynik netto" FROM kampania_podsumowanie',
        "viz": {"column_settings": {kol("Wynik netto"): ZL}},
    },
    "wynik_przedzial": {
        "name": "Wynik netto: przedział 95%",
        "display": "scalar",
        "sql": f"SELECT 'od ' || {zl('wynik_netto_od_zl')} || ' do ' || {zl('wynik_netto_do_zl')} AS \"Przedział\" "
        "FROM kampania_podsumowanie",
        "viz": {},
    },
    "roi": {
        "name": "ROI kampanii Q3 2026",
        "display": "scalar",
        "sql": 'SELECT roi AS "ROI" FROM kampania_podsumowanie',
        "viz": {"column_settings": {kol("ROI"): PROCENT}},
    },
    "roi_przedzial": {
        "name": "ROI: przedział 95%",
        "display": "scalar",
        "sql": f"SELECT 'od ' || {proc('roi_od')} || ' do ' || {proc('roi_do', 2)} AS \"Przedział\" "
        "FROM kampania_podsumowanie",
        "viz": {},
    },
    "przedluzenia_wykres": {
        "name": "Odsetek przedłużeń: z ofertą i bez oferty",
        "display": "bar",
        "sql": 'SELECT grupa AS "Grupa", odsetek_przedluzen AS "Odsetek przedłużeń" FROM kampania_grupy '
        "ORDER BY kolejnosc",
        "viz": {
            "graph.dimensions": ["Grupa"],
            "graph.metrics": ["Odsetek przedłużeń"],
            "graph.show_values": True,
            "graph.y_axis.title_text": "Odsetek przedłużeń",
            "graph.x_axis.title_text": "Grupa",
            "column_settings": {kol("Odsetek przedłużeń"): PROCENT},
        },
    },
    "przedluzenia_tabela": {
        "name": "Przedłużenia w grupach",
        "display": "table",
        "sql": 'SELECT grupa AS "Grupa", umowy AS "Umowy", przedluzenia AS "Przedłużenia", '
        'odsetek_przedluzen AS "Odsetek przedłużeń", przedzial_od AS "Przedział 95%: od", '
        'przedzial_do AS "Przedział 95%: do" FROM kampania_grupy ORDER BY kolejnosc',
        "viz": {
            "column_settings": {
                kol("Odsetek przedłużeń"): PROCENT,
                kol("Przedział 95%: od"): PROCENT,
                kol("Przedział 95%: do"): PROCENT,
            }
        },
    },
    "wynik_skladniki": {
        "name": "Skąd bierze się wynik",
        "display": "table",
        "sql": 'SELECT pozycja AS "Pozycja", wartosc AS "Wartość", jednostka AS "Jednostka", '
        'przedzial_od AS "Przedział 95%: od", przedzial_do AS "Przedział 95%: do" '
        "FROM kampania_wynik ORDER BY kolejnosc",
        "viz": {
            "column_settings": {
                kol("Wartość"): {"decimals": 1},
                kol("Przedział 95%: od"): {"decimals": 1},
                kol("Przedział 95%: do"): {"decimals": 1},
            }
        },
    },
    "lista_liczba": {
        "name": "Umowy na liście tego tygodnia",
        "display": "scalar",
        "sql": 'SELECT count(*) AS "Umowy" FROM lista_tydzien',
        "viz": {},
    },
    "lista_oferty": {
        "name": "Oferty do wysłania w tym tygodniu",
        "display": "scalar",
        "sql": 'SELECT count(*) FILTER (WHERE wyslac_oferte) AS "Oferty" FROM lista_tydzien',
        "viz": {},
    },
    "lista_kontrola": {
        "name": "W grupie kontrolnej",
        "display": "scalar",
        "sql": "SELECT count(*) FILTER (WHERE grupa = 'kontrolna (bez oferty)') AS \"Kontrolna\" FROM lista_tydzien",
        "viz": {},
    },
    "lista_podsumowanie": {
        "name": "Lista tego tygodnia: co robimy",
        "display": "table",
        "sql": 'SELECT co_robimy AS "Co robimy", count(*) AS "Umowy" FROM lista_tydzien GROUP BY 1 ORDER BY 2 DESC',
        "viz": {},
    },
    "lista": {
        "name": "Lista na ten tydzień: umowy kończące się za 60–66 dni",
        "display": "table",
        "sql": 'SELECT co_robimy AS "Co robimy", id_umowy AS "Umowa", id_najemcy AS "Najemca", '
        'rodzaj_klienta AS "Klient", miasto AS "Miasto", budynek AS "Budynek", '
        "strftime(koniec_umowy, '%d.%m.%Y') AS \"Koniec umowy\", "
        'szansa_odejscia AS "Szansa odejścia", powod AS "Powód" '
        "FROM lista_tydzien ORDER BY wyslac_oferte DESC, szansa_odejscia DESC, id_umowy",
        "viz": {
            "column_settings": {
                kol("Szansa odejścia"): {"number_style": "percent", "decimals": 0},
                kol("Powód"): {"text_wrapping": True},
                kol("Co robimy"): {"text_wrapping": True},
            },
            "table.column_widths": [165, 90, 95, 85, 90, 150, 120, 125, 410],
        },
    },
    "segmenty": {
        "name": "Efekt oferty w grupach klientów i miesiącach",
        "display": "table",
        "sql": 'SELECT segment AS "Grupa umów", umowy_z_oferta AS "Umowy z ofertą", '
        'umowy_kontrolne AS "Umowy bez oferty", '
        'odsetek_z_oferta AS "Przedłużenia z ofertą", odsetek_kontrola AS "Przedłużenia bez oferty", '
        'roznica_pp AS "Różnica", roznica_od_pp AS "Przedział 95%: od", roznica_do_pp AS "Przedział 95%: do" '
        "FROM kampania_segmenty ORDER BY kolejnosc",
        "viz": {
            "column_settings": {
                kol("Przedłużenia z ofertą"): PROCENT,
                kol("Przedłużenia bez oferty"): PROCENT,
                kol("Różnica"): PP,
                kol("Przedział 95%: od"): PP,
                kol("Przedział 95%: do"): PP,
            }
        },
    },
    "zalozenia": {
        "name": "Założenia do wyniku w złotówkach (od firmy)",
        "display": "table",
        "sql": 'SELECT symbol AS "Symbol", wartosc_zl AS "Wartość", co_oznacza AS "Co oznacza", '
        'odpowiedzialny AS "Kto podał", zrodlo AS "Źródło" FROM zalozenia',
        "viz": {
            "column_settings": {
                kol("Wartość"): ZL,
                kol("Źródło"): {"text_wrapping": True},
                kol("Co oznacza"): {"text_wrapping": True},
            },
            "table.column_widths": [80, 90, 280, 130, 400],
        },
    },
    "odswiezono": {
        "name": "Dane panelu",
        "display": "table",
        "sql": "SELECT strftime(data_listy, '%d.%m.%Y') AS \"Lista z dnia\", "
        "strftime(stan_danych_na, '%d.%m.%Y') AS \"Dane źródłowe do dnia\", "
        'strftime(odswiezono, \'%d.%m.%Y %H:%M\') AS "Odświeżono", zrodlo AS "Źródło" FROM panel_info',
        "viz": {},
    },
}

TEKSTY = {
    "naglowek": (
        "# Kampania retencyjna: panel dla marketingu\n"
        "Oferta retencyjna to rabat w nowej umowie dla najemcy, którego umowa się kończy. Żeby wiedzieć, czy rabat "
        "działa, część umów **losowo nie dostaje oferty** (grupa kontrolna). Porównujemy, jak często przedłużają "
        "obie grupy, i przeliczamy różnicę na złotówki.\n\n"
        "Panel ma trzy części: **1. czy kampania zarabia**, **2. czy oferta zatrzymuje najemców**, "
        "**3. lista umów na ten tydzień**."
    ),
    "czesc1": (
        "## 1. Czy kampania zarabia?\n"
        "**Wynik netto** = dodatkowe przedłużenia × koszt odejścia najemcy − wypłacone rabaty − koszt wysłania "
        "ofert. **ROI** = wynik netto ÷ wydatki na kampanię (ujemny = tracimy). **Przedział 95%** pokazuje, "
        "gdzie z dużą pewnością leży prawdziwy wynik: jeśli cały jest poniżej zera, kampania traci pieniądze; "
        "jeśli obejmuje zero, jeszcze nie wiemy. Założenia (koszt odejścia, rabat, koszt kontaktu) są na dole panelu."
    ),
    "czesc2": (
        "## 2. Czy oferta zatrzymuje najemców?\n"
        "Odsetek przedłużeń w grupie z ofertą i w losowej grupie bez oferty. **Różnica między nimi to efekt "
        "oferty.** Grupa bez oferty jest mała, więc przedziały są szerokie. Tabela pod spodem rozbija efekt na "
        "klientów prywatnych, firmy i miesiące końca umowy (małe liczby: tylko poglądowo)."
    ),
    "czesc3": (
        "## 3. Lista na ten tydzień\n"
        "Umowy, które kończą się za **60–66 dni** od poniedziałku (lista odświeża się co tydzień). "
        "**Co robimy** mówi, co zrobić z umową, a **Powód** dlaczego. Umowy z grupy kontrolnej **nie dostają oferty**, "
        "nawet gdy model ją zaleca: inaczej nie zmierzymy, ile daje kampania. „Bez rabatu” oznacza zwykłe "
        "przedłużenie bez rabatu, a „Nie proponuj rabatu” to umowy, w których oferta według modelu raczej "
        "zniechęca. Szansa odejścia i efekt oferty pochodzą z modeli; dane źródłowe kończą się w dniu podanym "
        "w tabeli „Dane panelu”."
    ),
    "czesc4": (
        "## Założenia i dane\n"
        "Kwoty do wyniku w złotówkach podała firma (kto i skąd: tabela obok). Pełny opis liczenia: "
        "docs/kampania_2026q3.md, docs/lista_retencyjna.md i docs/panel_kampanii.md w repozytorium."
    ),
}

# (klucz, wiersz, kolumna, szerokość, wysokość); siatka Metabase ma 24 kolumny
UKLAD = [
    ("tekst:naglowek", 0, 0, 24, 3),
    ("tekst:czesc1", 3, 0, 24, 3),
    ("czy_zarabia", 6, 0, 24, 3),
    ("wynik_netto", 9, 0, 5, 4),
    ("wynik_przedzial", 9, 5, 7, 4),
    ("roi", 9, 12, 5, 4),
    ("roi_przedzial", 9, 17, 7, 4),
    ("wynik_skladniki", 13, 0, 24, 7),
    ("tekst:czesc2", 20, 0, 24, 3),
    ("przedluzenia_wykres", 23, 0, 10, 8),
    ("przedluzenia_tabela", 23, 10, 14, 3),
    ("segmenty", 26, 10, 14, 5),
    ("tekst:czesc3", 31, 0, 24, 3),
    ("lista_liczba", 34, 0, 5, 4),
    ("lista_oferty", 34, 5, 5, 4),
    ("lista_kontrola", 34, 10, 5, 4),
    ("lista_podsumowanie", 34, 15, 9, 4),
    ("lista", 38, 0, 24, 16),
    ("tekst:czesc4", 54, 0, 6, 9),
    ("zalozenia", 54, 6, 18, 6),
    ("odswiezono", 60, 6, 18, 3),
]


# --- API --------------------------------------------------------------------------------------------------------------


def pobierz_sterownik() -> None:
    STEROWNIK.parent.mkdir(parents=True, exist_ok=True)
    if not STEROWNIK.exists():
        print(f"Pobieram {STEROWNIK_URL}")
        with httpx.stream("GET", STEROWNIK_URL, follow_redirects=True, timeout=300) as r:
            r.raise_for_status()
            with open(STEROWNIK, "wb") as f:
                for kawalek in r.iter_bytes():
                    f.write(kawalek)
    skrot = hashlib.sha256(STEROWNIK.read_bytes()).hexdigest()
    if skrot != STEROWNIK_SHA256:
        raise RuntimeError(f"{STEROWNIK}: sha256 {skrot}, oczekiwano {STEROWNIK_SHA256}")


def czekaj_na_metabase(limit_s: int = 300) -> None:
    start = time.time()
    while time.time() - start < limit_s:
        try:
            if httpx.get(f"{ADRES}/api/health", timeout=5).json().get("status") == "ok":
                return
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(3)
    raise TimeoutError(f"Metabase pod {ADRES} nie odpowiada od {limit_s} s")


def dane_logowania() -> dict:
    if PLIK_ENV.exists():
        wpisy = dict(line.split("=", 1) for line in PLIK_ENV.read_text().splitlines() if "=" in line)
        return {"email": wpisy["MB_ADMIN_EMAIL"], "haslo": wpisy["MB_ADMIN_HASLO"]}
    dane = {"email": EMAIL_ADMINA, "haslo": secrets.token_urlsafe(18)}
    PLIK_ENV.write_text(f"MB_ADMIN_EMAIL={dane['email']}\nMB_ADMIN_HASLO={dane['haslo']}\n", encoding="utf-8")
    PLIK_ENV.chmod(0o600)
    return dane


class Metabase:
    def __init__(self):
        self.http = httpx.Client(base_url=ADRES, timeout=120)

    def _sprawdz(self, r: httpx.Response) -> dict | list:
        if r.status_code >= 400:
            raise RuntimeError(f"{r.request.method} {r.request.url}: {r.status_code} {r.text[:500]}")
        return r.json() if r.content else {}

    def get(self, sciezka, **kw):
        return self._sprawdz(self.http.get(sciezka, **kw))

    def post(self, sciezka, dane=None):
        return self._sprawdz(self.http.post(sciezka, json=dane))

    def put(self, sciezka, dane):
        return self._sprawdz(self.http.put(sciezka, json=dane))

    def zaloguj(self) -> None:
        dane = dane_logowania()
        wlasciwosci = self.get("/api/session/properties")
        if not wlasciwosci.get("has-user-setup"):
            self.post(
                "/api/setup",
                {
                    "token": wlasciwosci["setup-token"],
                    "user": {
                        "first_name": "Administrator",
                        "last_name": "Domilo",
                        "email": dane["email"],
                        "password": dane["haslo"],
                        "site_name": "Domilo",
                    },
                    "prefs": {"site_name": "Domilo", "site_locale": "pl", "allow_tracking": False},
                },
            )
        sesja = self.post("/api/session", {"username": dane["email"], "password": dane["haslo"]})
        self.http.headers["X-Metabase-Session"] = sesja["id"]

    def ustawienia(self) -> None:
        for klucz, wartosc in {
            "site-locale": "pl",
            "enable-public-sharing": True,
            "custom-formatting": {
                "type/Number": {"number_separators": ", "},
                "type/Temporal": {"date_style": "D/M/YYYY", "date_separator": ".", "time_style": "HH:mm"},
            },
            "anon-tracking-enabled": False,
        }.items():
            self.put(f"/api/setting/{klucz}", {"value": wartosc})

    def baza(self) -> int:
        pliki = sorted(KATALOG_DANYCH.glob("*.parquet"))
        if not pliki:
            raise FileNotFoundError(f"Brak plików Parquet w {KATALOG_DANYCH}: najpierw retention_bc/panel_kampanii.py")
        init_sql = "\n".join(
            f"CREATE OR REPLACE VIEW {p.stem} AS SELECT * FROM read_parquet('/dane/{p.name}');" for p in pliki
        )
        szczegoly = {"database_file": ":memory:", "read_only": False, "init_sql": init_sql}
        bazy = self.get("/api/database")
        bazy = bazy["data"] if isinstance(bazy, dict) else bazy
        istniejaca = next((b for b in bazy if b["name"] == NAZWA_BAZY), None)
        if istniejaca is None:
            id_bazy = self.post("/api/database", {"engine": "duckdb", "name": NAZWA_BAZY, "details": szczegoly})["id"]
        else:
            id_bazy = istniejaca["id"]
            self.put(f"/api/database/{id_bazy}", {"details": szczegoly})
        self.post(f"/api/database/{id_bazy}/sync_schema")
        oczekiwane = {p.stem for p in pliki}
        for _ in range(30):
            tabele = {t["name"] for t in self.get(f"/api/database/{id_bazy}/metadata")["tables"]}
            if oczekiwane <= tabele:
                break
            time.sleep(2)
        else:  # karty to zapytania SQL, więc działają także bez zsynchronizowanych metadanych
            print(f"Uwaga: Metabase nie pokazuje jeszcze tabel {sorted(oczekiwane - tabele)} w przeglądarce danych")
        return id_bazy

    def kolekcja(self) -> int:
        for k in self.get("/api/collection"):
            if k.get("name") == NAZWA_KOLEKCJI and not k.get("archived"):
                return k["id"]
        return self.post("/api/collection", {"name": NAZWA_KOLEKCJI, "description": "Panel kampanii retencyjnej"})["id"]

    def karty(self, id_bazy: int, id_kolekcji: int) -> dict[str, int]:
        istniejace = {
            c["name"]: c["id"]
            for c in self.get(f"/api/collection/{id_kolekcji}/items", params={"models": "card"})["data"]
        }
        ids = {}
        for klucz, k in KARTY.items():
            tresc = {
                "name": k["name"],
                "display": k["display"],
                "collection_id": id_kolekcji,
                "dataset_query": {"type": "native", "native": {"query": k["sql"]}, "database": id_bazy},
                "visualization_settings": k["viz"],
            }
            if k["name"] in istniejace:
                ids[klucz] = istniejace[k["name"]]
                self.put(f"/api/card/{ids[klucz]}", tresc)
            else:
                ids[klucz] = self.post("/api/card", tresc)["id"]
            wynik = self.post(f"/api/card/{ids[klucz]}/query")
            if wynik.get("status") != "completed":
                raise RuntimeError(f"Karta {k['name']}: {wynik.get('error')}")
        for nazwa, id_karty in istniejace.items():  # karty spoza KARTY (np. po zmianie nazwy) do archiwum
            if id_karty not in ids.values():
                self.put(f"/api/card/{id_karty}", {"archived": True})
        return ids

    def panel(self, id_kolekcji: int, karty: dict[str, int]) -> int:
        panele = [d for d in self.get("/api/dashboard") if d["name"] == NAZWA_PANELU and not d.get("archived")]
        if panele:
            id_panelu = panele[0]["id"]
        else:
            id_panelu = self.post(
                "/api/dashboard",
                {
                    "name": NAZWA_PANELU,
                    "collection_id": id_kolekcji,
                    "description": OPIS_PANELU,
                },
            )["id"]
        dashcards = []
        for i, (klucz, wiersz, kolumna, szer, wys) in enumerate(UKLAD, start=1):
            karta = {"id": -i, "row": wiersz, "col": kolumna, "size_x": szer, "size_y": wys}
            if klucz.startswith("tekst:"):
                karta |= {
                    "card_id": None,
                    "visualization_settings": {
                        "virtual_card": {
                            "name": None,
                            "display": "text",
                            "visualization_settings": {},
                            "dataset_query": {},
                            "archived": False,
                        },
                        "text": TEKSTY[klucz.split(":", 1)[1]],
                    },
                }
            else:
                karta |= {"card_id": karty[klucz], "visualization_settings": {}}
            dashcards.append(karta)
        self.put(f"/api/dashboard/{id_panelu}", {"dashcards": dashcards, "width": "full"})
        return id_panelu

    def link_publiczny(self, id_panelu: int) -> str:
        return self.post(f"/api/dashboard/{id_panelu}/public_link")["uuid"]


def main() -> dict:
    pobierz_sterownik()
    czekaj_na_metabase()
    mb = Metabase()
    mb.zaloguj()
    mb.ustawienia()
    id_bazy = mb.baza()
    id_kolekcji = mb.kolekcja()
    karty = mb.karty(id_bazy, id_kolekcji)
    id_panelu = mb.panel(id_kolekcji, karty)
    uuid = mb.link_publiczny(id_panelu)
    adresy = {
        "panel": f"{ADRES}/dashboard/{id_panelu}",
        "panel_publiczny": f"{ADRES}/public/dashboard/{uuid}",
        "logowanie": f"{EMAIL_ADMINA} (hasło w dev/metabase/.env)",
        "karty": len(karty),
    }
    print(json.dumps(adresy, ensure_ascii=False, indent=2))
    return adresy


if __name__ == "__main__":
    if "--tylko-sterownik" in sys.argv:  # przed startem kontenera: Metabase ładuje sterowniki tylko przy starcie
        pobierz_sterownik()
        print(f"Sterownik DuckDB: {STEROWNIK}")
        sys.exit(0)
    sys.exit(0 if main() else 1)
