# Incident Runbook Library

## HighErrorRate (5xx > 5% for 5min)

Companion: [engineer-solutions/mod-108 ex-09](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-108-monitoring-observability/exercise-09-incident-response-gameday) for fault-injection rehearsals.

1. Ack in PagerDuty
2. Check dashboard: error rate by status code + by pod
3. If recent deploy: rollback via Argo Rollouts undo
4. If downstream issue: check feature store + model registry availability
5. Escalate if no clear cause within 15 min

## HighDrift (PSI > 0.25 for 30min)

1. Check which features drifted (drift_exporter Grafana)
2. Check upstream data pipeline for source-data change
3. Notify model owner; queue retrain if drift sustained

## ModelAccuracyRegression (rolling 7d < baseline -5pp)

1. Validate ground-truth pipeline is healthy
2. Compare slice metrics: which segment regressed?
3. If isolated to one slice: investigate that slice's input distribution
4. If global: investigate model or training-data change
5. Rollback to prior production version if cause unclear

## BudgetExhausted (monthly model budget > 95%)

1. Notify model owner
2. Show projected end-of-month cost vs budget
3. Options: optimize (rightsize / spot / batch), retrain smaller, raise budget

## TrainingDAGSLAMiss

1. Check Airflow scheduler health
2. Check pool slots (are tasks Pending?)
3. Check task logs for the specific stuck task
4. If retraining is critical: escalate; consider manual trigger with raised priority
