# Governance Gate — Solution

`gate.py` checks for required tags (`model_card_uri`, `bias_review_uri`,
`decision_log_uri`) before promoting to Production. Refuses with a clear
error if any are missing.

Companion: [engineer-solutions/mod-106 ex-10](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-106-mlops/exercise-10-model-governance) for the templates that fill those URIs.
