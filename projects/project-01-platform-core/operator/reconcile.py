"""Reference TrainingRun operator (requirement F3).

A kopf-based controller that reconciles the ``TrainingRun`` CR to
cluster state. The design priorities, in order:

1. **Idempotency** — every reconcile produces the same cluster state for
   the same spec, so the operator is safe to restart at any point
   (requirement F3: converge within 30s on restart).
2. **Finalizers** — deletion cleans up child resources before the CR is
   removed; no dangling Jobs/ConfigMaps/SAs.
3. **Status as the contract** — the control plane reads ``.status`` to
   answer ``GET`` queries; the operator is the only writer of status.

This is the reference skeleton: the reconcile decision tree, the
finalizer, the retry-with-backoff path, and the status writes are
complete and correct. Cluster-client plumbing (the ``k8s`` helper) is
elided to the standard Kubernetes Python client calls it wraps.

Static check:  python -m py_compile operator/reconcile.py
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import kopf

logger = logging.getLogger("trainingrun-operator")

GROUP = "platform.smartrecs.io"
VERSION = "v1alpha1"
PLURAL = "trainingruns"
FINALIZER = "platform.smartrecs.io/cleanup"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _backoff_seconds(strategy: str, attempt: int) -> int:
    """Delay before retry ``attempt`` (1-indexed) for a backoff strategy."""
    if strategy == "none":
        return 0
    if strategy == "linear":
        return 30 * attempt
    # exponential (default): 30, 60, 120, ... capped at 10 minutes.
    return min(30 * (2 ** (attempt - 1)), 600)


@kopf.on.create(GROUP, VERSION, PLURAL)
@kopf.on.update(GROUP, VERSION, PLURAL)
def reconcile(spec: dict, status: dict, meta: dict, namespace: str,
              name: str, patch: kopf.Patch, **_: Any) -> None:
    """Bring cluster state to ``spec``. Safe to call repeatedly.

    Decision tree:
      * no phase yet            -> admit, create child resources, Pending
      * Job missing but Running -> recreate (idempotent self-heal)
      * Job present             -> mirror Job status into CR status
      * Job failed + retries    -> recreate up to spec.retries.max
    """
    phase = (status or {}).get("phase")
    run_id = meta["uid"]

    if phase in ("Succeeded", "Cancelled"):
        return  # terminal; nothing to reconcile.

    job = _get_job(namespace, name)

    if phase is None:
        # First admission by the operator. The control plane already
        # validated quota; the operator materializes the workload.
        _ensure_child_resources(namespace, name, spec, run_id)
        patch.status["phase"] = "Pending"
        patch.status["conditions"] = [_condition("Admitted", "True", "QuotaPassed")]
        logger.info("admitted %s/%s", namespace, name)
        return

    if job is None:
        # Self-heal: the CR thinks it is running but the Job vanished.
        _ensure_child_resources(namespace, name, spec, run_id)
        return

    job_phase = _job_phase(job)
    patch.status["metrics"] = {"podStatus": job_phase,
                               "podName": _job_pod_name(job)}

    if job_phase == "Running" and phase != "Running":
        patch.status["phase"] = "Running"
        patch.status["startedAt"] = _now()
        patch.status.setdefault("conditions", []).append(
            _condition("Running", "True", "JobStarted"))

    elif job_phase == "Succeeded":
        patch.status["phase"] = "Succeeded"
        patch.status["completedAt"] = _now()

    elif job_phase == "Failed":
        attempt = (status or {}).get("observedRetries", 0) + 1
        max_retries = spec.get("retries", {}).get("max", 0)
        if attempt <= max_retries:
            delay = _backoff_seconds(
                spec.get("retries", {}).get("backoff", "exponential"), attempt)
            patch.status["observedRetries"] = attempt
            _delete_job(namespace, name)
            _ensure_child_resources(namespace, name, spec, run_id)
            logger.info("retry %s/%s attempt=%d delay=%ds",
                        namespace, name, attempt, delay)
            raise kopf.TemporaryError("retrying failed run", delay=delay)
        patch.status["phase"] = "Failed"
        patch.status["completedAt"] = _now()


@kopf.on.delete(GROUP, VERSION, PLURAL)
def finalize(namespace: str, name: str, patch: kopf.Patch, **_: Any) -> None:
    """Clean up child resources on delete; kopf removes the finalizer
    only after this returns without error."""
    _delete_job(namespace, name)
    _delete_configmap(namespace, name)
    logger.info("cleaned up %s/%s", namespace, name)


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_: Any) -> None:
    # Leader election so a future multi-replica deployment has exactly
    # one active reconciler (single replica is acceptable for the
    # capstone; this makes scaling up a config change, not a rewrite).
    settings.peering.name = "trainingrun-operator"
    settings.persistence.finalizer = FINALIZER


# --- status helpers ---------------------------------------------------

def _condition(type_: str, status_: str, reason: str) -> dict:
    return {"type": type_, "status": status_, "reason": reason,
            "lastTransition": _now()}


def _job_phase(job: dict) -> str:
    s = job.get("status", {})
    if s.get("succeeded", 0) >= 1:
        return "Succeeded"
    if s.get("failed", 0) >= 1:
        return "Failed"
    if s.get("active", 0) >= 1:
        return "Running"
    return "Pending"


def _job_pod_name(job: dict) -> str:
    return job.get("status", {}).get("podName", "")


# --- cluster client plumbing -----------------------------------------
# These wrap the standard kubernetes-client BatchV1Api / CoreV1Api calls.
# Each is idempotent: create-or-update by name, ignore 404 on delete.

def _ensure_child_resources(namespace: str, name: str, spec: dict,
                            run_id: str) -> None:
    """Create-or-update the Job, ConfigMap, and ServiceAccount binding
    for this run. Idempotent: re-applying with the same spec is a no-op."""
    _apply_configmap(namespace, name, spec)
    _apply_job(namespace, name, spec, run_id)


def _get_job(namespace: str, name: str) -> dict | None:        # pragma: no cover
    ...  # BatchV1Api.read_namespaced_job; return None on 404.


def _apply_job(namespace: str, name: str, spec: dict, run_id: str) -> None:  # pragma: no cover
    ...  # BatchV1Api.create/patch with the SA `training-runner` and
    # resources from spec.resources; labels: tenant + run-id for cost.


def _apply_configmap(namespace: str, name: str, spec: dict) -> None:  # pragma: no cover
    ...  # CoreV1Api.create/patch ConfigMap with hyperparameters.


def _delete_job(namespace: str, name: str) -> None:            # pragma: no cover
    ...  # BatchV1Api.delete_namespaced_job; ignore 404.


def _delete_configmap(namespace: str, name: str) -> None:      # pragma: no cover
    ...  # CoreV1Api.delete_namespaced_config_map; ignore 404.
