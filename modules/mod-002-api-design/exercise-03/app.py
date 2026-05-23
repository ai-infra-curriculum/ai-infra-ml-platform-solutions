"""FastAPI implementation of the training-jobs API."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ml-training-jobs")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/metrics", make_asgi_app())


# In-memory store
JOBS: dict[str, dict] = {}
IDEMPOTENCY: dict[str, str] = {}    # idempotency_key → job_id


class JobRequest(BaseModel):
    model_uri: str
    dataset_uri: str
    gpu_count: int = Field(1, ge=1, le=8)
    max_runtime_hours: int = Field(8, ge=1, le=168)
    hyperparams: dict = {}


def tenant_dep(x_tenant_id: str = Header(...)) -> str:
    return x_tenant_id


@app.get("/health")
def health(): return {"status": "ok"}


@app.post("/v1/training-jobs", status_code=202)
@limiter.limit("60/minute")
async def submit(request: Request, body: JobRequest,
                  idempotency_key: str = Header(..., alias="Idempotency-Key"),
                  tenant: str = Depends(tenant_dep)):
    if idempotency_key in IDEMPOTENCY:
        return JOBS[IDEMPOTENCY[idempotency_key]]
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id, "status": "pending",
        "tenant": tenant, "spec": body.dict(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    JOBS[job_id] = job
    IDEMPOTENCY[idempotency_key] = job_id
    return job


@app.get("/v1/training-jobs/{id}")
def get_job(id: str, tenant: str = Depends(tenant_dep)):
    job = JOBS.get(id)
    if not job or job["tenant"] != tenant:
        raise HTTPException(404, "not found")
    return job


@app.get("/v1/training-jobs")
def list_jobs(tenant: str = Depends(tenant_dep),
               cursor: str | None = None,
               status: str | None = None,
               limit: int = 50):
    items = [j for j in JOBS.values() if j["tenant"] == tenant]
    if status:
        items = [j for j in items if j["status"] == status]
    items.sort(key=lambda j: j["created_at"], reverse=True)
    start = int(cursor) if cursor else 0
    page = items[start:start + limit]
    next_cursor = str(start + limit) if start + limit < len(items) else None
    return {"items": page, "next_cursor": next_cursor}


@app.delete("/v1/training-jobs/{id}", status_code=204)
def cancel(id: str, tenant: str = Depends(tenant_dep)):
    job = JOBS.get(id)
    if not job or job["tenant"] != tenant:
        raise HTTPException(404, "not found")
    if job["status"] not in ("pending", "scheduled", "running"):
        raise HTTPException(409, f"cannot cancel in status {job['status']}")
    job["status"] = "cancelled"
    return None
