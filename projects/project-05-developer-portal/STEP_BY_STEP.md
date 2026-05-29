# STEP_BY_STEP — Project 05 Solution

Solution-side walk-through. The learning repo's
[`STEP_BY_STEP.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-05-developer-portal/STEP_BY_STEP.md)
prescribes nine phases over ~70 hours; this document mirrors
those phases and pins what each one yields *in this solution's
terms*. Use it to sequence your build and to know when each
phase is "done enough" to move on.

Each phase below points at the artifact in this directory that
captures its contract. Build implementations to meet those
contracts; the curated files are the rubric.

## Phase 0 — Setup (2-3 h)

**Yield**: a Node 20 toolchain, a working Backstage app scaffolded
from `npx @backstage/create-app`, a Postgres instance for the
catalog, and the repo skeleton from the learning `STEP_BY_STEP.md`
§0.

Solution-side check: `yarn dev` brings up the bare app at
`http://localhost:3000` with an empty catalog; `psql -d backstage -c '\dt'`
shows the catalog tables created by the backend on first boot.

## Phase 1 — Catalog (8-10 h)

**Yield**: static `catalog-info.yaml` for each component repo in
scope; the GitHub discovery processor wired in
`app-config.yaml`; the two custom kinds (`MLModel`, `Dataset`)
registered with their validators; the `TrainingRunEntityProvider`
and `ModelVersionEntityProvider` running on a 30 s tick against
project-01 and project-04.

Pin: `catalog/processors.md` — the entity providers are the
non-negotiable part. Without them, the catalog drifts the day
after launch.

Done when:

```bash
yamllint -s projects/project-05-developer-portal/catalog/catalog-info.yaml
# In the portal: visit /catalog, filter by kind=MLModel, see at
# least one entity sourced from the registry; delete the model
# version, wait one tick, see lifecycle flip to "deprecated".
```

## Phase 2 — Scaffolder (10-12 h)

**Yield**: the three golden-path templates from
`scaffolder/templates.md` (`training-run-from-scratch`,
`fine-tune-from-base`, `onboard-tenant`); per-tenant GitHub App
installations for the publish step; `catalog:register` as the
required final step of every template.

Pin: `scaffolder/training-run-template.yaml`. The `steps:` list
is the platform contract; the `parameters:` JSON Schema is the
guardrail. The picker for `spec.owner` is bound to `kind: Group`
so users cannot type a team that does not exist.

Acceptance vibe-check: from a fresh user account, scaffolder
the "new training run" template, accept the PR it opens, watch
the new Component appear under `/catalog` with a working
TechDocs page and a green CI badge.

## Phase 3 — TechDocs (6-8 h)

**Yield**: `techdocs.builder: 'external'` in `app-config.yaml`;
a build pipeline (GitHub Actions or otherwise) that runs MkDocs
on every merge to main; an S3-compatible bucket holding the
built HTML; the TechDocs reader plugin enabled in the portal;
search indexed across all docs.

Pin: `techdocs/architecture.md` — the external build model is
the rubric expectation. Local-build mode is fine for `yarn dev`
but does not scale past ten components.

Done when: open the portal's entity page for a Component with
TechDocs, see the rendered docs; type a string from the docs
into the global search bar; the search result links back to the
right page.

## Phase 4 — Auth (8-10 h)

**Yield**: an OIDC provider wired in `app-config.yaml`
(`auth.providers.<provider>`); session cookies with
`HttpOnly`, `Secure`, `SameSite=Lax`; OAuth 2.0 Token Exchange
(RFC 8693) plumbed from the portal backend to the platform APIs;
the backend's own service identity (`client_credentials`) for
catalog ingestion.

Pin: `auth/identity.md`. The negative test — sending the portal
session cookie directly to project-01 must return 401 — is the
F5 hard fail probe.

Done when:

1. Anonymous user visits `/` → redirected to IdP → returned with
   a session.
2. Session cookie alone is rejected by the platform API.
3. Portal-issued exchanged token is accepted by the platform API
   with the user's identity in `sub` and tenant in the audience
   claim.

## Phase 5 — Scorecards (5-7 h)

**Yield**: the three default scorecards from
`scorecards/scorecards.md` registered; each check parameterized
by `scorecards/scorecard-definitions.yaml`; entity pages show
per-entity scorecard results; the team-rollup view aggregates
by `spec.owner`.

Pin: scorecards are *advisory* in the portal. Anything that
must hard-gate (signed model required for production
deployment) hard-gates at the registry — see project-04 §F3.

Drill it: deliberately remove `mkdocs.yml` from a Component,
wait one scorecard tick, see the Platform Baseline scorecard
drop from 8/8 to 7/8 with a remediation link pointing at the
TechDocs setup guide.

## Phase 6 — Platform-component plugins (10-14 h)

**Yield**: one frontend plugin per platform component
(`@ml-platform/plugin-training-runs`,
`@ml-platform/plugin-model-registry`,
`@ml-platform/plugin-feature-store`,
`@ml-platform/plugin-workflows`); each backend plugin handles
proxying + per-user caching; each plugin ships with Jest tests.

Pin: `plugins/plugin-architecture.md`. One plugin per
component, not one plugin to rule them all. The package layout
is what makes plugin upgrades incremental.

Acceptance vibe-check: on an `MLModel` entity page, the
registry plugin renders metadata, lineage graph, deployment
timeline, promotion approvers, and the artifact digest — all
sourced live from project-04 through the backend cache.

## Phase 7 — Observability + adoption (5-7 h)

**Yield**: the portal backend exposes `/metrics`; the dashboards
listed in `observability/adoption-metrics.md` ship as JSON next
to the platform's other Grafana boards; the adoption event
schema is published and reviewed; the four product KPIs are
plotted with targets.

Pin: PII scrubbing at the source. Adoption events use opaque
hashed user IDs (per-tenant salt). Name, email, and manager
chain never appear in the event payload.

Done when: a fresh user signing in, scaffolding a template,
and getting their first successful TrainingRun produces a
complete funnel trace under one hashed user ID, with the four
KPI panels updating within five minutes.

## Phase 8 — Testing + docs (4-6 h)

**Yield**: Jest test suites for each plugin; one end-to-end
Cypress (or Playwright) flow that runs the eight-step
acceptance demo from `rubric.md`; a portal runbook covering
catalog drift, scaffolder failure, TechDocs build failure,
and auth provider outage.

The acceptance demo is the only test that *proves* the portal.
Everything else is a precondition.

## Time-budget recap

| Phase | Hours |
|---|---|
| 0 — Setup | 2-3 |
| 1 — Catalog | 8-10 |
| 2 — Scaffolder | 10-12 |
| 3 — TechDocs | 6-8 |
| 4 — Auth | 8-10 |
| 5 — Scorecards | 5-7 |
| 6 — Platform plugins | 10-14 |
| 7 — Observability + adoption | 5-7 |
| 8 — Testing + docs | 4-6 |
| **Total** | **~68** |

## When you're done

The portal is the product surface every internal ML engineer
opens in the morning. The catalog is the source of truth for
what exists; the scaffolder is the source of truth for how new
things get started; TechDocs is the source of truth for how
they work; scorecards are the source of truth for how well
they meet the bar. Every action is authenticated to the
requesting user, audited at the platform API layer, and
attributable to a tenant.

This is the front door the rest of the platform stack opens
behind.
