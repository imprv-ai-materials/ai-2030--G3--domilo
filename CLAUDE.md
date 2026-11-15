# CLAUDE.md — Domilo S.A.

## Firma

Domilo S.A. to operator najmu instytucjonalnego: wynajmuje mieszkania w budynkach, które sam posiada i obsługuje.
Dane są syntetyczne (firmy, osoby i adresy fikcyjne), przygotowane do kursu „Zostań praktykiem modeli predykcyjnych”.

Skala według danych (sprawdzone 2026-11-15 na `pms_budynki`, `pms_lokale`, `serwis_windy`):

| Miasto | Budynki | Lokale | Windy |
|---|---:|---:|---:|
| Warszawa | 14 | 2 900 | 52 |
| Kraków | 7 | 1 300 | 26 |
| Wrocław | 6 | 1 100 | 22 |
| Poznań | 4 | 700 | 14 |
| Gdańsk | 4 | 650 | 15 |
| Łódź | 3 | 550 | 11 |
| **Razem** | **38** | **7 200** | **140** |

Systemy źródłowe: PMS (lokale, najmy, umowy, płatności), CRM (zapytania, doradcy, www), portal najemcy,
serwisownik (zgłoszenia techniczne, windy), Telemetra (czujniki wind i ciepła), Radar (rynek: oferty, transakcje RCN,
operaty, zdjęcia), FK (koszty), dane zewnętrzne (POI, dzielnice GUS). Opis tabel: [data/README.md](data/README.md).

## Cztery modele

| Model | Pytanie biznesowe | Główne źródła |
|---|---|---|
| Wycena lokali z przedziałem | Ile wart jest czynsz / lokal i z jaką niepewnością? | `radar/`, `zewnetrzne/`, `pms_lokale` |
| Kolejka zapytań dla doradców | Którym zapytaniem doradca ma zająć się najpierw? | `crm/` |
| Lista retencyjna najemców | Którzy najemcy nie przedłużą umowy i komu dać ofertę? | `pms_umowy`, `portal/`, `retencja_decyzje`, `fk_rabaty` |
| Alerty o awariach wind | Która winda wkrótce się zepsuje? | `serwis/`, `telemetra/telemetra_windy` |

## Zasady (obowiązują zawsze)

1. **`data/` jest tylko do odczytu.** Nie zapisuj, nie przenoś, nie usuwaj i nie nadpisuj niczego w `data/`.
   Bazy (`domilo.duckdb`), wyniki pośrednie, modele i raporty zapisuj poza tym katalogiem.
2. **Liczby tylko z danych.** Każda liczba w raporcie, kodzie, komentarzu i odpowiedzi pochodzi z zapytania lub
   obliczenia wykonanego na `data/` (albo na artefakcie z niego zbudowanym), a zapytanie jest pokazane obok.
   Nie podawaj liczb z pamięci, wiedzy ogólnej ani szacunków „na oko”. Jeśli danych brakuje, napisz „brak w danych”.
   Założenia biznesowe (np. koszt utraconego najemcy) podawaj tylko od użytkownika i oznaczaj jako założenie.
3. **Każdy model ma punkt odniesienia (baseline)** zapisany w [evals/porownanie.md](evals/porownanie.md):
   prosta reguła lub obecny sposób działania firmy, liczony na tym samym podziale danych i tymi samymi metrykami co model.
   Bez porównania z baseline nie piszemy, że model „działa” ani że jest „lepszy”.
4. **Raporty w `docs/`** (Markdown) mają stały układ:
   1. 3–5 zdań wniosków (co z tego wynika dla Domilo, bez żargonu);
   2. tabele z wynikami;
   3. SQL i kod, którymi wyniki policzono (tak, by dało się je powtórzyć).
5. **Odpowiedź w czacie kończ** listą zmienionych plików i pytaniami do użytkownika.

## Pułapki w danych (ważne dla modeli)

- **Dzień eksportu: 2026-09-30 23:59 Europe/Warsaw.** Dane zdarzeniowe 2023-01-01 – 2026-09-30.
- **Stan na dzień eksportu ≠ historia:** `pms_lokale.status`, `pms_lokale.czynsz_katalogowy`, `crm_leady.status`
  opisują stan na koniec eksportu. Cechy do modelu bierz z historii (`crm_historia_statusow`, `pms_umowy`, …)
  według stanu na moment predykcji, inaczej przeciek przyszłości.
- **Importy i migracje:** PMS od 2019-04, rekordy sprzed 2023-03-01 to import (puste `data_podpisania`,
  puste `zrodlo`); CRM sprzed 2025-03-03 to migracja z poprzedniego systemu.
- **Opóźnienie RCN:** `rcn_transakcje` kończy się 2026-06-30 (publikacja z opóźnieniem 60–120 dni).
- **Czas:** CRM — tekst ISO 8601 z przesunięciem; serwisownik — czas lokalny bez strefy (2025-10-26 02:00–03:00
  występuje dwa razy); Telemetra — `ts_utc` w UTC, koniec okna 10 min. Czas biznesowy: Europe/Warsaw.
- **Formaty:** `serwis_czesci.koszt_netto` to tekst z przecinkiem dziesiętnym (`1 234,50`);
  `wibracje_rms_mg` puste przed montażem czujnika (`serwis_windy.czujnik_wibracji_od`).
- Najmy z `data_wprowadzenia` po dniu eksportu to umowy już podpisane (lokal ma jeszcze status „wolny”).
- `portal_logowania_mies` to agregat za **cały** miesiąc kalendarzowy — uważaj na miesiąc predykcji.

## Mapa folderów

```
data/                         # dane źródłowe Domilo — TYLKO DO ODCZYTU
domilo.duckdb                 # baza budowana z data/ (pypyr baza), w .gitignore
docs/                         # raporty (wnioski → tabele → SQL i kod)
├── bank/                     # raporty kwartalne dla banku (zadanie nocne, raport_RRRRQn.md)
evals/porownanie.md           # model vs baseline, wszystkie cztery modele
dev/                          # pipeline'y pypyr (m.in. baza.yaml)
api/api/                      # kod Pythona (src_dir pypyr; testy w api/tests/)
├── main.py                   # FastAPI: POST /valuation, odczyty dla panelu, Inngest pod /api/inngest (pypyr api)
├── inngest_app.py            # funkcja Inngest wyceny-nocne (02:00 Europe/Warsaw; ręcznie: pypyr nocne)
├── adapters/                 # połączenia z systemami zewnętrznymi
│   ├── duckdb_baza.py        # polacz(), polaczenie() (blokada procesu) i zbuduj_baze() dla domilo.duckdb
│   └── wyceny_historia.py    # tabela wyceny_historia w domilo.duckdb (przenoszona przy przebudowie bazy)
├── contexts_boundaries/      # konteksty biznesowe (bounded contexts)
│   ├── valuation_bc/         # wycena lokali
│   ├── leasing_bc/           # zapytania i doradcy (najem)
│   ├── retention_bc/         # retencja najemców
│   └── maintenance_bc/       # serwis i windy
│       └── zalozenia.yaml    # (w każdym bc) stałe ekonomiczne — tylko od użytkownika, z opisem źródła
└── ai/
    ├── features/             # budowa cech per model
    │   ├── wycena/
    │   ├── leady/
    │   ├── najemcy/
    │   └── windy/
    ├── valuation_model/      # wycena lokali z przedziałem
    ├── lead_model/           # kolejka zapytań dla doradców
    ├── churn_model/          # lista retencyjna najemców
    ├── failure_model/        # alerty o awariach wind
    │   ├── base.py           # (w każdym modelu) wspólny interfejs / definicja modelu
    │   ├── versions/         # kolejne wersje modelu
    │   ├── evals/            # ewaluacje wersji
    │   └── current.yaml      # wskazanie wersji używanej obecnie
    └── llm/
        ├── prompts/          # prompty
        ├── schemas/          # schematy odpowiedzi
        └── cache/            # cache odpowiedzi LLM (poza gitem)
ui/                           # panel rzeczoznawcy (Next.js, port 3100; pnpm --dir ui dev)
```

Powiązania: `valuation_bc` ↔ `features/wycena` ↔ `valuation_model`; `leasing_bc` ↔ `features/leady` ↔ `lead_model`;
`retention_bc` ↔ `features/najemcy` ↔ `churn_model`; `maintenance_bc` ↔ `features/windy` ↔ `failure_model`.

## Baza domilo.duckdb

- Budowa: `pypyr baza`, czyli `api.adapters.duckdb_baza.zbuduj_baze()`. Trwa kilka sekund, a bazę zawsze buduje
  od zera z `data/`. W kodzie łącz się przez `polacz()`, nie przez `duckdb.connect()` bezpośrednio.
- **Tabele:** po jednej na każdy plik Parquet z `data/`, nazwa = nazwa pliku bez rozszerzenia (39 tabel, w tym
  `metadane` ze `zdjecia/metadane.parquet` oraz `telemetra_firmware` i `telemetra_urzadzenia_ciepla`). Zdjęć JPEG
  nie wczytujemy.
- **Widoki:** `telemetra_windy` i `telemetra_cieplo` czytają partycje `rok=/miesiac=` (kolumny `rok`, `miesiac`
  jako INTEGER). Mają ścieżki względne `data/...`: `polacz()` ustawia `file_search_path` na katalog repozytorium,
  a w CLI uruchamiaj zapytania z katalogu głównego.
- **Czas:** `polacz()` ustawia `TimeZone = 'Europe/Warsaw'`.
  - CRM (`crm_*.utworzono|data_statusu|data_czas`, `www_sesje.data_czas`): TIMESTAMPTZ, czyli dokładny moment.
  - Serwisownik (`serwis_*`): TIMESTAMP bez strefy = czas lokalny Warszawy, bez zmian względem źródła. Godziny
    2025-10-26 02:00–03:00 baza nie rozstrzyga.
  - Telemetra (`ts_utc`): TIMESTAMPTZ, tak jak w Parquecie.
  - Porównanie TIMESTAMP z TIMESTAMPTZ traktuje TIMESTAMP jako czas warszawski, co jest poprawne dla Serwisownika,
    PMS i portalu. Bez `polacz()` (np. w CLI) najpierw wykonaj `SET TimeZone = 'Europe/Warsaw'`.
- `serwis_czesci.koszt_netto` jest w bazie liczbą DECIMAL(12,2) (w źródle tekst `1 234,50`).
- Testy: `api/tests/test_duckdb_baza.py` sprawdza liczby wierszy względem Parquetów, typy czasu i widoki.

## Narzędzia

- Python 3.12 + Poetry (`poetry install`, `poetry run pypyr install`); zadania: `pypyr format|lint|test`.
- Biblioteki: duckdb 2.0, pandas 3.1, pyarrow 26, scikit-learn 1.9, lightgbm 4.7, pytz (`pyproject.toml`).
  `pytz` jest potrzebny, bo bez niego DuckDB nie zwraca do Pythona kolumn TIMESTAMPTZ.
- Dane czytamy przez `polacz()` (baza) albo DuckDB/pandas wprost z Parquetu.
  **DuckDB 2.0:** relacja z `duckdb.sql(...)` nie ma `fetchone()` — używaj `.fetchall()` albo
  `con.execute(...).fetchone()`. CLI `duckdb` 1.5 na hoście **nie otworzy** `domilo.duckdb` (format pliku 2.0),
  ale wciąż czyta pliki Parquet.
- MLflow 3.18: eksperymenty w `mlflow.db` + `mlartifacts/` (katalog główny, w .gitignore), połączenie przez
  `api.adapters.mlflow_rejestr.ustaw_eksperyment()`; wycena loguje się do eksperymentu `wycena`
  (`valuation_model/evals/ewaluacja.py`). Podgląd: `poetry run mlflow ui --backend-store-uri sqlite:///mlflow.db`.
- Skille procesu pracy: `.claude/skills/` (m.in. `use-sw-development-workflow`, `sw-test-driven-development`).
