# STEP_BY_STEP — Project 01 Solution

Solution-side walk-through. The learning repo's
[`STEP_BY_STEP.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/STEP_BY_STEP.md)
prescribes ten phases over ~80 hours; this document mirrors those
phases and pins what each one yields *in this solution's terms*. Use
it to sequence your build and to know when each phase is "done
enough" to move on.

Each phase below points at the artifact in this directory that
captures its contract. Build implementations to meet those
contracts; the curated files are the rubric.

## Phase 0 — Cluster + skeleton (1–2 h)

**Yield**: a kind/k3d cluster, an empty repo skeleton, pinned
Python deps.

Solution-side check: `kubectl get nodes` returns a Ready node;
`tree` of the repo matches the skeleton in the learning
`STEP_BY_STEP.md` §0.

## Phase 1 — CRD (2–3 h)

**Yield**: `TrainingRun` registered, schema rejects bad specs,
accepts good ones, `v1alpha1` with structural schema.

Pin: [`crd/training-run-crd.yaml`](./crd/training-run-crd.yaml).
Seven validated spec fields, status subresource enabled,
conversion strategy `None` (ready for `Webhook` when v1beta1
arrives).

Done when:
```bash
kubectl apply -f tests/fixtures/invalid-run.yaml   # rejected
kubectl apply -f tests/fixtures/minimal-valid-run.yaml  # accepted
```

## Phase 2 — Operator skeleton (5–7 h)

**Yield**: reconcile fires on CR create/update, logs the event,
applies RBAC. No business logic yet.

Pin: [`operator/reconcile.py`](./operator/reconcile.py). Note
`desired_job()` is deterministic and `next_phase()` is pure —
write tests against those before wiring kopf.

Done when applying a sample CR fires the log and *no* dangling
resources appear after `kubectl delete trainingrun foo`.

## Phase 3 — Reconciliation (8–10 h)

**Yield**: full state machine, finalizers, retries, idempotent
reconcile, operator-restart convergence within 30 s.

The four test cases from the learning `STEP_BY_STEP.md` §3
("Test cases to cover") are the acceptance bar:

- happy path → success;
- failure path → retry → success;
- mid-run cancellation cleans up;
- mid-run operator restart converges.

Pin: the finalizer constant `FINALIZER` in `reconcile.py` —
adding it *before* applying child resources is the load-bearing
rule.

## Phase 4 — Control plane (6–8 h)

**Yield**: FastAPI app exposing the four endpoints in
[`control-plane/openapi.yaml`](./control-plane/openapi.yaml),
talking to PostgreSQL, applying CRs, emitting audit events.

Pin: the `Error` schema (`{error, code, request_id}`). Never
return a stack trace. Add an `X-Request-Id` middleware before
implementing any route — retro-fitting correlation IDs is more
work than it sounds.

Done when the six test cases from the learning `STEP_BY_STEP.md`
§4 pass.

## Phase 5 — Multi-tenancy (5–7 h)

**Yield**: `POST /v1/tenants` provisions all five tenant objects.
A pod in tenant A cannot read tenant B's bucket *or* hit a service
in tenant B's namespace.

Pin: [`multi-tenancy/tenant-bootstrap.yaml`](./multi-tenancy/tenant-bootstrap.yaml).
Treat the file as one templated apply, not five separate ones —
if the operator can create the namespace but fails on the
NetworkPolicy, the tenant is *less* secure than if onboarding had
failed entirely. Onboarding must be transactional.

Acceptance test from the learning `STEP_BY_STEP.md` §5 (cross-
tenant bucket read fails *and* cross-namespace HTTP fails) is
non-negotiable. Both must fail.

## Phase 6 — Observability (3–4 h)

**Yield**: `/metrics` on control plane + operator, structured
JSON logs, one Grafana dashboard.

Pin: [`observability/metrics.md`](./observability/metrics.md) for
the five metrics and label conventions, and
[`observability/grafana-dashboard.json`](./observability/grafana-dashboard.json)
for the rendered dashboard.

Single most-common mistake here: putting run ID on a metric.
The catalog calls it out; don't do it.

## Phase 7 — Audit chain (3–4 h)

**Yield**: every significant action emits a hash-chained event;
`verify` returns "verified" or the first bad row.

Pin: [`audit/schema.sql`](./audit/schema.sql). Enforce the
insert-only property at the *table* with three triggers
(`BEFORE UPDATE`, `BEFORE DELETE`, `BEFORE TRUNCATE`). The
`verify_audit_chain()` function is the body of the `verify` CLI
command.

Done when:
```sql
-- All three of these raise an exception:
UPDATE audit_log SET payload = '{}' WHERE sequence_no = 1;
DELETE FROM audit_log WHERE sequence_no = 1;
TRUNCATE TABLE audit_log;
```

## Phase 8 — SDK + CLI (3–4 h)

**Yield**: a generated Python SDK, a Typer/Click CLI wrapping
the four operations, examples in `examples/`.

Generate the SDK from the OpenAPI spec; don't hand-write it:
```bash
openapi-generator-cli generate \
  -i projects/project-01-platform-core/control-plane/openapi.yaml \
  -g python -o sdk/
```

CLI verbs are exactly the four `requirements.md` F6 verbs —
`create | list | status | cancel`.

## Phase 9 — Testing + acceptance (4–6 h)

**Yield**: unit + envtest + one end-to-end script that runs the
eight-step acceptance demo unattended.

The acceptance demo from `requirements.md` is the only test that
*proves* the platform. Everything else is a precondition.

## Phase 10 — Documentation (3–4 h)

**Yield**: `README.md`, `ARCHITECTURE.md`, auto-generated OpenAPI,
onboarding guide, runbook.

Pin: every "common mistake" in `SOLUTION.md` §5 should appear in
either the runbook (as an incident to recognise) or the onboarding
guide (as a thing not to do).

## Cross-references

- [`SOLUTION.md`](./SOLUTION.md) — 6-section solution document.
- [`rubric.md`](./rubric.md) — what graders grade.
- [`README.md`](./README.md) — artifact catalog.
- Learning-repo phases live at
  `https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core`.
