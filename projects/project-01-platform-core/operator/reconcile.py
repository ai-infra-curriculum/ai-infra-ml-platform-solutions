"""Reference reconciliation outline for the TrainingRun operator (F3).

This is a *reference outline*, not a runnable controller. It compiles
with ``python3 -m py_compile`` and validates the shape of the reconcile
loop graders should expect. Real deployment lives in the learner's
implementation; this file pins the contract.

Why this exists:
- Phase 2/3 of STEP_BY_STEP describe what reconcile() must do without
  showing the structure. Junior implementers often skip finalisers or
  overwrite ``spec`` from inside the operator. The skeleton below
  shows the right shape: read-only spec, idempotent step list,
  finalizer-driven cleanup, structured status updates.

Validation:
    python3 -m py_compile operator/reconcile.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

# kopf is the canonical Python operator framework; the import is
# referenced for type clarity. The module level guard keeps this file
# importable even where kopf is absent (CI lint, py_compile).
try:  # pragma: no cover - import guard, not behaviour
    import kopf
except ImportError:  # pragma: no cover
    kopf = None  # type: ignore[assignment]

FINALIZER = "platform.smartrecs.io/trainingrun-finalizer"


@dataclass(frozen=True)
class ReconcileInputs:
    """The frozen view of a TrainingRun the operator reconciles against.

    Reconcile must never mutate ``spec``. Mutating spec from the operator
    is a classic anti-pattern that turns the CR into both the source of
    truth and a scratchpad; status is the only field the operator owns.
    """

    namespace: str
    name: str
    uid: str
    spec: Mapping[str, Any]
    status: Mapping[str, Any]


def desired_job(inputs: ReconcileInputs) -> Mapping[str, Any]:
    """Return the deterministic Job manifest for this TrainingRun.

    Idempotency requirement: same inputs → byte-identical output. That
    means no timestamps, no random suffixes; the Job is named after the
    TrainingRun so a re-apply is a no-op instead of a new Job.
    """
    spec = inputs.spec
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"trainingrun-{inputs.name}",
            "namespace": inputs.namespace,
            "labels": {
                "platform.smartrecs.io/training-run": inputs.name,
                "platform.smartrecs.io/tenant": inputs.namespace,
            },
            "ownerReferences": [
                # OwnerReference -> when the TrainingRun is deleted,
                # Kubernetes garbage-collects the Job. Finalizers handle
                # cleanup of *out-of-cluster* state (audit, DB rows).
                {
                    "apiVersion": "platform.smartrecs.io/v1alpha1",
                    "kind": "TrainingRun",
                    "name": inputs.name,
                    # uid comes from the owning CR's metadata.uid (assigned
                    # by the apiserver on create). An empty UID makes the
                    # apiserver reject the Job create, so the operator must
                    # plumb metadata.uid through ReconcileInputs.
                    "uid": inputs.uid,
                    "controller": True,
                    "blockOwnerDeletion": True,
                }
            ],
        },
        "spec": {
            "backoffLimit": int(spec.get("retries", {}).get("max", 0)),
            "template": {
                "metadata": {
                    "labels": {
                        "platform.smartrecs.io/training-run": inputs.name,
                    }
                },
                "spec": {
                    "serviceAccountName": "tenant-trainer",
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": True,
                    "containers": [
                        {
                            "name": "trainer",
                            "image": spec["image"],
                            "command": spec.get("command", []),
                            "resources": spec["resources"],
                            "securityContext": {
                                "runAsNonRoot": True,
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "readOnlyRootFilesystem": True,
                            },
                        }
                    ],
                },
            },
        },
    }


def next_phase(job_status: Mapping[str, Any], current_phase: str) -> str:
    """Pure state-machine step: where does this run go next?

    Pulled out as a pure function so it is testable without a cluster.
    The full state machine: Pending -> Running -> {Succeeded, Failed,
    Cancelled}. Cancelled is set by the control plane on DELETE; the
    operator never transitions *into* Cancelled on its own.
    """
    if current_phase in ("Succeeded", "Failed", "Cancelled"):
        return current_phase
    if job_status.get("succeeded", 0) >= 1:
        return "Succeeded"
    if job_status.get("failed", 0) >= 1:
        return "Failed"
    if job_status.get("active", 0) >= 1:
        return "Running"
    return "Pending"


def reconcile(
    inputs: ReconcileInputs,
    cluster: "ClusterClient",
) -> MutableMapping[str, Any]:
    """One idempotent step. Caller (kopf) handles retry on exception."""
    if FINALIZER not in cluster.finalizers(inputs.namespace, inputs.name):
        cluster.add_finalizer(inputs.namespace, inputs.name, FINALIZER)

    cluster.apply(desired_job(inputs))
    job_status = cluster.get_job_status(
        inputs.namespace, f"trainingrun-{inputs.name}"
    )
    new_phase = next_phase(
        job_status, str(inputs.status.get("phase", "Pending"))
    )

    # Status patch shape mirrors the CRD's status schema (see
    # crd/training-run-crd.yaml). The operator writes only fields it owns.
    return {
        "status": {
            "phase": new_phase,
            "metrics": {
                "podName": job_status.get("podName"),
                "podStatus": job_status.get("podStatus"),
            },
        }
    }


def finalize(
    inputs: ReconcileInputs,
    cluster: "ClusterClient",
    audit: "AuditClient",
) -> None:
    """Cleanup hook -- runs when the TrainingRun is deleted."""
    cluster.delete_job(inputs.namespace, f"trainingrun-{inputs.name}")
    audit.emit(
        action="training_run_cancelled",
        tenant=inputs.namespace,
        resource=f"trainingrun:{inputs.namespace}/{inputs.name}",
        payload={"name": inputs.name, "reason": "deleted"},
    )
    cluster.remove_finalizer(inputs.namespace, inputs.name, FINALIZER)


# --- Protocols (typing only; real impls live in operator/k8s/ etc.) ---


class ClusterClient:  # pragma: no cover - protocol only
    def finalizers(self, namespace: str, name: str) -> "list[str]": ...
    def add_finalizer(self, namespace: str, name: str, value: str) -> None: ...
    def remove_finalizer(self, namespace: str, name: str, value: str) -> None: ...
    def apply(self, manifest: Mapping[str, Any]) -> None: ...
    def get_job_status(self, namespace: str, name: str) -> Mapping[str, Any]: ...
    def delete_job(self, namespace: str, name: str) -> None: ...


class AuditClient:  # pragma: no cover - protocol only
    def emit(
        self,
        *,
        action: str,
        tenant: str,
        resource: str,
        payload: Mapping[str, Any],
    ) -> None: ...
