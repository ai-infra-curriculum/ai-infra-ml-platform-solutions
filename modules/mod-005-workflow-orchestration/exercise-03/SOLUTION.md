# SOLUTION — Exercise 03: Safe Backfill Tooling

Reference for the learning exercise
`lessons/mod-005-workflow-orchestration/exercises/exercise-03-safe-backfill.md`
in the `ai-infra-ml-platform-learning` repo. Cross-exercise rationale
lives in [`../SOLUTION.md`](../SOLUTION.md).

## 1. Solution overview

"Our backfill took the cluster down" is the canonical workflow-
orchestration failure (see [`../SOLUTION.md`](../SOLUTION.md),
production failure #2). The exercise asks the engineer to build a
backfill driver with the four guard-rails that make the failure
mechanically impossible:

1. **Idempotency on the window key** — re-running the same window
   never double-writes.
2. **Bounded concurrency** — a backfill cannot saturate the
   cluster; the cap is explicit (`--max-concurrency`), not an
   emergent property of the scheduler.
3. **Dry-run first** — every invocation can print the plan without
   executing. No operator runs a backfill without reading the
   plan.
4. **Append-only audit log** — every window transition is recorded
   so a crash becomes a resumable event (`--retry-failed`), not a
   restart from scratch.

On top of those, the driver exposes three **strategies** so the
operator can match the backfill shape to the workload:

- `daily` — one window per calendar day, chronological. The
  default; correct for most feature or metric tables.
- `monthly` — one window per calendar month. Cheap for multi-year
  backfills where per-day orchestration overhead dominates.
- `reverse-daily` — one window per day, newest first. Correct when
  recent data has the highest business value and you want prod
  current before older history lands.

The runnable artifact is [`backfill.py`](backfill.py). It is
orchestrator-agnostic: the per-window `runner` is a stub that any
team can replace with an Airflow DAG trigger, a Spark submit, a
Kubernetes Job, or a direct SQL call.

A companion practitioner implementation lives in
[`engineer-solutions/mod-105 ex-09/backfill.py`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/blob/main/modules/mod-105-data-pipelines/exercise-09-backfill-strategies/backfill.py) — treat it as an
illustrative example, not an authoritative spec.

## 2. Worked implementation

### CLI surface

```
backfill.py [--strategy {daily,monthly,reverse-daily}]
            [--start YYYY-MM-DD] [--end YYYY-MM-DD]
            [--audit-log PATH] [--max-concurrency N]
            [--dry-run] [--retry-failed]
```

Every invocation ends with a one-line JSON summary of counts by
status. Exit code is `0` on clean success, `2` if any window
failed — operators can pipe the exit code into Make or CI.

### The window abstraction

```python
@dataclass(frozen=True)
class Window:
    start: date
    end: date   # half-open
    def key(self) -> str:
        return f"{self.start.isoformat()}__{self.end.isoformat()}"
```

The `key()` is what the audit log and the downstream job both key
on. The driver cannot make a non-idempotent job safe — the job
itself must UPSERT / MERGE or partition-replace on the window key.
This is the contract between driver and job and is enforced by
documentation, not code.

### Planning

```python
def plan(strategy: str, start: date, end: date) -> list[Window]:
    if strategy == "daily":        return daily_windows(start, end)
    if strategy == "monthly":      return monthly_chunks(start, end)
    if strategy == "reverse-daily":return list(reversed(daily_windows(start, end)))
```

Planning and execution are separated so `--dry-run` prints exactly
what would run.

### Executing with bounded concurrency

```python
with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
    futures = [ex.submit(_run, w) for w in windows]
    for fut in as_completed(futures):
        w, status, err = fut.result()
        audit.append(AuditRecord(w.key(), status, 1, now(), error=err))
```

The pool cap is the entire concurrency story — no sleep-based
hacks, no "queue it and hope". A 365-day backfill at
`--max-concurrency 4` consumes at most four worker slots,
regardless of how fast each window completes.

When the job it drives runs inside Airflow, the matching Airflow
knobs are `max_active_runs` on the DAG and `pool` on the task
(see the module rationale in [`../SOLUTION.md`](../SOLUTION.md)
§Ex-03). The CLI cap and the DAG-level cap belong together — set
both.

### Resumability via the audit log

Every window writes two JSONL records: a `running` transition and
a terminal (`succeeded` / `failed`) record. `--retry-failed` reads
the log and replans only windows whose **latest** record is
`failed`:

```python
def retry_failed_plan(audit: AuditLog) -> list[Window]:
    out = []
    for key, rec in audit.latest_status().items():
        if rec.status != "failed":
            continue
        start_s, end_s = key.split("__")
        out.append(Window(start=date.fromisoformat(start_s),
                          end=date.fromisoformat(end_s)))
    return sorted(out, key=lambda w: w.start)
```

The "latest" scan is the reason the log is append-only. Never
truncate it; a mid-backfill truncation hides failures.

### Dry-run

```
$ python backfill.py --strategy daily --start 2026-01-01 --end 2026-01-04 --dry-run
[dry-run] 3 windows at concurrency 4:
  - 2026-01-01__2026-01-02
  - 2026-01-02__2026-01-03
  - 2026-01-03__2026-01-04
{"succeeded": 0, "failed": 0, "skipped": 3}
```

The plan is a strict subset of what a real run would do; there is
no "dry-run only" execution path that could drift from reality.

## 3. Validation steps

All checks run without a live cluster.

1. **Static type / syntax check:**
   ```bash
   python -m py_compile backfill.py
   ```
2. **Dry-run a small window:**
   ```bash
   python backfill.py --strategy daily \
       --start 2026-01-01 --end 2026-01-05 --dry-run
   ```
   Expected: four lines of planned windows, exit code 0.
3. **End-to-end with the stub runner** (safe; `run_window` is a
   no-op):
   ```bash
   python backfill.py --strategy daily \
       --start 2026-01-01 --end 2026-01-05 \
       --audit-log /tmp/audit.jsonl
   cat /tmp/audit.jsonl
   ```
   Expected: eight records (four `running` + four `succeeded`).
4. **Simulated failure + retry.** Monkey-patch `run_window` to
   raise on a specific window in a throwaway script, run the
   driver, then:
   ```bash
   python backfill.py --retry-failed --audit-log /tmp/audit.jsonl
   ```
   Expected: only the previously-failed window reruns; exit code
   `0` if the retry succeeds.
5. **Concurrency sanity.** Point `run_window` at a stub that
   records its thread name; assert the set of active threads at
   any instant never exceeds `--max-concurrency`.
6. **Airflow-integrated check** (optional). Replace the stub
   `run_window` with an Airflow CLI call and confirm the DAG's
   `max_active_runs` and the per-task `pool` caps do not conflict
   with the driver's concurrency cap. See [Airflow's backfill
   command reference](https://airflow.apache.org/docs/apache-airflow/stable/cli-and-env-variables-ref.html#backfill).

## 4. Rubric / review checklist

| Axis | Pass | Fail |
| --- | --- | --- |
| Idempotency contract | Driver documents the window-key contract; downstream job UPSERTs / partition-replaces on the key | Documents nothing; relies on "we re-run rarely" |
| Bounded concurrency | Explicit cap flag, enforced by the executor | Launches all windows in parallel, or "sleeps" between launches |
| Dry-run | Flag prints the planned windows and exits non-destructively; plan is a strict subset of real execution | Dry-run mode runs a different code path than real execution |
| Audit log | JSONL, append-only, written on every state transition | Overwritten each run, or only on success |
| Retry-failed | Reads the audit log to recompute the plan; only failed windows re-run | Reruns everything, or requires operator to list failed windows by hand |
| Strategy coverage | At least two of {daily, monthly, reverse-daily} implemented and justified | Only one strategy; no rationale |
| CLI UX | `argparse` with `--help`; non-zero exit on failures | `sys.argv` splat; silent failures |
| Airflow guard-rails named | Memo explicitly cites `max_active_runs` and per-task `pool` | No mention; backfill runs "wherever" |

A submission passes every row to be considered complete.

## 5. Common mistakes

Carried forward from the module-level common-mistakes list
([`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see)
items 1, 2, and 4):

1. **Idempotency by convention, not mechanism.** "We just won't
   re-run it" is not a guard-rail. If the job itself INSERTs
   rather than UPSERTs, the driver cannot save you.
2. **No `max_active_runs`.** The driver caps thread concurrency
   but the orchestrator still launches as many DAG runs as the
   scheduler allows. Both caps must be set.
3. **Dry-run that is not a strict subset of real run.** A separate
   code path drifts and lies to the operator. Share the planner;
   skip only the executor.
4. **Truncating the audit log between runs.** `--retry-failed`
   becomes a lie; ops thinks the backfill succeeded because the
   last run of a tiny window did.
5. **One pool for everything.** The backfill shares a worker pool
   with production DAGs; a long backfill starves them. Reach for
   a dedicated `backfill` pool (see
   [`../exercise-05/CAPACITY_PLAN.md`](../exercise-05/CAPACITY_PLAN.md)).
6. **Unbounded fan-out.** A one-year backfill at daily grain with
   no cap generates 365 concurrent runs. Always set the cap
   before the strategy.

## 6. References

**Local**

- Module rationale — [`../SOLUTION.md`](../SOLUTION.md)
  (Ex-03 section, "Safe backfill").
- Pool-capacity planning — [`../exercise-05/CAPACITY_PLAN.md`](../exercise-05/CAPACITY_PLAN.md).
- Runnable driver — [`backfill.py`](backfill.py).

**External primary sources**

- [Apache Airflow documentation — `max_active_runs` and DAG parameters](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html).
- [Apache Airflow documentation — Pools](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/pools.html).
- [Apache Airflow CLI — `dags backfill`](https://airflow.apache.org/docs/apache-airflow/stable/cli-and-env-variables-ref.html#backfill).
- [Apache Airflow documentation — Params](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/params.html)
  (for parameterizing the DAG the driver triggers).

**Companion practitioner example (illustrative, not authoritative)**

- Engineer track — [`mod-105-data-pipelines/exercise-09-backfill-strategies/backfill.py`](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/blob/main/modules/mod-105-data-pipelines/exercise-09-backfill-strategies/backfill.py).
