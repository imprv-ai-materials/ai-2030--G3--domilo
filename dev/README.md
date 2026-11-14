# dev/ — pipeline'y pypyr

Uruchamiaj z katalogu głównego repozytorium (tam, gdzie `pyproject.toml` i `.venv`). Tabela
`[tool.pypyr.shortcuts]` w `pyproject.toml` mapuje krótką nazwę na plik w tym katalogu, a `[tool.pypyr.vars]`
trzyma wspólne zmienne (długość linii, katalogi kodu i testów).

| Polecenie | Co robi |
|---|---|
| `pypyr install` | `poetry install`, hooki pre-commit, `pnpm install` w `ui/` (gdy `ui/` istnieje) |
| `pypyr format` | `black` + `isort` (zapisuje zmiany) |
| `pypyr check_format` | `black --check` + `isort --check` |
| `pypyr lint` | `flake8` na `api/api` |
| `pypyr test` | `pytest` z pokryciem na `api/tests` (`pypyr test tests=api/tests/x.py` zawęża) |
| `pypyr precommit` | wszystkie hooki pre-commit na wszystkich plikach |

Bez aktywnego `.venv` poprzedź polecenie `poetry run` (w devcontainerze `.venv/bin` jest w PATH).
Kolejne pipeline'y (start API, nocne zadania, MLflow) dopisujemy razem z kodem, który uruchamiają.
