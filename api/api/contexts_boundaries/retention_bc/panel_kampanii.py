"""Dane panelu kampanii retencyjnej w Metabase (dev/metabase/, docs/panel_kampanii.md).

Metabase czyta dane sterownikiem DuckDB 1.5 (motherduckdb/metabase_duckdb_driver 1.5.6.0), który nie otwiera
domilo.duckdb (format pliku 2.0), a otwarta baza blokowałaby zapis zadaniom. Dlatego panel czyta pliki Parquet
z `dev/metabase/dane/<tabela>.parquet`: Metabase łączy się z DuckDB `:memory:`, a Init SQL połączenia tworzy widoki
`read_parquet(...)` (dev/metabase/konfiguruj.py). Każde zapytanie czyta bieżący plik, więc nowe dane widać od razu,
bez przeładowania Metabase. Plik powstaje obok i podmienia stary jednym `os.replace` (nigdy połowa zapisu).

Tabele (po jednym pliku Parquet):
- `lista_tydzien`: ostatnia lista z tabeli lista_retencyjna (zadanie lista-retencyjna) z opisami po polsku:
  co robimy z umową i dlaczego;
- `kampania_grupy`, `kampania_wynik`, `kampania_podsumowanie`, `kampania_segmenty`: wyniki kampanii Q3 2026
  z retention_bc/wyniki/kampania_2026q3.json (kampania_2026q3.py, docs/kampania_2026q3.md: bootstrap 1 000 losowań);
- `zalozenia`: R, D, k z retention_bc/zalozenia.yaml (źródło i osoba odpowiedzialna);
- `panel_info`: kiedy odświeżono i z czego.

Uruchomienie: `pypyr metabase` (dane + Metabase + panel) albo
`cd api && poetry run python -m api.contexts_boundaries.retention_bc.panel_kampanii`.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from api.adapters import lista_retencyjna
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polaczenie
from api.contexts_boundaries.retention_bc.zalozenia import wczytaj_zalozenia

STREFA = ZoneInfo("Europe/Warsaw")
KATALOG_PANELU = KATALOG_REPO / "dev" / "metabase" / "dane"
SCIEZKA_KAMPANII = Path(__file__).with_name("wyniki") / "kampania_2026q3.json"
NAZWA_KAMPANII = "Kampania Q3 2026 (końce umów lipiec–wrzesień 2026)"

ETYKIETA_LINII = {"B2C": "prywatny", "B2B": "firma"}
ETYKIETA_GRUPY = {"kontrola": "kontrolna (bez oferty)", "polityka": "objęta kampanią"}
ETYKIETA_AKCJI = {
    "rabat": "oferta rabatowa",
    "bez rabatu": "bez rabatu",
    "nie budzić": "nie proponować rabatu",
}
POWOD_KONTROLI = (
    "Umowa wylosowana do grupy kontrolnej: 20% umów nie dostaje oferty, żeby porównać, ile przedłużeń daje kampania. "
    "Model sugerował: "
)

SQL_LISTY = f"""
SELECT l.*, b.miasto, b.nazwa AS budynek
FROM {lista_retencyjna.TABELA} AS l
JOIN pms_najmy AS n USING (id_najmu)
JOIN pms_lokale AS lo ON lo.id_lokalu = n.id_lokalu
JOIN pms_budynki AS b ON b.id_budynku = lo.id_budynku
WHERE l.data_listy = (SELECT max(data_listy) FROM {lista_retencyjna.TABELA})
ORDER BY l.wyslac_oferte DESC, l.ryzyko DESC, l.id_umowy
"""


# --- przekształcenia (bez plików) ------------------------------------------------------------------------------------


def co_robimy(grupa: str, akcja: str, wyslac_oferte: bool) -> str:
    """Decyzja dla marketingu jednym zwrotem."""
    if wyslac_oferte:
        return "Wyślij ofertę rabatową"
    if grupa == "kontrola":
        return "Nic nie wysyłaj (grupa kontrolna)"
    if akcja == "nie budzić":
        return "Nie proponuj rabatu (mógłby zniechęcić)"
    return "Bez rabatu (zwykłe przedłużenie)"


def lista_dla_panelu(lista: pd.DataFrame) -> pd.DataFrame:
    """Lista retencyjna z kolumnami po polsku, w kolejności: najpierw oferty do wysłania, potem wg szansy odejścia."""
    zrozumiale = [
        u.replace("w dniu migawki", "w dniu decyzji (60 dni przed końcem umowy)").replace(
            "Nie budzić:", "Nie proponuj rabatu:"
        )
        for u in lista["uzasadnienie"]
    ]
    powod = [
        (POWOD_KONTROLI + u[0].lower() + u[1:]) if g == "kontrola" else u for g, u in zip(lista["grupa"], zrozumiale)
    ]
    return pd.DataFrame(
        {
            "data_listy": pd.to_datetime(lista["data_listy"]).dt.date,
            "co_robimy": [
                co_robimy(g, a, bool(w)) for g, a, w in zip(lista["grupa"], lista["akcja"], lista["wyslac_oferte"])
            ],
            "powod": powod,
            "id_umowy": lista["id_umowy"].astype(str),
            "id_najemcy": lista["id_najemcy"].astype(str),
            "rodzaj_klienta": lista["linia"].map(ETYKIETA_LINII),
            "miasto": lista["miasto"],
            "budynek": lista["budynek"],
            "koniec_umowy": pd.to_datetime(lista["data_do"]).dt.date,
            "dni_do_konca": lista["dni_do_konca"].astype(int),
            "szansa_odejscia": lista["ryzyko"].astype(float),
            "zmiana_szansy_przedluzenia_przez_oferte": lista["uplift"].astype(float),
            "zalecenie_modelu": lista["akcja"].map(ETYKIETA_AKCJI),
            "grupa": lista["grupa"].map(ETYKIETA_GRUPY),
            "wyslac_oferte": lista["wyslac_oferte"].astype(bool),
            "kampania": lista["kampania"],
        }
    )


def werdykt(od: float, do: float) -> str:
    """Odpowiedź na „czy kampania zarabia” z 95% przedziału wyniku netto (zł)."""
    if do < 0:
        return "Nie. Kampania traci pieniądze: nawet najlepszy wynik z przedziału jest poniżej zera."
    if od > 0:
        return "Tak. Kampania zarabia: nawet najgorszy wynik z przedziału jest powyżej zera."
    return "Nie wiadomo. Przedział obejmuje i stratę, i zysk: potrzeba więcej danych."


def tabele_kampanii(k: dict) -> dict[str, pd.DataFrame]:
    """Tabele wyników kampanii z kampania_2026q3.json (główny wariant: bootstrap w grupach)."""
    g = k["glowny"]
    ci = g["ci95_bootstrap"]
    grupy = pd.DataFrame(
        [
            {
                "kolejnosc": 1,
                "grupa": "z ofertą",
                "umowy": g["n_oferta"],
                "przedluzenia": g["przedluzone_oferta"],
                "odsetek_przedluzen": g["odsetek_oferta"],
                "przedzial_od": ci["odsetek_oferta"][0],
                "przedzial_do": ci["odsetek_oferta"][1],
            },
            {
                "kolejnosc": 2,
                "grupa": "bez oferty (kontrolna)",
                "umowy": g["n_kontrola"],
                "przedluzenia": g["przedluzone_kontrola"],
                "odsetek_przedluzen": g["odsetek_kontrola"],
                "przedzial_od": ci["odsetek_kontrola"][0],
                "przedzial_do": ci["odsetek_kontrola"][1],
            },
        ]
    )
    wynik = pd.DataFrame(
        [
            (1, "Różnica w odsetku przedłużeń (oferta − kontrola)", "punkty procentowe", 100 * g["ate"],
             100 * ci["ate"][0], 100 * ci["ate"][1]),
            (2, "Dodatkowe przedłużenia dzięki ofercie", "umowy", g["dodatkowe_przedluzenia"],
             ci["dodatkowe_przedluzenia"][0], ci["dodatkowe_przedluzenia"][1]),
            (3, "Korzyść: dodatkowe przedłużenia × koszt odejścia (R)", "zł", g["korzysc"], None, None),
            (4, "Koszt rabatów (przedłużenia z rabatem × D)", "zł", -g["koszt_rabatow"], None, None),
            (5, "Koszt kontaktu (oferty × k)", "zł", -g["koszt_kontaktu"], None, None),
            (6, "Wynik netto kampanii", "zł", g["wynik_netto"], ci["wynik_netto"][0], ci["wynik_netto"][1]),
            (7, "ROI (wynik netto / koszt)", "%", 100 * g["roi"], 100 * ci["roi"][0], 100 * ci["roi"][1]),
        ],
        columns=["kolejnosc", "pozycja", "jednostka", "wartosc", "przedzial_od", "przedzial_do"],
    )  # fmt: skip
    od, do = ci["wynik_netto"]
    podsumowanie = pd.DataFrame(
        [
            {
                "kampania": NAZWA_KAMPANII,
                "czy_kampania_zarabia": werdykt(od, do),
                "wynik_netto_zl": g["wynik_netto"],
                "wynik_netto_od_zl": od,
                "wynik_netto_do_zl": do,
                "roi": g["roi"],
                "roi_od": ci["roi"][0],
                "roi_do": ci["roi"][1],
                "oferty": g["n_oferta"],
                "umowy_kontrolne": g["n_kontrola"],
                "koszt_jednego_dodatkowego_przedluzenia_zl": g["koszt_na_dodatkowe_przedluzenie"],
                "losowania_z_zyskiem": k["glowny"]["udzial_losowan_netto_dodatni"],
            }
        ]
    )
    segmenty = pd.DataFrame(
        [
            {
                "kolejnosc": i,
                "segment": etykieta,
                "umowy_z_oferta": s["n_oferta"],
                "umowy_kontrolne": s["n_kontrola"],
                "odsetek_z_oferta": s["odsetek_oferta"],
                "odsetek_kontrola": s["odsetek_kontrola"],
                "roznica_pp": 100 * s["ate"],
                "roznica_od_pp": 100 * s["ci95_ate_wald"][0],
                "roznica_do_pp": 100 * s["ci95_ate_wald"][1],
            }
            for i, (klucz, etykieta) in enumerate(
                [("linia=B2C", "klienci prywatni"), ("linia=B2B", "firmy")]
                + [(m, f"koniec umowy {m.split('=')[1]}") for m in sorted(k["segmenty"]) if m.startswith("miesiac")],
                start=1,
            )
            for s in [k["segmenty"][klucz]]
        ]
    )
    return {
        "kampania_grupy": grupy,
        "kampania_wynik": wynik,
        "kampania_podsumowanie": podsumowanie,
        "kampania_segmenty": segmenty,
    }


def tabela_zalozen(z: dict) -> pd.DataFrame:
    nazwy = {"koszt_odejscia_R": "R", "rabat_roczny_D": "D", "koszt_kontaktu_k": "k"}
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "wartosc_zl": float(z[klucz]["wartosc"]),
                "co_oznacza": z[klucz]["jednostka"],
                "zrodlo": " ".join(str(z[klucz]["zrodlo"]).split()),
                "odpowiedzialny": z[klucz]["odpowiedzialny"],
            }
            for klucz, symbol in nazwy.items()
        ]
    )


# --- zapis -----------------------------------------------------------------------------------------------------------


def zbuduj_panel(sciezka_bazy: Path = SCIEZKA_BAZY, katalog: Path = KATALOG_PANELU) -> dict:
    """Zapisuje tabele panelu jako `<katalog>/<tabela>.parquet` (plik obok + os.replace); zwraca liczby wierszy."""
    with polaczenie(sciezka=sciezka_bazy) as con:
        istnieje = con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [lista_retencyjna.TABELA]
        ).fetchone()[0]
        lista = con.execute(SQL_LISTY).df() if istnieje else pd.DataFrame(columns=[*lista_retencyjna.KOLUMNY])
    tabele = {"lista_tydzien": lista_dla_panelu(lista) if len(lista) else lista_dla_panelu_pusta()}
    tabele |= tabele_kampanii(json.loads(SCIEZKA_KAMPANII.read_text(encoding="utf-8")))
    tabele["zalozenia"] = tabela_zalozen(wczytaj_zalozenia())
    data_listy = tabele["lista_tydzien"]["data_listy"].max() if len(tabele["lista_tydzien"]) else None
    tabele["panel_info"] = pd.DataFrame(
        [
            {
                "odswiezono": datetime.now(STREFA).replace(microsecond=0, tzinfo=None),
                "data_listy": data_listy,
                "stan_danych_na": pd.Timestamp("2026-09-30").date(),
                "zrodlo": "domilo.duckdb (lista_retencyjna, PMS) i retention_bc/wyniki/kampania_2026q3.json",
            }
        ]
    )

    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)
    for nazwa, df in tabele.items():
        plik = katalog / f"{nazwa}.parquet"
        tymczasowy = katalog / f".{nazwa}.parquet.tmp"
        df.to_parquet(tymczasowy, index=False)
        os.replace(tymczasowy, plik)
    return {nazwa: len(df) for nazwa, df in tabele.items()}


def lista_dla_panelu_pusta() -> pd.DataFrame:
    kolumny = lista_dla_panelu(
        pd.DataFrame(columns=[*lista_retencyjna.KOLUMNY, "miasto", "budynek"]).astype({"data_listy": "object"})
    )
    return kolumny


if __name__ == "__main__":
    print(json.dumps(zbuduj_panel(), ensure_ascii=False))
    print(KATALOG_PANELU)
