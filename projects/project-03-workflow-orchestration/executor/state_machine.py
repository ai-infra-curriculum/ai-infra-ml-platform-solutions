"""DAG state machine for the workflow orchestration engine.

Pure transition functions. The only side effects are raised exceptions.
Callers wrap a `transition()` call together with the persistence write
in a single DB transaction (see `db/schema.sql` and `SOLUTION.md` § 2).

Validate syntax with: python -m py_compile executor/state_machine.py
Run tests with:       pytest tests/test_state_machine.py
"""

from __future__ import annotations

from enum import Enum


class RunState(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class StepState(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    WAITING_APPROVAL = "WaitingApproval"


class Event(str, Enum):
    """Events the executor / API can send into the state machine."""
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    GATE_WAIT = "gate_wait"
    APPROVED = "approved"
    REJECTED = "rejected"
    ALL_STEPS_DONE = "all_steps_done"
    ANY_STEP_FAILED = "any_step_failed"


class InvalidTransition(Exception):
    """Raised when an event is not allowed in the current state."""


# Allowed run-level transitions.
# Each entry is (from_state, event) -> to_state.
_RUN_TRANSITIONS: dict[tuple[RunState, Event], RunState] = {
    (RunState.PENDING, Event.STARTED): RunState.RUNNING,
    (RunState.PENDING, Event.CANCELLED): RunState.CANCELLED,
    (RunState.RUNNING, Event.ALL_STEPS_DONE): RunState.SUCCEEDED,
    (RunState.RUNNING, Event.ANY_STEP_FAILED): RunState.FAILED,
    (RunState.RUNNING, Event.CANCELLED): RunState.CANCELLED,
}


# Allowed step-level transitions.
_STEP_TRANSITIONS: dict[tuple[StepState, Event], StepState] = {
    (StepState.PENDING, Event.STARTED): StepState.RUNNING,
    (StepState.PENDING, Event.SKIPPED): StepState.SKIPPED,
    (StepState.PENDING, Event.GATE_WAIT): StepState.WAITING_APPROVAL,
    (StepState.PENDING, Event.CANCELLED): StepState.FAILED,
    (StepState.RUNNING, Event.SUCCEEDED): StepState.SUCCEEDED,
    (StepState.RUNNING, Event.FAILED): StepState.FAILED,
    # On a transient retry, the executor sends FAILED -> the step
    # goes back to PENDING for the next attempt. The transition is
    # intentional: it makes the retry visible in the audit log
    # (RUNNING -> FAILED -> PENDING) rather than hiding it.
    (StepState.FAILED, Event.STARTED): StepState.PENDING,
    (StepState.WAITING_APPROVAL, Event.APPROVED): StepState.PENDING,
    (StepState.WAITING_APPROVAL, Event.REJECTED): StepState.FAILED,
    (StepState.WAITING_APPROVAL, Event.CANCELLED): StepState.FAILED,
}


TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
)
TERMINAL_STEP_STATES: frozenset[StepState] = frozenset(
    {StepState.SUCCEEDED, StepState.SKIPPED}
)


def transition_run(state: RunState, event: Event) -> RunState:
    """Return the new run state for (state, event), or raise.

    Pure function. Callers persist the result inside a DB transaction
    alongside an audit_log insert.
    """
    try:
        return _RUN_TRANSITIONS[(state, event)]
    except KeyError as exc:
        raise InvalidTransition(
            f"run: cannot apply {event.value!r} in state {state.value!r}"
        ) from exc


def transition_step(state: StepState, event: Event) -> StepState:
    """Return the new step state for (state, event), or raise."""
    try:
        return _STEP_TRANSITIONS[(state, event)]
    except KeyError as exc:
        raise InvalidTransition(
            f"step: cannot apply {event.value!r} in state {state.value!r}"
        ) from exc


def is_terminal_run(state: RunState) -> bool:
    return state in TERMINAL_RUN_STATES


def is_terminal_step(state: StepState) -> bool:
    """A step is terminal once it has reached Succeeded or Skipped.

    Failed is NOT terminal here because the retry path goes
    Failed -> Pending. The executor decides whether to fire the
    retry STARTED event based on attempts + retry policy; if it
    chooses not to retry, the run-level transition ANY_STEP_FAILED
    fires and the run becomes Failed.
    """
    return state in TERMINAL_STEP_STATES


def next_actionable_steps(
    steps: dict[str, StepState],
    depends_on: dict[str, list[str]],
) -> list[str]:
    """Return step names whose dependencies are all Succeeded and
    whose own state is Pending.

    Pure function over the in-memory state map. The executor reads
    `step_states` from the DB, calls this, then issues a STARTED
    event for each returned step in its own transaction.
    """
    actionable: list[str] = []
    for name, state in steps.items():
        if state is not StepState.PENDING:
            continue
        deps = depends_on.get(name, [])
        if all(steps.get(dep) is StepState.SUCCEEDED for dep in deps):
            actionable.append(name)
    return actionable
