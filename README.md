# ai-2030--G3--domilo

Repozytorium do kursu „Zostań praktykiem modeli predykcyjnych”. Budujemy w nim dla Domilo S.A. (operator najmu mieszkań: 7 200 lokali w 38 budynkach w 6 miastach, 140 wind) cztery modele: wycenę lokali z przedziałem, kolejkę zapytań dla doradców, listę retencyjną najemców i alerty o awariach wind.

Na start repozytorium ma tylko dane i narzędzia. Kod, bazę i raporty buduje agent, lekcja po lekcji.

## Co tu jest

| Co | Gdzie |
|---|---|
| Dane Domilo (Parquet, zdjęcia), opis tabel | `data/`, [data/README.md](data/README.md) |
| Skille dla Claude Code (praca krok po kroku, TDD, przegląd kodu, modelowanie domeny…) | `.claude/skills/` |
| Devcontainer: Python 3.12, Poetry, Node 20, pnpm, Claude Code, serwer Inngest | `.devcontainer/` |
| Zadania pypyr: instalacja, formatowanie, lint, testy | `dev/`, [dev/README.md](dev/README.md) |
| Zależności i ustawienia narzędzi | `pyproject.toml` |

## Budujesz razem ze mną: punkt startowy i własna gałąź

Stan repozytorium sprzed pierwszej lekcji praktycznej oznacza tag **`start`**. Gałąź `main` rośnie razem z kursem:
trafia na nią to, co buduję na nagraniach. Tag `start` się nie zmienia, więc zawsze możesz od niego zacząć.

Pobranie repozytorium i własna gałąź od punktu startowego (dane leżą w Git LFS):

```bash
git clone https://github.com/imprv-ai-materials/ai-2030--G3--domilo.git
cd ai-2030--G3--domilo
git lfs install && git lfs pull
git switch -c moja-praca start
```

Pracujesz i robisz commity na gałęzi `moja-praca`. Gałęzi `main` nie zmieniaj: służy do podglądania, jak ten sam krok wyszedł u mnie.

```bash
git fetch origin                          # pobierz moje najnowsze zmiany
git diff moja-praca origin/main           # porównaj swoją wersję z moją
git switch main && git pull               # obejrzyj moją wersję; z powrotem: git switch moja-praca
```

Powrót do punktu startowego:

| Chcę… | Polecenie |
|---|---|
| zacząć od nowa i zachować dotychczasową próbę | `git switch -c proba-2 start` |
| wyrzucić zmiany, których nie zapisałem commitem | `git restore . && git clean -fd` |
| cofnąć swoją gałąź do startu, tracąc jej commity | `git reset --hard start && git clean -fd` |

`git clean -fd` usuwa nowe pliki, których git jeszcze nie śledzi (np. `domilo.duckdb`, wygenerowany kod), ale nie rusza plików z `.gitignore` (`.venv`). Najbezpieczniejsza jest pierwsza opcja: nic nie ginie, a do starej próby wracasz przez `git switch moja-praca`. Jeśli chcesz trzymać swoją pracę na GitHubie, zrób fork repozytorium i wypchnij do niego swoją gałąź.

## Uruchomienie

Najpierw pobierz repozytorium i dane z Git LFS (polecenia w sekcji wyżej).

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
2. struktura repozytorium: cztery konteksty biznesowe, cztery modele, `docs/`, oraz biblioteki do danych i modeli (DuckDB, pandas, pyarrow, scikit-learn, LightGBM);
3. `domilo.duckdb`: jedna baza ze wszystkimi tabelami z `data/` i widokami na telemetrię;
4. `docs/pierwsze_zapytanie.md`: liczba wierszy i zakres dat każdej tabeli, spójność kluczy, obłożenie i końce umów, porównane z tym, co wiemy o firmie.

Po każdym prompcie przejrzyj zmiany i zrób commit.

Jedna zasada obowiązuje od pierwszego promptu: **`data/` jest tylko do odczytu**. Wyniki, bazy i raporty zapisujemy poza tym katalogiem.
