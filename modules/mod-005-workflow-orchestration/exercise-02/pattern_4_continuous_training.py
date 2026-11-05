"""Pattern 4 — Continuous training (CT).

Scheduled retraining that only promotes a new model if the
challenger beats the champion on a holdout slice. Combines a cron
cadence with a quality gate — you can retrain every day, but the
production model only updates when it's genuinely better.

The guardrail that separates CT from "a cron job that trains" is
the champion/challenger comparison before registry promotion.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException


DEFAULT_ARGS = {
    "owner": "ml-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "sla": timedelta(hours=3),
}


@dag(
    dag_id="continuous_training_iris",
    description="Nightly retrain; promote only if challenger beats champion.",
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["training", "iris", "pattern-4", "continuous-training"],
)
def continuous_training_iris():
    @task
    def fetch_window() -> str:
        # Rolling 30-day window keeps the model fresh to concept drift.
        return "s3://features/iris/rolling_30d.parquet"

    @task
    def train_challenger(features_uri: str) -> str:
        return "s3://models/iris/challenger.joblib"

    @task
    def eval_challenger(challenger_uri: str) -> dict:
        return {"uri": challenger_uri, "accuracy": 0.964}

    @task
    def load_champion_metrics() -> dict:
        # Read from the model registry in real deployments.
        return {"uri": "s3://models/iris/production.joblib", "accuracy": 0.960}

    @task
    def compare_and_gate(challenger: dict, champion: dict) -> dict:
        min_delta = 0.002
        if challenger["accuracy"] - champion["accuracy"] < min_delta:
            # Legal to skip downstream — the champion stays in prod.
            raise AirflowSkipException(
                f"Challenger {challenger['accuracy']:.4f} not better than "
                f"champion {champion['accuracy']:.4f} by >= {min_delta}"
            )
        return challenger

    @task
    def promote(challenger: dict) -> None:
        # Registry call: mark challenger as the new production model.
        return None

    challenger = eval_challenger(train_challenger(fetch_window()))
    winner = compare_and_gate(challenger, load_champion_metrics())
    promote(winner)


continuous_training_iris()
