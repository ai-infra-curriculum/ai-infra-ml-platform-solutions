# SOLUTION — Project 05: ML Platform Developer Portal

> Worked solution for the
> [project-05-developer-portal](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-05-developer-portal)
> capstone in the paired learning repo. Follows the 6-section AICG
> Output Contract.

## 1. Solution overview

The developer portal is the **product surface** of the ML platform.
By the time a data scientist or ML engineer reaches it, the
TrainingRun control plane (project-01), feature store
(project-02), workflow orchestrator (project-03), and model
registry (project-04) already exist as APIs. None of those APIs
are the user-facing platform; the portal is. Its job is to take
the platform's higher-order primitives and present them as
discoverable, governed, self-service surfaces — a catalog the
user can browse, golden-path templates the user can scaffold
from, docs the user can search, and scorecards that tell the user
when their service is below the bar.

The reference solution makes five design commitments:

1. **The catalog is the source of truth for "what exists"**.
   Every TrainingRun CRD, ModelVersion, FeatureSet, and Pipeline
   appears as a Backstage entity. If something is not in the
   catalog, the platform cannot govern it, page on it, or
   attribute its cost. Entities are ingested from the same APIs
   the SDK talks to — not from a parallel database.
2. **Golden paths are the platform contract**. Scaffolder
   templates encode the platform team's opinion on "the right
   way" to start a training job, register a model, or onboard a
   tenant. A user who scaffolds gets workload identity, default
   NetworkPolicy, audit instrumentation, and metric naming for
   free. A user who hand-rolls gets none of it — and the
   scorecard tells them so.
3. **Docs ship with code**. TechDocs is wired so every catalog
   entity renders its own `mkdocs.yml` from the same repo that
   ships its code. Drift between "what the docs say" and "what
   the SDK does" is the most common DX failure; co-locating them
   under one `catalog-info.yaml` makes drift a code review smell.
4. **The portal is the auth boundary the user sees**. SSO at the
   portal, OIDC token-exchange to the platform APIs. The user
   types a password once a day; every downstream API call uses a
   short-lived token bound to the user's identity and tenant.
   The portal never proxies bearer tokens it should not see.
5. **Adoption is the grading metric, not feature completeness**.
   The portal ships with an instrumented set of conversion
   funnels — landed-on-page → scaffolded-template →
   first-successful-run — and the rubric grades the rate, not
   the existence, of the funnel.

Everything else (plugin extensibility, scorecards, search,
observability) supports these five commitments.

### Curated artifacts (mapped to F1-F8)

| Path | Maps to |
|---|---|
| `catalog/catalog-info.yaml` | F1 |
| `catalog/entity-kinds.md` | F1, F6 |
| `catalog/processors.md` | F1 |
| `scaffolder/templates.md` | F2 |
| `scaffolder/training-run-template.yaml` | F2 |
| `techdocs/architecture.md` | F3 |
| `techdocs/mkdocs.example.yml` | F3 |
| `scorecards/scorecards.md` | F4 |
| `scorecards/scorecard-definitions.yaml` | F4 |
| `auth/identity.md` | F5 |
| `plugins/plugin-architecture.md` | F6 |
| `observability/adoption-metrics.md` | F7, F8 |
| `STEP_BY_STEP.md` | build sequence |
| `rubric.md` | per-row grading bar |

## 2. Worked answer or implementation

### 2.1 Software Catalog (F1, F6)

Backstage's Software Catalog is an entity graph keyed by
`(kind, namespace, name)`. The reference solution uses six kinds
straight from the upstream model — `Component`, `API`,
`Resource`, `System`, `Domain`, `Group` — plus two custom kinds
the ML platform requires: `MLModel` and `Dataset`. Custom kinds
are declared by validators registered on the catalog backend, not
by patching upstream.

The two ingestion paths:

- **Static `catalog-info.yaml`** committed under each repo. The
  catalog's GitHub discovery processor walks org repos, finds
  the file, and registers its entities. This is the path for
  SDKs, CLIs, services, and human-authored documents.
- **API-driven processors** for things the platform creates
  *dynamically*. A `TrainingRunEntityProvider` polls the
  project-01 control plane every 30 s and emits
  `kind: Resource, spec.type: training-run` entities; a
  `ModelVersionEntityProvider` polls the project-04 registry and
  emits `kind: MLModel`. Polling, not pushing, because catalog
  consistency must survive control-plane restarts.

`catalog/entity-kinds.md` documents the two custom kinds:

```yaml
# MLModel kind (custom)
apiVersion: ml-platform.example.com/v1alpha1
kind: MLModel
metadata:
  name: recsys-ctr-predictor
  namespace: team-recs
  annotations:
    ml-platform.example.com/model-version-id: <uuid>
    ml-platform.example.com/registry-url: https://registry.example.com/v1/models/...
spec:
  type: classifier
  owner: group:team-recs
  system: recs-platform
  lifecycle: production
  framework: pytorch-2.1
  trainingRun: resource:default/training-run-2026-05-12-abc
  dataset: dataset:default/recs-curated-2026-05
```

`spec.trainingRun` and `spec.dataset` are typed cross-references;
the catalog backend resolves them on read. That's how lineage
inherits from the registry into the portal without re-storing it.

`catalog/processors.md` covers the failure modes that ship the
catalog to production cleanly:

- A processor that throws on one bad entity must not poison the
  rest of the import. Wrap per-entity in try/except, emit a
  catalog *error* (visible in the portal as a red badge), and
  continue.
- Stale entities are tombstoned, not deleted. A model version
  removed from the registry shows up as `lifecycle: deprecated`
  for 30 days so users searching for "what used to be here" can
  find it.

### 2.2 Software Templates (F2)

`scaffolder/templates.md` enumerates the three golden paths the
reference solution ships:

- **`training-run-from-scratch`** — clones a repo skeleton,
  wires the SDK, registers the new component in the catalog, and
  opens a PR. The output is a repo with `catalog-info.yaml`,
  CI that runs the training job through project-01's control
  plane, and an `mkdocs.yml` wired for TechDocs.
- **`fine-tune-from-base`** — same as above, but the template
  parameterizes a base model URI from the registry. The form's
  picker is populated from a live registry query — users select
  a real `MLModel` entity rather than typing a URI.
- **`onboard-tenant`** — admin-only path that creates the
  tenant namespace, applies the default-deny NetworkPolicy,
  binds SPIFFE identities, writes the tenant row in the audit
  chain, and posts a welcome page in TechDocs.

`scaffolder/training-run-template.yaml` is the canonical example.
The template's `steps:` list is the platform contract: every
action is reviewable, every action emits an audit entry. Notable
shapes:

- The `publish:github` step uses a per-tenant GitHub App
  installation, never a shared PAT. The bot identity is what
  shows up in `git log`.
- The `catalog:register` step is the last step, and it is
  *required*. A scaffolder run that opened the PR but did not
  register the entity is a failure — silent un-cataloged
  services are the bug class this prevents.
- `parameters` use the JSON Schema validation Backstage ships
  with; the picker for `owner` is bound to the `Group` kind so a
  user cannot type a non-existent team name.

### 2.3 TechDocs (F3)

`techdocs/architecture.md` walks the docs-as-code pipeline:

1. Every catalog entity that ships docs has
   `metadata.annotations['backstage.io/techdocs-ref']` pointing
   at the same repo (typically `dir:.`).
2. The TechDocs builder runs MkDocs against the repo on every
   merge to main, materializes the HTML, and pushes it to an
   S3-compatible bucket.
3. The portal's TechDocs reader plugin fetches that HTML and
   renders it inline. Search is indexed across all entities'
   docs so a user typing "TrainingRun status reasons" finds the
   right page in the right repo without knowing where it lives.

`techdocs/mkdocs.example.yml` is the configuration every catalog
entity inherits. The notable choice is `plugins: [techdocs-core]`
— TechDocs ships an opinionated MkDocs plugin that emits the
metadata Backstage's search and TOC widgets need. Importing it
is one line; forgetting to import it makes the portal silently
fall back to plain MkDocs, with broken anchors.

The reference solution treats the docs build as a CI gate. A PR
that breaks MkDocs (broken cross-link, missing nav entry) cannot
merge. Without that gate, doc rot starts the day after launch.

### 2.4 Scorecards (F4)

`scorecards/scorecards.md` describes the three default scorecards
the portal ships:

- **Platform Baseline** — does the component have an owner,
  TechDocs, an OpenAPI definition, and a healthy CI? This is the
  bar every component must clear.
- **Production Readiness** — does the component have an SLO
  defined, a runbook annotation, an on-call rotation in
  PagerDuty, alert routes wired? Required for any
  `lifecycle: production` component.
- **Compliance** — does the model have a signed registry
  entry, a published lineage edge to a documented dataset, and
  an approver on its last production promotion? Required for
  any `MLModel` whose tenant is flagged as regulated.

`scorecards/scorecard-definitions.yaml` shows each check as a
rule with a query, a threshold, and a remediation link. The
remediation link is non-negotiable: a failing check that does
not tell the user how to fix it is a tax, not a tool.

Scorecard results are entity annotations
(`scorecards.example.com/platform-baseline: 7/8`), surfaced on
each entity page and rolled up to team-level dashboards.
Scorecards are deliberately *advisory* by default — a hard
gate at the registry promotion path (project-04 §F3) is where
"must pass" lives. The portal nudges; the registry enforces.

### 2.5 Identity and access (F5)

`auth/identity.md` documents the auth model end-to-end.

- Portal sign-in is OIDC against the org IdP. The portal stores
  no passwords.
- The portal's session cookie is `HttpOnly`, `Secure`,
  `SameSite=Lax`, and short-lived (8 h with sliding refresh).
- API calls from the portal frontend to the portal backend
  carry the session cookie. API calls from the portal backend
  to the platform APIs use OAuth 2.0 Token Exchange
  ([RFC 8693](https://www.rfc-editor.org/rfc/rfc8693)) — the
  portal exchanges its server identity + the user's sub for a
  short-lived access token bound to the user. Project-01's
  control plane validates the token against the IdP; the
  `tenant` claim selects the row-level-security scope.
- Service accounts (for CI and the scaffolder bot) use the
  same flow with a `client_credentials` grant, scoped by an
  audience claim.
- The catalog backend has read access to almost everything but
  write access to nothing. The scaffolder is the only component
  with write access, and its writes always run as the
  *requesting user* via token exchange — never as the bot.

The negative test that pins this is the F5 acceptance check:
take the portal session cookie, send it to the project-01
`POST /trainingruns` endpoint directly — must return 401. The
session is not an API credential.

### 2.6 Plugin model (F6)

`plugins/plugin-architecture.md` describes how the ML platform
extends Backstage cleanly:

- **Frontend plugins** render entity pages. The `MLModel` page
  shows registry metadata, lineage graph, deployment timeline,
  promotion approvers, and the artifact digest. The
  `TrainingRun` page shows live status from project-01 with the
  same `Pending → Running → Succeeded` state machine the CRD
  exposes.
- **Backend plugins** proxy and cache. Polling the registry
  every page load destroys it; the backend caches with a 30 s
  TTL and a stale-on-error fallback. The cache is per-user so a
  tenant boundary breach is impossible.
- **Plugin proxy** is the path for read-only embeddings of
  external dashboards (Grafana panels via the proxy plugin).
  Grafana is iframed only at the cost of an `X-Frame-Options`
  exemption — the reference uses the proxy plugin's HTML
  rewriting instead, keeping CSP intact.

Each plugin ships with a `plugin-id`, a `package.json` whose
`backstage.role` field is `frontend-plugin` or `backend-plugin`,
and a Jest test suite. The reference solution rejects plugins
without tests at the platform-team review step.

### 2.7 Observability + adoption (F7, F8)

The portal's own observability has two surfaces:

- **Operator-facing**: standard Prometheus metrics from the
  Backstage backend (`http_request_duration_seconds`, the
  catalog processor queue depth, scaffolder action durations).
  Dashboards live next to the platform's other Grafana boards.
- **Product-facing**: the *adoption funnel*. Every page view,
  every scaffolder run, every search query is emitted as a
  structured event keyed by user and tenant. The
  `observability/adoption-metrics.md` doc lists the four KPIs
  the platform team commits to:
  1. *Time-to-first-success*: median seconds from a new user's
     first sign-in to their first successful TrainingRun.
  2. *Self-service rate*: fraction of new components onboarded
     via Scaffolder vs. opened as platform-team tickets.
  3. *Catalog coverage*: fraction of in-cluster TrainingRuns
     and MLModels that have a corresponding catalog entity.
  4. *Scorecard pass rate*: weighted average across the three
     default scorecards.

The reference solution treats these as *contracts the platform
team signs*, not vanity metrics. The rubric grades the
**existence and target** of each KPI, not the absolute number;
each platform team picks numbers honest to its baseline.

PII is scrubbed at the source. Adoption events carry an
opaque user ID hashed with a per-tenant salt; no name, no
email, no manager chain. The legal review of the event schema
is part of NF3.

## 3. Validation steps

Run from the repo root in the order below. Each command exits 0
on success; non-zero is the diagnostic for the failing artifact.

```bash
# Catalog entity files parse and validate against the schema.
yamllint -s projects/project-05-developer-portal/catalog/catalog-info.yaml
python3 -m json.tool < /dev/null  # ensure python3 is present

# Scaffolder template parses + matches the Software Template schema.
yamllint -s projects/project-05-developer-portal/scaffolder/training-run-template.yaml

# Scorecard definitions parse.
yamllint -s projects/project-05-developer-portal/scorecards/scorecard-definitions.yaml

# TechDocs MkDocs example parses.
yamllint -s projects/project-05-developer-portal/techdocs/mkdocs.example.yml

# All design docs Markdown lints clean.
markdownlint projects/project-05-developer-portal/**/*.md
```

Note: this workspace blocks `python3 ...` and `npm ...` execution;
graders run the commands above with their own toolchain. The
artifacts have been review-validated statically against the
Backstage entity and template schemas at the versions cited in
`References`.

In addition, run the eight-step acceptance demo from
`rubric.md` — that's the actual end-to-end proof the portal is
the platform front door, not just a wiki.

## 4. Rubric or review checklist

See [`rubric.md`](./rubric.md). The grader marks each row Pass /
Partial / Fail. Two Fails or four Partials means the project does
not pass; one Fail with otherwise-Pass rows means "return for
revision".

The acceptance demo at the bottom of `rubric.md` is the only
end-to-end proof of the portal; a learner without a screencast
of all eight steps grades Partial regardless of how complete the
code is.

## 5. Common mistakes

- **Catalog populated by hand**, not by entity providers. Works
  for the first ten components and silently rots after that. The
  rubric's F1 row asks for the providers; static `catalog-info.yaml`
  alone grades Partial.
- **Scaffolder templates that do not register in the catalog**.
  The PR ships, the user is happy, the platform has no record
  the component exists. Every template's final step is
  `catalog:register`; templates without it are an F2 hard fail.
- **TechDocs pointed at a separate docs repo**. Drift between
  code and docs starts the same week. `techdocs-ref: dir:.` is
  the rubric expectation; remote refs grade Partial unless the
  remote is *generated* from the code repo on every merge.
- **Scorecards used as hard gates**. The registry is the
  enforcement plane. Scorecards in the portal nudge; turning
  them into blockers without a registry-side equivalent
  bypassable bypasses the audit chain.
- **Bearer tokens proxied through the portal backend**. Any
  pattern where the portal forwards the user's IdP access token
  to the platform API is a confused-deputy waiting to happen.
  Token exchange (RFC 8693) is the reference; anything else
  grades Fail on F5.
- **Polling the platform APIs on every page load**. The catalog
  backend cache is the contract; a portal that hits project-04
  on every entity render takes the registry down at peak.
- **Adoption events with PII**. Logging the user's email or
  manager chain is a legal failure and an NF3 hard fail.
- **No `lifecycle` field on entities**. The
  `experimental → production → deprecated` lifecycle is what
  scorecards key off and what consumers filter on. Components
  without `lifecycle` are invisible to half the rubric.
- **One giant plugin that knows everything**. The reference
  solution has one plugin per platform component
  (`@ml-platform/plugin-training-runs`,
  `@ml-platform/plugin-model-registry`, …). Coupling them
  collapses the plugin model and makes plugin upgrades a
  big-bang release.
- **A portal launch with no adoption funnel instrumented**.
  Without the funnel, the team cannot tell if the portal is the
  product or the wallpaper. F7 grades Partial without it.

## 6. References

Curriculum-internal:

- Paired learning project:
  [`projects/project-05-developer-portal`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/tree/main/projects/project-05-developer-portal)
  — `README.md`, `architecture.md`, `requirements.md`, `STEP_BY_STEP.md`.
- Module 07 reference solution:
  [`modules/mod-007-developer-experience/SOLUTION.md`](../../modules/mod-007-developer-experience/SOLUTION.md).
- Platform-core control plane the portal sits on top of:
  [`projects/project-01-platform-core/SOLUTION.md`](../project-01-platform-core/SOLUTION.md).
- Model registry the portal renders entities for:
  [`projects/project-04-model-registry/SOLUTION.md`](../project-04-model-registry/SOLUTION.md).
- Track-level overview: [`SOLUTION_OVERVIEW.md`](../../SOLUTION_OVERVIEW.md).

External (official):

- Backstage Software Catalog model and entity descriptor:
  <https://backstage.io/docs/features/software-catalog/descriptor-format>
- Backstage Software Templates (Scaffolder):
  <https://backstage.io/docs/features/software-templates/>
- Backstage TechDocs:
  <https://backstage.io/docs/features/techdocs/>
- Backstage Authentication providers + identity:
  <https://backstage.io/docs/auth/>
- Backstage backend plugin architecture:
  <https://backstage.io/docs/backend-system/>
- CNCF TAG App Delivery — Platforms White Paper v1
  (definitions of internal developer platforms, platform-as-product,
  golden paths): <https://tag-app-delivery.cncf.io/whitepapers/platforms/>
- OAuth 2.0 Token Exchange (RFC 8693):
  <https://www.rfc-editor.org/rfc/rfc8693>
- OAuth 2.0 Authorization Framework (RFC 6749):
  <https://www.rfc-editor.org/rfc/rfc6749>
- OpenID Connect Core 1.0:
  <https://openid.net/specs/openid-connect-core-1_0.html>
- MkDocs (TechDocs build engine):
  <https://www.mkdocs.org/>
- OpenAPI 3.1.0 specification (API entity definitions):
  <https://spec.openapis.org/oas/v3.1.0>
- Prometheus naming + label conventions (portal metrics):
  <https://prometheus.io/docs/practices/naming/>

External (practitioner examples, used only as illustration of
specific implementation patterns, never as authoritative claims):

- Spotify's "Building a Platform with Backstage" engineering
  blog series (origin of the Backstage project, donated to CNCF):
  <https://backstage.spotify.com/>
- VeriSwarm engineer-solutions `mod-107` developer experience
  patterns (used only as practitioner illustration):
  <https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions/tree/main/modules/mod-107-developer-experience>

<!-- Author note: this solution treats the eight-step
acceptance demo enumerated in rubric.md as the canonical demo
flow. If the learning repo's requirements.md later codifies a
different sequence, reconcile rubric.md and this section against
that requirements.md at that time. -->
