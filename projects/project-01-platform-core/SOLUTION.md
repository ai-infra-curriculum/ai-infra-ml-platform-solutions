# SOLUTION -- project-01-platform-core

> Worked solution for the
> [project-01-platform-core](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core)
> capstone in the paired learning repo. Follows the 6-section AICG
> Output Contract.

## 1. Solution overview

The platform-core capstone is the foundation every later project
sits on. Project-04 (model registry) writes to its audit chain;
project-02 (feature store), project-03 (workflow orchestration),
and project-05 (developer portal) all submit work through its
control-plane API and reconcile through its operator. Get this
project wrong and every later project inherits the same wrong
shape.

The reference solution is shaped by one product-level claim:

> An ML platform exposes higher-order primitives -- `Tenant`,
> `ResourceClaim`, `TrainingRun` -- not Kubernetes objects. If
> a user has to write a Pod spec or a NetworkPolicy, the
> platform has failed its mission, regardless of how good the
> infrastructure is.

That claim drives five design commitments:

1. **`Tenant`, `ResourceClaim`, and `TrainingRun` are first-class
   resources** in `control-plane/openapi.yaml`. They are not
   pass-through wrappers over K8s objects; the platform owns the
   translation.
2. **Tenant scope is enforced at the database layer**, not just at
   the handler. `control-plane/schema.sql` ships row-level
   security policies that return zero rows when the handler
   forgets to bind `platform.tenant_id`. Cross-tenant lookups
   return 404, not 403, because 403 leaks existence.
3. **Every state change writes one audit row**, in the same
   transaction as the resource row. `audit/schema.sql` hashes the
   row in a BEFORE INSERT trigger so the caller cannot tamper with
   the chain; UPDATE and DELETE on `audit_log` both raise.
4. **The operator's reconcile loop is idempotent.** Terminal
   phases (`Succeeded`, `Failed`, `Cancelled`) do not get
   re-reconciled into a new Pod. Audit rows are emitted on phase
   transitions, not per reconcile, so a stuck reconciler does not
   flood the chain.
5. **POSTs are idempotent end-to-end.** Every state-changing call
   requires an `Idempotency-Key`; the control-plane handler
   replays the original response inside a 24 h window. The SDK
   pays no penalty for retries.

The four track-level principles from `SOLUTION_OVERVIEW.md` --
self-service, platform-owned multi-tenancy, cost attribution from
day one, backward-compatible APIs -- are all visible in the
curated artifacts. Project-01 is where they get instantiated as
code.

### Curated artifacts (mapped to F1-F8)

| Path | Maps to |
|---|---|
| `control-plane/openapi.yaml` | F1, F2, F3 |
| `control-plane/schema.sql` | F1, F2, F5 |
| `control-plane/training_runs.py` | F1, F2 |
| `audit/schema.sql` | F6 |
| `audit/verify.py` | F6 |
| `operator/crds.yaml` | F4 |
| `operator/reconcile.py` | F4 |
| `multi-tenancy/namespace-template.yaml` | F5 |
| `STEP_BY_STEP.md` | build sequence |
| `rubric.md` | per-row grading bar |

F7 (identity) and F8 (self-service onboarding) do not have a
curated artifact in this directory -- they grade against the
learner's OIDC wiring and CLI integration. The references for
each row are in `mod-009/ex-01` and `mod-007/ex-02` respectively.

## 2. Worked answer or implementation

### 2.1 Higher-order primitives (F1)

The platform's user-facing object model is three nouns:

- **`Tenant`** -- a team's slice of the platform. One tenant maps
  to one K8s namespace, one OIDC group, one quota envelope, and
  one default-deny network boundary. The operator's job is to
  keep that 1:1:1:1:1 mapping intact.
- **`ResourceClaim`** -- a tenant's CPU/memory/GPU budget grant.
  Submitting work that would exceed an active claim returns 402;
  the user must create another claim (which may pend on platform-
  admin approval if it exceeds the tenant's base budget).
- **`TrainingRun`** -- a single ML training job. Async by
  construction; the API returns 202, the operator drives phase
  transitions, the caller polls or watches.

The OpenAPI spec uses the colon-action verb (`:cancel`,
`:verify`) for non-CRUD operations. That's the same Google-style
syntax that mod-001 ex-01 introduces; carrying it forward is the
"contracts are forever" principle in practice.

### 2.2 Idempotency contract (F2)

Every POST endpoint requires `Idempotency-Key`. The middleware:

1. Computes `sha256(canonical_request_body)` as the request hash.
2. Looks up `(tenant_id, key)` in `idempotency_keys`.
3. If found and the stored hash matches: returns the stored
   `(status, body)` verbatim.
4. If found and the hash differs: returns **409**.
5. If not found: runs the handler in a transaction, then inserts
   the `(key, request_hash, response_status, response_body)`
   tuple before commit.

`control-plane/training_runs.py` shows the shape inline in
`submit_training_run`. The replay window is 24 hours (a TTL job
sweeps older rows); that's long enough for any reasonable client
retry loop and short enough that the table stays small.

### 2.3 Multi-tenancy is platform-owned (F5)

The user does not write any of these objects:

- `Namespace` (with restricted Pod Security Admission labels).
- `LimitRange` (so manifests without requests/limits still get
  sane defaults; mod-003 ex-01 grades on this).
- `ResourceQuota` (so a tenant cannot escape its own budget; the
  numbers come from the approved `ResourceClaim`).
- `NetworkPolicy` x 4: default-deny ingress, default-deny egress,
  allow intra-namespace, allow platform-services egress +
  kube-dns. Mod-003 ex-03's "namespace is not a security
  boundary; NetworkPolicy is" lesson is the floor.
- `Role` + `RoleBinding` mapping the OIDC group to namespace-edit.

All of those are in `multi-tenancy/namespace-template.yaml` and
get rendered + applied by the operator when a `Tenant` goes from
`Provisioning` to `Active`. The application of that bundle is the
F5 hard-pass; missing any one of the four NetPols is the most
common reason F5 grades Partial.

Cross-tenant ID lookups return 404. 403 leaks that the resource
exists; F5 is specific about this and the `multi-tenancy_scope`
RLS policy in `control-plane/schema.sql` is what enforces it at
the data layer (the policy returns zero rows; the handler maps
zero rows to 404).

### 2.4 Audit chain (F6)

`audit/schema.sql` is the trust anchor. Design points:

- A **genesis row** at `seq = 0` with zero hashes seeds the chain
  so the very first real entry has a deterministic predecessor.
  No special case in the trigger; no off-by-one bug at row 1.
- The **`audit_chain_link()` BEFORE INSERT trigger** computes
  `prev_hash` from `max(seq)`'s `entry_hash` and
  `entry_hash = sha256(canonical_payload)`. The caller's values,
  if any, are overwritten -- the chain is the system's word, not
  the caller's.
- **`audit_chain_immutable()`** is attached to both UPDATE and
  DELETE; an attacker who controls the application cannot
  silently rewrite history. They have to either drop the triggers
  (loud, requires DDL privilege) or break the chain (loud, surfaces
  the next time `verify_audit_chain` runs).
- **`verify_audit_chain(start_seq, end_seq)`** walks the range and
  returns one row per break. Empty result = clean. Project-04
  calls this on a schedule and pages on any non-empty result.
- **`audit/verify.py`** is the Python mirror -- an auditor with
  read-only access can verify the chain without needing to trust
  the database's PL/pgSQL function definition. The
  `_canonical_blob` function MUST byte-match the SQL trigger.
  Because the SQL trigger casts `jsonb_build_object(...)` to
  text, the canonical form is whatever JSONB emits: keys sorted
  alphabetically at every nesting level, `", "` between items,
  `": "` between key and value, and non-ASCII not escaped. The
  Python mirror sets `sort_keys=True, separators=(", ", ": "),
  ensure_ascii=False` so the two sides agree to the byte. If
  either side drifts, every chain breaks at the next verification
  -- intended fail-loud, but during development the two
  definitions are kept in sync by hand.

The chain commits to the *content* (tenant, actor, action,
resource, payload, request_id, prev_hash), not to the *transport*
(id, seq, occurred_at). Wall-clock time can skew on a replica;
seq is assigned after the hash; UUIDs are random. The
distinction is the difference between a tamper-evident log and a
just-a-log.

### 2.5 Operator (F4)

`operator/crds.yaml` defines `TrainingRun` and `ResourceClaim`
with structural schemas. The API server validates submissions at
admission time, before the reconciler ever sees them.

`operator/reconcile.py` ships the reconcile contract:

- **Terminal phases are sticky.** A `Succeeded` TrainingRun is
  not re-created if its Pod is garbage-collected. The terminal
  set is enumerated once at the top of the module.
- **One audit row per phase transition**, not per reconcile. A
  steady-state reconciler that runs every 15 s does not emit a
  row every 15 s; it emits one when the phase changes.
- **The operator never trusts user input for `tenantID`.** The
  control-plane admission webhook stamps `spec.tenantID` from the
  OIDC token; the operator reads it from there. A user who tries
  to set `tenantID` directly on a manifest is rejected by the
  webhook before the CRD lands.
- **The workload Pod is locked down**: `runAsNonRoot`, no
  privilege escalation, read-only root, `drop: [ALL]` caps,
  no automounted service account token. The Pod-spec template in
  `_build_pod_manifest` is the reference shape; copy it.

The operator-framework choice (kopf, controller-runtime,
operator-sdk) is the learner's; the contract above grades against
any of them.

### 2.6 Identity + RBAC (F7)

`control-plane/openapi.yaml` declares `bearerAuth` as the only
security scheme. The platform accepts:

- OIDC-issued user tokens (group claim drives RBAC).
- Short-lived service tokens (SPIFFE or workload-identity for
  intra-cluster service-to-service).

No long-lived static credentials anywhere. The reference
solution refuses to ship one even for local dev; the kind
cluster's Dex instance hands out 5-minute tokens and the CLI
re-auths automatically. Rotation is the property that makes the
platform breach-resilient; F7 grades on its presence.

The detailed identity model lives in `mod-009/ex-01`; this
project's contribution is wiring it into the API server's bearer-
token validator and the namespace RBAC bindings in
`multi-tenancy/namespace-template.yaml`.

### 2.7 Self-service onboarding (F8)

The headline metric is **time-to-first-TrainingRun**: from "a new
team has zero account" to "their first TrainingRun is in
`Succeeded`", measured in wall-clock minutes. The bar is 10
minutes for a competent engineer; mod-007 ex-03's tutorial is the
artifact graders run.

The CLI from `mod-007/ex-02` is the platform team's own first
customer. If the platform team cannot happily run
`platform run submit`, no one else will. Dogfood is the test, not
a survey.

### 2.8 What this project does *not* own

Five things are referenced and used, but defined elsewhere:

- The model registry's database schema -- lives in
  `project-04-model-registry/registry/schema.sql`, not here.
- The feature store -- `project-02-feature-store`.
- Workflow orchestration -- `project-03-workflow-orchestration`.
- The developer portal -- `project-05-developer-portal`.
- The OIDC IdP itself -- the platform consumes one; it does not
  ship one.

This is deliberate. `SOLUTION_OVERVIEW.md` calls the platform "a
product, not infrastructure." A product team owns its API and
its data; it integrates with the rest of the org's
infrastructure.

## 3. Validation steps

Run from the repo root in the order below. Each command exits 0
on success; non-zero is the diagnostic for the failing artifact.

```bash
# Audit-chain schema applies cleanly and immutability holds.
psql -d platform \
     -f projects/project-01-platform-core/audit/schema.sql \
     --single-transaction --set ON_ERROR_STOP=1

# Control-plane schema applies cleanly; RLS policies attach.
psql -d platform \
     -f projects/project-01-platform-core/control-plane/schema.sql \
     --single-transaction --set ON_ERROR_STOP=1

# OpenAPI spec parses.
openapi-spec-validator projects/project-01-platform-core/control-plane/openapi.yaml

# Operator CRDs are structural-schema-valid.
kubeconform -strict -summary -kubernetes-version 1.29 \
    projects/project-01-platform-core/operator/crds.yaml

# Tenant namespace template is structural-schema-valid.
kubeconform -strict -summary -kubernetes-version 1.29 \
    projects/project-01-platform-core/multi-tenancy/namespace-template.yaml

# Python artifacts compile.
python3 -m py_compile \
    projects/project-01-platform-core/audit/verify.py \
    projects/project-01-platform-core/control-plane/training_runs.py \
    projects/project-01-platform-core/operator/reconcile.py
```

Note: this workspace blocks `python3 ...` execution; graders run
the commands above with their own toolchain. The artifacts have
been review-validated statically.

In addition, run the eight-step acceptance demo from `rubric.md`
(the actual end-to-end proof that the system works).

## 4. Rubric or review checklist

See [`rubric.md`](./rubric.md). The grader marks each row Pass /
Partial / Fail. Two Fails or four Partials means the project does
not pass; one Fail with otherwise-Pass rows means "return for
revision".

The acceptance demo at the bottom of `rubric.md` is the only
end-to-end proof of the system; a learner without a screencast of
all eight steps grades Partial regardless of how complete the
code is. Steps 7 and 8 together are what prove F6 (audit chain)
is *real* rather than aspirational.

## 5. Common mistakes

- **Pass-through wrappers over K8s objects.** A `POST /jobs` that
  takes a Pod spec is not a platform; it is `kubectl apply -f`
  with extra steps. F1 grades on the existence of higher-order
  primitives.
- **Tenant scope enforced only in the handler.** A bug that
  forgets the `WHERE tenant_id = ?` clause leaks rows across
  tenants. Row-level security in `control-plane/schema.sql` is
  the safety belt for when the handler is wrong.
- **403 on cross-tenant lookup.** 403 leaks existence. Return
  404. The rubric's F5 row is specific.
- **`Idempotency-Key` advisory, not required.** A POST without
  the header must return **400**, not be silently processed. The
  contract is the contract.
- **Idempotency that compares request bodies loosely.** Whitespace
  or key-order differences must NOT collapse to the same hash;
  use a canonical JSON serialization. `_hash_request` in
  `training_runs.py` shows the shape.
- **Caller-supplied audit hashes.** The audit-link trigger
  overwrites `prev_hash` and `entry_hash`. A handler that
  computes them itself is fine -- the trigger silently corrects
  -- but a handler that *trusts* a value supplied by an external
  caller is the F6 hard fail.
- **Audit emit *after* the resource write.** If the resource row
  commits and the audit row's commit then fails, you have an
  orphaned resource with no audit trail. The audit row must be in
  the same transaction as the resource row; `training_runs.py`
  writes the audit row first to make the dependency obvious.
- **Reconciler that emits an audit row every loop.** Phase
  transitions are the event, not reconciles. A reconciler that
  emits per loop floods the chain and makes the rubric F6
  un-gradable.
- **NetworkPolicy in audit mode forever.** Audit teaches you what
  flows exist; enforce is what blocks the bad ones. Mod-003 ex-03
  is the prerequisite reading.
- **Quotas without object-count limits.** A misconfigured
  controller that creates a million ConfigMaps takes down the
  cluster, not just the offending namespace. The template ships
  `pods`, `services`, `configmaps`, `secrets`, and `pvc` caps.
- **Long-lived static tokens for the operator.** The operator's
  bearer token for talking to the control plane must be SPIFFE-
  issued or workload-identity-issued; a baked-in token is the F7
  hard fail.
- **A tenant-deprovision procedure that's never been drilled.**
  Counts as "no deprovision procedure" for grading purposes. The
  runbook ships with a quarterly drill cadence.

## 6. References

Curriculum-internal:

- Paired learning project:
  [`projects/project-01-platform-core`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core)
  -- `README.md`, `architecture.md`, `requirements.md`,
  `STEP_BY_STEP.md`.
- Module 01 reference solution:
  [`modules/mod-001-platform-fundamentals/SOLUTION.md`](../../modules/mod-001-platform-fundamentals/SOLUTION.md)
  -- the OpenAPI-as-artifact discipline and the platform-product
  framing this project instantiates.
- Module 02 reference solution:
  [`modules/mod-002-api-design/SOLUTION.md`](../../modules/mod-002-api-design/SOLUTION.md)
  -- versioning, deprecation, idempotency, and the SDK-from-spec
  posture.
- Module 03 reference solution:
  [`modules/mod-003-multi-tenancy-resources/SOLUTION.md`](../../modules/mod-003-multi-tenancy-resources/SOLUTION.md)
  -- the tenancy patterns that `multi-tenancy/namespace-template.yaml`
  applies.
- Module 07 reference solution:
  [`modules/mod-007-developer-experience/SOLUTION.md`](../../modules/mod-007-developer-experience/SOLUTION.md)
  -- the CLI + tutorial that F8 grades against.
- Module 09 reference solution:
  [`modules/mod-009-security-governance/SOLUTION.md`](../../modules/mod-009-security-governance/SOLUTION.md)
  -- the OIDC + RBAC identity model F7 depends on.
- Project-04 (depends on this project's audit chain):
  [`projects/project-04-model-registry/`](../project-04-model-registry/)
  -- `SOLUTION.md` references `audit/schema.sql` and
  `verify_audit_chain()` directly.
- Track-level overview: [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md).

External (official):

- OpenAPI 3.1.0 specification:
  <https://spec.openapis.org/oas/v3.1.0>
- Kubernetes API Conventions (resource kinds, status, conditions):
  <https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md>
- Kubernetes CustomResourceDefinition structural schemas:
  <https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#specifying-a-structural-schema>
- Kubernetes Pod Security Admission:
  <https://kubernetes.io/docs/concepts/security/pod-security-admission/>
- Kubernetes NetworkPolicy:
  <https://kubernetes.io/docs/concepts/services-networking/network-policies/>
- Kubernetes ResourceQuota + LimitRange:
  <https://kubernetes.io/docs/concepts/policy/resource-quotas/>,
  <https://kubernetes.io/docs/concepts/policy/limit-range/>
- PostgreSQL row-level security:
  <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- PostgreSQL `pgcrypto` (sha256 / digest):
  <https://www.postgresql.org/docs/current/pgcrypto.html>
- OpenID Connect Core 1.0:
  <https://openid.net/specs/openid-connect-core-1_0.html>
- SPIFFE / SPIRE specification:
  <https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE.md>
- CNCF Platforms Working Group whitepaper (platform-as-product
  framing):
  <https://tag-app-delivery.cncf.io/whitepapers/platforms/>

External (practitioner examples, used only as illustration of
specific implementation patterns, never as authoritative claims):

- VeriSwarm engineer-solutions `mod-104` -- Kubernetes primitives
  and multi-tenancy patterns:
  <https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-104-kubernetes>
