"""Governance gate: refuse promotion to Production without required artifacts."""
from __future__ import annotations

import sys

from mlflow.tracking import MlflowClient


REQUIRED_TAGS = ["model_card_uri", "bias_review_uri", "decision_log_uri"]


def gate(name: str, version: str) -> None:
    c = MlflowClient()
    mv = c.get_model_version(name, version)
    missing = [t for t in REQUIRED_TAGS if t not in mv.tags]
    if missing:
        sys.exit(f"GATE FAILED: missing tags {missing}; cannot promote {name} v{version} to Production")
    print(f"GATE PASSED: {name} v{version} has all required artifacts")


def promote(name: str, version: str) -> None:
    gate(name, version)
    c = MlflowClient()
    c.transition_model_version_stage(
        name=name, version=version, stage="Production",
        archive_existing_versions=True,
    )
    print(f"promoted {name} v{version} → Production")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("name")
    p.add_argument("version")
    args = p.parse_args()
    promote(args.name, args.version)
