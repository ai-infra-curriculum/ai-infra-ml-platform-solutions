"""Bidirectional v1 ↔ v2 translator."""
from __future__ import annotations

import argparse
import json
import sys


def v1_to_v2(v1: dict) -> dict:
    out = {k: v for k, v in v1.items() if k != "gpu_count"}
    out["gpu"] = {"type": "l40s", "count": v1.get("gpu_count", 1)}
    return out


def v2_to_v1(v2: dict) -> dict:
    out = {k: v for k, v in v2.items() if k != "gpu"}
    gpu = v2.get("gpu", {})
    out["gpu_count"] = int(gpu.get("count", 1))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("direction", choices=["v1-to-v2", "v2-to-v1"])
    args = p.parse_args()
    body = json.load(sys.stdin)
    out = v1_to_v2(body) if args.direction == "v1-to-v2" else v2_to_v1(body)
    json.dump(out, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
