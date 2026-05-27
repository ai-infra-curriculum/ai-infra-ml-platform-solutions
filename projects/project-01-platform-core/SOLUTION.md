# SOLUTION — Project 01: Self-Service ML Platform Core

Reference solution for [project-01-platform-core](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/README.md)
(capstone; primary modules mod-001, mod-002, mod-003, mod-007).

> This is the canonical grader-facing answer. It explains *what a
> passing submission must demonstrate*, the design rationale behind the
> reference choices, and how each deliverable maps to the project's
> acceptance criteria. Curated, statically-valid reference artifacts
> ship alongside it (see [§2](#2-worked-implementation)); they are the
> hardest-to-get-right pieces a grader checks, not an 80-hour codebase.

## 1. Solution overview

The project is graded on one distinction: did the submitter build **a
platform**, or **a Kubernetes cluster with extra steps**? A passing
solution makes the difference concrete with four things the brief calls
for ([README §1](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/README.md)):

1. **A higher-order primitive** — the `TrainingRun` CRD. The user
   declares *intent* ("run this image on this dataset with these
   resources"), never a Pod spec.
2. **A contract** — a versioned control-plane API plus a Python SDK and
   CLI. The user programs against the contract, not against `kubectl`.
3. **A control plane that validates and an operator that enforces** —
   admission-time checks (schema, quota, tenant) are separate from
   continuous reconciliation.
4. **Tenant isolation as a property of the platform** — namespace +
   quota + default-deny network policy + workload identity, provisioned
   once per tenant rather than re-solved by every team.

The architecture (from the brief's [architecture.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/architecture.md))
is a dual-store control loop:

```
SDK / CLI ── HTTPS ──▶ Control plane (FastAPI + Postgres)
                          │ validates intent, checks quota, persists,
                          │ emits audit event, applies the CR
                          ▼
                     Kubernetes API ──watch──▶ TrainingRun operator
                                                  │ reconciles → Job,
                                                  │ ConfigMap, SA in the
                                                  ▼ tenant namespace
                                          per-tenant workload resources
```

**The central design decision: the CR is the operational source of
truth; the DB mirrors it for query and audit.** The operator reconciles
against the CR (so it inherits Kubernetes-native finalizers, garbage
collection, and RBAC), while the Postgres mirror answers fast
cross-tenant list/filter queries and preserves history after the CR is
deleted. The accepted cost is keeping the two stores consistent; the
alternative (DB-only) loses Kubernetes semantics, and CR-only loses
fast query. This trade-off is the thing to defend in a review.

## 2. Worked implementation

The reference artifacts in this directory are each statically valid and
map one-to-one to a graded requirement. Validation commands are in
[§3](#3-validation-steps) and in each file's header comment.

| Artifact | Requirement | What it demonstrates |
|---|---|---|
| [`crd/trainingrun-crd.yaml`](./crd/trainingrun-crd.yaml) | F1 | `v1alpha1` CRD, structural OpenAPI v3 schema, ≥5 validated fields, status subresource, printer columns |
| [`operator/reconcile.py`](./operator/reconcile.py) | F3 | kopf reconcile decision tree, finalizer cleanup, retry-with-backoff, idempotent self-heal, leader election |
| [`control-plane/training_runs.py`](./control-plane/training_runs.py) | F2, F5 | FastAPI CRUD + filters, `{error,code,request_id}` contract, `X-Request-Id` propagation, quota admission (HTTP 429) |
| [`tenant/tenant-namespace.yaml`](./tenant/tenant-namespace.yaml) | F4 | namespace + ResourceQuota + LimitRange + default-deny NetworkPolicy + workload-identity binding |
| [`audit/schema.sql`](./audit/schema.sql) | F8 | hash-chained, **DB-enforced** insert-only `audit_log` |
| [`audit/verify.py`](./audit/verify.py) | F8 | chain walker returning first tampering or `verified` |

### 2.1 The CRD is the contract — get it right first

`crd/trainingrun-crd.yaml` ships at `v1alpha1` with a **structural**
schema, which is what makes a later `v1` possible. Five spec fields are
validated at admission, satisfying F1:

- **`image`** — pattern requires a tag or `@sha256:` digest, rejecting
  bare references so a run is reproducible (digest preferred).
- **`resources.requests`** — required; forces explicit sizing.
- **`dataset.name`** — required, non-empty.
- **`hyperparameters`** — typed map (stringified scalars keep the schema
  structural; see "common mistakes").
- **`retries`** — `max` bounded `0..10`, `backoff` an enum.

The conversion strategy is deliberately `None`: a single served+stored
version needs no webhook, and shipping a conversion webhook with no
running service behind it fails admission. The migration story (the
piece F1 asks you to *plan*, not run) is: add `v1beta1` as
`served: true, storage: false`, stand up a conversion webhook, flip
storage, then migrate stored objects with `kubectl get … -o yaml |
kubectl apply`. The structural schema is the precondition that keeps
that path open.

### 2.2 Control plane validates, operator enforces

This separation is the most-tested architectural idea in the project.

- **Admission (control plane, [`training_runs.py`](./control-plane/training_runs.py)).**
  `POST /v1/training-runs` validates the body with Pydantic, looks up
  the tenant, checks quota, persists the intent, applies the CR, and
  emits an audit event — *in that order*, so a quota rejection never
  leaves a persisted-but-unapplied run. Quota failures return **HTTP
  429** with `{error, code: "quota_exceeded", request_id}`. A single
  exception handler guarantees no endpoint ever leaks a stack trace
  (F2).
- **Enforcement (operator, [`reconcile.py`](./operator/reconcile.py)).**
  The reconcile loop is a decision tree keyed on `status.phase`:
  unset → admit and create children; running-but-Job-missing → recreate
  (idempotent self-heal); Job present → mirror its phase into status;
  Job failed with retries left → delete, recreate, and re-queue with
  backoff via `kopf.TemporaryError`. Terminal phases short-circuit.
  Because every path is a create-or-update by name, restarting the
  operator re-derives the same state — that is the F3 "converge within
  30s on restart" guarantee, and the reason finalizers (not ad-hoc
  delete handlers) own cleanup.

### 2.3 Multi-tenancy is layered, because namespace is not a boundary

`tenant/tenant-namespace.yaml` provisions, per tenant: a namespace
(with the Pod Security `restricted` profile), a `ResourceQuota`
(GPU/CPU/memory caps), a `LimitRange` with **no defaults** (every pod
must declare requests+limits, surfacing the missing-request bug before
scheduling), a **default-deny** `NetworkPolicy` plus a narrow allow to
DNS and the platform's own dependencies, and a `ServiceAccount` bound to
a tenant-scoped workload identity (IRSA / GKE Workload Identity /
SPIFFE SVID). The data boundary is enforced by the *IAM or SPIFFE*
policy, not by Kubernetes — the SA annotation only names the identity to
assume. This is why the acceptance demo's cross-tenant read fails at the
IAM layer, and the cross-tenant service call fails at the NetworkPolicy
layer: two independent controls, not one.

### 2.4 The audit chain is the compliance backbone

`audit/schema.sql` makes the `audit_log` **insert-only at the database
level** via `BEFORE UPDATE OR DELETE` and `BEFORE TRUNCATE` triggers
that raise an exception. Application-level immutability does not answer
the auditor's real question ("can a privileged DB user rewrite
history?"); a DB-enforced constraint does. Each row stores
`payload_hash = sha256(canonical(payload))`, `prev_hash`, and
`entry_hash = sha256(payload_hash || prev_hash)`, so the log is a hash
chain. `audit/verify.py` walks it in `id` order, recomputes all three
relations, and returns the first inconsistency or `verified` — the
command an auditor runs after the acceptance test. Audit writes are
async so a failed write never blocks the user (architecture.md NF
target).

### 2.5 SDK / CLI surface (F6)

The user-facing surface is the SDK shown in the brief's
[README §3](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/README.md):
`client.create_training_run(...)` returns a handle with `.wait()`,
`.status`, `.metrics_uri`, `.artifact_uri`. The SDK is a thin wrapper
over the control-plane HTTP contract; the CLI
(`smartrecs runs create|list|status|cancel`, Click or Typer) wraps the
same SDK so behaviour cannot drift between them. Both authenticate with
a bearer token (static or OIDC is acceptable for the capstone).

## 3. Validation steps

These reproduce the acceptance demo from
[requirements.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/requirements.md).
A full reproduction runbook is in [`STEP_BY_STEP.md`](./STEP_BY_STEP.md).

**Static validation of the shipped artifacts:**

```bash
# CRD + tenant manifests are valid and accepted by the API server
kubectl apply --dry-run=server -f crd/trainingrun-crd.yaml
kubectl apply --dry-run=server -f tenant/tenant-namespace.yaml

# Python artifacts byte-compile
python -m py_compile operator/reconcile.py \
    control-plane/training_runs.py audit/verify.py

# Audit schema applies and the insert-only constraint actually rejects writes
psql "$PLATFORM_DB_URL" -f audit/schema.sql
psql "$PLATFORM_DB_URL" -c "UPDATE audit_log SET action='x' WHERE id=1;"  # must ERROR
```

**Behavioural acceptance (the grading demo):**

1. Fresh `kind`/`k3d` cluster; `make up` brings the platform up
   (NF1: single command, all manifests in `deploy/`).
2. Create tenants `team-a`, `team-b` via the CLI → each gets a
   namespace, quota, network policy, SA.
3. Submit one run per tenant → both reach `Running`.
4. Submit a `team-a` run that exceeds its GPU-hour quota → **rejected at
   admission, HTTP 429**, `code: quota_exceeded` (F5).
5. From a `team-a` pod, read `team-b`'s bucket prefix → **denied at
   IAM**; call a `team-b` service → **denied by NetworkPolicy** (F4).
6. `python audit/verify.py` against the platform DB → **`verified`**
   (F8).
7. Restart the operator → in-flight runs continue; state converges in
   <30s (F3).

## 4. Rubric / review checklist

Score each requirement Pass / Partial / Fail. A passing capstone clears
every **F** and **NF** line; "Partial" anywhere blocks promotion to
`v1`-grade.

| # | Requirement | Pass criterion |
|---|---|---|
| F1 | TrainingRun CRD | Installs; structural schema rejects ≥5 invalid spec shapes; status subresource present; `v1` conversion plan documented |
| F2 | Control-plane API | All four verbs; filters (`tenant`,`phase`,`created_*`); `{error,code,request_id}` on every error; `X-Request-Id` in logs + audit |
| F3 | Operator reconciliation | Creates/cleans children via finalizers; status tracks Job phase; retries with backoff; restart converges <30s; idempotent |
| F4 | Multi-tenancy | Per-tenant namespace+quota+LimitRange+default-deny NetworkPolicy; workload identity proven by a denied cross-tenant read |
| F5 | Quota enforcement | GPU-hour and concurrent-run caps enforced at admission; `GET /tenants/{id}/quota-usage` works |
| F6 | SDK + CLI | SDK matches README §3; CLI wraps the SDK; token auth; runnable `examples/` |
| F7 | Observability | The five named Prometheus metrics exposed on both components; structured JSON logs; one Grafana dashboard JSON shipped |
| F8 | Audit chain | DB-enforced insert-only; hash-chained rows; `verify` returns first tampering or `verified` |
| NF1 | Reproducibility | `make up`; all infra as manifests; `.env.example` |
| NF2 | Testing | Control-plane unit tests ≥80%; operator tests (envtest/kopf harness); one e2e test |
| NF3 | Security | Non-root images; no long-lived static creds; ESO for secrets; Cosign-signed images |
| NF4 | Documentation | Root README; ARCHITECTURE.md; generated OpenAPI; tenant onboarding guide; ops runbook |

**Reviewer's quick disqualifiers:** users writing Pod specs (no
primitive); admission and enforcement collapsed into one component;
namespace treated as the security boundary; audit immutability enforced
only in app code; CRD shipped with no `v1` path.

## 5. Common mistakes

From the brief's pitfalls list plus what graders see most often:

1. **Reaching for distributed training.** Single-pod Jobs only; this is
   a platform project, not a training project. Multi-pod is project-03.
2. **Skipping finalizers.** Deleting children in an ad-hoc delete
   handler leaks resources on operator crash. Finalizers gate CR
   removal on successful cleanup.
3. **Treating the CRD as immutable.** No `served`/`storage` versioning
   and no structural schema means there is no path to `v1`; the
   conversion plan is a graded deliverable, not optional.
4. **Audit immutability in application code only.** If a privileged DB
   user can `UPDATE`/`DELETE`/`TRUNCATE` the audit table, the chain is
   theatre. Enforce it with triggers (and treat dropping the trigger as
   itself an auditable DDL event).
5. **Hardcoding the tenant list.** Tenants are first-class API
   resources created at onboarding, not config baked into manifests.
6. **Treating namespace as a security boundary.** It is a naming + RBAC
   + quota boundary. Isolation comes from NetworkPolicy *and* workload
   identity, layered.
7. **Combining `properties` and `additionalProperties` at the same
   level** in the CRD schema — Kubernetes structural-schema validation
   rejects it. The reference uses a typed `additionalProperties` map for
   `hyperparameters` and `resources.requests`, with no sibling
   `properties`.
8. **Quota checked after the CR is applied.** Validate at admission,
   before persisting or applying, so a rejected run leaves no residue.
9. **Synchronous audit writes** on the request path. A slow or failed
   audit write must never block or fail the user's action; write async.

## 6. References

**Authoritative exercise context (the project brief):**

- [Project README](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/README.md) ·
  [architecture.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/architecture.md) ·
  [requirements.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/requirements.md) ·
  [STEP_BY_STEP.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/STEP_BY_STEP.md)
  — the non-functional targets (p95 latencies, 30s convergence) are
  drawn from `architecture.md`, not invented here.

**Official standards & documentation:**

- Kubernetes — [Custom Resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/),
  [CustomResourceDefinitions](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/),
  [Finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/),
  [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/),
  [Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/),
  [Limit Ranges](https://kubernetes.io/docs/concepts/policy/limit-range/),
  [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/).
- [kopf — Kubernetes Operator Pythonic Framework](https://kopf.readthedocs.io/).
- [FastAPI](https://fastapi.tiangolo.com/) ·
  [Prometheus Python client](https://prometheus.github.io/client_python/).
- [PostgreSQL — Trigger functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html).
- [SPIFFE / SPIRE](https://spiffe.io/docs/latest/spiffe-about/overview/) ·
  [Sigstore Cosign](https://docs.sigstore.dev/cosign/signing/overview/) ·
  [SLSA](https://slsa.dev/spec/v1.0/) ·
  [External Secrets Operator](https://external-secrets.io/latest/).

**Track cross-references:**

- [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md) — track-wide design philosophy.
- [`mod-001`](../../modules/mod-001-platform-fundamentals/SOLUTION.md) (abstraction design),
  [`mod-002`](../../modules/mod-002-api-design/SOLUTION.md) (API versioning/deprecation),
  [`mod-003`](../../modules/mod-003-multi-tenancy-resources/SOLUTION.md) (tenancy + quotas).
- [`senior-engineer-solutions/projects/project-204-k8s-operator`](https://github.com/ai-infra-curriculum/ai-infra-senior-engineer-solutions/tree/main/projects/project-204-k8s-operator)
  — production-grade operator reference.
