# Address review feedback on PR #5

## Goal

Reviewers (human or bot) left feedback that blocks auto-merge.
Address each blocker below with the smallest possible code
change. Do NOT rewrite scope and do NOT touch unrelated files.

## Blockers

### 1. Unresolved review thread (bot: @chatgpt-codex-connector) in `projects/project-01-platform-core/control-plane/openapi.yaml:168`

> **<sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub>  Require idempotency keys on mutating POSTs**

For `POST /training-runs`, this marks `Idempotency-Key` optional even though the solution text and retry-safety contract say it is required. OpenAPI-generated SDKs and validators will therefore allow callers to omit the header; a network retry of a create request without a stable key can create duplicate TrainingRuns and double-spend quota/GPU time.

Useful? React

## Output contract

- Edit only the files referenced by these blockers.
- Preserve the existing structure; don't delete sections.
- Do NOT touch CURRICULUM.md, README.md, or VERSIONS.md.
- Do NOT mark review threads resolved yourself — only the
  reviewer can do that. Your job is to push commits that
  address the underlying issue. Bot threads auto-resolve
  when their metric recovers; human threads stay open until
  the human resolves them.
