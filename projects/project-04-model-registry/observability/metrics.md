# Metrics catalog -- reference solution for F8

The registry exposes the four metrics named in `requirements.md` F8
on its `/metrics` endpoint (Prometheus text format). Each is listed
below with its type, labels, and -- most importantly -- the labels
it must NOT carry. Cardinality discipline is non-negotiable: a
metric with a per-version label set will blow up Prometheus inside a
quarter at any non-trivial model population.

## `registry_models_total`

- **Type**: Gauge.
- **Labels**: `tenant`, `status`.
- **Forbidden labels**: model name (high-cardinality), version,
  artifact digest.
- **Semantics**: count of `model_versions` rows partitioned by
  status, per tenant. Updated by a periodic refresh task or via the
  `models_total_dirty` channel after every promotion.
- **PromQL example**: `sum by (tenant) (registry_models_total{status="Production"})`.

## `registry_promotions_total`

- **Type**: Counter.
- **Labels**: `tenant`, `from_status`, `to_status`, `outcome`.
- `outcome` ∈ {`completed`, `blocked`, `rejected`}.
- **Forbidden labels**: model name, version, approver identity.
- **Semantics**: every call to `POST /promotions` increments this
  once; blocked/rejected outcomes increment along with completed.
- **PromQL example**:
  ```
  sum by (outcome) (
    rate(registry_promotions_total{to_status="Production"}[5m])
  )
  ```

## `registry_deployments_active`

- **Type**: Gauge.
- **Labels**: `tenant`, `target_environment`, `rollout_strategy`.
- **Forbidden labels**: deployment ID, model name, version.
- **Semantics**: count of `deployments` rows with `status = 'Active'`.
  The deployment timeline (Grafana) joins this with the audit-chain
  feed to render per-model "what's where, when did it get there".
- **PromQL example**:
  ```
  sum by (target_environment) (registry_deployments_active)
  ```

## `registry_rollouts_in_flight`

- **Type**: Gauge.
- **Labels**: `tenant`, `rollout_strategy`.
- **Semantics**: count of deployments where the rollout has started
  but the bake/ramp has not completed. For `canary`, that's any row
  with `traffic_share > 0 AND traffic_share < 1`. For `blue-green`,
  it's the temporary period both fleets are `Active`. For
  `shadow`, the row is always counted while it's `Active` (shadow
  rollouts are perpetually "in flight" from a registry POV).
- **PromQL example**:
  ```
  sum by (rollout_strategy) (registry_rollouts_in_flight)
  ```

## Label conventions

- `tenant` is the namespace string -- match it 1:1 with the
  audit-chain `tenant_id` field. Stable, low-cardinality.
- `status` and `to_status` use the canonical state-machine names
  (`Registered`, `Staging`, ...). Do not introduce ad-hoc labels
  like `prod` -- the rubric checks the canonical spelling.
- All metrics carry the standard `service` label so a multi-service
  Grafana board can filter to the registry.

## NOT a metric -- a structured log instead

The registry emits a JSON log line for every promotion request and
deployment write. Log-line fields include the request ID, version
ID, signing identity, and rollback reason. Logs are *not* labels --
high-cardinality dimensions live in logs, not in Prometheus.

## SLOs

The track does not pin specific numeric SLOs for the registry; the
learner picks reasonable ones (e.g. registry read p99 < 100 ms,
promotion request p99 < 1 s, rollback API p99 < 5 s). The Grafana
dashboard ships an empty "SLO" row -- the learner is graded on
their reasoning when filling it in, not on the specific numbers.
