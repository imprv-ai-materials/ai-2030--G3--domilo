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
| `pypyr baza` | `domilo.duckdb` z `data/`, tabela `leady_cel`, modele dbt (schemat `metryki`) |
| `pypyr api` | API (FastAPI) z funkcjami Inngest na porcie 8101 |
| `pypyr nocne` | zadanie nocne wyceny bez Inngest |
| `pypyr mock_lejek` | atrapa CRM dla webhooka kolejek doradców i pola „powód pominięcia” (`dev/mock_lejek/`, port 8102; `/doradca/D01`) |
| `pypyr kolejka_wstecz [od=… do=…]` | ranking kolejki policzony wstecz (punkt odniesienia panelu kierownika, domyślnie 2026-04-15 – 2026-06-30) |
| `pypyr kolejka [data=RRRR-MM-DD]` | zadanie kolejka-doradcow bez Inngest (te same kroki); wymaga atrapy albo `CRM_LEJEK_URL` |
| `pypyr metabase` | panel kampanii retencyjnej w Metabase (`dev/metabase/`, port 3300): dane panelu, sterownik DuckDB, kontener, konfiguracja przez API; wypisuje adres panelu |
| `pypyr lista_retencyjna [data=RRRR-MM-DD] [kampania=…]` | zadanie lista-retencyjna bez Inngest (te same kroki): umowy za 60–66 dni, ryzyko, uplift, akcja, grupa, zapis w `lista_retencyjna` |

Bez aktywnego `.venv` poprzedź polecenie `poetry run` (w devcontainerze `.venv/bin` jest w PATH).
Kolejne pipeline'y (start API, nocne zadania, MLflow) dopisujemy razem z kodem, który uruchamiają.
