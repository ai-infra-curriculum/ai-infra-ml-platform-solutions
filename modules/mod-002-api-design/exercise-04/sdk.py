"""Hand-written high-level SDK over the generated low-level client."""
from __future__ import annotations

import os
import time
import uuid
from typing import Iterator

import httpx


class JobFailedError(Exception): pass
class QuotaExceededError(Exception): pass


class Client:
    def __init__(self, base_url: str = "https://api.ml-platform.example.com/v1",
                 api_key: str | None = None, tenant: str | None = None):
        self.base = base_url
        self.api_key = api_key or os.environ["ML_PLATFORM_API_KEY"]
        self.tenant = tenant or os.environ["ML_PLATFORM_TENANT"]
        self.http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "X-Tenant-Id": self.tenant},
            timeout=30,
        )

    @property
    def jobs(self): return _Jobs(self)


class _Jobs:
    def __init__(self, c: Client): self.c = c

    def submit(self, spec: dict, idempotency_key: str | None = None) -> dict:
        key = idempotency_key or str(uuid.uuid4())
        for attempt in range(3):
            r = self.c.http.post("/training-jobs", json=spec,
                                  headers={"Idempotency-Key": key})
            if r.status_code == 429:
                raise QuotaExceededError(r.text)
            if r.status_code < 500:
                r.raise_for_status()
                return r.json()
            time.sleep(2 ** attempt)
        raise RuntimeError("retries exhausted")

    def get(self, job_id: str) -> dict:
        r = self.c.http.get(f"/training-jobs/{job_id}")
        r.raise_for_status()
        return r.json()

    def list(self, status: str | None = None) -> Iterator[dict]:
        """Pagination iterator — transparent next-cursor fetching."""
        cursor = None
        while True:
            params = {"status": status} if status else {}
            if cursor: params["cursor"] = cursor
            r = self.c.http.get("/training-jobs", params=params)
            r.raise_for_status()
            page = r.json()
            yield from page["items"]
            if not page.get("next_cursor"):
                return
            cursor = page["next_cursor"]

    def submit_and_wait(self, spec: dict, *, poll_interval: int = 30,
                         on_status=None, timeout_s: int = 7200) -> dict:
        job = self.submit(spec)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            current = self.get(job["id"])
            if on_status:
                on_status(current["status"])
            if current["status"] == "succeeded":
                return current
            if current["status"] in ("failed", "cancelled"):
                raise JobFailedError(f"job {job['id']}: {current['status']}")
            time.sleep(poll_interval)
        raise TimeoutError(f"job {job['id']} did not finish in {timeout_s}s")
