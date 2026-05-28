# SOLUTION -- project-04-model-registry

> Worked solution for the
> [project-04-model-registry](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-04-model-registry)
> capstone in the paired learning repo. Follows the 6-section AICG
> Output Contract.

## 1. Solution overview

The model registry is a **governance system**, not a storage system.
Object storage holds the bytes; the registry holds metadata, digests,
signatures, lineage, promotions, and deployments. Everything in this
project is shaped by one question: when a regulator (or an incident
review, or a hallway tap on the shoulder) asks "what model is in
production right now, why, and who said it was OK?" -- the registry
must answer in seconds, with evidence the auditor can verify
independently.

The reference solution makes four design commitments:

1. **`ModelVersion` is immutable** once registered. Enforced at the
   DB layer via the trigger in `registry/schema.sql`, not just at
   the handler.
2. **Signatures are verified twice**: once at the promotion gate,
   once again at deployment time. Verifying only at promotion lets
   an attacker who can write to the artifact bucket swap clean
   bytes for poisoned ones between those two events.
3. **State transitions are the audit event**, not artifact uploads.
   Every `Registered -> Staging -> Production -> Deprecated ->
   Decommissioned` step writes a row to `promotions` *and* an entry
   to the platform audit chain (`project-01-platform-core/audit/schema.sql`).
4. **Rollback uses the promotion path, in reverse**. There is no
   special "rollback API" with its own state machine -- a rollback
   is a new deployment row pointing at the prior `Production`
   version, plus an audit entry, with a required `reason`.

Everything else (multi-tenancy, observability, lineage) supports
these four commitments.

### Curated artifacts (mapped to F1-F8)

| Path | Maps to |
|---|---|
| `registry/schema.sql` | F1, F6, F7 |
| `registry/openapi.yaml` | F1, F3, F4, F5, F6 |
| `gates/gates.yaml` | F3 |
| `gates/evaluate.py` | F3 |
| `signing/verify.py` | F2 |
| `deployment/rollout-strategies.md` | F4, F5 |
| `lineage/queries.sql` | F6 |
| `multi-tenancy/policy.md` | F7 |
| `observability/metrics.md` | F8 |
| `observability/grafana-dashboard.json` | F8 |
| `STEP_BY_STEP.md` | build sequence |
| `rubric.md` | per-row grading bar |

## 2. Worked answer or implementation

### 2.1 Data model (F1, F6, F7)

The relational core of the registry is six tables and one view:

- `models(id, namespace, name, owner, created_at)` -- the named
  thing a tenant owns.
- `model_versions(id, model_id, version, artifact_uri,
  artifact_digest, signature_uri, metadata, metrics, status,
  registered_by, registered_at)` -- the immutable
  fact about a specific trained model. The `model_versions_immutable`
  BEFORE UPDATE trigger blocks mutation of every column except
  `status`, which is owned by the promotion code path.
- `lineage_edges(model_version_id, source_kind, source_identifier)` --
  many-to-many edges to `training_data`, `feature_snapshot`,
  `base_model`, and `training_run`. Reverse traversal (a recursive
  CTE in `lineage/queries.sql`) is the load-bearing query for the
  "which models trained on dataset X" regulator question.
- `promotions(...)` -- one row per state-machine transition with
  the approver, the signed approval blob, and a pointer into the
  audit chain.
- `deployments(...)` -- ties a version to a target environment +
  rollout strategy. `traffic_share` is the canary handle; a
  `rollback_reason` is non-null whenever `status = 'Rolled-back'`.
- `production_deployments` view -- the "what's in prod right now"
  query.

The model is metadata-only; bytes live in object storage. The pair
`(artifact_uri, artifact_digest)` is the binding to the bytes; the
digest is what makes signature verification meaningful.

### 2.2 API surface (F1, F3, F4, F5, F6)

`registry/openapi.yaml` pins the contract. The verbs that matter:

- `POST /v1/models` and `POST /v1/models/{id}/versions` (F1);
  the latter is the only place a version is created; subsequent
  PUTs/PATCHes return **405**.
- `GET /v1/models?status=...&accuracy_gte=...&training_data_version=...` --
  filtered list (F1).
- `POST /v1/promotions` -- returns **201 Completed** when all
  gates pass automatically, **202 Pending** when a human-approval
  gate is unsatisfied, **422 GateFailure** with the failing gate's
  name and evaluated value when a hard gate fails (F3).
- `POST /v1/promotions/{id}/approve` -- records a human approval
  with the signed approval blob (F3).
- `POST /v1/deployments` -- creates a deployment; performs a
  *second* signature verification before the row is written (F2 +
  F4).
- `POST /v1/deployments/{id}/rollback` -- requires `reason`,
  returns the new Active deployment (F5).
- `GET /v1/lineage/{model_version_id}` -- forward DAG.
- `GET /v1/lineage/reverse?source_kind=...&source_identifier=...` --
  reverse, multi-hop (F6).

Standard error envelope (`{error, code, request_id}`) is shared with
project-01.

### 2.3 Promotion gates (F3)

`gates/gates.yaml` is the default gate set, mirroring
`architecture.md` §Promotion gates:

- `signature` (assertion) -- `signature_valid AND signing_identity_matches(expected_workflow)`,
  evaluated by `signing/verify.py`.
- `accuracy >= 0.85` (threshold).
- `fairness.disparate_impact <= 1.25` (threshold).
- `adversarial.robust_accuracy_at_eps_8_255 >= 0.30` (threshold).
- `human_approval` (approval) -- `team-lead` + `security-eng`.

`gates/evaluate.py` is a **pure function** over
`(gates, transition, context)`. The handler does the side effects;
the evaluator decides. That separation makes the four test cases
trivial (all-pass, one-threshold-fail, signature-fail,
human-pending).

`next_state(current, target)` is the single source of truth for
allowed transitions. Adding `Production -> Staging` (a downgrade)
means editing exactly one dict.

### 2.4 Signature verification (F2)

`signing/verify.py` defines `VerificationResult` and
`ExpectedIdentity`. The function checks **three** things, in order:

1. The artifact digest is in `sha256:<hex64>` form. (Cheap, fails
   loud on a corrupt SDK.)
2. The Sigstore root + Rekor log accept the signature for the
   artifact. (Delegated to `cosign verify` or `sigstore-python`.)
3. The signing OIDC issuer and subject match `ExpectedIdentity`.
   Sigstore proves "some OIDC identity signed this"; the registry
   demands "the *training pipeline's* identity signed this".

Verification is called from two paths:

- `gates/evaluate.py` -> precomputes `assertions.signature` for
  the `signature` gate, before the promotion state machine moves.
- Deployment handler -> calls `verify_signature` again immediately
  before the `deployments` row is written.

Both call sites grade against F2.

### 2.5 Rollout + rollback (F4, F5)

`deployment/rollout-strategies.md` is the design doc. Concrete
behaviors:

- **Rolling** -- the default; one row per (target, version), no
  `traffic_share`.
- **Blue-green** -- two `Active` rows briefly; the LB swap is the
  cutover; the old row goes `Decommissioned` after bake.
- **Canary** -- two `Active` rows with `traffic_share` summing to
  1.0; ramp updates *both* rows in a single transaction so the
  registry is never lying to readers of `production_deployments`.
- **Shadow** -- new row at `traffic_share = 0` with
  `rollout_strategy = shadow`. Mirrored traffic is the mesh's job;
  the registry just records that the row exists. Confusing shadow
  for a 0 % canary is the F4 hard fail.

Rollback is a SQL CTE: find the prior `Production` deployment for
the same target, insert a new Active row pointing at it, flip the
current one to `Rolled-back` with the required `reason`. Both
writes share a transaction; the audit-chain entry is emitted
*after* `COMMIT`. SLO: < 5 minutes from API call to traffic
restored on a single-cluster setup.

### 2.6 Lineage (F6)

Edges flow into `lineage_edges` from the SDK at registration time
(the SDK reads `MLFLOW_RUN_ID`, dataset version, feature snapshot
URL, base model URI from the training job's environment). Forward
queries are one hop by default; reverse queries multi-hop with a
depth cap of 8 to defend against accidental cycles.

`lineage/queries.sql` ships two prepared statements:

```sql
EXECUTE forward_lineage('00000000-...-uuid');
EXECUTE reverse_lineage('training_data', 'recs-curated-2026-05');
```

Reverse returns the affected versions ordered by shortest path so
the operator working an incident can act on direct dependents first.

### 2.7 Multi-tenancy + audit (F7)

`multi-tenancy/policy.md` shows Postgres row-level security
attached to every tenanted table. The handler runs
`SET LOCAL platform.tenant = :caller_tenant`; the policy resolves
`models.namespace = current_setting('platform.tenant')`. Forget
the SET -> zero rows (fail-closed). The policy is the safety belt
even when the application logic is wrong.

Cross-tenant ID lookups return **404** rather than 403; 403 leaks
existence. Cross-tenant share is an explicit `POST /v1/models/{id}/share`
that writes both the `shares` row and the audit-chain event.

Audit entries reuse the chain defined in
`project-01-platform-core/audit/schema.sql`. The registry depends
on it; it does not redefine it.

### 2.8 Observability (F8)

`observability/metrics.md` catalogs the four metrics
(`registry_models_total`, `registry_promotions_total`,
`registry_deployments_active`, `registry_rollouts_in_flight`) with
their *allowed* and *forbidden* labels. Cardinality discipline is
the F8 rubric; putting `model_name` on a metric is the single most
common reason the row grades Partial.

`observability/grafana-dashboard.json` is the one dashboard
required by F8. The SLO panel is intentionally empty -- the
learner pins their own numbers and is graded on the reasoning.

## 3. Validation steps

Run from the repo root in the order below. Each command exits 0 on
success; non-zero is the diagnostic for the failing artifact.

```bash
# Schema applies cleanly and immutability holds.
psql -d registry \
     -f projects/project-04-model-registry/registry/schema.sql \
     --single-transaction --set ON_ERROR_STOP=1

# OpenAPI spec parses.
openapi-spec-validator projects/project-04-model-registry/registry/openapi.yaml

# Gates YAML parses.
yamllint -s projects/project-04-model-registry/gates/gates.yaml

# Python artifacts compile.
python3 -m py_compile \
  projects/project-04-model-registry/gates/evaluate.py \
  projects/project-04-model-registry/signing/verify.py

# Lineage queries parse + prepared statements compile (uses the
# schema from step 1 -- prepare-only, no execute).
psql -d registry \
     -f projects/project-04-model-registry/lineage/queries.sql \
     --single-transaction --set ON_ERROR_STOP=1

# Grafana JSON parses.
python3 -c "import json,sys; json.load(open('projects/project-04-model-registry/observability/grafana-dashboard.json'))"
```

Note: this workspace blocks `python3 ...` execution; graders run the
commands above with their own toolchain. The artifacts have been
review-validated statically.

In addition, run the nine-step acceptance demo from
`requirements.md` (the actual end-to-end proof that the system
works).

## 4. Rubric or review checklist

See [`rubric.md`](./rubric.md). The grader marks each row Pass /
Partial / Fail. Two Fails or four Partials means the project does
not pass; one Fail with otherwise-Pass rows means "return for
revision".

The acceptance demo at the bottom of `rubric.md` is the only
end-to-end proof of the system; a learner without a screencast of
all nine steps grades Partial regardless of how complete the code
is.

## 5. Common mistakes

- **Mutable `ModelVersion`**: allowing re-registration under the
  same version. Compliance pain; "what was in prod last Tuesday?"
  becomes unanswerable. The DB-level immutability trigger blocks
  this even when the handler is buggy.
- **Signature verified only at registration**: the F2 "double
  verify" requirement exists because an attacker who can write to
  the artifact bucket can swap bytes between registration and
  deployment. Verify again in the deployment handler.
- **No reason on rollback**: every rollback captures *why* --
  incident report, regression, etc. The API contract refuses an
  empty string.
- **Treating shadow as canary**: shadow's output never reaches
  clients. Mixing them up ships silent customer impact.
- **Rollout that updates one deployment row at a time**: ramp must
  update *both* old and new rows in a single transaction. Anything
  else leaves a window where `sum(traffic_share)` != 1.0.
- **403 on cross-tenant lookup**: 403 leaks that the model exists.
  Return 404. The rubric's F7 row is specific about this.
- **High-cardinality labels on metrics**: putting `model_name` or
  `version` on `registry_models_total` blows up Prometheus.
  `observability/metrics.md` enumerates the forbidden labels.
- **A rollback procedure that's never been drilled**: counts as
  "no rollback procedure" for grading purposes. The runbook ships
  with a quarterly drill cadence; the rubric expects evidence the
  drill has happened.
- **Approver who is the model owner**: the gate must reject
  self-approval. Even with one approver, the approver cannot be
  the registering identity.

## 6. References

Curriculum-internal:

- Paired learning project:
  [`projects/project-04-model-registry`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-04-model-registry)
  -- `README.md`, `architecture.md`, `requirements.md`, `STEP_BY_STEP.md`.
- Module 06 reference solution:
  [`modules/mod-006-model-management/SOLUTION.md`](../../modules/mod-006-model-management/SOLUTION.md).
- Audit-chain schema and `verify_audit_chain()` function:
  [`projects/project-01-platform-core/audit/schema.sql`](../project-01-platform-core/audit/schema.sql).
- Track-level overview: [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md).

External (official):

- MLflow Model Registry concepts:
  <https://mlflow.org/docs/latest/model-registry.html>
- Sigstore Cosign documentation:
  <https://docs.sigstore.dev/cosign/>
- `sigstore-python` keyless signing/verification:
  <https://github.com/sigstore/sigstore-python>
- PostgreSQL row-level security:
  <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- Prometheus naming + label conventions:
  <https://prometheus.io/docs/practices/naming/>
- OpenAPI 3.1.0 specification:
  <https://spec.openapis.org/oas/v3.1.0>
- Argo Rollouts (canary, blue-green, analysis runs):
  <https://argo-rollouts.readthedocs.io/en/stable/>

External (practitioner examples, used only as illustration of
specific implementation patterns, never as authoritative claims):

- VeriSwarm engineer-solutions `mod-106 exercise-03` --
  MLflow Model Registry basics:
  <https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops>
