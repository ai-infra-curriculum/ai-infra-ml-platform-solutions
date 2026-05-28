# Address review feedback on PR #7

## Goal

Reviewers (human or bot) left feedback that blocks auto-merge.
Address each blocker below with the smallest possible code
change. Do NOT rewrite scope and do NOT touch unrelated files.

## Blockers

### 1. Unresolved review thread (bot: @chatgpt-codex-connector) in `projects/project-03-workflow-orchestration/db/schema.sql:102`

> **<sub><sub>![P1 Badge](https://img.shields.io/badge/P1-orange?style=flat)</sub></sub>  Grant sequence usage for audit inserts**

When the engine uses the dedicated `orchestrator` role described here, `INSERT INTO audit_log (...)` without an explicit `id` will still call the `audit_log_id_seq` created by `BIGSERIAL`; table-level `INSERT` does not grant `USAGE` on that sequence. Because the design writes `audit_log` in the same transaction as every state transition, this permission gap makes thos

## Output contract

- Edit only the files referenced by these blockers.
- Preserve the existing structure; don't delete sections.
- Do NOT touch CURRICULUM.md, README.md, or VERSIONS.md.
- Do NOT mark review threads resolved yourself — only the
  reviewer can do that. Your job is to push commits that
  address the underlying issue. Bot threads auto-resolve
  when their metric recovers; human threads stay open until
  the human resolves them.
