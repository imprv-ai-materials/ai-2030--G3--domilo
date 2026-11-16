import json

import numpy as np
import pandas as pd
import pytest
from api.ai.failure_model.base import KATALOG_MODELU, KOLUMNY_ZAKAZANE, wczytaj_obecny
from api.ai.failure_model.versions.v3_punkt_pracy.model import ModelPunktPracy
from api.ai.features.windy.cechy import filtr_serwisu
from api.contexts_boundaries.maintenance_bc.alarmy_wind import wczytaj_zalozenia


def test_current_wskazuje_v3_punkt_pracy():
    model = wczytaj_obecny()
    assert isinstance(model, ModelPunktPracy) and model.wersja == "v3_punkt_pracy"
    assert not set(model.cechy) & KOLUMNY_ZAKAZANE
    z = wczytaj_zalozenia()
    assert model.punkt_pracy == {k: z[k] for k in ("alarmy_na_tydzien", "dzien_alarmu", "przerwa_dni")}
    metryki = json.loads((KATALOG_MODELU / "versions" / "v3_punkt_pracy" / "metryki.json").read_text("utf-8"))
    assert metryki["wariant_cech"] == ("bez serwisu" if model.bez_serwisu else "z serwisem")


def test_v3_ranking_jak_model_bazowy_i_prawdopodobienstwo_monotoniczne():
    model = wczytaj_obecny()
    rng = np.random.default_rng(0)
    dni = pd.DataFrame(rng.normal(1.0, 0.5, size=(500, len(model.cechy))), columns=list(model.cechy))
    dni.insert(0, "dzien", pd.Timestamp("2026-03-02"))
    dni.insert(0, "id_windy", [f"W{i}" for i in range(500)])
    wynik = model.predict(dni)
    assert np.array_equal(wynik, model.model_bazowy.predict(dni))
    p = model.prawdopodobienstwo(dni)
    assert ((p >= 0) & (p <= 1)).all()
    assert (np.diff(p[np.argsort(wynik)]) >= -1e-12).all()
    e = model.explain(dni.head(5))
    assert list(e.columns[:2]) == ["wynik", "p_awarii_7d"]


def test_pusty_current_to_blad(tmp_path):
    plik = tmp_path / "current.yaml"
    plik.write_text("# pusty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="żadna wersja"):
        wczytaj_obecny(plik)


def test_filtr_serwisu():
    assert filtr_serwisu(True) == "tryb IS DISTINCT FROM 'serwis'"
    assert filtr_serwisu(True, "t.") == "t.tryb IS DISTINCT FROM 'serwis'"
    assert filtr_serwisu(False) == "TRUE"
