"""Retry classification for step pod failures.

Maps a Kubernetes pod result to one of TRANSIENT / INTERMITTENT /
PERMANENT, consulted by the executor before the retry policy decides
whether to fire another attempt.

Default table is derived from `architecture.md` § 4 and the project
README's notes on exit-code 137 (OOM) and pod eviction. A step author
can override any entry by supplying a `classify_overrides` dict on
the step's `retries` block - see `examples/nightly-recs-retrain.yaml`
for an example.

Validate syntax with: python -m py_compile executor/retry_classifier.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Classification(str, Enum):
    TRANSIENT = "transient"
    INTERMITTENT = "intermittent"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class PodResult:
    """Subset of a Kubernetes pod terminated state that the
    classifier reads. Populated by the executor from the
    `Pod.status.containerStatuses[*].state.terminated` block."""

    exit_code: int
    # Reason is the Kubernetes-supplied reason string when present:
    # "OOMKilled", "Error", "Completed", "Evicted", ...
    reason: str | None = None
    # Pod-level phase, used for eviction detection.
    phase: str | None = None


# Default classifications, applied in order of specificity.
# Keys are matched against (reason, exit_code).
#
# References:
#   - "exit code 137 (OOM) -> transient" (project README § Phase 6)
#   - "pod evicted -> transient" (project README § Phase 6)
#   - "default -> transient with backoff" (project README § Phase 6)
#
# Adding an entry here must come with a test (see tests/).
DEFAULT_BY_REASON: dict[str, Classification] = {
    "OOMKilled": Classification.TRANSIENT,
    "Evicted": Classification.TRANSIENT,
    "DeadlineExceeded": Classification.TRANSIENT,
    "Error": Classification.TRANSIENT,
    "ContainerCannotRun": Classification.PERMANENT,
    "ImagePullBackOff": Classification.PERMANENT,
    "ErrImagePull": Classification.PERMANENT,
    "CreateContainerConfigError": Classification.PERMANENT,
    "InvalidImageName": Classification.PERMANENT,
}

# Pod phase signal that overrides exit code: a pod-evicted phase is
# always treated as transient, even if the container had not yet
# produced an exit code.
EVICTED_PHASES: frozenset[str] = frozenset({"Failed", "Evicted"})


# Default fallback when no other signal classifies the result.
DEFAULT_FALLBACK: Classification = Classification.TRANSIENT


def classify(
    result: PodResult,
    overrides: dict[str, str] | None = None,
) -> Classification:
    """Classify a pod result.

    Override keys may be:
      - "reason:<Reason>"     e.g. "reason:OOMKilled"
      - "exit:<code>"         e.g. "exit:2"
      - "phase:<Phase>"       e.g. "phase:Failed"

    Override values are one of "transient" / "intermittent" /
    "permanent". An invalid value raises ValueError early so a
    misconfigured pipeline does not silently degrade retry behaviour.
    """
    overrides = overrides or {}

    if result.reason and f"reason:{result.reason}" in overrides:
        return _coerce(overrides[f"reason:{result.reason}"])
    if f"exit:{result.exit_code}" in overrides:
        return _coerce(overrides[f"exit:{result.exit_code}"])
    if result.phase and f"phase:{result.phase}" in overrides:
        return _coerce(overrides[f"phase:{result.phase}"])

    if result.reason and result.reason in DEFAULT_BY_REASON:
        return DEFAULT_BY_REASON[result.reason]

    # The brief calls out exit 137 specifically; surface it as a
    # named case even when the reason string is missing (e.g.,
    # because the container was killed before the kubelet wrote
    # the reason).
    if result.exit_code == 137:
        return Classification.TRANSIENT

    if result.exit_code == 0:
        # Defensive: a "success" reaching the classifier is a bug
        # in the executor (it should not call the classifier on a
        # successful step). Raise rather than silently retry.
        raise ValueError(
            "classify() called with exit_code=0; "
            "executor should not retry-classify successful pods"
        )

    return DEFAULT_FALLBACK


def _coerce(value: str) -> Classification:
    try:
        return Classification(value)
    except ValueError as exc:
        raise ValueError(
            f"invalid classification override {value!r}; "
            "expected 'transient' | 'intermittent' | 'permanent'"
        ) from exc
