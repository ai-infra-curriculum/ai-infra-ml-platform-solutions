"""Airflow DAG with SLA + on_failure + Slack callbacks."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from airflow.decorators import dag, task


SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK", "")


def slack(text: str):
    if SLACK_WEBHOOK:
        httpx.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)


def sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
    slack(f"⏱ SLA MISS on {dag.dag_id}: tasks {[s.task_id for s in slas]}")


def failure_callback(context):
    ti = context["task_instance"]
    if ti.try_number > 3:
        slack(f"❌ {ti.dag_id}.{ti.task_id} failed {ti.try_number} times — paging on-call")


@dag(dag_id="ml_training_with_sla",
     start_date=datetime(2026, 1, 1),
     schedule="0 4 * * *",
     catchup=False,
     default_args={
         "retries": 3,
         "retry_delay": timedelta(minutes=2),
         "sla": timedelta(hours=4),
         "on_failure_callback": failure_callback,
     },
     sla_miss_callback=sla_miss_callback)
def pipeline():
    @task
    def train(): return "trained"
    @task
    def deploy(model: str): return f"deployed: {model}"
    deploy(train())


pipeline()
