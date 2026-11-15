import mlflow
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run


def test_run_trafia_do_eksperymentu_z_parametrami_metrykami_tagami_i_artefaktem(tmp_path):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artefakt = tmp_path / "metryki.json"
    artefakt.write_text("{}", encoding="utf-8")

    eksperyment_id = ustaw_eksperyment("wycena", tracking_uri=uri, katalog_artefaktow=tmp_path / "artefakty")
    run_id = zapisz_run(
        "v1_liniowa",
        parametry={"metraz_log": True},
        metryki={"test_mape": 10.2},
        tagi={"podzial": "czasowy"},
        artefakty=[artefakt],
    )

    run = mlflow.get_run(run_id)
    assert run.info.experiment_id == eksperyment_id
    assert mlflow.get_experiment(eksperyment_id).name == "wycena"
    assert run.info.run_name == "v1_liniowa"
    assert run.data.params == {"metraz_log": "True"}
    assert run.data.metrics == {"test_mape": 10.2}
    assert run.data.tags["podzial"] == "czasowy"
    assert [a.path for a in mlflow.MlflowClient().list_artifacts(run_id)] == ["metryki.json"]
    assert str(tmp_path / "artefakty") in mlflow.get_experiment(eksperyment_id).artifact_location
