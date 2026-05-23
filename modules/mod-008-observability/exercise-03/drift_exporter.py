"""Daily drift exporter: PSI per feature from inference logs."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from prometheus_client import Gauge, start_http_server


DRIFT_PSI = Gauge("model_drift_psi", "PSI per feature", ["model", "feature"])


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(reference.min(), reference.max(), bins + 1)
    ref_pct = np.where(np.histogram(reference, edges)[0] == 0, 1e-6,
                        np.histogram(reference, edges)[0] / len(reference))
    cur_pct = np.where(np.histogram(current, edges)[0] == 0, 1e-6,
                        np.histogram(current, edges)[0] / len(current))
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def load_reference(model: str) -> pd.DataFrame:
    return pd.read_parquet(f"s3://ml-monitoring/{model}/reference.parquet")


def load_current(model: str) -> pd.DataFrame:
    return pd.read_parquet(f"s3://ml-monitoring/{model}/current.parquet")


def main():
    start_http_server(8000)
    while True:
        for model in ["iris-rf", "recs-rf"]:
            ref = load_reference(model)
            cur = load_current(model)
            for col in ref.select_dtypes(include="number").columns:
                DRIFT_PSI.labels(model=model, feature=col).set(
                    psi(ref[col].to_numpy(), cur[col].to_numpy()))
        time.sleep(86400)   # daily


if __name__ == "__main__":
    main()
