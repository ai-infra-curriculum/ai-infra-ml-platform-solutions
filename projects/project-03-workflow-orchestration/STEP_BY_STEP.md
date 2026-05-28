# Project 03 — Solution Walkthrough

> Companion to [`SOLUTION.md`](SOLUTION.md). Walks through how a
> grader (or an engineer re-deriving the answer) should read the
> artifacts here against the eleven phases in the
> [learning STEP_BY_STEP](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-03-workflow-orchestration/STEP_BY_STEP.md).

## How to read this directory

Start with `SOLUTION.md` § 2 (Worked answer or implementation). Then
walk the artifacts in **dependency order** — schema first, data model
second, behaviour third. That is also the order the engine resolves
state at runtime.

| # | Read | Then ask |
|---|---|---|
| 1 | [`api/pipeline.schema.json`](api/pipeline.schema.json) | Could a malformed pipeline get past this and into the DB? |
| 2 | [`examples/nightly-recs-retrain.yaml`](examples/nightly-recs-retrain.yaml) | Does it match the schema? (Validate with `jsonschema`.) |
| 3 | [`db/schema.sql`](db/schema.sql) | Are state transitions and audit-chain inserts in one transaction? |
| 4 | [`executor/state_machine.py`](executor/state_machine.py) | What disallowed transitions exist? Are they all rejected? |
| 5 | [`executor/retry_classifier.py`](executor/retry_classifier.py) | Which classifications can a step author override? |
| 6 | [`gates/condition.py`](gates/condition.py) | What AST nodes are allowed? What is rejected? |
| 7 | [`tests/test_state_machine.py`](tests/test_state_machine.py) | Does every allowed transition succeed? Every disallowed one raise? |

## Mapping to the learning phases

Each row references the artifact that satisfies the phase's
deliverable, plus what is **out of scope here** (and where to look
instead).

### Phase 0 — Setup

Not vendored. The brief assumes local Kubernetes + PostgreSQL. The
project skeleton in the brief is mirrored by the directory layout of
this solution: `api/`, `executor/`, `gates/`, `db/`, `examples/`,
`tests/`. (`scheduler/`, `sdk/`, `cli/`, `deploy/` are not vendored
— see *not vendored* notes below.)

### Phase 1 — Pipeline parser

**Artifact**: [`api/pipeline.schema.json`](api/pipeline.schema.json)
+ [`examples/nightly-recs-retrain.yaml`](examples/nightly-recs-retrain.yaml).

The JSON Schema is the contract. The parser is a 30-line function
that loads YAML, validates against the schema, and builds a
`networkx.DiGraph` from `depends_on` edges. Cycle detection is
`networkx.is_directed_acyclic_graph(graph) or raise ValueError(...)`.
The fixture set the learner is asked to write is exactly:

- A valid pipeline (the sample).
- An invalid pipeline with a cycle.
- An invalid pipeline with a `depends_on` target that does not exist.
- An invalid pipeline that hits a JSON Schema constraint (e.g.,
  unknown top-level key, malformed retries block).

Validation command:

```sh
python -c "import json, yaml, jsonschema
schema = json.load(open('api/pipeline.schema.json'))
spec = yaml.safe_load(open('examples/nightly-recs-retrain.yaml'))
jsonschema.Draft202012Validator(schema).validate(spec)"
```

### Phase 2 — DAG state machine

**Artifacts**:
[`executor/state_machine.py`](executor/state_machine.py),
[`db/schema.sql`](db/schema.sql),
[`tests/test_state_machine.py`](tests/test_state_machine.py).

The state graph mirrors `architecture.md` § Data model. Read
`state_machine.py` top-to-bottom: enums, allowed transitions table,
`transition()` (the only function callers should use). The DB schema
adds the `audit_log` table the brief implies but does not spell out,
plus the `parent_run_id` column that makes re-run-from-step trivial.

The tests cover the transition graph exhaustively for run-level
states and spot-check step-level states.

### Phase 3 — Executor

Not vendored beyond `state_machine.py`. The executor loop is a
thirty-line function that, for each non-terminal run, reads
`step_states`, asks `state_machine.next_actionable_steps`, launches a
pod for each, and records the result. Reference snippet:

```python
def tick(run_id: UUID) -> None:
    run = db.runs.get(run_id)
    for step in next_actionable_steps(run, db):
        with db.transaction():
            transition_step(run, step, Event.STARTED, db)
            pod = k8s.create_namespaced_pod(...)
            db.step_states.set_pod_name(run.id, step.name, pod.name)
```

The Kubernetes client wrapper is reference plumbing — see
`kubernetes-client/python` docs. The interesting part of Phase 3 is
the state machine, which is in this directory.

### Phase 4 — Scheduler

Not vendored. The reference design has two entry points:

1. A Kubernetes `CronJob` that runs every minute, queries
   `pipelines WHERE schedule IS NOT NULL`, computes whether to fire
   each (using `croniter`), and `INSERT`s a new `runs` row.
2. A FastAPI endpoint `POST /v1/events` that takes `{name, payload}`,
   matches against `pipelines WHERE event_filter MATCHES name`, and
   `INSERT`s a new `runs` row.

Both produce the same table row; the executor does not care which
fired the run. That is the design point worth grading on.

### Phase 5 — Gates

**Artifact**: [`gates/condition.py`](gates/condition.py).

The condition evaluator is the **single highest-risk surface** in the
engine — it parses operator-authored strings against per-step
outputs. The reference uses an AST walker with a whitelist:
comparisons, boolean ops, arithmetic, and name lookups against a
provided context dictionary. Anything else raises
`UnsafeExpression`.

Human-approval gates are not in the evaluator — they are a state
transition (`WaitingApproval → Succeeded` via `Event.APPROVED`).
That is in `state_machine.py`.

### Phase 6 — Retry classification

**Artifact**:
[`executor/retry_classifier.py`](executor/retry_classifier.py).

The classifier consumes a pod result (exit code + optional
`reason` from the pod status) and returns one of `TRANSIENT`,
`INTERMITTENT`, `PERMANENT`. Defaults come from the table in
`architecture.md` § 4 plus the brief's "exit code 137 (OOM) →
transient" guidance. Per-step overrides are a dict on the step
definition (`step.retries.classify_overrides`).

The executor consults the policy after classification, not before:

```python
classification = classifier.classify(pod_result, step.retries.classify_overrides)
policy = retry_policy_for(step)
if classification == TRANSIENT and attempts < policy.max_attempts:
    schedule_retry_after(backoff(attempts, policy))
else:
    transition(step, Event.FAILED, db)
```

### Phase 7 — Re-run from step

Not vendored as code, but the design is encoded in the SQL schema
(`runs.parent_run_id`) and in the state machine:

1. Insert a new `runs` row with `parent_run_id = <original-run-id>`,
   `triggered_by = 'manual'`.
2. Copy `step_states` rows for steps prior to `<step>` from the
   parent run, preserving `outputs`, status `Succeeded`.
3. Insert `step_states` rows for `<step>` onward as `Pending`.
4. The executor's normal loop picks the run up — no special case.

This is the canonical "re-run is data, not control flow" pattern from
`SOLUTION.md` § 2 decision (2).

### Phase 8 — Per-tenant isolation

Not vendored. Reference:

1. The `pipelines.namespace` column is the tenant identifier.
2. API middleware reads the caller's tenant claim from the auth
   token and enforces `caller.tenant == pipeline.namespace` on every
   read/write/trigger.
3. The executor sets the step pod's Kubernetes namespace to
   `pipelines.namespace`, so RBAC + NetworkPolicy in the cluster
   give a second layer of defence.

The most common bug is enforcing tenancy only at the Kubernetes
layer — that lets a malicious caller against the API trigger
arbitrary runs even if the pod is then sandboxed. Both layers are
required.

### Phase 9 — Audit chain + observability

**Artifact**: `db/schema.sql` defines the audit-chain table with an
insert-only constraint (`REVOKE UPDATE`, `REVOKE DELETE`). The
state machine commits to `audit_log` in the same transaction as the
state change — that part is the design rule.

Prometheus + OpenTelemetry instrumentation is referenced in
`SOLUTION.md` § 4 Pillar D. The metric names follow
`architecture.md` § Observability verbatim.

### Phase 10 — Notifications

Not vendored. PagerDuty + Slack webhook clients are HTTP `POST`s
fired from a notification step at run-terminal transitions
(`Succeeded`, `Failed`). The notification step is a row in the
state machine's terminal hook, not a separate subsystem.

### Phase 11 — Testing + docs

**Artifact**: [`tests/test_state_machine.py`](tests/test_state_machine.py).

Demonstrates the test discipline the grader is looking for: every
allowed transition is asserted; every disallowed transition is
asserted to raise. The same shape extends to step-level transitions
(included) and to the gate evaluator (writers should add their own
test file `tests/test_condition.py`).

## End-to-end acceptance demo (the grader's runbook)

The brief's "When you're done" list translates to a six-step demo
the grader walks through:

1. `kubectl apply -f examples/nightly-recs-retrain.yaml` — pipeline
   accepted.
2. `smartrecs workflow run nightly-recs-retrain` — `runs` row
   inserted, executor picks it up.
3. Kill the executor pod mid-run — on restart, executor resumes from
   the persisted state. (This is what makes the state-machine /
   transaction discipline visible.)
4. Force one step to exit 137 — retry fires; failure classified
   `transient`; backoff visible in logs.
5. Approve the human gate via `POST /v1/runs/{id}/approve` — the
   run continues past `WaitingApproval`.
6. `smartrecs workflow rerun <run-id> --from train` — new run
   created with `train`/`evaluate`/`promote` re-run, `ingest` and
   `features` skipped via the parent-run outputs.

All six should leave matching entries in the `audit_log` table.

## Where to go next

- Module 05 cross-exercise rationale:
  [`mod-005/SOLUTION.md`](../../modules/mod-005-workflow-orchestration/SOLUTION.md).
- Engineering-track deep dive into ML orchestration patterns:
  [`engineer-solutions/mod-106 ex-11`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops).
- For an enterprise-scale orchestration architecture (above the
  engine — federation, fleet management, multi-cluster):
  `architect-solutions/projects/project-301-enterprise-mlops/`.
