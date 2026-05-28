Done. Project-03 workflow-orchestration solution is authored.

**What I created** under `projects/project-03-workflow-orchestration/`:

| File | Purpose |
|---|---|
| `SOLUTION.md` | The 6-section graded deliverable (overview, worked answer, validation, rubric, mistakes, refs) |
| `README.md` | Project-solution navigation page |
| `STEP_BY_STEP.md` | Phase-by-phase walkthrough mapped to the learning brief's 11 phases |
| `api/pipeline.schema.json` | JSON Schema 2020-12 for the Pipeline contract |
| `db/schema.sql` | PostgreSQL data model + `audit_log` (insert-only) + `parent_run_id` for re-run lineage |
| `executor/state_machine.py` | Pure-function DAG state machine with `InvalidTransition` |
| `executor/retry_classifier.py` | TRANSIENT / INTERMITTENT / PERMANENT classification with per-step overrides |
| `gates/condition.py` | AST-restricted gate evaluator (closed-world allowlist; no `eval`) |
| `examples/nightly-recs-retrain.yaml` | Sample pipeline matching the brief's example |
| `tests/test_state_machine.py` | Parametrized pytest coverage of every allowed + key disallowed transition |

**Design points the rubric grades on** (and which the artifacts encode):
- Pipelines are immutable per `(namespace, name, version)`; runs reference a specific pipeline version.
- State transitions are pure functions, persisted atomically with the audit-chain insert.
- Re-run-from-step is *data* (a new `runs` row with `parent_run_id`), not an executor branch.
- Gate evaluator never reaches Python's dynamic-code-execution function — AST allowlist rejects every unknown node.
- Retry classification is overridable per step (see `examples/...yaml`'s `train` step).

**No `<!-- needs-research -->` markers needed** — all claims are grounded in the project brief (`README.md`, `STEP_BY_STEP.md`, `architecture.md`) and public references (Argo, Kubeflow, JSON Schema 2020-12, asteval, Kubernetes pod lifecycle, OpenTelemetry).

**Validation note**: per the workspace's python-exec-blocked constraint, artifacts were reviewed statically; the grader-side validation commands (`jsonschema`, `py_compile`, `pytest`, `psql`) are listed in `SOLUTION.md` § 3 and `STEP_BY_STEP.md`.
