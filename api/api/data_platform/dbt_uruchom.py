"""Uruchamia projekt dbt (api/api/data_platform/dbt) na domilo.duckdb.

Modele trafiają do schematu `metryki` w domilo.duckdb. Bazę trzeba mieć zbudowaną (`pypyr baza`, kroki 1–2),
bo modele czytają `leady_cel` i tabele z data/. `pypyr baza` uruchamia to jako krok 3.

Użycie: `cd api && poetry run python -m api.data_platform.dbt_uruchom [build|run|test|...]` (domyślnie build).
"""

import os
import sys
from pathlib import Path

from api.adapters.duckdb_baza import SCIEZKA_BAZY

KATALOG_DBT = Path(__file__).resolve().with_name("dbt")
SCHEMAT_METRYK = "metryki"


def uruchom_dbt(argumenty: list[str] | None = None) -> bool:
    """Uruchamia dbt z projektem i profilem z KATALOG_DBT; zwraca True, gdy wszystko przeszło."""
    from dbt.cli.main import dbtRunner

    os.environ["DOMILO_DUCKDB"] = str(SCIEZKA_BAZY)
    argumenty = list(argumenty or ["build"])
    wynik = dbtRunner().invoke(
        [*argumenty, "--project-dir", str(KATALOG_DBT), "--profiles-dir", str(KATALOG_DBT)],
    )
    return bool(wynik.success)


if __name__ == "__main__":
    sys.exit(0 if uruchom_dbt(sys.argv[1:]) else 1)
