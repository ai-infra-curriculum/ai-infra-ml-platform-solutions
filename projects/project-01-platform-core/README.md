# Project 01 Solution — Self-Service ML Platform Core

Reference solution for [project-01-platform-core](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/README.md)
(ml-platform capstone). Build the foundational layer that turns
Kubernetes into a self-service ML platform: a `TrainingRun` primitive,
a control plane that validates intents, an operator that reconciles
them, per-tenant isolation, and a compliance-grade audit chain.

| Document | Purpose |
|---|---|
| [`SOLUTION.md`](./SOLUTION.md) | Canonical answer: design rationale, worked implementation, validation, rubric, common mistakes |
| [`STEP_BY_STEP.md`](./STEP_BY_STEP.md) | Reproduction + validation runbook for the reference artifacts |

| Reference artifact | Requirement | Demonstrates |
|---|---|---|
| [`crd/trainingrun-crd.yaml`](./crd/trainingrun-crd.yaml) | F1 | `TrainingRun` CRD — `v1alpha1`, structural schema, ≥5 validated fields |
| [`operator/reconcile.py`](./operator/reconcile.py) | F3 | kopf reconcile loop, finalizers, retry/backoff, idempotent restart |
| [`control-plane/training_runs.py`](./control-plane/training_runs.py) | F2, F5 | FastAPI CRUD, error contract, quota admission (429) |
| [`tenant/tenant-namespace.yaml`](./tenant/tenant-namespace.yaml) | F4 | namespace + quota + LimitRange + default-deny NetworkPolicy + workload identity |
| [`audit/schema.sql`](./audit/schema.sql) | F8 | DB-enforced insert-only hash-chained audit log |
| [`audit/verify.py`](./audit/verify.py) | F8 | audit-chain verifier (first tampering or `verified`) |

The artifacts are the hardest-to-get-right, most-graded pieces — not a
full 80-hour codebase. Each is statically valid; validation commands are
in [`SOLUTION.md` §3](./SOLUTION.md#3-validation-steps) and each file's
header. Start with [`SOLUTION.md`](./SOLUTION.md).
