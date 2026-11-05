"""Pattern 3 — Event-driven.

A DAG that waits on an object-arrival event rather than a cron
schedule. Two valid wirings in Airflow 2.x:

1. ``S3KeySensor`` with ``deferrable=True`` — cheap on the worker,
   fires when the key lands.
2. Airflow ``Dataset`` — the producer DAG declares it writes a
   dataset; this DAG subscribes via ``schedule=[Dataset(...)]``.
   Preferred when the producer lives in Airflow too.

This file demonstrates both — comment out whichever does not fit.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import Dataset
from airflow.decorators import dag, task
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor


FEATURES_DATASET = Dataset("s3://features/iris/latest.parquet")
DEFAULT_ARGS = {
    "owner": "ml-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="train_iris_on_event_sensor",
    description="Sensor-based event trigger — fires when a new feature file lands",
    start_date=datetime(2026, 1, 1),
    schedule=None,  # externally triggered or polled by the sensor below
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["training", "iris", "pattern-3", "event-driven"],
)
def train_iris_on_event_sensor():
    wait_for_file = S3KeySensor(
        task_id="wait_for_features",
        bucket_key="s3://features/iris/{{ ds }}.parquet",
        deferrable=True,
        timeout=60 * 60 * 6,
        poke_interval=30,
    )

    @task
    def train() -> str:
        return "s3://models/iris/event_triggered.joblib"

    wait_for_file >> train()


@dag(
    dag_id="train_iris_on_dataset",
    description="Dataset-triggered — fires whenever the producer DAG updates the dataset",
    start_date=datetime(2026, 1, 1),
    schedule=[FEATURES_DATASET],
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["training", "iris", "pattern-3", "event-driven"],
)
def train_iris_on_dataset():
    @task
    def train() -> str:
        return "s3://models/iris/dataset_triggered.joblib"

    train()


train_iris_on_event_sensor()
train_iris_on_dataset()
