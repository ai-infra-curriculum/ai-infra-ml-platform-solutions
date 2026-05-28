# SOLUTION — Project 01: Self-Service ML Platform Core

> Read this *after* the per-component reference code under
> `control-plane/`, `operator/`, and `audit/`. This file explains
> the cross-component design rationale: why the platform is
> partitioned the way it is, what discipline the capstone
> collectively teaches, and the trade-offs the reference
> solution accepts.

## Overview

A platform team's deliverable is not "Kubernetes plus YAML." It is
**a contract that data scientists program against, and a control
loop that turns that contract into infrastructure**. The capstone
forces the engineer to internalize four things at once:

- Higher-order primitive (`TrainingRun`), not pod specs.
- Operator pattern end-to-end: CRD → controller → status writes →
  finalizers.
- Multi-tenant isolation that survives a hostile pod, not just a
  namespace label.
- An audit trail that produces evidence a compliance auditor will
  accept, not a log file.

The project's grade is whether all four hold up *together* under
the acceptance demo. Any one in isolation is a sub-skill that
modules 001-003 already teach.

## Implementation

### `control-plane/` — admission and intent storage

The control plane validates, persists, and dispatches. It does
**not** enforce. Three deliberate shapes:

- **Tenant in a header**, not in the path. Carried over from
  mod-001 ex-01; eliminates one combinatorial axis from the route
  table and lets a single `Depends(get_tenant)` cover every route.
- **CR is the operational source of truth, DB mirrors it**. The
  control plane writes both, but reconciles to the CR. The DB
  exists for cross-tenant queries the Kubernetes API can't answer
  cheaply, and for an audit history that survives CR deletion.
- **Idempotency-Key on POST**. Provisioning is expensive; double-
  posts under retry must not double-provision Jobs. The key maps
  to the CR `metadata.name`, which the cluster will reject on
  duplicate — so idempotency is enforced by Kubernetes, not by
  application code.

The point: the control plane is the *contract layer*. It must
fail fast and explain why. Stack traces never reach the user; the
`{error, code, request_id}` shape is non-negotiable.

### `operator/` — reconciliation and enforcement

The operator is intentionally **boring**. It does one thing:
makes cluster state match `spec`. The reference solution accepts:

- **Single reconcile entrypoint** for create + update + delete.
  Kopf's per-event handlers are a footgun — the same logic must
  run for every transition, or restart-recovery diverges.
- **Idempotent every call**. `reconcile(spec)` produces the same
  Job/ConfigMap/SA regardless of how many times it runs. This is
  what makes operator restart safe and what makes test cases
  tractable (assert on final state, not transition order).
- **Finalizers are mandatory, not optional**. Without them,
  deleting a `TrainingRun` leaves the Job, ConfigMap, and SA
  orphaned. Compliance auditors find these. The reference adds
  one finalizer (`platform.smartrecs.io/finalizer`) and removes
  it only after the cleanup path runs.
- **Status writes are separate from spec reads**. The operator
  never reads its own status to decide what to do — it reads
  cluster state. Status is a *publication channel for the user*,
  not internal memory.

Trade-off explicitly accepted: leader election is wired up but
the reference runs single-replica. The capstone is graded on
correctness, not HA.

### `audit/` — the compliance backbone

The audit chain is the single component an auditor will inspect
line-by-line. The reference solution treats it as a *separate*
component, not a logging library, for one reason: **a logger that
can also be turned off, redirected, or filtered cannot produce
evidence**. The audit chain is structurally different:

- **Insert-only at the SQL level**. A trigger rejects UPDATE and
  DELETE on the `audit_log` table. The application cannot tamper
  even if it wants to.
- **Hash-chained, with the previous-entry hash bound into the
  current entry's signature**. Removing or reordering an entry
  invalidates every entry after it.
- **Signing identity is workload identity**, not a shared key.
  The control plane signs with its SPIFFE SVID; the operator
  signs with its own. An auditor can prove which component
  emitted which event.
- **`verify` walks the chain and reports the first mismatch**.
  Not "the chain is fine" — the first byte that disagrees with
  the recomputed hash. That's what an investigator needs.

The point: this is the only component where you cannot ship
"good enough." The acceptance demo runs `verify` against the
platform DB; "verified" is binary.

## Design decisions the project shares

- **Higher-order primitive, not pod specs**. Users write
  `TrainingRun`, never `apiVersion: batch/v1`. If the CRD leaks
  Job semantics into the user's mental model, the abstraction
  has failed and you should rename the field.
- **Workload identity over service-account tokens**. Long-lived
  bearer tokens in a tenant namespace are a compromise that
  spreads. SPIFFE SVIDs (or cloud IRSA) are bound to the pod's
  identity and rotate automatically.
- **Default-deny NetworkPolicy in every tenant namespace**. The
  default-allow that Kubernetes ships with is the most common
  multi-tenancy bug in junior platform teams. The reference adds
  the deny policy *during tenant onboarding*, before any
  workload exists, so the first workload deploys against the
  enforced policy and not a permissive default.
- **Per-tenant cost attribution from day one**. Every metric and
  every audit entry carries `tenant`. Retrofitting tenant labels
  onto an established platform is the work of a quarter.
- **OpenAPI spec is version-controlled**, not generated as a
  build artifact. The spec is the source of truth that the SDK,
  CLI, and tests all consume.

## Rubric

Graders evaluate the capstone against the four-axis contract from the
Overview: higher-order primitive, end-to-end operator pattern, hostile-
pod multi-tenancy, and an evidence-grade audit chain. Below are the
failure modes that disqualify a submission — each is something the
acceptance demo surfaces deterministically.

### Common mistakes graders see

1. **Database-only model with no CR**. Loses Kubernetes-native
   semantics (RBAC, garbage collection, finalizers). The
   acceptance demo's "restart the operator" step exposes this
   immediately — there is no spec to reconcile against.
2. **CR-only model with no DB**. Cross-tenant listing requires
   walking every namespace; quota lookup is `O(runs)` instead of
   `O(1)`. The control plane's p95 latency target fails.
3. **Treating namespace as a security boundary**. Namespace
   provides naming + RBAC + quotas. NetworkPolicy + workload
   identity provide isolation. The acceptance demo's
   cross-tenant read attempt is exactly this trap.
4. **Skipping finalizers**. Deletion leaves orphaned Jobs and
   the next reconcile fires for resources that no longer have a
   CR. Symptom: the operator log fills with "not found" errors
   and the Job count drifts upward.
5. **Audit log as a logger, not a chain**. If `verify` is not
   shipped, or if the table allows UPDATE/DELETE, the audit
   trail is decorative. An auditor will reject it.
6. **Quota enforced only at admission**. A quota reduction
   *after* admission must be detected by the operator on next
   reconcile. The reference reads the current quota every time;
   it does not cache the admission-time value.
7. **Tenants as configuration**. Hardcoded tenant lists, env
   vars, or a YAML file. Tenants are first-class resources with
   their own lifecycle (onboarding, quota changes, offboarding).

## Validation

The reference solution is graded by an acceptance demo, not by unit
tests in isolation. The demo is the integration contract; passing
it is what "done" means.

- **End-to-end golden path**. `POST /trainingruns` from a tenant
  SDK → CR created → operator reconciles → Job runs → status
  transitions through `Pending → Running → Succeeded` → audit
  entries chained for every transition.
- **Operator restart recovery**. Kill the operator mid-run; on
  restart, `reconcile(spec)` reproduces the same Job/ConfigMap/SA
  without duplicating side effects. Idempotency is what the
  graders probe here.
- **Cross-tenant isolation under attack**. From inside tenant A's
  pod, attempt to (a) reach tenant B's service IP, (b) read
  tenant B's secrets via the Kubernetes API, (c) emit metrics
  labelled with tenant B. All three must fail closed —
  NetworkPolicy, RBAC bound to SPIFFE SVID, and the metrics
  middleware respectively.
- **Quota enforcement after admission**. Lower a tenant's quota
  *while* a run is queued; the operator's next reconcile must
  detect the violation and refuse to launch the Job (status
  reason: `QuotaExceeded`), not rely on the admission-time value.
- **Audit chain `verify` passes**. Run the audit verifier against
  the platform DB; it must return "verified" and the chain hash
  must match across control-plane and operator entries. Tamper
  with one row out-of-band and rerun; the verifier must report
  the **first** mismatched offset, not a generic failure.
- **Finalizer cleanup**. Delete a `TrainingRun`; the operator's
  finalizer path must remove the Job, ConfigMap, and SA before
  releasing the CR. `kubectl get all -l platform.smartrecs.io/run=<id>`
  returns empty.

If any of the six probes fails, the capstone is incomplete — not
"mostly working." The platform contract is binary at this layer.

## Where this project lands in the track

- It is the **integration test** for modules 001-003 and 007. If
  the per-module exercises taught the right vocabulary, this
  project assembles it.
- It is the **foundation** for projects 02-05. The feature store,
  workflow orchestrator, model registry, and serving plane all
  assume this control-plane shape and this tenant model.
- It is the **lower bound** of "real" ML platform engineering.
  Production platforms add HA, multi-region, fair-share
  scheduling, cost-based admission, and observability per SLO —
  none of which change the shape laid out here, only its
  amplitude.

## References

### Curriculum touchpoints

- [`ml-platform/mod-001`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/tree/main/modules/mod-001-platform-fundamentals)
  — platform fundamentals; the contract mindset this project enacts.
- [`ml-platform/mod-002`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/tree/main/modules/mod-002-api-design)
  — API design; the versioning + error shape the control plane ships.
- [`ml-platform/mod-003`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/tree/main/modules/mod-003-multi-tenancy-resources)
  — multi-tenancy + resources; the tenant isolation model.
- [`ml-platform/mod-007`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/tree/main/modules/mod-007-developer-experience)
  — developer experience; the SDK + CLI ergonomics.
- [`ml-platform/mod-008`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/tree/main/modules/mod-008-observability)
  — observability; the Prometheus + structured-log surface.
- [`ml-platform/mod-009`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/tree/main/modules/mod-009-security-governance)
  — security + governance; the audit chain and workload-identity binding.
- [`engineer-solutions/mod-104`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-104-kubernetes)
  — Kubernetes primitives the operator builds on.
- [`senior-engineer-solutions/projects/project-204-k8s-operator`](https://github.com/ai-infra-curriculum/ai-infra-senior-engineer-solutions/tree/main/projects/project-204-k8s-operator)
  — the production-grade `TrainingJob` operator; what this
  capstone's operator becomes after HA, leader election,
  graduated CRD versioning, and full envtest coverage land.
- [`architect-solutions/projects/project-301-enterprise-mlops`](https://github.com/ai-infra-curriculum/ai-infra-architect-solutions/tree/main/projects/project-301-enterprise-mlops)
  — what an enterprise-scale version of this same platform looks like.

### Upstream specifications and tooling

- [Kubernetes CustomResourceDefinitions](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/)
  — the CRD contract the `TrainingRun` type implements.
- [Kubernetes Finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/)
  — the deletion-handshake the operator relies on for cleanup.
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
  — the default-deny posture each tenant namespace ships with.
- [Kopf operator framework](https://kopf.readthedocs.io/) — the
  reference operator's reconciliation runtime.
- [SPIFFE / SPIRE](https://spiffe.io/docs/latest/spiffe-about/overview/)
  — workload identity used to sign audit entries and bind RBAC.
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
  — the trace + metric attribute shape platform components emit.
