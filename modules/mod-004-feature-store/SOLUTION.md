# SOLUTION — Module 04: Feature Store

> Read after the per-exercise solutions. Explains the cross-
> exercise design rationale.

## What the module is really teaching

Feature stores are infrastructure for **avoiding the train-serve
skew bug**. The bug: training features are computed by one job in
one language with one schema; serving features are computed by a
different job in a different language with a slightly different
schema; the model is silently 10% worse in production than in
training, and nobody notices for three months.

Every exercise in this module is shaped around the four
disciplines that prevent that:

1. **Point-in-time correctness** (the training-set bug).
2. **Online/offline consistency** (the serving-skew bug).
3. **Materialization with backfill** (the data-freshness bug).
4. **Streaming + batch unification** (the lambda-architecture
   bug).

## Exercise-by-exercise rationale

### Ex-01 — Feast quickstart

The reference solution stands up Feast against:

- **Postgres** as the offline store (cheap, sufficient).
- **Redis** as the online store (low-latency point-lookup).
- **A local file** as the registry (real platforms move this to
  S3 + versioning).

Why Feast specifically? It's the only widely-adopted open-source
feature store as of writing. Tecton is the commercial standard
but adoption requires budget; Feast is the right learning
starting point.

### Ex-02 — Point-in-time correctness

This is the **most consequential** exercise in the module. The
reference solution demonstrates:

- A naive `JOIN` between labels (at time T) and features (latest
  available) leaks future information into training data.
- The correct `JOIN` is "feature value as of T, not after."
- Feast's `get_historical_features()` builds the correct join;
  hand-rolled SQL almost always gets it wrong.

The bug is invisible: training looks perfectly accurate, model
deployed, model crushes in evaluation, model is mediocre in
production. The fix is a one-line API change once you know the
bug; the bug is invisible if you don't.

### Ex-03 — Materialization with backfill

Materialization is the offline-to-online sync. The reference:

- Daily incremental materialization for the previous day's
  features.
- Backfill: a parameterized re-materialization job that can
  recompute any historical window.
- Idempotency at the writer (re-running over the same window
  produces the same online state).

Backfill is when a new feature is added — the entire historical
window must be computed and pushed online. Backfill jobs that
aren't idempotent are non-rerunnable, which makes them
non-debuggable.

### Ex-04 — Streaming feature

A streaming feature (e.g., "transactions in the last 5 minutes
for this user") can't come from a batch materialization. The
reference solution:

- Kafka topic of transactions.
- A Faust / Flink stateful aggregator computing the rolling
  window.
- The aggregator writes to Redis directly (online store).
- An offline-store-equivalent computation runs nightly to keep
  the offline + online stores in sync (so training data exists).

The unstated lesson: streaming features ship the train-serve skew
bug back to the front of the queue. The aggregator + nightly
reconciliation is the discipline that prevents it.

### Ex-05 — Feature store operations

The capstone. Operational concerns:

- **Schema evolution**: how to add a feature without breaking
  consumers.
- **Lineage**: which feature came from which job?
- **SLA**: feature freshness budget and how to alert when it's
  breached.
- **Governance**: who can register new features, who can deprecate
  them, who reviews.

Feature stores are governance-heavy. The reference doc covers
each operational concern + an opinion.

## Cross-exercise design decisions

- **Feast** as the reference implementation.
- **Point-in-time correctness** is non-negotiable; every example
  in the module enforces it.
- **Online + offline stores are separate**; consistency between
  them is a *job*.
- **Streaming features need offline backstops**.

## Common mistakes graders see

1. **Hand-rolled time-travel JOINs** that leak future data.
2. **Same store for online + offline**. Postgres can't serve
   single-digit ms point lookups; Redis can't store a 2-year
   training window.
3. **Materialization without idempotency**. First failure means
   manual cleanup.
4. **Streaming feature with no nightly reconciliation**. Training
   data drifts from online state silently.
5. **No schema-evolution policy**. Adding a feature breaks last
   month's training data.

## Related curriculum touchpoints

- `engineer/mod-105/ex-03-streaming-pipeline-kafka` — the
  streaming-feature substrate.
- `engineer/mod-106/ex-04-experiment-tracking-mlflow` — feature
  sets are an MLflow input artifact.
- `mlops/project-1-ml-pipeline` — the same train-serve-skew
  discipline at the MLOps tier.
- `architect/mod-304-data-platform` — feature stores at enterprise
  scale.
