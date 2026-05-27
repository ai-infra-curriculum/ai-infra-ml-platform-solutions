# SOLUTION — Module 08: Observability

> Read after the per-exercise solutions. Cross-exercise rationale.

## What the module is really teaching

ML-platform observability is the engineer-track observability
(`engineer/mod-108`) **plus** the model-specific signals nobody
else's monitoring stack captures:

- Per-model latency + throughput + error rate.
- Per-model drift signals (data drift, concept drift, prediction
  drift).
- Per-model cost attribution.
- Per-model SLO + error budget.

A platform that monitors only infra is a platform that lets bad
models hide behind green infra dashboards.

## Exercise-by-exercise rationale

### Ex-01 — Per-model dashboard

The reference dashboard is **one panel per golden signal × per
model**:

- p50/p95/p99 latency.
- Request rate.
- Error rate.
- Saturation (GPU + memory utilization).

Plus model-specific:

- Average confidence.
- Class-distribution histogram.
- Drift score (vs. last week's baseline).

One dashboard per model. The model owner reads it before they
go to bed.

### Ex-02 — Burn-rate alerts

The reference replaces threshold alerts (`p95 > 500ms`) with
multi-window multi-burn-rate alerts:

- Fast page: budget exhaustion in <1 hour.
- Slow page: budget exhaustion in <3 days.

The thresholds are derived from the SLO + the burn-rate math, not
guessed. Static thresholds drift; burn-rate alerts auto-tighten
when traffic grows.

### Ex-03 — Drift monitoring

Three drift types, three detectors:

- **Data drift**: KS test on input features, sampled hourly.
- **Concept drift**: rolling-window accuracy vs reference window.
- **Prediction drift**: class-distribution chi-square vs baseline.

Each detector has a clear false-positive rate. Each fires only
on persistent drift, not single-sample anomalies.

### Ex-04 — Cost rollup

A query layer over the cost-attribution pipeline from `mod-003/
ex-05`. The model owner sees:

- Today's spend across all their models.
- This month's spend vs. budget.
- Per-request cost (compute + GPU-hours / requests).

Cost without per-request granularity hides the inefficient models.

### Ex-05 — Incident runbooks

One runbook per alert. Each runbook follows the structure:

- **What this alert means** (the symptom the user feels).
- **What to check first** (the most-common cause).
- **How to mitigate now** (the on-call action).
- **How to fix permanently** (the follow-up issue).

A platform with N alerts but no runbooks has N pages and zero
ability to respond. A platform with N alerts and N runbooks has
N pages and N response paths.

## Cross-exercise design decisions

- **One dashboard per model**, not a giant grid.
- **Burn-rate alerts** over static thresholds.
- **Multiple drift signals**, not a single composite.
- **Cost-per-request** as a first-class metric.
- **Every alert has a runbook**, no exceptions.

## Common mistakes graders see

1. **One mega-dashboard for all models**. Unreadable during an
   incident.
2. **Static `p95 > X` alerts** that drift as traffic grows.
3. **A single drift metric** that papers over the type
   distinction.
4. **Cost reported only at the team level**. Hides which
   model bleeds.
5. **Alerts without runbooks**. On-call eventually mutes them.

## Related curriculum touchpoints

- `engineer/mod-108/ex-01-observability-stack` — the prom + ELK
  infrastructure.
- `engineer/mod-108/ex-02-ml-model-monitoring` — the model-
  specific monitoring details.
- `engineer/mod-106/ex-05-model-monitoring-drift` — the
  drift-detection algorithms.
- `architect/mod-301` — observability discipline at enterprise
  scale.
