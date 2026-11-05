"""Pattern 1 — DAG-per-model.

One Airflow DAG file per model. Explicit, versioned, easy to grep.
The right pattern while N(models) is small (<~15) and each model
has distinct training/eval logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag, task


DEFAULT_ARGS = {
    "owner": "ml-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "sla": timedelta(hours=2),
}


@dag(
    dag_id="train_iris_rf",
    description="Random-forest classifier for the iris dataset",
    start_date=datetime(2026, 1, 1),
    schedule="0 3 * * *",
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["training", "iris", "pattern-1"],
)
def train_iris_rf():
    @task
    def extract() -> str:
        return "s3://features/iris/2026-01-01.parquet"

    @task
    def train(features_uri: str) -> str:
        return f"s3://models/iris_rf/{features_uri.rsplit('/', 1)[-1]}.joblib"

    @task
    def evaluate(model_uri: str) -> dict:
        return {"model_uri": model_uri, "accuracy": 0.97}

    @task
    def register(eval_result: dict) -> None:
        if eval_result["accuracy"] < 0.90:
            raise ValueError(f"Model below quality gate: {eval_result}")

    register(evaluate(train(extract())))


train_iris_rf()
