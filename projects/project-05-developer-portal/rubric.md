# Grading rubric — project-05-developer-portal

Graders mark each row Pass / Partial / Fail. The rule of thumb:
**two Fails or four Partials means the project does not pass; one
Fail with otherwise-Pass rows means "return for revision".** This
mirrors `requirements.md` F1–F8 + the project's non-functional
requirements.

## Functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| F1 | Software Catalog | Static `catalog-info.yaml` *plus* two API-driven entity providers (`TrainingRunEntityProvider`, `ModelVersionEntityProvider`) populating the catalog on a poll interval. Custom `MLModel` and `Dataset` kinds registered with validators. Deleted upstream entities flip to `lifecycle: deprecated` rather than disappearing. Submission references `catalog/processors.md` and `catalog/entity-kinds.md`. |
| F2 | Software Templates | Three golden paths shipped (`training-run-from-scratch`, `fine-tune-from-base`, `onboard-tenant`). Every template's final step is `catalog:register`. `parameters` use JSON Schema with `Group`-kind-bound pickers for `owner`. Submission references `scaffolder/training-run-template.yaml`. |
| F3 | TechDocs | `techdocs-ref: dir:.` on every catalog entity that ships docs. External build pipeline; HTML on an S3-compatible bucket; search indexed across docs. PR with broken MkDocs cannot merge. Submission references `techdocs/architecture.md`. |
| F4 | Scorecards | Three default scorecards (Platform Baseline, Production Readiness, Compliance) registered. Each failing check carries a remediation link. Scorecards are *advisory* in the portal; any hard gate lives in the registry promotion path (project-04). |
| F5 | Identity + access | OIDC sign-in to the portal. Session cookies `HttpOnly`/`Secure`/`SameSite=Lax`. Downstream API calls use OAuth 2.0 Token Exchange (RFC 8693); portal session cookie alone is rejected by platform APIs with 401. |
| F6 | Plugin model | One plugin per platform component (training-runs, model-registry, feature-store, workflows). Backend plugins cache per-user with stale-on-error fallback. Each plugin ships with Jest tests. Submission references `plugins/plugin-architecture.md`. |
| F7 | Adoption funnel | Four KPIs instrumented and plotted: time-to-first-success, self-service rate, catalog coverage, scorecard pass rate. Targets are defined for each (the *value* is the team's choice; the *existence and definition* of a target is the bar). |
| F8 | Operator observability | Backstage backend exposes Prometheus metrics; one Grafana dashboard ships JSON-defined; structured JSON logs; alerts on catalog processor queue depth + scaffolder action error rate. |

## Non-functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| NF1 | Reproducibility | `yarn dev` brings the portal up against a local Postgres; `app-config.yaml` ships an `.example` variant; no secrets in the repo. |
| NF2 | Testing | Unit tests on every custom plugin; one Cypress/Playwright end-to-end run covers the eight steps in §Acceptance demo. |
| NF3 | Security + privacy | Container image non-root; CSP set; adoption events scrub PII at the source with a per-tenant salt; the event schema has had a documented privacy review. |
| NF4 | Documentation | Onboarding guide and platform-team runbook in TechDocs; catalog-drift and scaffolder-failure procedures have been *drilled*, not just documented. |

## Acceptance demo checklist

Each step is exercised end-to-end and captured on a screencast:

1. [ ] Anonymous user hits `/`, gets redirected to the IdP, signs
       in, lands on the home page. Session cookie is `HttpOnly`.
2. [ ] User browses `/catalog`, filters `kind=MLModel`, sees
       entries sourced live from the project-04 registry — at
       least one ingested by the entity provider, not committed
       statically.
3. [ ] User scaffolds the `training-run-from-scratch` template;
       the PR opens; the catalog registers the new Component as
       the final step.
4. [ ] User opens the new Component's TechDocs tab; the rendered
       MkDocs page loads from the CDN.
5. [ ] User submits a TrainingRun through the new component; the
       portal's TrainingRuns plugin shows the
       `Pending → Running → Succeeded` state machine live.
6. [ ] User registers the resulting model in the registry; the
       portal's `MLModel` entity page renders metadata, lineage,
       deployment timeline, and the verified signing identity.
7. [ ] User deliberately removes `mkdocs.yml`; on the next
       scorecard tick the Platform Baseline scorecard drops, with
       a remediation link pointing at the TechDocs setup guide.
8. [ ] Take the portal session cookie, replay it directly against
       the project-01 control plane API. The platform API returns
       401. The portal is not a confused deputy.

A learner who can demonstrate all eight on a screencast gets the
rubric's Pass on `Acceptance demo`. Skipping the screencast is a
Partial regardless of how complete the code is.
