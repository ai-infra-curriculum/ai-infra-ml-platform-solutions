"""Airflow DAG: daily Feast materialization with backfill support."""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models.param import Param


@dag(dag_id="feast_materialize",
     start_date=datetime(2026, 1, 1),
     schedule="0 5 * * *",
     catchup=False,
     max_active_runs=1,        # safety: only one materialization at a time
     default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
     params={
         "start_iso": Param(None, type=["null", "string"]),
         "end_iso": Param(None, type=["null", "string"]),
     })
def materialize_dag():

    @task
    def run(params: dict):
        from feast import FeatureStore
        fs = FeatureStore("feature_repo")
        if params["start_iso"] and params["end_iso"]:
            start = datetime.fromisoformat(params["start_iso"])
            end = datetime.fromisoformat(params["end_iso"])
            fs.materialize(start, end)
            return {"mode": "backfill", "start": str(start), "end": str(end)}
        fs.materialize_incremental(datetime.now())
        return {"mode": "incremental"}

    run()


materialize_dag()
