# Project 03 Solution — ML Workflow Orchestration Engine

Reference solution for
[`ml-platform-learning/projects/project-03-workflow-orchestration`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-03-workflow-orchestration).

| Document | Purpose |
|---|---|
| [`SOLUTION.md`](SOLUTION.md) | Design rationale + 6-section graded answer (rubric, mistakes, refs) |
| [`STEP_BY_STEP.md`](STEP_BY_STEP.md) | Phase-by-phase walkthrough mapped to the learning brief |

## Curated artifacts

The capstone is a 75-hour build. The artifacts here are not a full
implementation; they are the load-bearing pieces — the ones evaluators
read first, and the ones learners get wrong most often.

| Artifact | Maps to |
|---|---|
| [`api/pipeline.schema.json`](api/pipeline.schema.json) | Phase 1 — Pipeline parser (JSON Schema 2020-12) |
| [`db/schema.sql`](db/schema.sql) | Data model + audit chain + re-run lineage |
| [`executor/state_machine.py`](executor/state_machine.py) | Phase 2 — DAG state machine (pure transitions) |
| [`executor/retry_classifier.py`](executor/retry_classifier.py) | Phase 6 — Retry classification |
| [`gates/condition.py`](gates/condition.py) | Phase 5 — Safe gate-condition evaluator |
| [`examples/nightly-recs-retrain.yaml`](examples/nightly-recs-retrain.yaml) | Sample pipeline from the project README |
| [`tests/test_state_machine.py`](tests/test_state_machine.py) | Acceptance for the state machine |

## What is **not** vendored

- Scheduler loop (a `CronJob` and a `POST /v1/events` handler — both
  trivial once the run table is correctly modelled).
- Kubernetes pod runner (a thin wrapper over `kubernetes-client/python`).
- Notification clients (PagerDuty + Slack webhook calls).
- Grafana dashboards (covered by `mod-008-observability`).
- A web UI (explicitly out of scope per the project brief).

These are linked at the right place in `STEP_BY_STEP.md`.

## Companion module

The orchestrator-selection memo, four-pattern catalog, backfill
safety, SLA + alerting, and pool tuning are all covered in
[`mod-005-workflow-orchestration`](../../modules/mod-005-workflow-orchestration/SOLUTION.md).
This capstone is the *engine* that those patterns run on.
