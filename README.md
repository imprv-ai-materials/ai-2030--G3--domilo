# ai-2030--G3--domilo

Repozytorium do kursu „Zostań praktykiem modeli predykcyjnych”. Budujemy w nim dla Domilo S.A. (operator najmu
mieszkań: 7 200 lokali w 38 budynkach w 6 miastach, 140 wind) cztery modele: wycenę lokali z przedziałem, kolejkę
zapytań dla doradców, listę retencyjną najemców i alerty o awariach wind.

Na start repozytorium ma tylko dane i narzędzia. Kod, bazę i raporty buduje agent, lekcja po lekcji.

## Co tu jest

| Co | Gdzie |
|---|---|
| Dane Domilo (Parquet, zdjęcia), opis tabel | `data/`, [data/README.md](data/README.md) |
| Skille dla Claude Code (praca krok po kroku, TDD, przegląd kodu, modelowanie domeny…) | `.claude/skills/` |
| Devcontainer: Python 3.12, Poetry, Node 20, pnpm, Claude Code, serwer Inngest | `.devcontainer/` |
| Zadania pypyr: instalacja, formatowanie, lint, testy | `dev/`, [dev/README.md](dev/README.md) |
| Zależności i ustawienia narzędzi | `pyproject.toml` |

## Uruchomienie

Dane leżą w Git LFS, więc najpierw (raz):

```bash
git lfs install
git lfs pull
```

**W devcontainerze (zalecane).** Wymagania: Docker Desktop, VS Code z rozszerzeniem Dev Containers.
Otwórz repozytorium w VS Code i wybierz **Dev Containers: Reopen in Container**. Szczegóły i problemy na Windowsie:
[.devcontainer/README.md](.devcontainer/README.md).

**Na hoście.** Wymagania: Python 3.12 z Poetry (Node 20+ z pnpm przyda się, gdy powstanie panel).

```bash
poetry install
poetry run pypyr install     # zależności + hooki pre-commit
```

Potem w katalogu repozytorium uruchom `claude`.

## Pierwsza lekcja praktyczna: środowisko i pierwsze zapytanie

W tej lekcji agent przygotowuje wszystko, na czym pracują cztery projekty kursu:

1. `CLAUDE.md`: opis firmy i zasady pracy z danymi;
2. struktura repozytorium: cztery konteksty biznesowe, cztery modele, `docs/`, oraz biblioteki do danych
   i modeli (DuckDB, pandas, pyarrow, scikit-learn, LightGBM);
3. `domilo.duckdb`: jedna baza ze wszystkimi tabelami z `data/` i widokami na telemetrię;
4. `docs/pierwsze_zapytanie.md`: liczba wierszy i zakres dat każdej tabeli, spójność kluczy, obłożenie
   i końce umów, porównane z tym, co wiemy o firmie.

Po każdym prompcie przejrzyj zmiany i zrób commit.

Jedna zasada obowiązuje od pierwszego promptu: **`data/` jest tylko do odczytu**. Wyniki, bazy i raporty
zapisujemy poza tym katalogiem.
