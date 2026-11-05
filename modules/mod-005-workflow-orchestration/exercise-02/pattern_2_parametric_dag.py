"""Pattern 2 — Parametric / dynamic-DAG factory.

One DAG per row in ``models.yaml``, generated at parse time. Scales
with N(models) at the cost of per-model observability clarity.

Dynamic DAG generation is a supported Airflow pattern — generate at
parse time (top level of the file), not inside a task.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow.decorators import dag, task

CONFIG_PATH = Path(__file__).parent / "models.yaml"
DEFAULT_ARGS = {
    "owner": "ml-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _build_dag(cfg: dict):
    dag_id = f"train_{cfg['name']}"

    @dag(
        dag_id=dag_id,
        description=f"Parametric training DAG for {cfg['name']}",
        start_date=datetime(2026, 1, 1),
        schedule=cfg["schedule"],
        catchup=False,
        default_args={**DEFAULT_ARGS, "sla": timedelta(hours=2)},
        tags=["training", cfg["algorithm"], "pattern-2"],
        params={"model_name": cfg["name"], "quality_gate": cfg["quality_gate"]},
    )
    def _pipeline():
        @task
        def extract() -> str:
            return cfg["features_uri"]

        @task
        def train(features_uri: str) -> str:
            return f"s3://models/{cfg['name']}/{datetime.now():%Y-%m-%d}.joblib"

        @task
        def evaluate(model_uri: str) -> dict:
            return {"model_uri": model_uri, "accuracy": 0.95}

        @task
        def gate(result: dict) -> None:
            if result["accuracy"] < cfg["quality_gate"]:
                raise ValueError(
                    f"{cfg['name']} failed gate: {result['accuracy']} < {cfg['quality_gate']}"
                )

        gate(evaluate(train(extract())))

    return _pipeline()


# Parse-time generation: each row in models.yaml becomes a DAG.
with CONFIG_PATH.open() as fh:
    _catalog = yaml.safe_load(fh)

for _cfg in _catalog["models"]:
    globals()[f"dag_{_cfg['name']}"] = _build_dag(_cfg)
