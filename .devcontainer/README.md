# Dev Container — Domilo S.A. na każdym systemie

Kontener daje wszystkim to samo środowisko: Python 3.12, Poetry, Node 20, pnpm, git-lfs, Claude Code i serwer
Inngest. Na komputerze potrzebujesz tylko Dockera (Docker Desktop) i VS Code z rozszerzeniem Dev Containers.

## Start

1. Pobierz dane z Git LFS (raz, na hoście): `git lfs install && git lfs pull`.
2. Otwórz repozytorium w VS Code i wybierz **Dev Containers: Reopen in Container**.
   Pierwsze otwarcie trwa kilka minut: obraz, potem `poetry install` w `postCreate.sh`.
3. Gdy w terminalu pojawi się **„Devcontainer gotowy”**, otwórz nowy terminal i uruchom `claude`.

## Co jest w środku

```
┌───────── app (kontener roboczy) ─────────┐        ┌──── inngest ────┐
│  /workspaces/domilo  ← repozytorium      │        │  inngest dev    │
│  .venv, ui/node_modules ← wolumeny       │ ─────▶ │  :8288          │
│  tu uruchamiasz claude, pypyr, uvicorn   │        └────────┬────────┘
└──────────────────────────────────────────┘                 │
                                                 host: http://localhost:8588
```

| Usługa | Adres na hoście | Uwagi |
|---|---|---|
| Panel Inngest | http://localhost:8588 | stały port; pusta lista funkcji, dopóki nie ma `inngest_app.py` |
| API (FastAPI) | port 8101, zakładka Ports | gdy powstanie `api/` |
| Panel (Next.js) | port 3100, zakładka Ports | gdy powstanie `ui/` |

- `.venv` i `ui/node_modules` są w nazwanych wolumenach, więc nie mieszają się z `.venv` zbudowanym na hoście.
  Po zmianie zależności: `poetry install` w terminalu kontenera albo przebudowa kontenera.
- Baza danych to plik DuckDB w repozytorium, więc nie ma osobnego serwera bazy.
- Gdy coś nie startuje (zwłaszcza na Windowsie): [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
