"""Reference reconcile loop -- shape only.

The operator owns three CRD kinds:

  * `Tenant`         (cluster-scoped, derived from the API row).
  * `ResourceClaim`  (namespaced).
  * `TrainingRun`    (namespaced).

For each kind the reconcile contract is the same:

  1. Read the *desired* state from the CRD `spec`.
  2. Read the *actual* state from the cluster (the Pod/Job/Namespace
     bundle the operator manages).
  3. Compute the minimal action to converge.
  4. Update the CRD `status`.
  5. Emit *one* audit-chain row per status transition (not per
     reconcile -- reconciles are idempotent).

This file is not a runnable controller. It compiles cleanly
(`python3 -m py_compile operator/reconcile.py`); the learner
ports the shape into kopf, controller-runtime, or whichever
operator framework they pick.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


logger = logging.getLogger("platform.operator")


class TrainingRunPhase(str, Enum):
    PENDING   = "Pending"
    SCHEDULED = "Scheduled"
    RUNNING   = "Running"
    SUCCEEDED = "Succeeded"
    FAILED    = "Failed"
    CANCELLED = "Cancelled"


_TERMINAL = {
    TrainingRunPhase.SUCCEEDED,
    TrainingRunPhase.FAILED,
    TrainingRunPhase.CANCELLED,
}


@dataclass(frozen=True)
class TrainingRunSpec:
    image: str
    command: list[str]
    cpu: str
    memory: str
    gpu: str
    priority: str
    tenant_id: str
    audit_chain_entry_id: str


@dataclass(frozen=True)
class TrainingRunStatus:
    phase: TrainingRunPhase
    pod_name: Optional[str]
    exit_code: Optional[int]


@dataclass(frozen=True)
class TrainingRunCR:
    name: str
    namespace: str
    spec: TrainingRunSpec
    status: TrainingRunStatus
    resource_version: str


@dataclass(frozen=True)
class ReconcileResult:
    """Tells the controller framework whether to requeue."""
    requeue_after_seconds: Optional[int]


# ---------------------------------------------------------------------------
# Client protocols -- replaced by the operator framework's clients.
# ---------------------------------------------------------------------------


class KubeClient(Protocol):
    def get_pod(self, namespace: str, name: str) -> Optional[dict]: ...
    def create_pod(self, namespace: str, manifest: dict) -> None: ...
    def delete_pod(self, namespace: str, name: str) -> None: ...
    def patch_cr_status(self, cr: TrainingRunCR, new_status: TrainingRunStatus) -> None: ...


class AuditEmitter(Protocol):
    def emit(self, action: str, resource_kind: str, resource_id: str,
             tenant_id: str, payload: dict) -> str: ...


# ---------------------------------------------------------------------------
# Reconciler
# ---------------------------------------------------------------------------


def reconcile_training_run(
    cr: TrainingRunCR,
    kube: KubeClient,
    audit: AuditEmitter,
) -> ReconcileResult:
    """Single-pass reconcile for one TrainingRun.

    Contract:

    * Terminal phases (`Succeeded`, `Failed`, `Cancelled`) do NOT
      re-create the Pod. If the Pod is gone but the run is terminal,
      that's fine -- the run has finished.
    * Audit events are emitted ONLY on a phase transition. Calling
      `reconcile_training_run` ten times in a row with no change
      produces zero audit rows.
    * The operator never sets `tenant_id` from request input -- it
      reads it from the spec field the control-plane admission
      webhook populated.
    """
    if cr.status.phase in _TERMINAL:
        return ReconcileResult(requeue_after_seconds=None)

    pod_name = _pod_name(cr)
    pod = kube.get_pod(cr.namespace, pod_name)

    desired_phase = _next_phase(cr.status.phase, pod)

    if pod is None and desired_phase == TrainingRunPhase.PENDING:
        # Pending -> Scheduled: create the workload Pod.
        manifest = _build_pod_manifest(cr, pod_name)
        kube.create_pod(cr.namespace, manifest)
        new_status = TrainingRunStatus(
            phase=TrainingRunPhase.SCHEDULED,
            pod_name=pod_name,
            exit_code=None,
        )
    else:
        new_status = TrainingRunStatus(
            phase=desired_phase,
            pod_name=pod_name if pod is not None else cr.status.pod_name,
            exit_code=_exit_code(pod),
        )

    if new_status.phase != cr.status.phase:
        kube.patch_cr_status(cr, new_status)
        audit.emit(
            action=f"training_run.phase.{new_status.phase.value.lower()}",
            resource_kind="TrainingRun",
            resource_id=cr.name,
            tenant_id=cr.spec.tenant_id,
            payload={
                "from": cr.status.phase.value,
                "to":   new_status.phase.value,
                "exit_code": new_status.exit_code,
            },
        )

    if new_status.phase in _TERMINAL:
        return ReconcileResult(requeue_after_seconds=None)
    return ReconcileResult(requeue_after_seconds=15)


def _next_phase(current: TrainingRunPhase, pod: Optional[dict]) -> TrainingRunPhase:
    """Map current phase + Pod state to the next CR phase.

    Single source of truth for transitions. New transitions are added
    here, not in the reconcile body.
    """
    if pod is None:
        return current  # let the body decide whether to create the Pod

    pod_phase = pod.get("status", {}).get("phase", "")
    if pod_phase in ("Pending", ""):
        return TrainingRunPhase.SCHEDULED
    if pod_phase == "Running":
        return TrainingRunPhase.RUNNING
    if pod_phase == "Succeeded":
        return TrainingRunPhase.SUCCEEDED
    if pod_phase == "Failed":
        return TrainingRunPhase.FAILED
    return current


def _pod_name(cr: TrainingRunCR) -> str:
    return f"tr-{cr.name}"


def _exit_code(pod: Optional[dict]) -> Optional[int]:
    if pod is None:
        return None
    containers = pod.get("status", {}).get("containerStatuses", [])
    if not containers:
        return None
    terminated = containers[0].get("state", {}).get("terminated", {})
    return terminated.get("exitCode")


def _build_pod_manifest(cr: TrainingRunCR, pod_name: str) -> dict:
    spec = cr.spec
    resources = {
        "requests": {"cpu": spec.cpu, "memory": spec.memory},
        "limits":   {"cpu": spec.cpu, "memory": spec.memory},
    }
    if spec.gpu and spec.gpu != "0":
        resources["limits"]["nvidia.com/gpu"] = spec.gpu

    return {
        "apiVersion": "v1",
        "kind":       "Pod",
        "metadata": {
            "name":      pod_name,
            "namespace": cr.namespace,
            "labels": {
                "platform.example.com/tenant":       spec.tenant_id,
                "platform.example.com/run":          cr.name,
                "platform.example.com/audit-entry":  spec.audit_chain_entry_id,
                "platform.example.com/priority":     spec.priority,
            },
            "ownerReferences": [
                {
                    "apiVersion":         "platform.example.com/v1",
                    "kind":               "TrainingRun",
                    "name":               cr.name,
                    "uid":                cr.resource_version,
                    "controller":         True,
                    "blockOwnerDeletion": True,
                }
            ],
        },
        "spec": {
            "restartPolicy":      "Never",
            "automountServiceAccountToken": False,
            "serviceAccountName": "platform-trainingrun",
            "containers": [
                {
                    "name":      "trainer",
                    "image":     spec.image,
                    "command":   list(spec.command) or None,
                    "resources": resources,
                    "securityContext": {
                        "runAsNonRoot":            True,
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem":  True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                }
            ],
        },
    }
