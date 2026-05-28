# Project 04 — Model Management System (Solution)

Reference solution for [project-04-model-registry](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-04-model-registry)
in the paired learning repository.

This directory is **a curated reference, not a full deployable codebase**.
Every artifact is statically valid (validates with `kubeconform`,
`openapi-spec-validator`, `psql --single-transaction`, `yamllint`, or
`python3 -m py_compile`) and is sized to make the design rationale
clear, not to be `make up`-able on its own.

## What's here

| Path | Maps to | Purpose |
|---|---|---|
| `SOLUTION.md` | (this project) | Worked solution following the 6-section AICG Output Contract. |
| `STEP_BY_STEP.md` | learning `STEP_BY_STEP.md` | Solution-side build order with annotations on what each phase yields. |
| `rubric.md` | `requirements.md` | Grading rubric distilled from F1–F8 + NF requirements. |
| `registry/schema.sql` | F1, F6 | Immutable-version DDL + lineage edges + promotions + deployments. |
| `registry/openapi.yaml` | F1, F3, F4, F5, F6 | Registry API contract (register, list, promote, deploy, rollback, lineage). |
| `gates/gates.yaml` | F3 | Default promotion gates per `architecture.md` §Promotion gates. |
| `gates/evaluate.py` | F3 | Pure-function gate evaluator + state machine. |
| `signing/verify.py` | F2 | Cosign keyless verification skeleton invoked at promotion and at deployment. |
| `deployment/rollout-strategies.md` | F4, F5 | Rolling / blue-green / canary / shadow semantics + rollback sequence. |
| `lineage/queries.sql` | F6 | Recursive-CTE forward and reverse lineage traversal. |
| `multi-tenancy/policy.md` | F7 | Tenant scope enforcement + cross-tenant share contract. |
| `observability/metrics.md` | F8 | Catalog of the four required registry metrics + label conventions. |
| `observability/grafana-dashboard.json` | F8 | One Grafana dashboard JSON covering the F8 metrics + deployment timeline. |

## What's intentionally not here

- The full FastAPI registry app, full SDK, full CLI, the actual
  traffic-splitting layer (Istio/mesh manifests), and Helm
  charts. Those are the learner's deliverable. The curated
  artifacts above pin the **interfaces** that grade against the
  rubric; the implementations behind them are part of the
  ~70-hour learning exercise.
- A `Makefile` or `make up` target. The non-functional
  requirements section in the rubric is what grades the
  learner's deployable bundle.
- Production Sigstore/Fulcio/Rekor wiring. `signing/verify.py`
  shows the *verification contract*; the learner picks one
  Cosign Python binding or shells out to `cosign verify`.
- The shared audit-chain table. That artifact lives in
  [`project-01-platform-core/audit/schema.sql`](../project-01-platform-core/audit/schema.sql);
  this project depends on it but does not redefine it.

See [`SOLUTION.md`](./SOLUTION.md) for the reasoning, validation
commands, common mistakes, and references.

## Quick links

- [SOLUTION.md](./SOLUTION.md)
- [STEP_BY_STEP.md](./STEP_BY_STEP.md)
- [rubric.md](./rubric.md)
- Learning project: [`projects/project-04-model-registry`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-04-model-registry)
- Track overview: [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md)
