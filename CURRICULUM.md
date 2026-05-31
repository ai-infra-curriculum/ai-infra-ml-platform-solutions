# Curriculum Guide

This document defines the expected structure for `ai-infra-ml-platform-solutions`.

## Repository Type
- Track type: solutions
- Paired learning repo: `ai-infra-ml-platform-learning`
- Primary content directories: `modules/` + `projects/`

## Top-Level Layout
- `modules/`: per-module reference solutions, mirroring the learning repo's `lessons/`
- `projects/`: full reference implementations for each capstone project
- `guides/`: cross-cutting troubleshooting + implementation notes
- `resources/`: supporting references + shared assets

## Module Minimums

Each module solution directory (`modules/mod-NNN-<slug>/`) should include:
- One subdirectory per learning exercise (`exercise-NN/`)
- Each exercise directory has a `README.md` linking back to the learning exercise
- Working reference code/configs where applicable; pointer + cross-reference where the engineer-solutions track has the deeper implementation

## Structural Rules
- Module slugs MUST match the paired learning repository.
- Solutions are reference implementations; learners attempt exercises first.
- Operational reports belong in the workspace `_meta/`, not the repo root.

## Shipped (autonomous)

Auto-appended by the AICG runner. One row per verified work item. Edit the rest of the document by hand; this section is additive only.

| Date | Work ID | Scope | Title |
|---|---|---|---|
| 2026-05-27 | `fill-project-01-platform-core-solution` | `project-01-platform-core` | Author solution artifact for project-01-platform-core |
| 2026-05-29 | `fill-project-05-developer-portal-solution` | `project-05-developer-portal` | Author solution artifact for project-05-developer-portal |
| 2026-05-29 | `depth-mod-001-platform-fundamentals-exercises` | `mod-001-platform-fundamentals` | Add exercise-level depth for mod-001-platform-fundamentals |
| 2026-05-29 | `depth-mod-002-api-design-exercises` | `mod-002-api-design` | Add exercise-level depth for mod-002-api-design |
| 2026-05-30 | `nav-nav-missing-reference-curriculum-md-mod-003-multi-tenancy-resources` | `mod-003-multi-tenancy-resources` | Align CURRICULUM.md nav reference for mod-003-multi-tenancy-resources |
| 2026-05-30 | `nav-nav-missing-reference-curriculum-md-mod-004-feature-store` | `mod-004-feature-store` | Align CURRICULUM.md nav reference for mod-004-feature-store |
| 2026-05-30 | `nav-nav-missing-reference-curriculum-md-mod-005-workflow-orchestration` | `mod-005-workflow-orchestration` | Align CURRICULUM.md nav reference for mod-005-workflow-orchestration |
| 2026-05-30 | `nav-nav-missing-reference-curriculum-md-mod-006-model-management` | `mod-006-model-management` | Align CURRICULUM.md nav reference for mod-006-model-management |
| 2026-05-30 | `nav-nav-missing-reference-curriculum-md-mod-007-developer-experience` | `mod-007-developer-experience` | Align CURRICULUM.md nav reference for mod-007-developer-experience |
