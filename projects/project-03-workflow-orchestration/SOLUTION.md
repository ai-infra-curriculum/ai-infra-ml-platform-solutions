# SOLUTION — Project 03: ML Workflow Orchestration Engine

> Capstone solution for `ml-platform/projects/project-03-workflow-orchestration`.
> Read the [project README](../../../ai-infra-ml-platform-learning/projects/project-03-workflow-orchestration/README.md)
> and [`architecture.md`](../../../ai-infra-ml-platform-learning/projects/project-03-workflow-orchestration/architecture.md)
> first; this file is the reference answer, not a re-statement of the brief.

## 1. Solution overview

This project asks the engineer to build an **engine**, not an Airflow
wrapper. The four production failure classes that define correctness:

| Failure | Engine responsibility |
|---|---|
| Transient infra fault | Classify, retry with bounded backoff |
| Permanent code/config fault | Stop the DAG, fire the right alert |
| Partial success | Decide which downstream steps still run; preserve outputs |
| Operator wants to re-run from step N | Clone the run, preserve prior outputs, resume |

The reference design (mirrors `architecture.md`):

- **Pipeline** = immutable, versioned YAML (`apiVersion: workflows.smartrecs.io/v1`).
- **Run** = mutable execution of a Pipeline version with one row per step in `step_states`.
- **DAG state machine** is a set of pure transition functions (`transition(state, event) -> state`).
  Every transition is persisted in a DB transaction together with an
  audit-chain insert — atomic, restart-safe.
- **Executor** is *idempotent*: every iteration re-derives the next
  actionable step from DB state, so a process crash mid-iteration is
  recoverable.
- **Gate conditions** are evaluated against step outputs through an
  **AST-restricted evaluator** (e.g.,
  [`asteval`](https://lmfit.github.io/asteval/) or
  [`simpleeval`](https://pypi.org/project/simpleeval/)). Never
  Python's built-in dynamic-code-execution function — that is an
  arbitrary-code-execution vector.
- **Scheduler** is two endpoints into the same `runs` table:
  Kubernetes `CronJob` for `spec.schedule`, FastAPI `POST /v1/events`
  for triggered runs.

Curated artifacts in this directory illustrate the load-bearing parts
of that design. They are not a fork of Argo Workflows or Kubeflow
Pipelines — both are linked in the learning brief for inspiration but
the capstone is the *engine itself*.

### Higher-order primitive

`Pipeline` and `Run` are what users see. They never write a `Pod`
spec, never read Kubernetes events, never reason about exit code 137.
That is the platform's job. The artifacts in `api/`, `executor/`, and
`gates/` are how that contract is upheld.

## 2. Worked answer or implementation

The repository under [`projects/project-03-workflow-orchestration/`](.)
is organised by the major subsystems from `architecture.md`:

| Path | Maps to | Validates |
|---|---|---|
| [`api/pipeline.schema.json`](api/pipeline.schema.json) | Phase 1 — Pipeline parser | JSON Schema 2020-12; parser uses this to reject bad YAML before any DB write |
| [`db/schema.sql`](db/schema.sql) | `architecture.md` § Data model + Phase 2 | Extends the brief with the audit-chain table and the `runs.parent_run_id` re-run linkage |
| [`executor/state_machine.py`](executor/state_machine.py) | Phase 2 — DAG state machine | Pure transition functions; every disallowed transition raises `InvalidTransition` |
| [`executor/retry_classifier.py`](executor/retry_classifier.py) | Phase 6 — Retry classification | Maps pod exit conditions to `transient` / `intermittent` / `permanent` (per `architecture.md` § 4) |
| [`gates/condition.py`](gates/condition.py) | Phase 5 — Gates (programmatic) | AST-restricted evaluator; the unsafe `eval` path is **not** an option |
| [`examples/nightly-recs-retrain.yaml`](examples/nightly-recs-retrain.yaml) | Project README § 3 — sample pipeline | Matches the README's example verbatim plus an explicit `retries.per_step` block |
| [`tests/test_state_machine.py`](tests/test_state_machine.py) | Phase 2 acceptance | Every allowed transition succeeds; every disallowed transition raises |

The remaining phases (scheduler loop, pod runner, notifications,
observability dashboards) are **not** vendored here. Three reasons:

1. The brief asks for a 75-hour build — vendoring all of it would
   create a parallel codebase that drifts from the learning repo.
2. The graded "engine correctness" question is dominated by the
   parser, the state machine, the retry classifier, and the gate
   evaluator. Those are exactly what learners get wrong, and exactly
   what is here.
3. The scheduler is a `CronJob` + an HTTP endpoint, and the executor
   pod runner is a Kubernetes API client. Neither has interesting
   design tension once the state machine is correct, and both have
   well-trodden references (`kubernetes-client/python`, FastAPI).

[`STEP_BY_STEP.md`](STEP_BY_STEP.md) walks an evaluator through how
the artifacts here compose into the full engine.

### How the pieces compose at runtime

```
Scheduler / events → INSERT into runs (Pending)
                          │
                          ▼
Executor loop ──► state_machine.next_actionable_steps(run_id)
       │                  │
       │                  ├─► gates/condition.evaluate(step.outputs) ──► pass/fail/wait
       │                  │
       │                  ▼
       └──► launch step pod ──► watch ──► retry_classifier.classify(pod_result)
                                              │
                                              ▼
                                  state_machine.transition(state, event)
                                              │
                                              ▼
                                  DB txn: UPDATE step_states + INSERT audit_log
```

Everything between "executor loop" and the DB transaction is *one*
atomic unit per step. That is what makes the engine restart-safe:
crash anywhere in the loop and the next iteration re-derives the same
work.

### Decisions worth defending in code review

1. **State machine as pure functions.** `transition(state, event)`
   has no I/O. All I/O (DB write, audit insert, pod create) happens
   in a thin shell around it. This keeps the state graph testable
   without a database and is the single biggest factor in being able
   to ship the engine in 75 hours.
2. **Re-run from step is data, not control flow.** A re-run is a new
   `runs` row with `parent_run_id` set, with prior step states copied
   in and `<step>` onward set to `Pending`. The executor's normal loop
   does the rest. No special "re-run mode" in the executor.
3. **Retry classification is per-step-overridable.** The default
   table (`retry_classifier.DEFAULT_CLASSIFICATION`) handles 90% of
   cases; a step author can override via
   `step.retries.classify_overrides`. This is the only way a
   platform team scales support — if every step needs to file a
   ticket to add a classification rule, the platform team becomes
   the bottleneck.
4. **Gate evaluator is a whitelist of operators, not a sandbox.**
   The AST walker rejects every node type it does not recognise.
   That's a closed-world policy: future Python syntax additions
   (walrus, structural pattern matching) are *rejected by default*
   until explicitly added.

## 3. Validation steps

The validation tools required (PostgreSQL, `kubectl`, the Python
runtime, `asteval`) are not assumed to be installed in this
workspace. Graders run these commands locally; each is listed with
the exact tool it requires.

| What to check | How |
|---|---|
| JSON Schema is valid 2020-12 | `python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('api/pipeline.schema.json')))"` |
| Sample pipeline matches the schema | `python -c "import json, yaml, jsonschema; jsonschema.validate(yaml.safe_load(open('examples/nightly-recs-retrain.yaml')), json.load(open('api/pipeline.schema.json')))"` |
| Python modules are syntactically valid | `python -m py_compile executor/state_machine.py executor/retry_classifier.py gates/condition.py tests/test_state_machine.py` |
| State machine semantics | `pytest tests/test_state_machine.py -v` |
| SQL parses (no execution) | `psql -X -f db/schema.sql --single-transaction --set ON_ERROR_STOP=1 -d template1` (or `pgsanity db/schema.sql`) |
| Pod-spec semantics for the executor's launch path | not vendored; the executor calls `kubernetes.client.CoreV1Api.create_namespaced_pod` — verify with `kubectl --dry-run=server` against any generated spec |

The "Phase 11 — Testing + docs" acceptance demo in
[`STEP_BY_STEP.md`](STEP_BY_STEP.md) lists the end-to-end demo flow.

> Note: this workspace cannot execute `python3` for static
> validation; the artifacts have been reviewed by Read. See
> [`STEP_BY_STEP.md`](STEP_BY_STEP.md) for the grader-side toolchain.

## 4. Rubric / review checklist

Score each of the four pillars 0/1/2 (missing / present / correct).
A passing capstone scores ≥ 1 on every pillar **and** ≥ 6/8 total.

### Pillar A — Pipeline contract (parser + schema)

- [ ] JSON Schema rejects pipelines with cycles before any DB write.
- [ ] JSON Schema rejects unknown `depends_on` targets.
- [ ] `Pipeline` is immutable per (namespace, name, version); a
      second `apply` of the same version is a no-op, not an
      overwrite.
- [ ] Pipeline version is stored on the `Run`, not looked up at
      execution time — yesterday's run replays yesterday's spec.

### Pillar B — DAG state machine

- [ ] States are explicitly enumerated (`Pending`, `Running`,
      `Succeeded`, `Failed`, `Cancelled`, `WaitingApproval`,
      `Skipped`).
- [ ] Transitions are pure functions; tests do not require a DB.
- [ ] Every disallowed transition raises a typed error
      (`InvalidTransition`) — not a silent no-op.
- [ ] Each transition is persisted **in the same DB transaction** as
      the audit-chain insert.

### Pillar C — Retry + gates

- [ ] Failures are classified into transient / intermittent /
      permanent (`architecture.md` § 4) before retry policy is
      consulted.
- [ ] Per-step classification overrides exist and are honoured.
- [ ] Transient retries use bounded exponential backoff with a
      configurable cap — not a tight loop.
- [ ] Gate evaluator uses an AST-restricted parser. Grep the
      submission for `eval(` / `exec(` / `compile(` — any hit is an
      automatic fail.
- [ ] Human-approval gates pause the run; approval is recorded with
      an approver identity and emits an audit-chain entry.

### Pillar D — Operability

- [ ] Re-run from step is implemented as a new `runs` row with
      `parent_run_id` set; the executor's normal loop drives it.
      No special "re-run mode" branch in the executor.
- [ ] Per-tenant isolation: an API caller in tenant A cannot
      trigger or read runs of a pipeline in tenant B (enforced in
      the API layer, not relied on at the Kubernetes layer alone).
- [ ] Metrics from `architecture.md` § Observability are emitted on
      every transition: `workflow_step_duration_seconds`,
      `workflow_step_retry_total`, `workflow_gate_evaluation_total`,
      `workflow_run_duration_seconds`.

## 5. Common mistakes

The five mistakes that fail capstone reviews most often:

1. **`eval()` in the gate evaluator.** "It's only used by trusted
   pipeline authors" is not a defense — pipeline authors *are* the
   threat model for an arbitrary-code-execution surface. Use an
   AST-restricted library and reject every unknown node.
2. **Non-atomic state transitions.** Writing `step_states` first and
   then the audit-chain entry "in a second" creates a window where a
   crash loses the audit trail. Wrap both in a single transaction.
3. **Retry classification baked into the executor.** When the
   classifier is a method on the executor, a new failure mode means
   editing the engine. Make it a small standalone module with a
   declarative default table that can be overridden per step.
4. **Re-run from step implemented as a control-flow branch in the
   executor.** Looks like a small change; in practice doubles the
   number of code paths the executor must keep correct. Re-run is
   data: a new `runs` row with prior steps cloned, executor
   unchanged.
5. **Forgetting `parent_run_id` in lineage.** Re-runs that drop the
   pointer to the original run silently break "what produced model
   X" forever. The audit-chain table cannot reconstruct it after the
   fact.

A subtler one specific to schedulers:

6. **Cron triggering at "0 2 * * *" for every pipeline.** Without
   jitter, every tenant's nightly run lands at 02:00 UTC, the
   scheduler queue spikes, and pool capacity is undersized for the
   peak. Stagger via a per-pipeline jitter applied at insert into
   `runs`, not at definition time.

## 6. References

Official / project sources (used to ground the design):

- **Argo Workflows** — DAG semantics, retry strategies, suspend
  steps. <https://argoproj.github.io/argo-workflows/>
- **Kubeflow Pipelines** — pipeline versioning + run lineage.
  <https://www.kubeflow.org/docs/components/pipelines/>
- **Kubernetes API** — pod lifecycle, exit codes, eviction
  semantics that drive `retry_classifier`.
  <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/>
- **JSON Schema 2020-12** — Pipeline definition validation.
  <https://json-schema.org/draft/2020-12>
- **OpenTelemetry tracing concepts** — parent/child span model used
  for run/step tracing.
  <https://opentelemetry.io/docs/concepts/signals/traces/>
- **`asteval` documentation** — the AST-restricted evaluator
  recommended for gate conditions.
  <https://lmfit.github.io/asteval/>

Local exercise context (the brief itself — *not* third-party
claims):

- [`project-03 README`](../../../ai-infra-ml-platform-learning/projects/project-03-workflow-orchestration/README.md)
  — declarative pipeline format, in/out of scope.
- [`project-03 STEP_BY_STEP`](../../../ai-infra-ml-platform-learning/projects/project-03-workflow-orchestration/STEP_BY_STEP.md)
  — the eleven implementation phases.
- [`project-03 architecture.md`](../../../ai-infra-ml-platform-learning/projects/project-03-workflow-orchestration/architecture.md)
  — data model and retry semantics referenced throughout this
  document.
- [`mod-005 SOLUTION.md`](../../modules/mod-005-workflow-orchestration/SOLUTION.md)
  — module-level rationale (orchestrator selection, pool tuning).

Cross-track companions:

- [`engineer-solutions/mod-105 ex-01`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-105-data-pipelines)
  — pipeline architecture deep dive.
- [`engineer-solutions/mod-106 ex-11`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops)
  — ML orchestration patterns.
