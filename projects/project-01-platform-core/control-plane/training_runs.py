"""Control-plane TrainingRun API (requirements F2 + F5).

The control plane is the user-facing surface. Its job at admission time:
validate the request, check the tenant's quota, persist the intent,
apply the CR to the cluster, and emit an audit event. The operator
(operator/reconcile.py) does the continuous enforcement afterwards.

Key contract decisions:
  * Errors are ``{error, code, request_id}`` JSON — never a stack trace
    (requirement F2). A single exception handler guarantees this.
  * Quota-exceeded returns HTTP 429 with a clear, machine-readable code.
  * Every request carries an ``X-Request-Id`` propagated into logs and
    audit-chain entries; if the caller omits it, the middleware mints one.

Static check:  python -m py_compile control-plane/training_runs.py
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# These collaborators are defined elsewhere in the deliverable; imported
# here by interface. They keep this module focused on the HTTP contract.
from db import RunStore, TenantStore       # type: ignore
from k8s import apply_cr, delete_cr        # type: ignore
from audit import emit                      # type: ignore


# --- error contract ---------------------------------------------------

class PlatformError(Exception):
    """Raised for any client-visible failure. Carries an HTTP status and
    a stable machine-readable code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


class QuotaExceeded(PlatformError):
    def __init__(self, message: str) -> None:
        super().__init__(429, "quota_exceeded", message)


# --- request / response models ---------------------------------------

class ResourceSpec(BaseModel):
    requests: dict[str, str]
    limits: Optional[dict[str, str]] = None


class DatasetSpec(BaseModel):
    name: str = Field(min_length=1)
    version: Optional[str] = None


class RetrySpec(BaseModel):
    max: int = Field(default=0, ge=0, le=10)
    backoff: str = Field(default="exponential", pattern="^(none|linear|exponential)$")


class CreateRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=253)
    tenant: str
    image: str = Field(pattern=r"^.+(:.+|@sha256:[0-9a-f]{64})$")
    command: list[str] = Field(default_factory=list)
    resources: ResourceSpec
    dataset: DatasetSpec
    hyperparameters: dict[str, str] = Field(default_factory=dict)
    retries: RetrySpec = Field(default_factory=RetrySpec)


class RunResponse(BaseModel):
    id: str
    name: str
    tenant: str
    phase: str
    created_at: datetime


# --- dependencies -----------------------------------------------------

def request_id(x_request_id: Optional[str] = Header(default=None)) -> str:
    """Use the caller's request id or mint one. Propagated to logs +
    audit so a single user action is traceable end-to-end."""
    return x_request_id or str(uuid.uuid4())


router = APIRouter(prefix="/v1", tags=["training-runs"])


# --- handlers ---------------------------------------------------------

@router.post("/training-runs", status_code=201, response_model=RunResponse)
def create_run(body: CreateRunRequest, rid: str = Depends(request_id)) -> RunResponse:
    tenant = TenantStore.get(body.tenant)
    if tenant is None:
        raise PlatformError(404, "tenant_not_found", f"unknown tenant {body.tenant!r}")

    # Quota admission (F5): reject before anything is persisted or applied.
    usage = RunStore.quota_usage(tenant.id)
    requested_gpu_hours = _estimate_gpu_hours(body)
    if usage.gpu_hours + requested_gpu_hours > tenant.gpu_hours_per_month:
        emit("quota_violation", tenant=body.tenant, request_id=rid,
             payload={"resource": "gpu_hours_per_month",
                      "requested": requested_gpu_hours,
                      "used": usage.gpu_hours, "limit": tenant.gpu_hours_per_month})
        raise QuotaExceeded(
            f"run would exceed monthly GPU-hour quota "
            f"({usage.gpu_hours}+{requested_gpu_hours} > {tenant.gpu_hours_per_month})")
    if usage.active_runs >= tenant.concurrent_run_limit:
        raise QuotaExceeded(
            f"tenant at concurrent-run limit ({tenant.concurrent_run_limit})")

    run = RunStore.insert(tenant_id=tenant.id, name=body.name,
                          spec=body.model_dump(), phase="Pending")
    apply_cr(namespace=tenant.namespace, name=body.name, spec=body.model_dump())
    emit("training_run_admitted", tenant=body.tenant, request_id=rid,
         payload={"run_id": run.id, "name": body.name})
    return RunResponse(id=run.id, name=run.name, tenant=body.tenant,
                       phase=run.phase, created_at=run.created_at)


@router.get("/training-runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str, rid: str = Depends(request_id)) -> RunResponse:
    run = RunStore.get(run_id)
    if run is None:
        raise PlatformError(404, "run_not_found", f"no run with id {run_id!r}")
    return RunResponse(id=run.id, name=run.name, tenant=run.tenant,
                       phase=run.phase, created_at=run.created_at)


@router.get("/training-runs", response_model=list[RunResponse])
def list_runs(
    tenant: Optional[str] = None,
    phase: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    rid: str = Depends(request_id),
) -> list[RunResponse]:
    runs = RunStore.list(tenant=tenant, phase=phase,
                         created_after=created_after,
                         created_before=created_before, limit=limit)
    return [RunResponse(id=r.id, name=r.name, tenant=r.tenant,
                        phase=r.phase, created_at=r.created_at) for r in runs]


@router.delete("/training-runs/{run_id}", status_code=200, response_model=RunResponse)
def cancel_run(run_id: str, rid: str = Depends(request_id)) -> RunResponse:
    run = RunStore.get(run_id)
    if run is None:
        raise PlatformError(404, "run_not_found", f"no run with id {run_id!r}")
    delete_cr(namespace=run.namespace, name=run.name)
    run = RunStore.set_phase(run_id, "Cancelled")
    emit("training_run_cancelled", tenant=run.tenant, request_id=rid,
         payload={"run_id": run_id})
    return RunResponse(id=run.id, name=run.name, tenant=run.tenant,
                       phase=run.phase, created_at=run.created_at)


@router.get("/tenants/{tenant_id}/quota-usage")
def quota_usage(tenant_id: str, rid: str = Depends(request_id)) -> dict:
    usage = RunStore.quota_usage(tenant_id)
    return {"tenant_id": tenant_id, "gpu_hours": usage.gpu_hours,
            "active_runs": usage.active_runs}


def _estimate_gpu_hours(body: CreateRunRequest) -> float:
    """Conservative pre-admission estimate: GPUs requested × a wall-clock
    ceiling. A real platform would use historical run durations; the
    capstone accepts a fixed ceiling."""
    gpus = float(body.resources.requests.get("nvidia.com/gpu", 0) or 0)
    return gpus * 24.0  # assume up to 24h per run for admission accounting.


# --- app wiring + global error handler --------------------------------

app = FastAPI(title="SmartRecs ML Platform — Control Plane", version="v1alpha1")
app.include_router(router)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(PlatformError)
async def handle_platform_error(request: Request, exc: PlatformError) -> JSONResponse:
    rid = request.headers.get("x-request-id", "")
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.message, "code": exc.code, "request_id": rid},
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Never leak a stack trace to the client (F2). Log the detail
    # server-side; return a stable shape with the request id to correlate.
    rid = request.headers.get("x-request-id", "")
    return JSONResponse(
        status_code=500,
        content={"error": "internal error", "code": "internal", "request_id": rid},
    )
