# Observability + adoption metrics

The portal has two distinct observability surfaces:

- **Operator-facing**: standard Prometheus metrics, alert
  rules, and Grafana dashboards. Answers "is the portal
  healthy?"
- **Product-facing**: the adoption funnel. Answers "is the
  portal *adopted*?"

The product-facing surface is what makes the portal a product
instead of a wiki. F7 grades its existence and targets.

## Operator-facing

The Backstage backend exposes `/metrics` (Prometheus
text-exposition format). Metric naming follows the upstream
[Prometheus conventions](https://prometheus.io/docs/practices/naming/).

The minimum set the rubric expects:

| Metric | Type | Allowed labels |
|---|---|---|
| `http_request_duration_seconds` | histogram | method, route, status |
| `catalog_processor_queue_depth` | gauge | provider |
| `catalog_entities_total` | gauge | kind, namespace |
| `scaffolder_action_duration_seconds` | histogram | template, action, outcome |
| `techdocs_build_duration_seconds` | histogram | entity_kind, outcome |
| `auth_token_exchange_total` | counter | audience, outcome |

Forbidden labels (cardinality discipline, same rule as
project-04 §F8):

- Per-entity `name` on `catalog_entities_total` — explodes the
  cardinality. Use `kind` + `namespace`.
- Per-user `sub` on any metric. PII + cardinality.
- Per-request path on `http_request_duration_seconds` — use the
  route template, not the resolved path.

One Grafana dashboard ships with the portal. Panels:

- p50/p95/p99 portal request latency.
- Catalog processor queue depth + ingestion error rate.
- Scaffolder action error rate, faceted by template.
- TechDocs build failure rate.
- Auth token-exchange error rate.

Alerts:

- Catalog processor queue depth > 1000 for 10 min → page.
- Scaffolder action error rate > 5 % over 30 min → page.
- p95 portal latency > 2 s for 15 min → ticket (not page).

## Product-facing — adoption funnel

Every page view, scaffolder run, and search query is emitted as
a structured event:

```json
{
  "event_id": "<uuid>",
  "event_type": "scaffolder_template_completed",
  "ts": "2026-05-29T12:00:00Z",
  "user_id_hashed": "<hex>",
  "tenant": "team-recs",
  "template_id": "training-run-from-scratch",
  "outcome": "success"
}
```

The four KPIs the platform team commits to:

### 1. Time-to-first-success (TTFS)

Median seconds from a new user's *first sign-in* to their *first
successful TrainingRun*. Calculated weekly.

- Source events:
  `auth_signin_first_time(user)` →
  `training_run_completed(user, outcome=success)`.
- Target: a *number the team picks honestly* given the baseline,
  with a revisit cadence. The rubric grades the existence and
  reasonableness of a target, not the absolute number.
- Watch for: TTFS rising over time. New users in the recent
  cohort are the canary for new DX regressions.

### 2. Self-service rate

Fraction of new components onboarded via Scaffolder vs. opened
as platform-team tickets in the same window.

- Source events:
  `scaffolder_template_completed(outcome=success)` ÷
  `(scaffolder_completed + platform_ticket_opened.kind=onboarding)`.
- Target: a self-service rate **trend** toward 1.0 over time.
  The reference solution does not commit to a specific number;
  it commits to the trend.

### 3. Catalog coverage

Fraction of in-cluster TrainingRuns and registered MLModels
that have a corresponding catalog entity.

- Source: comparison of the catalog state with project-01's CRD
  count and project-04's registry count.
- Target: ≥ 95 %. Below 95 % means the entity providers are
  failing silently somewhere — the cause is almost always a
  validator rejecting an upstream entity the providers don't
  report.

### 4. Scorecard pass rate

Weighted average across the three default scorecards, computed
per team and per tenant.

- Weight Platform Baseline 1×, Production Readiness 1.5×,
  Compliance 2× — the production and compliance bars matter
  more than the baseline.
- Target: ≥ 0.80 platform-wide, ≥ 0.95 for regulated tenants.

## Privacy + PII

PII is scrubbed at the source. The adoption event schema's
`user_id_hashed` is `HMAC-SHA256(user_sub, per_tenant_salt)`.
The salt is rotated annually; old hashes are not retroactively
correlated with new ones, by design.

Name, email, and manager chain are *never* in the event payload.
The legal review of the event schema is part of NF3.

## Where the funnel lives

The events are emitted via the portal backend to the same log +
metrics pipeline the platform's other components feed. The four
KPIs are computed by a nightly job and surfaced on a dedicated
Grafana dashboard.

## References

- Prometheus metric and label naming:
  <https://prometheus.io/docs/practices/naming/>
- CNCF Platforms White Paper §"Measuring success":
  <https://tag-app-delivery.cncf.io/whitepapers/platforms/>
- DORA's "platform engineering" research note on adoption
  metrics:
  <https://dora.dev/research/platform-engineering/>
