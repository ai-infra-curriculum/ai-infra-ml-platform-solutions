# Observability metrics catalog (F7)

Catalog of the five Prometheus metrics required by `requirements.md` F7,
plus the label conventions every component re-uses. Naming follows the
Prometheus `<namespace>_<subsystem>_<unit>` convention so the platform's
metrics namespace is grep-able.

## Required metrics

| Metric | Type | Labels | Source |
|---|---|---|---|
| `platform_runs_admitted_total` | counter | `tenant`, `phase` | control-plane |
| `platform_runs_active` | gauge | `tenant` | operator |
| `platform_admission_latency_seconds` | histogram | `tenant`, `outcome` | control-plane |
| `platform_reconcile_latency_seconds` | histogram | `kind` | operator |
| `platform_audit_chain_writes_total` | counter | `result` (`ok`/`error`) | both |

Histograms use the default `prometheus_client` buckets except
`platform_admission_latency_seconds`, which uses `(0.05, 0.1, 0.25, 0.5,
1, 2, 5)` because the architectural target is p95 < 500 ms (see
`architecture.md` "Non-functional requirements").

## Label conventions

- `tenant` — tenant slug, never tenant UUID. UUIDs blow up Prometheus
  cardinality on tenant churn and the slug is what users see in Grafana.
- `phase` — TrainingRun phase enum (`Pending|Running|Succeeded|Failed|Cancelled`).
  Bounded set; safe to label.
- `outcome` — admission outcome (`admitted|rejected_quota|rejected_schema|rejected_policy`).
- `result` — boolean-style `ok|error`. Used only on counters that page on
  error-rate, not on user-visible work.

## What is deliberately not a label

- Run ID. Per-run state belongs in logs + the platform DB, not in
  metrics. Putting it on a metric would create one time-series per run.
- Image digest. Same cardinality reason.
- User identity. Audit chain owns this; metrics aggregate over it.

## Grafana dashboard

`grafana-dashboard.json` (sibling file) is the dashboard the platform
team operates against. It renders the five metrics above plus
derived panels (admit-rate, error-rate, P95 latency). Import with:

```
curl -X POST -H "Content-Type: application/json" \
  -d @grafana-dashboard.json \
  http://grafana.platform.svc/api/dashboards/db
```

## Reading the metrics

Two queries the platform team should know by heart:

```promql
# Per-tenant active runs (capacity-planning view)
sum by (tenant) (platform_runs_active)

# Admission error rate over the last 5 minutes (SLO view)
sum(rate(platform_runs_admitted_total{phase=~"rejected_.*"}[5m]))
  /
sum(rate(platform_runs_admitted_total[5m]))
```
