# SOLUTION — Project 01: Self-Service ML Platform Core

> The reference solution for [`projects/project-01-platform-core`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core)
> in the paired learning repository. This document follows the AICG
> Output Contract: 1) overview, 2) worked answer, 3) validation,
> 4) rubric, 5) common mistakes, 6) references.

## 1. Solution overview

Project 01 is the capstone of the foundation modules (mod-001
through mod-003 plus mod-007). The deliverable is a platform that
turns Kubernetes into a self-service ML platform: data scientists
submit `TrainingRun` intents through a CLI / SDK, and the platform
materialises them into per-tenant Kubernetes workloads with full
admission control, quota enforcement, isolation, observability, and
audit evidence.

The reference solution takes seven positions that together
distinguish a *platform* from "Kubernetes plus scripts":

1. **CRD is the operational source of truth; the DB mirrors it.**
   The operator reconciles against the CR. The PostgreSQL `training_runs`
   table exists for cross-tenant query (listing, filtering) and to
   survive CR garbage collection. Trade-off accepted: dual-store
   consistency overhead, in exchange for keeping Kubernetes-native
   semantics (RBAC, GC, finalizers) and getting fast queries.
2. **Control plane validates at admission; operator enforces
   continuously.** Schema, image allowlist, quota, dataset existence
   are checked at `POST /v1/training-runs`. The operator re-checks
   *only* the invariants it owns (Job state, retries, finalizers).
   Quota changes after admission do not kill running pods — that is
   a separate policy decision.
3. **Tenant isolation is layered, not single-mechanism.** A namespace
   alone is not a security boundary. Isolation requires *all four* of
   `ResourceQuota` + `LimitRange` + `NetworkPolicy default-deny` +
   workload identity (SPIFFE or cloud IRSA). The reference manifest
   ships them as a single onboarding artifact so they cannot drift
   apart.
4. **API is cursor-paginated, idempotency-keyed, header-tenanted.**
   Tenant is in the bearer token, not in the URL — one route table,
   one authorisation point. `Idempotency-Key` on POST is non-optional
   because retrying a training-run submission must not double-spend
   GPU-hours.
5. **Audit chain is insert-only at the SQL level, not just the app
   level.** A trigger rejects `UPDATE`, `DELETE`, *and* `TRUNCATE` on
   `audit_log`. The `verify_audit_chain()` SQL function walks the
   chain and returns the first tampered row's `sequence_no`, or
   `NULL` for verified. An auditor checking compliance asks for this
   property at the DB, not in code review.
6. **CRD ships at `v1alpha1` with a structural schema in place from
   day one.** Even though the conversion webhook does nothing yet,
   the structural-schema precondition has to be satisfied before the
   apiserver allows conversion later. Skipping it forces a CRD
   replacement (downtime + client breakage) when `v1beta1` arrives.
7. **Observability metrics are bounded-cardinality by design.**
   `tenant` is a label (bounded by org), `phase` is a label (bounded
   enum), run ID is *not* (unbounded). Putting run ID on a metric is
   the single mistake that has killed more Prometheus deployments
   than any other.

## 2. Worked answer or implementation

The curated artifacts in this directory map 1:1 to the eight
functional requirements:

### F1 — TrainingRun CRD ([`crd/training-run-crd.yaml`](./crd/training-run-crd.yaml))

OpenAPI v3 schema validates **seven** spec fields, not the bare
minimum of five required by F1:

- `spec.image` — registry-qualified, digest-pinned regex.
- `spec.resources.requests` / `spec.resources.limits` — Kubernetes
  quantity-syntax regex on every key.
- `spec.dataset.name` — DNS-1123 label.
- `spec.dataset.version` — semver-ish `vMAJOR[.MINOR[.PATCH]]`.
- `spec.hyperparameters` — `additionalProperties` constrained to
  scalar primitives (bounds the audit payload size).
- `spec.outputs.artifact_uri` — `s3://` / `gs://` / `abfss://` scheme.
- `spec.retries.max` — integer 0..10.

`status.phase` is constrained to the documented state-machine enum,
and `subresources.status: {}` is set so the operator updates
`status` without bumping `metadata.resourceVersion` of the spec
view (prevents reconcile-loops between the control plane writing
spec and the operator writing status).

Conversion strategy is `None` at `v1alpha1`; the structural schema
is the precondition for switching to `Webhook` in `v1beta1`.

### F2 — Control-plane API ([`control-plane/openapi.yaml`](./control-plane/openapi.yaml))

Surface deliberately narrow:

- `POST /v1/training-runs` — admission. Requires `Idempotency-Key`
  for retry safety; rejects with `429` and `code: quota.*` on
  over-quota; rejects with `400` and `code: schema.*` on bad input.
- `GET /v1/training-runs` — cursor-paginated list. Filters: `tenant`,
  `phase`, `created_after`, `created_before`. Cursor (not offset)
  tolerates list mutation mid-query, which is the dominant case
  here because the operator keeps writing status.
- `GET /v1/training-runs/{id}` — single-run state.
- `DELETE /v1/training-runs/{id}` — `202 Accepted` (cancellation is
  async; the operator finalises asynchronously).
- `GET /v1/tenants/{id}/quota-usage` — live usage vs. limits (F5).

`Error` shape is `{error, code, request_id}` — never stack traces.
`X-Request-Id` is server-assigned if absent and travels in the
response header and to logs / audit.

### F3 — Operator reconciliation ([`operator/reconcile.py`](./operator/reconcile.py))

The skeleton pins three properties graders should check:

- `desired_job()` is deterministic — same `spec` → byte-identical
  Job. This is what makes reconcile idempotent.
- `next_phase()` is a pure function. Tested without a cluster.
  Terminal states (`Succeeded`, `Failed`, `Cancelled`) are
  absorbing.
- `reconcile()` always adds the finalizer *before* touching child
  resources. This is the rule that prevents dangling Jobs when the
  CR is deleted between create and finalize.

Owner references make Job → CR GC automatic for in-cluster
resources; the finalizer handles *out-of-cluster* cleanup (audit
emit, DB row).

### F4 — Multi-tenancy ([`multi-tenancy/tenant-bootstrap.yaml`](./multi-tenancy/tenant-bootstrap.yaml))

Per tenant, all in one manifest the control plane templates and
applies at `POST /v1/tenants`:

- `Namespace` with Pod Security Admission `restricted` enforcement.
- `ResourceQuota` capping CPU, memory, GPU, pod count, job count.
- `LimitRange` with *no* default on `requests` (forces every
  Deployment to declare them) but defaults on `limits` (prevents a
  runaway pod consuming the whole quota).
- `NetworkPolicy default-deny` covering both ingress and egress.
- A second `NetworkPolicy` allowing only DNS + platform-component
  namespaces (feature-store, model-registry, MLflow) as egress.
- `ServiceAccount` with annotations for either AWS IRSA, GKE
  Workload Identity, or implicit SPIFFE — F4 accepts any of the
  three; the manifest shows the three placements so the choice is
  one annotation, not a refactor.

### F5 — Quota enforcement

Enforced at the control plane on `POST /v1/training-runs` (returns
`429 quota.gpu_hours.exceeded` or `quota.concurrent_runs.exceeded`).
Live usage exposed via `GET /v1/tenants/{id}/quota-usage`. Kubernetes
`ResourceQuota` is the second layer of defence at the namespace —
if the control plane is bypassed (a `kubectl apply` straight to the
cluster), the namespace quota still rejects the create.

### F6 — SDK + CLI

Out of scope for the curated artifacts — the OpenAPI spec is what
the SDK and CLI generate against. `openapi-generator-cli generate
-i control-plane/openapi.yaml -g python` is the SDK source. The
CLI verbs (`create | list | status | cancel`) wrap the four API
operations 1:1.

### F7 — Observability ([`observability/`](./observability))

Five metrics, label conventions documented, one dashboard JSON. The
catalog is explicit about what NOT to label (run ID, image digest,
user identity) — the single highest-leverage piece of guidance for
graders to check.

### F8 — Audit chain ([`audit/schema.sql`](./audit/schema.sql))

The trigger pattern is the load-bearing piece. Three triggers
(`BEFORE UPDATE`, `BEFORE DELETE`, `BEFORE TRUNCATE`) make the
table append-only at the SQL level. `verify_audit_chain()` returns
`NULL` for verified or the first bad `sequence_no`, which is what
the `verify` CLI command wraps.

## 3. Validation steps

Every artifact in this directory validates statically without a
running cluster. The platform's runtime tests are part of the
learner's deliverable.

```bash
# F1 — CRD shape
kubectl --dry-run=client -f crd/training-run-crd.yaml apply
kubeconform -strict -summary crd/training-run-crd.yaml

# F2 — OpenAPI spec
openapi-generator-cli validate -i control-plane/openapi.yaml
redocly lint control-plane/openapi.yaml

# F3 — Operator skeleton compiles
python3 -m py_compile operator/reconcile.py

# F4 — Tenant bootstrap is well-formed Kubernetes
kubeconform -strict -summary multi-tenancy/tenant-bootstrap.yaml

# F7 — Dashboard JSON parses
python3 -c "import json,sys; json.load(open('observability/grafana-dashboard.json')); print('ok')"

# F8 — Audit schema applies (against a throwaway DB)
psql -d audit_test -f audit/schema.sql --single-transaction --set ON_ERROR_STOP=1
```

The end-to-end acceptance demo (the 8-step grading procedure in
`requirements.md`) is what proves the *implementation*. The static
checks above prove the *contract* the learner is implementing
against is well-formed.

> Validation note: this solution was authored in a sandbox where
> Python and `kubectl` execution are not available. The artifacts
> were reviewed by hand against the official Kubernetes CRD spec,
> OpenAPI 3.0.3, PostgreSQL trigger semantics, and the Prometheus
> naming conventions. Graders running the commands above are the
> first execution path.

## 4. Rubric or review checklist

The full rubric is in [`rubric.md`](./rubric.md). Quick-look version:

| Pass means | Notes |
|---|---|
| All F1–F8 demonstrated end-to-end | The acceptance demo is non-negotiable. |
| `audit_log` rejects `UPDATE`/`DELETE`/`TRUNCATE` at the DB | Verified with three explicit psql commands, not "the code doesn't do it". |
| Cross-tenant bucket read fails *and* cross-namespace HTTP call fails | Two different layers of isolation — both must fail. |
| CRD has structural schema; `subresources.status: {}` set | Pre-requisite for safe future versioning + reconcile loops. |
| Metrics do not carry per-run labels | Single most common cardinality bomb. |
| `Idempotency-Key` honoured on POST | Tested with a deliberate retry of the same key + payload. |
| `make up` brings the whole platform up | NF1 — anything less is "scripts," not a platform. |

## 5. Common mistakes

Drawn from `STEP_BY_STEP.md` "Common pitfalls" in the learning repo
plus what graders see repeatedly in submissions:

- **Treating namespace as a security boundary.** It is a naming +
  RBAC + quota boundary. Cross-tenant isolation requires *all four*
  of namespace + quota + NetworkPolicy + workload identity. The
  reference `tenant-bootstrap.yaml` ships them together for this
  reason.
- **Skipping finalizers.** A `kubectl delete trainingrun foo` that
  leaves dangling Jobs is an automatic Fail on F3. Owner references
  handle in-cluster GC; finalizers handle out-of-cluster cleanup
  (DB row, audit emit).
- **Mutating `spec` from the operator.** Spec is the user's; status
  is the operator's. Mutating spec creates a feedback loop between
  the user's `kubectl edit` and the operator's writes.
- **Putting tenant in the URL path.** Doubles the route table, and
  per-tenant auth has to be re-implemented at every endpoint
  instead of in one middleware. The reference puts tenant in the
  bearer token.
- **Image tag instead of digest.** Tags are mutable; a `:v3.2.1`
  retagged at the registry silently changes what runs. The CRD
  regex enforces `@sha256:...`.
- **Audit-table insert-only enforced only in application code.** A
  DBA with psql or a misbehaving service bypasses the guard.
  Enforce it with a trigger on the *table*.
- **Putting run ID on Prometheus metrics.** Unbounded label
  cardinality kills the TSDB. Run-level state belongs in logs +
  DB, not metrics. The `observability/metrics.md` catalog
  documents this explicitly.
- **Auto-killing running pods on quota change.** Tempting, but a
  policy decision the platform team should make consciously and
  document — not a side effect of reconcile. The reference operator
  only blocks *new* pod creation when quota is reduced.
- **Hand-rolled CRD without `subresources.status: {}`.** Without
  the status subresource, every status write bumps the spec
  resource version, which retriggers reconcile, which writes status
  again — an infinite loop on a busy operator.
- **Skipping `Idempotency-Key` on POST.** Network retry → double
  training-run submission → double GPU-hour spend → angry FinOps
  team. The header is non-optional on any mutating endpoint that
  consumes real resources.

## 6. References

Project-local context:

- `projects/project-01-platform-core/README.md` (this dir).
- `projects/project-01-platform-core/STEP_BY_STEP.md` — solution-side
  build sequence.
- `projects/project-01-platform-core/rubric.md` — grading rubric.
- Curated artifacts: `crd/`, `control-plane/`, `operator/`,
  `multi-tenancy/`, `audit/`, `observability/`.

Paired learning repository (read alongside this solution):

- `projects/project-01-platform-core/README.md` — project framing.
- `projects/project-01-platform-core/requirements.md` — F1–F8 +
  NF1–NF4 and the acceptance demo.
- `projects/project-01-platform-core/architecture.md` — component
  map, CRD example, DB schema, non-functional targets.
- `projects/project-01-platform-core/STEP_BY_STEP.md` — phase-by-phase
  learner build guide.

Cross-references to other solutions in this repo:

- `modules/mod-001-platform-fundamentals/SOLUTION.md` — namespace
  is not a security boundary (ex-02); plugin model (ex-04).
- `modules/mod-002-api-design/SOLUTION.md` — versioning, error
  envelope, cursor pagination, `Idempotency-Key`.
- `modules/mod-003-multi-tenancy-resources/SOLUTION.md` — quotas,
  fair share, queueing.
- `modules/mod-007-developer-experience/SOLUTION.md` — SDK + CLI
  ergonomics.
- `modules/mod-008-observability/SOLUTION.md` — metric naming,
  label cardinality, structured logs.
- `modules/mod-009-security-governance/SOLUTION.md` — audit-chain
  pattern and compliance posture.

Official documentation (the source policy's "official first" tier):

- Kubernetes — [Custom Resource Definitions](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/),
  [Structural Schemas](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#specifying-a-structural-schema),
  [Status Subresource](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#status-subresource),
  [ResourceQuota](https://kubernetes.io/docs/concepts/policy/resource-quotas/),
  [LimitRange](https://kubernetes.io/docs/concepts/policy/limit-range/),
  [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/),
  [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/).
- [OpenAPI 3.0.3 specification](https://spec.openapis.org/oas/v3.0.3).
- [Prometheus — Naming](https://prometheus.io/docs/practices/naming/),
  [Instrumentation](https://prometheus.io/docs/practices/instrumentation/),
  [Histograms and summaries](https://prometheus.io/docs/practices/histograms/).
- [PostgreSQL — Triggers](https://www.postgresql.org/docs/current/triggers.html),
  [pgcrypto](https://www.postgresql.org/docs/current/pgcrypto.html).
- [SPIFFE specification](https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE.md) /
  [AWS IRSA](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) /
  [GKE Workload Identity](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity).
- [kopf — Kubernetes Operator Pythonic Framework](https://kopf.readthedocs.io/en/stable/).
