# Project 01 -- Self-Service ML Platform Core (Solution)

Reference solution for [project-01-platform-core](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core)
in the paired learning repository.

This directory is **a curated reference, not a full deployable
codebase**. Every artifact is statically valid (validates with
`kubeconform`, `openapi-spec-validator`, `psql --single-transaction`,
`yamllint`, or `python3 -m py_compile`) and is sized to make the
design rationale clear, not to be `make up`-able on its own.

## What's here

| Path | Maps to | Purpose |
|---|---|---|
| `SOLUTION.md` | (this project) | Worked solution following the 6-section AICG Output Contract. |
| `STEP_BY_STEP.md` | learning `STEP_BY_STEP.md` | Solution-side build order with annotations on what each phase yields. |
| `rubric.md` | `requirements.md` | Grading rubric distilled from F1-F8 + NF requirements. |
| `audit/schema.sql` | F6 | Hash-chained audit log, append-only triggers, `verify_audit_chain()` function. |
| `audit/verify.py` | F6 | Pure-Python verifier mirroring the SQL function for auditors with read-only access. |
| `control-plane/openapi.yaml` | F1, F2, F3 | Platform API contract (tenants, claims, training runs, audit read + verify). |
| `control-plane/schema.sql` | F1, F2, F5 | Relational state + row-level security tying every read to the caller's tenant. |
| `control-plane/training_runs.py` | F1, F2 | Reference handler shape: tenant scope, idempotency, audit-emit, budget check. |
| `operator/crds.yaml` | F4 | `TrainingRun` + `ResourceClaim` CRDs with structural schemas. |
| `operator/reconcile.py` | F4 | Reconcile-loop skeleton with terminal-phase guard and one-audit-per-transition. |
| `multi-tenancy/namespace-template.yaml` | F5 | Per-tenant Namespace + Quota + LimitRange + default-deny NetPol + RBAC. |

## What's intentionally not here

- The full FastAPI app, the full operator binary, the Helm charts,
  the OIDC stub, the CLI. Those are the learner's deliverable. The
  curated artifacts above pin the **interfaces** that grade against
  the rubric; the implementations behind them are part of the
  ~70-hour learning exercise.
- A `Makefile` or `make up` target. The non-functional
  requirements section in the rubric is what grades the
  learner's deployable bundle.
- Production OIDC provider configuration. `control-plane/openapi.yaml`
  declares the bearer-token security scheme; the learner picks an
  IdP (Dex, Keycloak, or a managed one).
- The model registry's database. That artifact lives in
  [`project-04-model-registry/registry/schema.sql`](../project-04-model-registry/registry/schema.sql);
  the registry **uses** the audit chain defined here but does not
  redefine it.

See [`SOLUTION.md`](./SOLUTION.md) for the reasoning, validation
commands, common mistakes, and references.

## Quick links

- [SOLUTION.md](./SOLUTION.md)
- [STEP_BY_STEP.md](./STEP_BY_STEP.md)
- [rubric.md](./rubric.md)
- Learning project: [`projects/project-01-platform-core`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-01-platform-core)
- Track overview: [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md)
