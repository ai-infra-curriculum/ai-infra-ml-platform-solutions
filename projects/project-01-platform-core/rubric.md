# Grading rubric — project-01-platform-core

This is the rubric graders use against a submission. It mirrors
`requirements.md` F1–F8 + NF1–NF4 and is referenced from `SOLUTION.md`
§4. Mark each row Pass / Partial / Fail. Two Fails or four Partials
mean the project does not pass; one Fail with otherwise-Pass rows means
"return for revision".

## Functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| F1 | TrainingRun CRD | Applied to cluster; ≥5 spec fields validated by OpenAPI v3 schema; `v1alpha1` + structural schema in place. Submission references `crd/training-run-crd.yaml`. |
| F2 | Control-plane API | All four operations (`POST`, `GET id`, `GET list`, `DELETE`) work end-to-end; errors return `{error, code, request_id}`; `X-Request-Id` flows to logs + audit chain. |
| F3 | Operator reconciliation | Create → Job + ConfigMap + SA in tenant namespace; delete → finalizer cleanup; restart converges within 30 s; retries respect `spec.retries.max` + backoff. |
| F4 | Multi-tenancy | Namespace + ResourceQuota + LimitRange + NetworkPolicy + ServiceAccount with workload identity, all present per tenant. Cross-tenant bucket read fails at IAM; cross-namespace HTTP call fails at NetworkPolicy. |
| F5 | Quota enforcement | Admission rejects an over-quota run with a clear error; `GET /v1/tenants/{id}/quota-usage` shows live usage; concurrent-run cap enforced. |
| F6 | SDK + CLI | SDK matches `README.md` §3 examples; CLI verbs `create \| list \| status \| cancel`; both authenticate with a token; `examples/` directory present. |
| F7 | Observability | All five required metrics emitted with the right labels; `/metrics` exposed on control-plane + operator; structured JSON logs; one Grafana dashboard JSON shipped. |
| F8 | Audit chain | Significant actions emit events; entries carry timestamp, identity, tenant, action, resource, payload hash, prev hash; `verify` walks the chain; DB rejects UPDATE/DELETE on `audit_log`. |

## Non-functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| NF1 | Reproducibility | `make up` brings the platform up from a fresh cluster; all infra in `deploy/`; `.env.example` documents required configuration. |
| NF2 | Testing | Control-plane unit tests ≥ 80 % coverage; operator tests via envtest / kopf harness; one end-to-end test creating a tenant, running a job, verifying outputs. |
| NF3 | Security | Images non-root; no long-lived static creds in-cluster; secrets via ESO (or equivalent); images Cosign-signed. |
| NF4 | Documentation | `README.md` + `ARCHITECTURE.md` + auto-generated OpenAPI + onboarding guide + runbook. |

## Acceptance demo

The eight steps in `requirements.md` "Acceptance demo" must pass on a
fresh cluster, in order, without manual intervention between steps.
Submissions that pass F1–F8 individually but fail the demo (typically
because tenant onboarding is manual) get a Partial on NF1 *and* are
returned for revision regardless of other rows.
