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

## Narzędzia

- Python 3.12 + Poetry (`poetry install`, `poetry run pypyr install`); zadania: `pypyr format|lint|test`.
- Dane czytamy DuckDB (`SELECT * FROM 'data/crm/crm_leady.parquet'`) lub pandas (`read_parquet`).
  CLI `duckdb` jest dostępne na hoście; biblioteki do danych i modeli dochodzą w pierwszej lekcji praktycznej.
- Skille procesu pracy: `.claude/skills/` (m.in. `use-sw-development-workflow`, `sw-test-driven-development`).
