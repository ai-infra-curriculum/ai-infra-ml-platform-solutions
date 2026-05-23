"""Export Feast per-FeatureView freshness as Prometheus gauges."""
from __future__ import annotations

import time

import boto3
from feast import FeatureStore
from prometheus_client import Gauge, start_http_server


FRESHNESS = Gauge("feature_view_freshness_seconds",
                  "Seconds since the feature view's source last had data",
                  ["feature_view"])


def main():
    fs = FeatureStore("feature_repo")
    s3 = boto3.client("s3")
    start_http_server(8000)
    while True:
        for fv in fs.list_feature_views():
            source = fv.batch_source
            if hasattr(source, "path") and source.path.startswith("s3://"):
                bucket, _, prefix = source.path[5:].partition("/")
                objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
                if objs:
                    last = max(o["LastModified"] for o in objs)
                    FRESHNESS.labels(feature_view=fv.name).set(
                        time.time() - last.timestamp())
        time.sleep(60)


if __name__ == "__main__":
    main()
