from fastapi.testclient import TestClient
from app import app


client = TestClient(app)
TENANT_HEADER = {"X-Tenant-Id": "test-tenant", "Idempotency-Key": "test-1"}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_submit_returns_202():
    r = client.post("/v1/training-jobs",
                     json={"model_uri": "s3://m", "dataset_uri": "s3://d"},
                     headers=TENANT_HEADER)
    assert r.status_code == 202
    assert r.json()["status"] == "pending"


def test_idempotency():
    r1 = client.post("/v1/training-jobs",
                      json={"model_uri": "s3://m", "dataset_uri": "s3://d"},
                      headers={**TENANT_HEADER, "Idempotency-Key": "test-2"})
    r2 = client.post("/v1/training-jobs",
                      json={"model_uri": "s3://different", "dataset_uri": "s3://d"},
                      headers={**TENANT_HEADER, "Idempotency-Key": "test-2"})
    # Same idempotency key → same job
    assert r1.json()["id"] == r2.json()["id"]


def test_tenant_isolation():
    r1 = client.post("/v1/training-jobs",
                      json={"model_uri": "s3://m", "dataset_uri": "s3://d"},
                      headers={"X-Tenant-Id": "tenant-a", "Idempotency-Key": "iso-1"})
    job_id = r1.json()["id"]
    # Tenant B cannot see tenant A's job
    r2 = client.get(f"/v1/training-jobs/{job_id}", headers={"X-Tenant-Id": "tenant-b"})
    assert r2.status_code == 404
