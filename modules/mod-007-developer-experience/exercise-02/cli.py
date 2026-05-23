"""Click-based ml-platform CLI."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import click
import httpx
import yaml


API_BASE = os.environ.get("ML_PLATFORM_API", "http://localhost:8000/v1")
API_KEY = os.environ.get("ML_PLATFORM_API_KEY", "")
TENANT = os.environ.get("ML_PLATFORM_TENANT", "default")


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "X-Tenant-Id": TENANT}


def _emit(obj: Any, fmt: str):
    if fmt == "json":
        click.echo(json.dumps(obj, indent=2))
    elif fmt == "yaml":
        click.echo(yaml.safe_dump(obj))
    else:
        if isinstance(obj, list):
            for row in obj:
                click.echo(f"{row.get('id', '?'):36s}  {row.get('status', '?'):12s}  {row.get('spec', {}).get('model_uri', '')}")
        else:
            click.echo(json.dumps(obj, indent=2))


def _error(action: str, cause: str, help_text: str, docs: str = ""):
    click.echo(f"Error: failed to {action}", err=True)
    click.echo(f"Cause: {cause}", err=True)
    click.echo(f"Help: {help_text}", err=True)
    if docs:
        click.echo(f"Docs: {docs}", err=True)
    sys.exit(1)


@click.group()
def ml(): pass


@ml.group()
def jobs(): pass


@jobs.command()
@click.option("--config", required=True, type=click.Path(exists=True))
@click.option("--output", default="table", type=click.Choice(["json", "yaml", "table"]))
def submit(config: str, output: str):
    """Submit a training job from a YAML spec."""
    spec = yaml.safe_load(open(config))
    r = httpx.post(f"{API_BASE}/training-jobs", json=spec, headers=_headers(), timeout=30)
    if r.status_code == 429:
        _error("submit job",
                "rate limit exceeded",
                "wait + retry, or contact your platform team to raise quota",
                "https://docs.example.com/quotas")
    if r.status_code >= 400:
        _error("submit job", f"HTTP {r.status_code}: {r.text[:200]}",
                "check the job spec against the schema",
                "https://docs.example.com/training-jobs")
    _emit(r.json(), output)


@jobs.command(name="list")
@click.option("--status", help="Filter by status")
@click.option("--output", default="table", type=click.Choice(["json", "yaml", "table"]))
def list_jobs(status: str, output: str):
    """List recent jobs."""
    params = {}
    if status: params["status"] = status
    r = httpx.get(f"{API_BASE}/training-jobs", params=params, headers=_headers(), timeout=30)
    r.raise_for_status()
    _emit(r.json()["items"], output)


@jobs.command()
@click.argument("job_id")
@click.option("--output", default="json", type=click.Choice(["json", "yaml"]))
def status(job_id: str, output: str):
    """Show status for a single job."""
    r = httpx.get(f"{API_BASE}/training-jobs/{job_id}", headers=_headers(), timeout=30)
    if r.status_code == 404:
        _error("get status",
                f"job {job_id} not found",
                "check the job id; you may not have permission for this tenant",
                "https://docs.example.com/jobs")
    r.raise_for_status()
    _emit(r.json(), output)


if __name__ == "__main__":
    ml()
