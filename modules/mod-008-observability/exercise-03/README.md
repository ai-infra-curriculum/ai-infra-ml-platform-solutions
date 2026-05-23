# Drift Monitoring — Solution

`drift_exporter.py` runs daily; computes PSI per feature per model; exports as Prometheus gauges. Alert when > 0.25.
