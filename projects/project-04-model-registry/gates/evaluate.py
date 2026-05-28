"""Promotion-gate evaluator -- reference solution for F3.

Validates with:
  python3 -m py_compile gates/evaluate.py

The evaluator is intentionally a pure function over (gates, metrics,
context). Side effects (DB writes, audit-chain emission) live in the
FastAPI handler that calls `evaluate_gates`. Keeping evaluation pure
makes the four test cases trivial:

    - all-pass            -> ALLOW
    - one threshold fail  -> BLOCK with that gate's name
    - signature fail      -> BLOCK (cannot be overridden)
    - human gate pending  -> PENDING

The state machine is encoded once in `next_state`. Add new transitions
there, not in the handler -- the registry's grading depends on the
state machine being the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


class Status(str, Enum):
    REGISTERED = "Registered"
    STAGING = "Staging"
    PRODUCTION = "Production"
    DEPRECATED = "Deprecated"
    DECOMMISSIONED = "Decommissioned"


# Allowed transitions. Anything else returns None from `next_state`.
ALLOWED_TRANSITIONS: dict[tuple[Status, Status], str] = {
    (Status.REGISTERED, Status.STAGING): "registered_to_staging",
    (Status.STAGING, Status.PRODUCTION): "staging_to_production",
    (Status.PRODUCTION, Status.DEPRECATED): "production_to_deprecated",
    (Status.DEPRECATED, Status.DECOMMISSIONED): "deprecated_to_decommissioned",
}


def next_state(current: Status, target: Status) -> str | None:
    """Return the canonical transition label, or None if illegal."""
    return ALLOWED_TRANSITIONS.get((current, target))


class Decision(str, Enum):
    ALLOW = "allow"        # all gates passed; promote synchronously
    PENDING = "pending"    # threshold gates passed; awaiting human approval
    BLOCK = "block"        # one or more gates failed


@dataclass(frozen=True)
class GateResult:
    name: str
    decision: Decision
    detail: str = ""
    evaluated_value: Any = None
    threshold: Any = None


@dataclass(frozen=True)
class EvaluationResult:
    decision: Decision
    results: tuple[GateResult, ...]

    @property
    def first_failure(self) -> GateResult | None:
        for r in self.results:
            if r.decision is Decision.BLOCK:
                return r
        return None

    @property
    def pending_approvals(self) -> tuple[GateResult, ...]:
        return tuple(r for r in self.results if r.decision is Decision.PENDING)


# --- evaluators ---------------------------------------------------------

def _read_path(obj: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path like 'metrics.fairness.disparate_impact'."""
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    "<":  lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _evaluate_threshold(
    gate: Mapping[str, Any], context: Mapping[str, Any]
) -> GateResult:
    value = _read_path(context, gate["metric"])
    op = gate["operator"]
    threshold = gate["threshold"]
    if value is None:
        return GateResult(
            name=gate["name"],
            decision=Decision.BLOCK,
            detail=f"missing metric '{gate['metric']}'",
            threshold=threshold,
        )
    passed = _OPS[op](value, threshold)
    return GateResult(
        name=gate["name"],
        decision=Decision.ALLOW if passed else Decision.BLOCK,
        detail=f"{gate['metric']} {op} {threshold} -> {passed}",
        evaluated_value=value,
        threshold=threshold,
    )


def _evaluate_assertion(
    gate: Mapping[str, Any], context: Mapping[str, Any]
) -> GateResult:
    # The expression is evaluated by the *caller* (FastAPI handler) using
    # the safe predicate parser shared with project-03. Here we just
    # consume the precomputed boolean to keep this module dependency-free.
    key = f"assertions.{gate['name']}"
    value = _read_path(context, key)
    if value is None:
        return GateResult(
            name=gate["name"],
            decision=Decision.BLOCK,
            detail=f"missing assertion result '{key}'",
        )
    return GateResult(
        name=gate["name"],
        decision=Decision.ALLOW if value else Decision.BLOCK,
        detail=f"{key} -> {value}",
        evaluated_value=value,
    )


def _evaluate_approval(
    gate: Mapping[str, Any], context: Mapping[str, Any]
) -> GateResult:
    required = {approver["role"] for approver in gate["approvers"]}
    recorded = set(_read_path(context, "approvals") or [])
    if required.issubset(recorded):
        return GateResult(
            name=gate["name"],
            decision=Decision.ALLOW,
            detail=f"all approvers signed: {sorted(required)}",
        )
    return GateResult(
        name=gate["name"],
        decision=Decision.PENDING,
        detail=f"awaiting: {sorted(required - recorded)}",
    )


_EVALUATORS = {
    "threshold": _evaluate_threshold,
    "assertion": _evaluate_assertion,
    "approval": _evaluate_approval,
}


def evaluate_gates(
    gates: Sequence[Mapping[str, Any]],
    transition: str,
    context: Mapping[str, Any],
) -> EvaluationResult:
    """Evaluate the gates relevant to `transition` against `context`.

    `context` carries the model-version metrics, precomputed assertion
    booleans (e.g. signature_valid), and the recorded approvals list.
    """
    results: list[GateResult] = []
    for gate in gates:
        if transition not in gate.get("runs_at", []):
            continue
        evaluator = _EVALUATORS[gate["type"]]
        results.append(evaluator(gate, context))

    if any(r.decision is Decision.BLOCK for r in results):
        decision = Decision.BLOCK
    elif any(r.decision is Decision.PENDING for r in results):
        decision = Decision.PENDING
    else:
        decision = Decision.ALLOW
    return EvaluationResult(decision=decision, results=tuple(results))
