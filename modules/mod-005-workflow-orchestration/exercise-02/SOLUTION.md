# SOLUTION — Exercise 02: Implement All Four Orchestration Patterns

Reference for the learning exercise
`lessons/mod-005-workflow-orchestration/exercises/exercise-02-implement-four-patterns.md`
in the `ai-infra-ml-platform-learning` repo. Cross-exercise rationale
lives in [`../SOLUTION.md`](../SOLUTION.md).

## 1. Solution overview

The exercise asks the engineer to implement the same training
workflow four different ways and reason about **when each pattern is
the right choice**. The four patterns are not alternatives to pick
between on a whim — they are the four shapes production ML teams
end up using, and each is correct in its own regime.

| # | Pattern | When it is right | When it goes wrong |
| --- | --- | --- | --- |
| 1 | DAG-per-model | Small N, bespoke logic per model | N > ~15 — copy-paste rot |
| 2 | Parametric DAG (factory) | Dozens of similar models | Per-model exceptions sneak into the factory |
| 3 | Event-driven | Freshness SLA tighter than any cron grain | "Event storm" from a bursty producer |
| 4 | Continuous training | Drift-sensitive models | Promoting a worse model because the gate is wrong |

The deliverable is four working Airflow 2.x DAG files that each
implement the pattern in its most defensible form, plus a short
decision memo (this document) explaining which pattern to reach for
when. The code lives beside this file:

- Pattern 1 — [`pattern_1_dag_per_model.py`](pattern_1_dag_per_model.py)
- Pattern 2 — [`pattern_2_parametric_dag.py`](pattern_2_parametric_dag.py) + [`models.yaml`](models.yaml)
- Pattern 3 — [`pattern_3_event_driven.py`](pattern_3_event_driven.py)
- Pattern 4 — [`pattern_4_continuous_training.py`](pattern_4_continuous_training.py)

A companion worked example in the engineer-track repo
([`mod-106 ex-11`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops/exercise-11-ml-orchestration-patterns))
demonstrates the same four patterns with additional task bodies;
treat it as an illustrative practitioner implementation, not an
authoritative specification.

## 2. Worked implementation

The four files are deliberately parallel so a reader can diff them
against each other. Shared conventions:

- Airflow 2.x TaskFlow API (`@dag`, `@task`) — one function per
  task, data flow is explicit through Python arguments.
- `retries=2`, `retry_delay=5min`, `sla=2-3h` on every DAG.
- `catchup=False` to avoid the backfill-on-deploy foot-gun covered
  in Ex-03.
- A quality gate after evaluation; low accuracy raises and the
  model is **not** registered.

### Pattern 1 — DAG-per-model

```python
@dag(dag_id="train_iris_rf", schedule="0 3 * * *", ...)
def train_iris_rf():
    @task
    def extract(): ...
    @task
    def train(uri): ...
    @task
    def evaluate(model_uri): ...
    @task
    def register(result):
        if result["accuracy"] < 0.90:
            raise ValueError(...)
    register(evaluate(train(extract())))
```

**Decision rationale.** Everything about the model is in one file.
You can grep, diff, and roll back per model. The pattern is
correct until the number of files becomes a maintenance burden —
roughly when you have more than a dozen near-identical DAGs.

### Pattern 2 — Parametric DAG (dynamic generation)

The catalog is a YAML file; each row produces a DAG at parse time.

```python
with CONFIG_PATH.open() as fh:
    _catalog = yaml.safe_load(fh)

for _cfg in _catalog["models"]:
    globals()[f"dag_{_cfg['name']}"] = _build_dag(_cfg)
```

**Decision rationale.** Onboarding a new model is a config change,
not a code review of a new file. The guard-rail that keeps this
pattern safe is **parse-time** generation, not runtime: the
scheduler needs the DAG set to be stable and cheap to materialize.
Reading from a slow or external source at parse time degrades the
scheduler — Airflow's documentation explicitly warns against it.

### Pattern 3 — Event-driven

Two valid wirings in Airflow 2.x; the file shows both.

- **Deferrable sensor** (`S3KeySensor(deferrable=True, ...)`) for
  cross-system triggers — the trigger lives in object storage.
- **Datasets** (`schedule=[Dataset("s3://...")]`) when the producer
  is another Airflow DAG — Airflow tracks the dependency natively,
  no sensor needed.

**Decision rationale.** Reach for a dataset trigger first (first-
party, cheapest, no polling). Reach for a deferrable sensor when
the producer is outside Airflow. Avoid non-deferrable sensors —
they occupy a worker slot while they poll.

### Pattern 4 — Continuous training

Scheduled retrain, but **promote only if challenger beats
champion**:

```python
@task
def compare_and_gate(challenger, champion):
    min_delta = 0.002
    if challenger["accuracy"] - champion["accuracy"] < min_delta:
        raise AirflowSkipException(...)
    return challenger
```

**Decision rationale.** The gate is what separates "continuous
training" from "a cron job that trains." Without it, a drift in
the training data silently degrades production. The gate must
check a holdout the challenger has not seen; identical-data
"improvement" is a bug, not a signal.

## 3. Validation steps

All four files are statically valid Airflow DAGs. Validation runs
without a live cluster:

1. **Import check.** Each file must import without raising:
   ```bash
   python -c "import pattern_1_dag_per_model"
   python -c "import pattern_2_parametric_dag"
   python -c "import pattern_3_event_driven"
   python -c "import pattern_4_continuous_training"
   ```
   Requires `apache-airflow>=2.7` and the AWS provider for
   pattern 3. If the environment does not have Airflow installed,
   the parse check still catches top-level syntax errors; use a
   constraints-pinned install (see [Airflow's installation guide](https://airflow.apache.org/docs/apache-airflow/stable/installation/installing-from-pypi.html))
   to add the runtime pieces.
2. **DAG parse under Airflow.** With `AIRFLOW_HOME` set, drop the
   four files into `dags/` and run `airflow dags list`. All five
   DAG IDs appear (pattern 3 contributes two). Any file whose
   parse exceeds ~30s is rejected — a slow parse is a scheduler
   regression. See [Airflow's dynamic-DAG guidance](https://airflow.apache.org/docs/apache-airflow/stable/howto/dynamic-dag-generation.html).
3. **Static graph check.** Each DAG renders a DAG shape that
   matches its pattern — no cycles, no orphan tasks. Run
   `airflow dags show <dag_id>` and confirm visually.
4. **Quality-gate behaviour.** Patterns 1, 2, and 4 each include a
   gate that raises on a bad metric. Lower the gate value in a
   local run and confirm the DAG fails there, not later.

## 4. Rubric / review checklist

| Axis | Pass | Fail |
| --- | --- | --- |
| Coverage | All four patterns implemented | Any pattern missing or stubbed |
| DAG parse | Every file parses under Airflow 2.x | Import error, syntax error, or unbounded parse time |
| TaskFlow discipline | Uses `@dag`/`@task`; data flow via arguments, not XCom pulls | Hand-written XCom pulls, string-concat DAG IDs |
| `catchup=False` | All four DAGs | Any DAG left on the default `catchup=True` |
| Quality gate | Pattern 4 blocks promotion if challenger is not better by a stated margin | No gate, or gate compares on training data |
| Dataset / sensor choice | Pattern 3 uses deferrable sensor OR dataset — justified in the memo | Non-deferrable sensor with a long timeout |
| Decision memo | Explicit "use pattern X when …" paragraph per pattern | Only code, no rationale |
| Parse-time safety | Pattern 2's generator reads config from a committed file; no network I/O | Reads a DB or API at parse time |

A submission passes every row to be considered complete.

## 5. Common mistakes

Carried forward from the module-level common-mistakes list
([`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see)):

1. **Non-deferrable sensors.** A classical `S3KeySensor` holds a
   worker slot for hours. The deferrable variant releases the slot
   to the triggerer. Airflow's sensor docs flag this as the default
   advice.
2. **Parametric DAG that reads from a DB at parse time.** Every
   scheduler heartbeat re-imports the file; a slow source degrades
   the whole deployment. Keep the catalog in a committed file.
3. **Continuous training without a champion comparison.** The DAG
   retrains and promotes every day whether the model improved or
   not. Any regression lands in production silently.
4. **`catchup=True` left on the default.** The first deploy
   silently kicks off months of runs. Set `catchup=False`
   explicitly on every DAG.
5. **Dynamic task generation against an unbounded source.** DAG
   gets too large to render, scheduler degrades — repeated from
   the module-level list.
6. **One pattern treated as universal.** Submissions that implement
   four flavors of Pattern 1 and label them as "the four patterns"
   are rejected — the exercise is about shape diversity.

## 6. References

**Local**

- Module rationale — [`../SOLUTION.md`](../SOLUTION.md)
  (Ex-02 section, "Four orchestration patterns").
- Sibling implementation style — [`../exercise-04/dag_with_sla.py`](../exercise-04/dag_with_sla.py).
- Pattern artifacts — [`pattern_1_dag_per_model.py`](pattern_1_dag_per_model.py),
  [`pattern_2_parametric_dag.py`](pattern_2_parametric_dag.py),
  [`models.yaml`](models.yaml),
  [`pattern_3_event_driven.py`](pattern_3_event_driven.py),
  [`pattern_4_continuous_training.py`](pattern_4_continuous_training.py).

**External primary sources**

- [Apache Airflow documentation — TaskFlow API](https://airflow.apache.org/docs/apache-airflow/stable/tutorial/taskflow.html).
- [Apache Airflow documentation — Dynamic DAG generation](https://airflow.apache.org/docs/apache-airflow/stable/howto/dynamic-dag-generation.html).
- [Apache Airflow documentation — Data-aware scheduling (Datasets)](https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/datasets.html).
- [Apache Airflow documentation — Deferrable operators & sensors](https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/deferring.html).
- [Apache Airflow provider — `S3KeySensor`](https://airflow.apache.org/docs/apache-airflow-providers-amazon/stable/sensors/s3.html).

**Companion practitioner example (illustrative, not authoritative)**

- Engineer track — [`mod-106-mlops/exercise-11-ml-orchestration-patterns`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops/exercise-11-ml-orchestration-patterns).
