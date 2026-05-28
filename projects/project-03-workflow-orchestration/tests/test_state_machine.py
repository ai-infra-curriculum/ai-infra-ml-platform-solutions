"""Acceptance tests for the DAG state machine.

These tests demonstrate the discipline asked for in
`STEP_BY_STEP.md` Phase 2: every allowed transition succeeds, every
disallowed transition raises.

Run with: pytest tests/test_state_machine.py -v

Static syntax check: python -m py_compile tests/test_state_machine.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the sibling executor/ package importable without packaging
# overhead (the project skeleton from the brief does not have a
# top-level package). Adjust if the engine is later packaged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from executor.state_machine import (  # noqa: E402
    Event,
    InvalidTransition,
    RunState,
    StepState,
    is_terminal_run,
    is_terminal_step,
    next_actionable_steps,
    transition_run,
    transition_step,
)


# ---------------------------------------------------------------------------
# Run-level transitions
# ---------------------------------------------------------------------------

ALLOWED_RUN_TRANSITIONS = [
    (RunState.PENDING, Event.STARTED, RunState.RUNNING),
    (RunState.PENDING, Event.CANCELLED, RunState.CANCELLED),
    (RunState.RUNNING, Event.ALL_STEPS_DONE, RunState.SUCCEEDED),
    (RunState.RUNNING, Event.ANY_STEP_FAILED, RunState.FAILED),
    (RunState.RUNNING, Event.CANCELLED, RunState.CANCELLED),
]


@pytest.mark.parametrize("frm,event,to", ALLOWED_RUN_TRANSITIONS)
def test_run_transition_allowed(frm: RunState, event: Event, to: RunState) -> None:
    assert transition_run(frm, event) is to


@pytest.mark.parametrize(
    "frm,event",
    [
        # Cannot start a Succeeded / Failed / Cancelled run.
        (RunState.SUCCEEDED, Event.STARTED),
        (RunState.FAILED, Event.STARTED),
        (RunState.CANCELLED, Event.STARTED),
        # Cannot finish a run that has not been started.
        (RunState.PENDING, Event.ALL_STEPS_DONE),
        (RunState.PENDING, Event.ANY_STEP_FAILED),
        # Cannot re-finish a terminal run (idempotency at the API
        # layer means a duplicate event reaches the state machine
        # only if a bug let it through - we want that to raise).
        (RunState.SUCCEEDED, Event.ALL_STEPS_DONE),
        (RunState.FAILED, Event.ANY_STEP_FAILED),
        (RunState.CANCELLED, Event.CANCELLED),
    ],
)
def test_run_transition_disallowed(frm: RunState, event: Event) -> None:
    with pytest.raises(InvalidTransition):
        transition_run(frm, event)


def test_terminal_run_states() -> None:
    assert is_terminal_run(RunState.SUCCEEDED)
    assert is_terminal_run(RunState.FAILED)
    assert is_terminal_run(RunState.CANCELLED)
    assert not is_terminal_run(RunState.PENDING)
    assert not is_terminal_run(RunState.RUNNING)


# ---------------------------------------------------------------------------
# Step-level transitions
# ---------------------------------------------------------------------------

ALLOWED_STEP_TRANSITIONS = [
    (StepState.PENDING, Event.STARTED, StepState.RUNNING),
    (StepState.PENDING, Event.SKIPPED, StepState.SKIPPED),
    (StepState.PENDING, Event.GATE_WAIT, StepState.WAITING_APPROVAL),
    (StepState.PENDING, Event.CANCELLED, StepState.FAILED),
    (StepState.RUNNING, Event.SUCCEEDED, StepState.SUCCEEDED),
    (StepState.RUNNING, Event.FAILED, StepState.FAILED),
    # Retry path: Failed -> Pending re-arms the step for the next
    # attempt. This is the design point asked about in Phase 6.
    (StepState.FAILED, Event.STARTED, StepState.PENDING),
    (StepState.WAITING_APPROVAL, Event.APPROVED, StepState.PENDING),
    (StepState.WAITING_APPROVAL, Event.REJECTED, StepState.FAILED),
    (StepState.WAITING_APPROVAL, Event.CANCELLED, StepState.FAILED),
]


@pytest.mark.parametrize("frm,event,to", ALLOWED_STEP_TRANSITIONS)
def test_step_transition_allowed(frm: StepState, event: Event, to: StepState) -> None:
    assert transition_step(frm, event) is to


@pytest.mark.parametrize(
    "frm,event",
    [
        # Cannot restart a Succeeded or Skipped step - that would
        # silently overwrite outputs.
        (StepState.SUCCEEDED, Event.STARTED),
        (StepState.SKIPPED, Event.STARTED),
        # Cannot succeed a step that is not running.
        (StepState.PENDING, Event.SUCCEEDED),
        (StepState.WAITING_APPROVAL, Event.SUCCEEDED),
        # Cannot approve a step that is not waiting for approval.
        (StepState.PENDING, Event.APPROVED),
        (StepState.RUNNING, Event.APPROVED),
        # Cannot rejected/approve outside the WaitingApproval state.
        (StepState.PENDING, Event.REJECTED),
    ],
)
def test_step_transition_disallowed(frm: StepState, event: Event) -> None:
    with pytest.raises(InvalidTransition):
        transition_step(frm, event)


def test_terminal_step_states() -> None:
    # Failed is intentionally NOT terminal: the retry path runs
    # through it. The executor decides whether to fire STARTED
    # again based on the retry policy + attempts counter.
    assert is_terminal_step(StepState.SUCCEEDED)
    assert is_terminal_step(StepState.SKIPPED)
    assert not is_terminal_step(StepState.FAILED)
    assert not is_terminal_step(StepState.PENDING)
    assert not is_terminal_step(StepState.RUNNING)
    assert not is_terminal_step(StepState.WAITING_APPROVAL)


# ---------------------------------------------------------------------------
# next_actionable_steps - the executor's read of the DAG
# ---------------------------------------------------------------------------

def test_next_actionable_runs_leaves_first() -> None:
    """No deps -> immediately actionable."""
    steps = {"ingest": StepState.PENDING, "features": StepState.PENDING}
    deps = {"ingest": [], "features": ["ingest"]}
    assert next_actionable_steps(steps, deps) == ["ingest"]


def test_next_actionable_unblocked_by_succeeded_dep() -> None:
    steps = {
        "ingest": StepState.SUCCEEDED,
        "features": StepState.PENDING,
        "train": StepState.PENDING,
    }
    deps = {"ingest": [], "features": ["ingest"], "train": ["features"]}
    assert next_actionable_steps(steps, deps) == ["features"]


def test_next_actionable_skipped_dep_does_not_unblock() -> None:
    """A Skipped upstream is NOT the same as Succeeded for this
    purpose - downstream steps that depend on its outputs should
    not run. The executor must decide whether to also skip them
    via a SKIPPED event."""
    steps = {
        "ingest": StepState.SKIPPED,
        "features": StepState.PENDING,
    }
    deps = {"ingest": [], "features": ["ingest"]}
    assert next_actionable_steps(steps, deps) == []


def test_next_actionable_does_not_include_running() -> None:
    """Already-running steps are not actionable."""
    steps = {
        "ingest": StepState.RUNNING,
        "features": StepState.PENDING,
    }
    deps = {"ingest": [], "features": ["ingest"]}
    assert next_actionable_steps(steps, deps) == []


def test_next_actionable_parallel_fanout() -> None:
    """Two siblings that both depend on the same upstream are both
    actionable once the upstream succeeds."""
    steps = {
        "ingest": StepState.SUCCEEDED,
        "branch_a": StepState.PENDING,
        "branch_b": StepState.PENDING,
    }
    deps = {"ingest": [], "branch_a": ["ingest"], "branch_b": ["ingest"]}
    assert sorted(next_actionable_steps(steps, deps)) == ["branch_a", "branch_b"]
