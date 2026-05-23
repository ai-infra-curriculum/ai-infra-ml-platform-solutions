# Orchestrator Decision Memo — Reference

## Scenario
Mid-size ML org (20 engineers, ~30 models). Current state: manual notebooks
+ cron + a couple of Argo Workflows. Picking the single orchestrator going
forward.

## Criteria + scoring (1-5)

| Criterion | Weight | Airflow | Prefect | Dagster | Kubeflow | Flyte |
|---|---|---|---|---|---|---|
| Maturity | 3 | 5 | 4 | 3 | 4 | 3 |
| Python-native | 2 | 3 | 5 | 5 | 3 | 5 |
| K8s integration | 2 | 4 | 3 | 4 | 5 | 5 |
| ML-domain ergonomics | 2 | 3 | 3 | 4 | 5 | 4 |
| Operational complexity | 3 | 2 | 4 | 3 | 1 | 1 |
| Hiring pool | 2 | 5 | 3 | 2 | 3 | 2 |
| **Weighted total** | | **48** | **47** | **44** | **45** | **40** |

## Recommendation: Airflow

Tied with Prefect on raw score. Airflow wins on hiring pool + maturity, which
matter more at this org size. Prefect is a strong second choice if the org
heavily values Python-native + lower operational complexity.

## Risks
- Airflow's web UI + scheduler require ops attention; budget ~0.5 platform-eng FTE
- Airflow's K8s executor needs care to avoid pool exhaustion under burst
- Plan to write a `dag_template.py` library so teams write thin DAGs not framework boilerplate
