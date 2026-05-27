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
