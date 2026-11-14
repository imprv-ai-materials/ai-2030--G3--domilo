# Obraz devcontainera Domilo S.A. Zawiera tylko NARZĘDZIA (Python 3.12, Poetry, Node 20, pnpm, git-lfs,
# Claude Code), bez kodu aplikacji. Repozytorium jest podmontowane, a zależności instaluje postCreate.sh,
# więc ten sam obraz działa na macOS, Windowsie (WSL2) i Linuksie.

FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

ENV POETRY_VERSION=2.1.4 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential do kompilacji pakietów bez gotowych kół, git-lfs do pobrania danych z data/.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential git-lfs \
 && rm -rf /var/lib/apt/lists/*

# Node 20 (NodeSource), potem pnpm przez corepack. Panel w ui/ powstaje w projektach kursu.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && corepack enable \
 && corepack prepare pnpm@latest --activate

# Claude Code CLI: `claude` jest w PATH od pierwszego uruchomienia kontenera.
RUN npm install -g @anthropic-ai/claude-code

# `penv` aktywuje .venv projektu z dowolnego katalogu.
RUN echo "alias penv='source /workspaces/domilo/.venv/bin/activate'" >> /home/vscode/.bashrc

# Entrypoint dopasowuje uid/gid użytkownika `vscode` do właściciela repozytorium na hoście z Linuksem
# (devcontainery na compose nie robią tego same). Usunięcie CR chroni przed klonem z Windowsa z końcami CRLF:
# jądro czytałoby wtedy shebang jako `/usr/bin/env bash\r` i kontener kończyłby pracę od razu.
COPY entrypoint.sh /usr/local/bin/devcontainer-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/devcontainer-entrypoint.sh \
 && chmod +x /usr/local/bin/devcontainer-entrypoint.sh

# Poetry we własnym venv (przypięta wersja), w PATH dla każdego użytkownika.
RUN python3 -m venv "${POETRY_HOME}" \
 && "${POETRY_HOME}/bin/pip" install --no-cache-dir "poetry==${POETRY_VERSION}"
ENV PATH="${POETRY_HOME}/bin:${PATH}"
