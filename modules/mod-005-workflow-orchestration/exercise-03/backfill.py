"""Safe backfill driver — three strategies, dry-run, retry-failed, audit log.

Design goals, in order:

1. Idempotent per window — re-running the same window must not
   double-write.
2. Bounded concurrency — a backfill must never saturate the
   cluster. Default 4 concurrent windows; cap is explicit, not
   implicit.
3. Resumable — a crashed backfill can be re-run with
   ``--retry-failed`` and only the failed windows run.
4. Auditable — every window transition is appended to the audit
   log. The log is the source of truth for ``--retry-failed``.
5. Dry-run first — ``--dry-run`` prints the plan without
   executing. No operator should run a backfill without reading
   the plan.

The driver is orchestrator-agnostic. ``run_window`` is a stub that
invokes whatever job your backfill actually runs — an Airflow DAG
trigger, a Spark submit, a Kubernetes job, etc.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Literal


Status = Literal["pending", "running", "succeeded", "failed", "skipped"]


@dataclass(frozen=True)
class Window:
    """One backfill unit. Half-open [start, end)."""
    start: date
    end: date

    def key(self) -> str:
        return f"{self.start.isoformat()}__{self.end.isoformat()}"


@dataclass
class AuditRecord:
    window_key: str
    status: Status
    attempt: int
    ts: str
    error: str | None = None


class AuditLog:
    """Append-only JSONL audit log keyed by window.

    The log is authoritative: retry-failed reads it to decide what
    to re-run. Never truncate it.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, record: AuditRecord) -> None:
        with self.path.open("a") as fh:
            fh.write(json.dumps(asdict(record)) + "\n")

    def latest_status(self) -> dict[str, AuditRecord]:
        by_key: dict[str, AuditRecord] = {}
        with self.path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = AuditRecord(**json.loads(line))
                by_key[rec.window_key] = rec
        return by_key


def daily_windows(start: date, end: date) -> list[Window]:
    """One window per calendar day, half-open."""
    if end <= start:
        raise ValueError(f"end ({end}) must be after start ({start})")
    out = []
    d = start
    while d < end:
        out.append(Window(start=d, end=d + timedelta(days=1)))
        d += timedelta(days=1)
    return out


def monthly_chunks(start: date, end: date) -> list[Window]:
    """Chunk into ~monthly windows for big backfills."""
    if end <= start:
        raise ValueError(f"end ({end}) must be after start ({start})")
    out = []
    d = start
    while d < end:
        nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
        nxt = min(nxt, end)
        out.append(Window(start=d, end=nxt))
        d = nxt
    return out


def plan(strategy: str, start: date, end: date) -> list[Window]:
    """Return the ordered plan of windows under the chosen strategy.

    - daily: one window per day, chronological.
    - monthly: one window per calendar month, chronological. Cheap
      for very long backfills where per-day overhead dominates.
    - reverse-daily: one window per day, newest first — useful when
      the latest data has the highest business value and you want
      the prod table current before older history lands.
    """
    if strategy == "daily":
        return daily_windows(start, end)
    if strategy == "monthly":
        return monthly_chunks(start, end)
    if strategy == "reverse-daily":
        return list(reversed(daily_windows(start, end)))
    raise ValueError(f"unknown strategy: {strategy}")


def run_window(w: Window) -> None:
    """Stub for the per-window job.

    Replace with the actual backfill unit — e.g. an Airflow
    ``trigger_dag`` call with ``conf={'window_start': w.start}``.
    The job itself MUST be idempotent on the window key
    (``w.key()``). The driver cannot make a non-idempotent job
    safe.
    """
    # Example: trigger an Airflow DAG with the window as conf.
    # cli: airflow dags trigger --conf '{"start":"...","end":"..."}' my_backfill
    return None


def execute(
    windows: Iterable[Window],
    *,
    audit: AuditLog,
    runner: Callable[[Window], None] = run_window,
    max_concurrency: int = 4,
    dry_run: bool = False,
) -> dict[str, int]:
    """Run the plan with bounded concurrency; return counts by status."""
    counts = {"succeeded": 0, "failed": 0, "skipped": 0}
    windows = list(windows)
    if dry_run:
        print(f"[dry-run] {len(windows)} windows at concurrency {max_concurrency}:")
        for w in windows:
            print(f"  - {w.key()}")
        counts["skipped"] = len(windows)
        return counts

    now = lambda: datetime.now(timezone.utc).isoformat()

    def _run(w: Window) -> tuple[Window, Status, str | None]:
        audit.append(AuditRecord(w.key(), "running", attempt=1, ts=now()))
        try:
            runner(w)
        except Exception as exc:  # noqa: BLE001 — audit any failure
            return w, "failed", f"{type(exc).__name__}: {exc}"
        return w, "succeeded", None

    with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
        futures = [ex.submit(_run, w) for w in windows]
        for fut in as_completed(futures):
            w, status, err = fut.result()
            audit.append(AuditRecord(w.key(), status, attempt=1, ts=now(), error=err))
            counts[status] += 1
    return counts


def retry_failed_plan(audit: AuditLog) -> list[Window]:
    """Return the subset of windows whose latest status is `failed`."""
    out = []
    for key, rec in audit.latest_status().items():
        if rec.status != "failed":
            continue
        start_s, end_s = key.split("__")
        out.append(Window(start=date.fromisoformat(start_s), end=date.fromisoformat(end_s)))
    out.sort(key=lambda w: w.start)
    return out


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Safe backfill driver")
    p.add_argument("--strategy", choices=["daily", "monthly", "reverse-daily"], default="daily")
    p.add_argument("--start", type=_parse_date)
    p.add_argument("--end", type=_parse_date)
    p.add_argument("--audit-log", type=Path, default=Path("backfill-audit.jsonl"))
    p.add_argument("--max-concurrency", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--retry-failed", action="store_true",
                   help="Re-run only windows whose latest status in the audit log is failed")
    args = p.parse_args(argv)

    audit = AuditLog(args.audit_log)

    if args.retry_failed:
        windows = retry_failed_plan(audit)
        if not windows:
            print("retry-failed: no failed windows in audit log; nothing to do.")
            return 0
    else:
        if not (args.start and args.end):
            p.error("--start and --end are required unless --retry-failed is set")
        windows = plan(args.strategy, args.start, args.end)

    counts = execute(
        windows,
        audit=audit,
        max_concurrency=args.max_concurrency,
        dry_run=args.dry_run,
    )
    print(json.dumps(counts))
    return 0 if counts["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
