# Pool Capacity Plan — Reference

## Workload assumptions (20-team ML platform)

- 50 daily DAGs (training, batch eval, monitoring rollups)
- 5 concurrent Airflow workers per pool
- GPU pool: 16 slots
- CPU pool: 80 slots
- Long-tail tasks: training jobs running 1-8h, holding GPU slot

## Pool layout

| Pool | Slots | Used by |
|---|---|---|
| `training_gpu` | 16 | KubernetesPodOperator GPU jobs (one slot per concurrent training) |
| `cpu_etl` | 80 | data ingest, feature materialization, monitoring rollups |
| `meta` | 10 | DAG-management tasks; airflow internals |

## Risks
- 02:00 thundering herd: most cron-triggered DAGs run at 02:00 — stagger via `schedule` jitter
- Training pool exhaustion: 16 slots filled by 16 training jobs → no new training for hours; add HPA on workers and consider Volcano for fairness
- Backfill DDoS: a 365-day backfill takes 365 slots if parallel — cap concurrency at 8

## Monitoring
- Per-pool slot utilization
- Tasks queued (pending) per pool
- Alert when queued > 50 for > 30 min
