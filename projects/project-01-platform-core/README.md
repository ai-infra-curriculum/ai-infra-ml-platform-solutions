# Project 01 — Platform Core (Solution)

Reference solution for [project-01-platform-core](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core)
in the paired learning repository.

This directory is **a curated reference, not a full deployable codebase**.
Every artifact is statically valid (validates with `kubectl --dry-run=client`,
`kubeconform`, `openapi-generator-cli validate`, `psql --single-transaction`,
or `python3 -m py_compile`) and is sized to make the design rationale
clear, not to be `make up`-able on its own.

## What's here

| Path | Maps to | Purpose |
|---|---|---|
| `SOLUTION.md` | (this project) | Worked solution following the 6-section AICG Output Contract. |
| `STEP_BY_STEP.md` | learning `STEP_BY_STEP.md` | Solution-side build order with annotations on what each phase yields. |
| `rubric.md` | `requirements.md` | Grading rubric distilled from F1–F8 + NF1–NF4. |
| `crd/training-run-crd.yaml` | F1 | Versioned CRD with OpenAPI v3 schema and 5+ validated spec fields. |
| `control-plane/openapi.yaml` | F2, F5, F6 | Control-plane API contract (POST/GET/DELETE, quota-usage, error envelope). |
| `operator/reconcile.py` | F3 | Reconciliation skeleton — pure state machine, idempotent step, finalizer wiring. |
| `multi-tenancy/tenant-bootstrap.yaml` | F4 | Namespace + ResourceQuota + LimitRange + NetworkPolicy + ServiceAccount with workload-identity binding. |
| `audit/schema.sql` | F8 | Insert-only audit table with hash-chain `verify()` SQL function. |
| `observability/metrics.md` | F7 | Catalog of the five required metrics, label conventions, and what NOT to label. |
| `observability/grafana-dashboard.json` | F7 | One Grafana dashboard JSON covering the five metrics + an admission-error SLO panel. |

## What's intentionally not here

- The full FastAPI control-plane app, full kopf controller, SDK,
  CLI, Helm charts. Those are the learner's deliverable. The
  curated artifacts above pin the **interfaces** that grade against
  the rubric; the implementations behind them are part of the
  ~80-hour learning exercise.
- A `Makefile` or `make up` target. NF1 in the rubric is what grades
  the learner's deployable bundle.
- Per-tenant Vault / ESO config. NF3 covers it; this solution shows
  the ServiceAccount + workload-identity binding, not the secret
  store wiring.

See [`SOLUTION.md`](./SOLUTION.md) for the reasoning, validation
commands, common mistakes, and references.
