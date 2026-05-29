# Solutions Index

Reference implementations for [ai-infra-ml-platform-learning](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning).
**Coverage: 100% modules (45 exercises) · 2 / 5 projects.** Last updated 2026-05-29.

## Layout
- `modules/`: per-exercise solutions (one dir per learning exercise)
- `projects/`: capstone solutions
- `guides/` / `resources/`: cross-cutting material

## Project coverage

| Project | Status |
|---|---|
| [project-04-model-registry](./projects/project-04-model-registry/) | ✅ |
| [project-05-developer-portal](./projects/project-05-developer-portal/) | ✅ |

## Module coverage

| Module | Exercises | Status |
|---|---|---|
| 001-platform-fundamentals | 5 | ✅ |
| 002-api-design | 5 | ✅ |
| 003-multi-tenancy-resources | 5 | ✅ |
| 004-feature-store | 5 | ✅ |
| 005-workflow-orchestration | 5 | ✅ |
| 006-model-management | 5 | ✅ |
| 007-developer-experience | 5 | ✅ |
| 008-observability | 5 | ✅ |
| 009-security-governance | 5 | ✅ |
| **Total** | **45** | **45/45** |

## Project coverage

| Project | Status | Notes |
|---|---|---|
| [01-platform-core](projects/project-01-platform-core/SOLUTION.md) | ✅ | TrainingRun CRD + control plane + operator + multi-tenancy + audit chain. |
| 02-feature-store | ⏳ | Pending. |
| 03-workflow-orchestration | ⏳ | Pending. |
| 04-model-registry | ⏳ | Pending. |
| [05-developer-portal](projects/project-05-developer-portal/SOLUTION.md) | ✅ | Backstage catalog + scaffolder + TechDocs + scorecards + token-exchange auth. |

## Cross-references to engineer-solutions

Many platform-engineering topics overlap engineering-track topics:

| Platform topic | Engineering deep dive |
|---|---|
| Multi-tenancy + quotas | engineer-solutions/mod-104 ex-14 |
| Cluster cost optimization | engineer-solutions/mod-104 ex-15 |
| Feature store | engineer-solutions/mod-106 ex-07 |
| Streaming features (Lambda) | engineer-solutions/mod-105 ex-11 |
| MLflow tracking + registry | engineer-solutions/mod-106 ex-02, ex-03 |
| Deployment strategies | engineer-solutions/mod-106 ex-08 |
| A/B testing | engineer-solutions/mod-106 ex-09 |
| Model governance | engineer-solutions/mod-106 ex-10 |
| Orchestration patterns | engineer-solutions/mod-106 ex-11 |
| Per-model cost | engineer-solutions/mod-106 ex-12 |
| Backfill safety | engineer-solutions/mod-105 ex-09 |
| Pipeline architecture | engineer-solutions/mod-105 ex-01 |
| SLO + burn rate | engineer-solutions/mod-108 ex-08 |
| Incident response | engineer-solutions/mod-108 ex-09 |
| Dashboards-as-code | engineer-solutions/mod-108 ex-04 |
| Secret mgmt (Vault + ESO) | engineer-solutions/mod-109 ex-07 |
| Supply chain (SLSA + cosign) | engineer-solutions/mod-103 ex-10 |
| Policy as code | engineer-solutions/mod-109 ex-08 |

## Synchronization
Module slugs MUST match the paired learning repository.
