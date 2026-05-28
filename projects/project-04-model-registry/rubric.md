# Grading rubric -- project-04-model-registry

Graders mark each row Pass / Partial / Fail. The rule of thumb:
**two Fails or four Partials means the project does not pass; one
Fail with otherwise-Pass rows means "return for revision".** This
mirrors `requirements.md` F1–F8 + the project's non-functional
requirements.

## Functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| F1 | Registry CRUD + search | `POST /v1/models`, `POST /v1/models/{id}/versions`, `GET /v1/models?...`, `GET /v1/models/{id}/versions/{version}` all return contract-shaped JSON. Attempts to mutate an existing version return **405**, not 200. Submission references `registry/schema.sql` and `registry/openapi.yaml`. |
| F2 | Signature verification | Cosign keyless signing at registration; verification at both promotion *and* deployment. Bad signature -> clear error message; mismatched OIDC subject -> rejection. Submission references `signing/verify.py`. |
| F3 | Promotion gates | Default gate set per `gates/gates.yaml`. Per-model gates configurable. Human-approval gate records the approver and the signed approval blob. Failed gate response carries the failing gate's name plus the evaluated value. |
| F4 | Deployment + rollout | All four rollout strategies (rolling, blue-green, canary, shadow) implementable; canary supports `traffic_share`; shadow never affects client-visible outputs; deployment row carries target, strategy, deployer, timestamp. |
| F5 | Rollback | `POST /v1/deployments/{id}/rollback` returns target to the prior `Production` version; audit-chain entry with a required `reason` field; SLO < 5 minutes API-call to traffic-restored. |
| F6 | Lineage | Forward + reverse queries; SDK auto-populates edges on registration; reverse query returns the affected models for a data source. Submission references `lineage/queries.sql`. |
| F7 | Multi-tenancy + audit | Tenant scope enforced at the DB layer (RLS or equivalent), not only in the handler. Cross-tenant ID lookup returns 404 (not 403). Every promotion/deployment/rollback/share emits an audit-chain event; `verify` clean. |
| F8 | Observability | All four metrics emitted with the documented label set; `/metrics` exposed; structured JSON logs; one Grafana dashboard JSON shipped. |

## Non-functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| NF1 | Reproducibility | `make up` brings registry + dependencies up from a fresh cluster; `.env.example` documents required config. |
| NF2 | Testing | Unit + integration tests; one end-to-end acceptance run covers the 9 steps in `requirements.md` §Acceptance demo. |
| NF3 | Security | Images non-root; images Cosign-signed; OpenAPI spec auto-generated. |
| NF4 | Documentation | Onboarding guide + runbook; rollback procedure has been *drilled*, not just documented. |

## Acceptance demo checklist

Each step from `requirements.md` §Acceptance demo:

1. [ ] Two models, two versions each, registered with signatures.
2. [ ] Promote one model through `Registered -> Staging -> Production`
       with passing gates. `outcome=completed` increments.
3. [ ] Attempt promote-with-failing-gate (low accuracy) -> 422 with
       the failed gate name; `outcome=blocked` increments.
4. [ ] Canary deploy at `traffic_share = 0.05`.
5. [ ] Ramp canary to 0.5, then 1.0.
6. [ ] Rollback to prior version with a non-empty `reason`.
7. [ ] Reverse-lineage query returns the expected set.
8. [ ] Cross-tenant access attempt -> 404 (not 403).
9. [ ] Audit-chain `verify` clean.

A learner who can demonstrate all nine on a screencast gets the
rubric's Pass on `Acceptance demo`. Skipping the screencast is a
Partial regardless of how complete the code is.
