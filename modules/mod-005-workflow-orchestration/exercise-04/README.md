# SLA + Alerting — Solution

`dag_with_sla.py` wires `sla_miss_callback` + `on_failure_callback` to Slack.
Failure callback only pages after 3 retries (avoid alert fatigue).
