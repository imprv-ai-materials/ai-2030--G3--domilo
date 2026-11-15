"""Rejestr eksperymentów MLflow (lokalnie: baza sqlite + katalog artefaktów w katalogu repozytorium).

Domyślnie: `mlflow.db` i `mlartifacts/` w katalogu głównym repozytorium (oba w .gitignore). Inny serwer wskaż
zmienną środowiskową MLFLOW_TRACKING_URI albo argumentem `tracking_uri`.
Podgląd: `poetry run mlflow ui --backend-store-uri sqlite:///mlflow.db` z katalogu głównego repozytorium.
"""

import os
from pathlib import Path
from typing import Any

import mlflow
from api.adapters.duckdb_baza import KATALOG_REPO

TRACKING_URI_DOMYSLNY = f"sqlite:///{(KATALOG_REPO / 'mlflow.db').as_posix()}"
KATALOG_ARTEFAKTOW = KATALOG_REPO / "mlartifacts"


def ustaw_eksperyment(nazwa: str, tracking_uri: str | None = None, katalog_artefaktow: Path | None = None) -> str:
    """Ustawia serwer i eksperyment (tworzy go, jeśli nie istnieje). Zwraca experiment_id."""
    mlflow.set_tracking_uri(tracking_uri or os.environ.get("MLFLOW_TRACKING_URI") or TRACKING_URI_DOMYSLNY)
    eksperyment = mlflow.get_experiment_by_name(nazwa)
    if eksperyment is None:
        katalog = Path(katalog_artefaktow or KATALOG_ARTEFAKTOW) / nazwa
        eksperyment_id = mlflow.create_experiment(nazwa, artifact_location=katalog.resolve().as_uri())
    else:
        eksperyment_id = eksperyment.experiment_id
    mlflow.set_experiment(experiment_id=eksperyment_id)
    return eksperyment_id


def zapisz_run(
    nazwa_runu: str,
    parametry: dict[str, Any],
    metryki: dict[str, float],
    tagi: dict[str, Any] | None = None,
    artefakty: list[Path] | None = None,
) -> str:
    """Zapisuje jeden run w bieżącym eksperymencie (najpierw `ustaw_eksperyment`). Zwraca run_id."""
    with mlflow.start_run(run_name=nazwa_runu, tags=tagi or {}) as run:
        if parametry:
            mlflow.log_params(parametry)
        if metryki:
            mlflow.log_metrics({k: float(v) for k, v in metryki.items()})
        for sciezka in artefakty or []:
            mlflow.log_artifact(str(sciezka))
        return run.info.run_id
