# Materialization w/ Backfill — Solution

`materialize_dag.py` runs Feast materialization daily; supports parameterized
backfill via DAG params. `max_active_runs=1` prevents concurrent runs from
corrupting the online store.

Trigger backfill:
```bash
airflow dags trigger feast_materialize --conf '{"start_iso":"2026-01-01","end_iso":"2026-01-31"}'
```
