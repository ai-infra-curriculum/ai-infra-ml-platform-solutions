"""Atomic rollback: current → Archived, previous Staging/Archived → Production."""
from __future__ import annotations

import argparse
import sys

from mlflow.tracking import MlflowClient


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name")
    args = p.parse_args()

    c = MlflowClient()
    versions = sorted(c.search_model_versions(f"name='{args.name}'"),
                       key=lambda v: int(v.version), reverse=True)

    current = next((v for v in versions if v.current_stage == "Production"), None)
    if not current:
        sys.exit("no Production version")
    previous = next((v for v in versions
                      if v.current_stage in ("Staging", "Archived")
                      and int(v.version) < int(current.version)), None)
    if not previous:
        sys.exit("no rollback target available")

    c.transition_model_version_stage(args.name, current.version, "Archived")
    c.transition_model_version_stage(args.name, previous.version, "Production")
    print(f"rolled back: v{current.version} → Archived, v{previous.version} → Production")


if __name__ == "__main__":
    main()
