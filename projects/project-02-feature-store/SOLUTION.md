# SOLUTION — Project 02: Enterprise Feature Store

> Read this *after* the learning project's
> [`architecture.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/architecture.md),
> [`requirements.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/requirements.md),
> and [`STEP_BY_STEP.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/STEP_BY_STEP.md).
> This file explains the cross-component design rationale: why
> the platform is partitioned the way it is, what discipline the
> capstone collectively teaches, and the trade-offs the reference
> solution accepts.

## Overview

A feature store's deliverable is not "Redis plus a YAML schema."
It is **a contract that training jobs and serving jobs both
program against**, with a control loop that keeps the offline
table and the online cache derivable from the same definition.
The capstone forces the engineer to internalize four things at
once:

- **One definition path** from YAML → offline table → online
  cache. Skew is structurally impossible because there is exactly
  one place a feature is defined and exactly one job that
  materialises it.
- **Point-in-time correctness** at the training boundary. The
  offline store answers "what was this feature at time T," not
  "what is it now," and a deliberate-skew fixture proves it.
- **Multi-tenancy that survives a hostile reader**. A namespace
  label is not the boundary; the IAM policy on the serving
  identity is. Cross-tenant reads fail at the registry and at
  the storage layer, with an audit-log entry on every denial.
- **Freshness as a measured SLO**, not a feeling. Per-feature
  Prometheus metrics plus drift detection turn "is this feature
  healthy" into a binary question.

The project's grade is whether all four hold up *together* under
the acceptance demo in
[`requirements.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/requirements.md).
Any one in isolation is a sub-skill that
[mod-004 exercises](../../modules/mod-004-feature-store/) already
teach.

## Implementation

### `registry/` — admission, lineage, and identity

The registry is the contract layer. It validates, persists, and
hands out feature definitions; it does **not** materialise or
serve. Three deliberate shapes:

- **YAML is canonical, Postgres is the index**. The YAML
  [`Feature`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/architecture.md)
  spec is what users edit and Git versions. Registration parses
  the YAML and writes `(namespace, name, version, spec_json)`
  into the `features` table so the registry can answer
  cross-namespace queries that scanning a Git repo can't.
- **Namespace in the path, tenant on the principal**. Routes are
  `/v1/features/{namespace}/{name}`; the requesting principal's
  tenant claim must include the namespace, otherwise the request
  fails at FastAPI dependency-resolution time. This mirrors the
  tenant-header pattern from
  [`mod-001`](../../modules/mod-001-platform-fundamentals/) but
  keeps the namespace public in the URL for discovery.
- **Version is part of the primary key**. The unique key is
  `(namespace, name, version)`, never `(namespace, name)`. A new
  version is a new row; old versions remain queryable so historic
  training runs can still be reproduced.

`POST /v1/features` is idempotent on `(namespace, name, version,
spec_hash)`: re-posting the same spec returns 200 with the
existing record, re-posting a *different* spec at the same version
returns 409. The registry refuses to mutate a published spec —
mutation is by new version, and the materialization pipeline
treats each version as a separate feature until backfill completes.

### `materializer/` — the offline → online conveyor

The materializer is intentionally **boring**. It is a per-feature
scheduled job that does one thing: makes the offline table and the
online cache match the spec's source query as of the run window.

- **Single entrypoint** for incremental and backfill runs.
  Backfill is incremental with a wider window — there is no
  separate "backfill mode" code path. This is the same discipline
  as the operator in
  [project-01](../project-01-platform-core/SOLUTION.md): one
  reconcile entrypoint or restart-recovery diverges.
- **Append-only to offline**. Each materialization writes
  `(entity_id, value, event_time)` rows; rows are never updated
  or deleted. The offline table is an audit log of what the
  feature was, not what it is now.
- **Online write is idempotent**. `SET feature:{namespace}:{name}
  :{entity_id}` with the latest offline value plus the
  materialization run id. Re-running over the same window
  produces the same final Redis state, which is what makes
  failure recovery a re-run, not a manual cleanup.
- **One CronJob per feature**, scheduled from the spec's
  `materialization.schedule`. Production-grade scheduling
  (Airflow, Prefect, Dagster) is out of scope per
  [`STEP_BY_STEP.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/STEP_BY_STEP.md);
  Kubernetes
  [CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
  is sufficient for the capstone.

Trade-off explicitly accepted: a long backfill is a single
long-running Job. Streaming the backfill in chunks is a
production refinement; the capstone is graded on correctness, not
throughput.

### `sdk/` — `get_historical_features` and `get_online_features`

The SDK is the only surface training and serving code touches.
Both methods are backed by the same feature definitions, which is
the structural guarantee against train-serve skew described in
[mod-004 SOLUTION.md](../../modules/mod-004-feature-store/SOLUTION.md).

- **`get_historical_features(entity_df, features,
  timestamp_column)`** issues one as-of join per feature against
  the offline table and returns a joined `DataFrame`. The
  reference uses a SQL `LATERAL JOIN` with
  `event_time <= row.timestamp ORDER BY event_time DESC LIMIT 1`,
  which Postgres plans efficiently with the
  `(entity_id, event_time DESC)` index already defined in the
  architecture's data model.
- **`get_online_features(features, entity_id)`** issues a single
  Redis `MGET` across the feature keys for the entity, returning
  both values and the per-feature `materialized_at` so callers
  can decide whether a stale value is still trustworthy.
- **The SDK never writes**. Writes flow through the registry
  (definitions) and the materializer (values). An SDK that can
  also write the online cache is the most common path to
  train-serve skew: a feature exists in serving that has no
  corresponding offline history.

### `deploy/` — local cluster, multi-tenancy, and signing

The capstone runs on `kind` or `k3d` via `make up`. The
deployment manifests carry three non-negotiables:

- **Default-deny `NetworkPolicy` in every tenant namespace**,
  applied during onboarding before any workload exists. This is
  the same posture as
  [project-01](../project-01-platform-core/SOLUTION.md) and the
  same Kubernetes
  [NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
  contract.
- **Workload identity, not bearer tokens**. The materializer
  signs into Postgres and Redis with its own identity; the
  registry signs into Postgres with its own. No long-lived
  static credentials, per
  [`requirements.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/requirements.md) F-NF.
- **All images non-root and
  [Cosign](https://docs.sigstore.dev/cosign/overview/)-signed**.
  The capstone's autograder verifies signatures; an unsigned
  image is a graded failure, not a warning.

## Design decisions the project shares

- **One source of truth: the YAML definition**. Offline is
  derivable from the source query; online is derivable from
  offline. There is no fourth surface where a feature value can
  enter.
- **Offline is authoritative, online is a cache**. If Redis is
  corrupted, re-materialise. The online store never receives
  writes from inference, which is the discipline that prevents
  silent skew (see the streaming-feature analysis in
  [mod-004 SOLUTION.md](../../modules/mod-004-feature-store/SOLUTION.md)).
- **`event_time` is `TIMESTAMPTZ`, always**. Off-by-time-zone
  bugs are the worst-class feature-store bugs because they
  corrupt training data silently. The architecture's data model
  spells this out; the reference enforces it at table creation.
- **Multi-tenancy via namespace + IAM, not via row filters**.
  Per-tenant tables (or per-tenant Redis key prefixes) plus an
  IAM policy on the serving identity is the boundary. A `WHERE
  tenant = ?` row filter is one missed clause from a cross-tenant
  read.
- **Drift detection is a flag in the registry, not a separate
  database**. The weekly drift job writes a `drift_status` field
  on the feature record; consumers read the registry to decide
  whether to trust a feature. One place to look.

## Rubric

Graders evaluate the capstone against the four-axis contract from
the Overview: one definition path, point-in-time correctness,
multi-tenant isolation, and freshness-as-SLO. Below are the
failure modes that disqualify a submission — each is something
the acceptance demo surfaces deterministically.

### Common mistakes graders see

1. **Naive feature joins**. A `JOIN ... ON entity_id` against
   the latest materialized value leaks future information into
   training data. The deliberate-skew fixture (F2 in
   [`requirements.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/requirements.md))
   exposes this on the first run; a passing implementation must
   return the earlier value, not the later one.
2. **Same store for online + offline**. Postgres cannot serve
   single-digit-ms point lookups at scale; Redis cannot store a
   multi-year training window. Conflating them is the same
   mistake as the one called out in
   [mod-004 SOLUTION.md](../../modules/mod-004-feature-store/SOLUTION.md)
   and the F3 latency target (p99 < 50 ms) will fail.
3. **Mutable offline table**. Updating `(entity_id)` rows in
   place destroys the historical record point-in-time correctness
   relies on. Append-only is non-negotiable.
4. **Materializer that isn't idempotent**. First failure means
   manual cleanup; rerunning the same window produces a different
   final state than running it once. Non-rerunnable jobs are
   non-debuggable.
5. **Tenant boundary as a row filter**. A serving identity that
   *could* read another tenant's row but happens not to is not
   isolation. The cross-tenant probe in the acceptance demo
   tests at the IAM layer.
6. **No backfill path for new features**. Adding a feature
   without backfilling history leaves training-data columns
   `NULL` for the entire window before the feature shipped. The
   `backfill_from` field in the spec exists precisely to avoid
   this; ignoring it is a graded failure.
7. **Online cache as source of truth**. Writes flowing to Redis
   outside of materialization create features that have no
   offline history and therefore no training-data representation.
   This is the silent-skew bug the project is designed to
   eliminate.
8. **Drift detection without a flag**. A drift job that logs to
   stdout but doesn't update the registry record cannot be used
   by downstream consumers. The flag is the contract; the log is
   decoration.

## Validation

The reference solution is graded by the acceptance demo from
[`requirements.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-02-feature-store/requirements.md),
not by unit tests in isolation. The demo is the integration
contract; passing it is what "done" means.

- **Register two features for two tenants**. `POST /v1/features`
  succeeds for both; `GET /v1/features?namespace=...` returns
  only the features owned by the caller's namespace.
- **Materialise once**. Trigger the materializer for each
  feature; assert the offline table has rows for the run window
  and the online cache returns the latest value via
  `get_online_features`.
- **Point-in-time correctness across a materialisation
  boundary**. Submit a `get_historical_features` query whose
  timestamps straddle a materialisation; the returned values must
  be the as-of values, not the latest values. The
  deliberate-skew fixture (a feature whose value is 5 at T1 and
  10 at T2; query at T2 - ε must return 5) is the canonical test.
- **Serving-side `get_online_features`** returns the current
  values plus per-feature `materialized_at`. The p99 latency
  probe runs against this endpoint and must come in under 50 ms
  for a single-entity lookup.
- **Cross-tenant denial**. From tenant A's serving identity,
  attempt to read a feature in tenant B's namespace. The
  registry must respond with 403, the audit log must record the
  attempt, and no value must be returned.
- **Drift detection**. Inject a synthetic distribution shift
  (e.g., shift the materialised values by 3 standard deviations);
  the next drift run must update `drift_status` on the feature
  record and the alerting rule (Prometheus + Alertmanager) must
  fire.
- **Backfill of a new feature**. Register a new feature with
  `materialization.backfill_from: "<historic date>"`; trigger the
  backfill; verify a `get_historical_features` query for entities
  whose label timestamps fall in the historic window returns
  point-in-time-correct values, not `NULL`.

If any of the seven probes fails, the capstone is incomplete —
not "mostly working." The feature-store contract is binary at
this layer.

## Where this project lands in the track

- It is the **integration test** for
  [mod-004](../../modules/mod-004-feature-store/) and a real-world
  exercise of
  [mod-002](../../modules/mod-002-api-design/) and
  [mod-003](../../modules/mod-003-multi-tenancy-resources/). If the
  per-module exercises taught the right vocabulary, this project
  assembles it.
- It is a **substrate** for
  [project-01](../project-01-platform-core/SOLUTION.md)'s
  `TrainingRun`. A training run names features; the feature store
  is what makes that naming meaningful end-to-end.
- It is the **lower bound** of "real" feature-store engineering.
  Production systems add streaming features, federated namespaces
  across organisations, and full lineage to source events — none
  of which change the shape laid out here, only its amplitude.

## References

### Curriculum touchpoints

- [`ml-platform/mod-004`](../../modules/mod-004-feature-store/)
  — the conceptual treatment of feature stores, point-in-time
  correctness, materialisation, and streaming features.
- [`ml-platform/mod-002`](../../modules/mod-002-api-design/) —
  the versioning and error-shape contract the registry ships.
- [`ml-platform/mod-003`](../../modules/mod-003-multi-tenancy-resources/)
  — the multi-tenancy + IAM patterns the registry and
  materializer enforce.
- [`ml-platform/mod-008`](../../modules/mod-008-observability/)
  — the Prometheus metric surface and Grafana dashboard the
  feature store emits.
- [`ml-platform/mod-009`](../../modules/mod-009-security-governance/)
  — workload identity, image signing, and audit-log patterns.
- [`ml-platform/project-01`](../project-01-platform-core/SOLUTION.md)
  — the control-plane and multi-tenancy shape this project
  inherits.
- [`engineer-solutions/mod-106 exercise-07`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops/exercise-07-feature-store-implementation)
  — feature-engineering basics and a worked `get_historical_features`
  reference.
- [`engineer-solutions/mod-105 exercise-11`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-105-data-pipelines/exercise-11-lambda-architecture)
  — the Lambda-architecture pattern for the streaming-feature
  extension out of scope here.

### Upstream specifications and tooling

- [Feast documentation](https://docs.feast.dev/) — production
  reference for the registry / online / offline split this
  project mirrors. Per
  [mod-004 SOLUTION.md](../../modules/mod-004-feature-store/SOLUTION.md),
  Feast is the open-source standard the capstone implementation
  is conceptually patterned after.
- [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
  — the scheduler for per-feature materialisation jobs.
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
  — the default-deny posture each tenant namespace ships with.
- [PostgreSQL `LATERAL` joins](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL)
  — the SQL primitive `get_historical_features` builds on for
  the as-of join.
- [PostgreSQL `TIMESTAMPTZ`](https://www.postgresql.org/docs/current/datatype-datetime.html)
  — the time-zone-aware type the offline table's `event_time`
  column uses.
- [Redis `MGET`](https://redis.io/commands/mget/) — the batched
  online lookup the serving path issues.
- [Prometheus metric types](https://prometheus.io/docs/concepts/metric_types/)
  — the histogram, counter, and gauge surface for per-feature
  freshness, retrieval latency, and retrieval volume.
- [Sigstore / Cosign](https://docs.sigstore.dev/cosign/overview/)
  — the image-signing toolchain the deployment manifests
  require.
- [SPIFFE / SPIRE](https://spiffe.io/docs/latest/spiffe-about/overview/)
  — the workload-identity primitive that replaces long-lived
  static credentials.
- [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0) — the
  auto-generated spec the registry's FastAPI app publishes.
