#!/usr/bin/env bash
# Uruchamia się raz, w kontenerze `app`, po jego utworzeniu. Można go puścić ponownie bez szkody.
set -euo pipefail

cd "$(dirname "$0")/.."   # → katalog główny repozytorium

# Repozytorium jest podmontowane z hosta. Jeśli użytkownik kontenera nie może w nim pisać, nic poniżej nie zadziała
# (edytor też nie zapisze plików). Zwykle entrypoint.sh już dopasował uid; to jest głośne zabezpieczenie.
if [ ! -w . ]; then
  cat >&2 <<MSG
✗ $(pwd) nie jest zapisywalny dla $(id -un) (uid $(id -u)); właściciel to uid $(stat -c %u .).
  • Host z Linuksem: przebuduj kontener (Dev Containers: Rebuild Container), żeby entrypoint dopasował uid.
  • Docker / Podman bez roota: ustaw "remoteUser": "root" w devcontainer.json albo uruchom podman z --userns=keep-id.
MSG
  exit 1
fi

echo "▸ Przejmuję punkty montowania wolumenów (.venv, ui/node_modules, ui/.next)…"
# Wolumeny montują się puste i należą do roota; oddajemy je użytkownikowi vscode, żeby poetry i pnpm mogły w nich pisać.
sudo chown -R "$(id -u):$(id -g)" .venv ui/node_modules ui/.next

# .venv to punkt montowania: poetry nie umie go usunąć i utworzyć od nowa, więc pusty albo zepsuty wypełniamy sami.
if [ ! -x .venv/bin/python ]; then
  echo "▸ .venv jest pusty albo zepsuty - tworzę go przez python3 -m venv…"
  python3 -m venv --clear .venv
fi

echo "▸ poetry install (zależności → .venv)…"
poetry install

# pypyr i reszta narzędzi z .venv działają w każdym terminalu kontenera bez `poetry run` ani aktywacji.
if ! grep -q "narzędzia projektu (pypyr)" ~/.bashrc; then
  echo "export PATH=\"$(pwd)/.venv/bin:\$PATH\"  # narzędzia projektu (pypyr) z .venv" >> ~/.bashrc
fi

if [ -f ui/package.json ]; then
  echo "▸ pnpm install (panel → ui/node_modules)…"
  pnpm --dir ui install
fi

# Dane w data/ leżą w Git LFS. Bez `git lfs pull` w plikach są tylko wskaźniki, a nie dane.
if [ -f data/pms/pms_budynki.parquet ] && ! head -c 4 data/pms/pms_budynki.parquet | grep -q PAR1; then
  cat >&2 <<'MSG'

⚠️  Pliki w data/ to wskaźniki Git LFS, nie dane. Pobierz je (na hoście albo w terminalu kontenera):
        git lfs install && git lfs pull
MSG
fi

cat <<'DONE'

✅ Devcontainer gotowy.

    claude              # Claude Code: tu zaczynasz pierwszą lekcję praktyczną
    pypyr format        # black + isort
    pypyr lint          # flake8 (gdy powstanie api/api)
    pypyr test          # pytest (gdy powstanie api/tests)

Panel Inngest: http://localhost:8588 (lista funkcji będzie pusta, dopóki nie powstanie inngest_app.py).

DONE
