# Project 05 — ML Platform Developer Portal (Solution)

Reference solution for [project-05-developer-portal](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-05-developer-portal)
in the paired learning repository.

This directory is **a curated reference, not a full deployable
Backstage instance**. Every artifact is statically valid
(validates with `yamllint`, `openapi-spec-validator`,
`markdownlint`, or — for the scaffolder template — the upstream
Backstage Software Template JSON Schema) and is sized to make
the design rationale clear, not to be `yarn dev`-able on its own.

## What's here

| Path | Maps to | Purpose |
|---|---|---|
| `SOLUTION.md` | (this project) | Worked solution following the 6-section AICG Output Contract. |
| `STEP_BY_STEP.md` | learning `STEP_BY_STEP.md` | Solution-side build order with annotations on what each phase yields. |
| `rubric.md` | `requirements.md` | Grading rubric distilled from F1–F8 + NF requirements. |
| `catalog/catalog-info.yaml` | F1 | Worked entity descriptors for `Component`, `API`, `Group`, `System`, and the custom `MLModel`. |
| `catalog/entity-kinds.md` | F1, F6 | The two custom entity kinds (`MLModel`, `Dataset`) and how they relate to Backstage's standard kinds. |
| `catalog/processors.md` | F1 | Ingestion design — static descriptors + API-driven entity providers + tombstoning. |
| `scaffolder/templates.md` | F2 | The three golden paths the portal ships and what each delivers. |
| `scaffolder/training-run-template.yaml` | F2 | Canonical Software Template for the "new training run" golden path. |
| `techdocs/architecture.md` | F3 | Docs-as-code pipeline: catalog entity → MkDocs build → CDN → portal reader. |
| `techdocs/mkdocs.example.yml` | F3 | The MkDocs config every catalog entity inherits, with `techdocs-core` wired. |
| `scorecards/scorecards.md` | F4 | The three default scorecards (Platform Baseline, Production Readiness, Compliance). |
| `scorecards/scorecard-definitions.yaml` | F4 | Each check as a rule with a query, threshold, and remediation link. |
| `auth/identity.md` | F5 | OIDC sign-in + OAuth 2.0 Token Exchange (RFC 8693) for downstream calls. |
| `plugins/plugin-architecture.md` | F6 | Frontend / backend plugin split + proxying + per-component plugins. |
| `observability/adoption-metrics.md` | F7, F8 | Operator-facing Prometheus metrics + product-facing adoption KPIs. |

## What's intentionally not here

- A runnable Backstage instance (`packages/app`, `packages/backend`,
  Yarn workspaces). Those are the learner's deliverable. The
  curated artifacts above pin the **interfaces** that grade
  against the rubric; the implementations behind them are the
  learning exercise.
- Helm charts and `kind` cluster bootstrap for the portal. The
  non-functional requirements section in the rubric is what
  grades the learner's deployable bundle.
- Real OIDC provider configuration. `auth/identity.md` shows the
  *flow* and the claim shapes; the learner picks Okta, Auth0,
  Keycloak, Dex, or Cognito.
- Production CDN wiring for TechDocs HTML. `techdocs/architecture.md`
  shows the contract; the learner picks S3 + CloudFront, GCS,
  Azure Blob, or a self-hosted alternative.
- The platform-component plugins (`@ml-platform/plugin-training-runs`,
  `@ml-platform/plugin-model-registry`, …). `plugins/plugin-architecture.md`
  pins the boundaries; building each plugin is the work.

See [`SOLUTION.md`](./SOLUTION.md) for the reasoning, validation
commands, common mistakes, and references.

## Quick links

- [SOLUTION.md](./SOLUTION.md)
- [STEP_BY_STEP.md](./STEP_BY_STEP.md)
- [rubric.md](./rubric.md)
- Learning project: [`projects/project-05-developer-portal`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-05-developer-portal)
- Track overview: [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md)
