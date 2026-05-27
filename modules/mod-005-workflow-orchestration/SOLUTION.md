# SOLUTION — Module 05: Workflow Orchestration

> Read after the per-exercise solutions. Cross-exercise rationale.

## What the module is really teaching

Workflow orchestration is *the* discipline that distinguishes a
platform from "a collection of scripts running on cron." The four
production failures the module is shaped around:

1. **Re-running a failed job overwrites the partial output of the
   first try** (no idempotency).
2. **A backfill takes the cluster down** (no concurrency
   limits).
3. **A late upstream silently produces wrong downstream answers**
   (no SLA + alerting).
4. **The orchestrator picks the same wrong job to run twice when
   the cluster is full** (no pool capacity model).

Each exercise targets one. The capstone (ex-05) integrates them
into a pool-tuning study.

## Exercise-by-exercise rationale

### Ex-01 — Orchestrator selection

A document, not code. The reference compares Airflow, Prefect,
Dagster, and Argo Workflows along seven axes (DAG expressiveness,
operational maturity, ecosystem, Python-native vs YAML, retry
semantics, observability, cost). The conclusion the reference
defends: **Airflow for the foreseeable mainstream choice**,
Dagster for teams who can adopt early and benefit from its data-
lineage model, Argo for teams already deep on Kubernetes.

The point of the exercise isn't the answer; it's the *muscle of
defending an orchestrator choice in writing*. Platform teams pick
this tool once and live with it for a decade.

### Ex-02 — Four orchestration patterns

The four patterns:

1. **Fan-out / fan-in** (parallelize then aggregate).
2. **Conditional branching** (if-then-else routing).
3. **Dynamic task generation** (loop over a list known only at
   runtime).
4. **Cross-DAG signaling** (one DAG waits on another).

Each has a canonical Airflow expression and a common
anti-pattern. The exercise teaches the engineer to recognize the
pattern shape before they write the DAG.

### Ex-03 — Safe backfill

The reference implementation:

- Parameterized DAG (`backfill_start`, `backfill_end` params).
- `max_active_runs` set so a long backfill doesn't eat all worker
  slots.
- Per-task `pool` membership so the backfill doesn't starve
  production runs.
- Idempotency check at the writer — re-running over the same
  window produces the same output.

A backfill that takes the cluster down is the canonical
"orchestration done wrong" failure. The four constraints above
make it impossible.

### Ex-04 — SLA + alerting

The reference shape:

- Each DAG has a **defined SLA** (max end-to-end runtime).
- Each critical task has a `sla_miss_callback` that pages.
- The on-call dashboard shows the rolling 7-day SLA hit-rate.
- Long-running DAGs send "still running, you should know" Slack
  pings at the SLA mark.

Without SLA + alerting, "the pipeline failed silently overnight"
is your daily ops report. With it, the pipeline tells you about
itself.

### Ex-05 — Pool capacity tuning

The capstone. A pool sizing study:

- Inventory: number of teams, average DAGs per team, peak hour-
  level concurrency need.
- Sizing: total worker slots, distribution across pools, queue-
  depth model.
- Tuning: iterative — measure backlog, adjust pool sizes,
  re-measure.

The deliverable is a written sizing doc + a Python notebook
that simulates worker-slot consumption under measured load.

## Cross-exercise design decisions

- **Airflow** as the reference orchestrator (market share +
  ecosystem).
- **Pools** for tenant isolation inside the orchestrator.
- **Every DAG has an SLA**; SLA misses page.
- **Backfill is a first-class operation**, parameterized in the
  same DAG, not a parallel codepath.

## Common mistakes graders see

1. **Idempotency-by-convention** instead of by mechanism.
   Eventually someone forgets.
2. **No `max_active_runs`** — one backfill saturates the cluster.
3. **SLA without a callback** — you know the SLA was missed; no
   one was paged.
4. **One pool for everything** — your noisy team can starve every
   other team.
5. **Dynamic task generation against an unbounded list** — DAG
   gets too large to render, scheduler degrades.

## Related curriculum touchpoints

- `engineer/mod-105/ex-04-workflow-orchestration-airflow` — the
  next-tier Airflow exercise.
- `ml-platform/mod-003` — quotas are the cluster-level analog of
  pools.
- `mlops/project-1-ml-pipeline` — the full-pipeline version.
- `architect/mod-301` — orchestration at enterprise scale.
