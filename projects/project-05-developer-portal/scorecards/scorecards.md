# Scorecards

Scorecards are the portal's advisory bar. They nudge owners
toward the platform's expectations; they do **not** hard-gate.
Anything that must hard-gate (signed model required for
production deployment) hard-gates at the registry — see
project-04 §F3.

The portal ships three default scorecards. Each one is a set of
checks, scored 0/1, rolled up to a fraction (`7/8`) on the
entity page and aggregated to a team-level dashboard.

## Platform Baseline (applies to all `Component` and `MLModel`)

The bar every component must clear.

| Check | Pass when |
|---|---|
| Has an owner | `spec.owner` resolves to an existing `Group` |
| Has TechDocs | `metadata.annotations['backstage.io/techdocs-ref']` is set and the doc URL returns 200 |
| Has lifecycle | `spec.lifecycle` is set to a non-empty value |
| Has tags | `metadata.tags` has at least one value |
| Has system | `spec.system` resolves to an existing `System` |
| Has an API definition (if a service) | `spec.providesApis` is non-empty for `spec.type: service` |
| Repo has CI | The repo has at least one GitHub Actions workflow that ran in the last 14 days |
| Repo green | The most-recent default-branch CI run is green |

## Production Readiness (applies to entities with `lifecycle: production`)

Required for promotion to production.

| Check | Pass when |
|---|---|
| Has an SLO | `metadata.annotations['slo.example.com/availability']` is set |
| Has a runbook | `metadata.annotations['runbook.example.com/url']` resolves |
| Has a pager target | `metadata.annotations['pagerduty.com/service-id']` resolves |
| Alerts wired | Prometheus rules referencing the SLO exist in the team's namespace |
| Dependencies declared | `spec.dependsOn` covers every cross-system dependency |

## Compliance (applies to `MLModel` whose tenant is `regulated: true`)

Required for regulated tenants' production models.

| Check | Pass when |
|---|---|
| Model signed | The registry record has a verified Cosign signature; signing identity matches `ExpectedIdentity` from project-04 |
| Lineage to documented dataset | `spec.dataset` resolves to a `Dataset` with `lifecycle: production` |
| Promotion approver recorded | The registry record's last `Registered → Production` promotion has an approver |
| Approver is not the registering identity | (Self-approval rejected — see project-04 §rubric F3) |
| Audit chain verified | `verify_audit_chain()` over the model's promotion events returns clean |

## Remediation

Every failing check ships with a `remediationLink`. A failing
check without a link is a tax on the user; the rubric grades
links as part of F4.

Remediation links resolve to:

- TechDocs runbook pages for "how do I add an SLO?", "how do I
  wire alerts?", etc.
- The platform team's onboarding checklist for whole-component
  problems ("no CI", "no owner").
- Project-04's signing guide for compliance failures.

## Scoring discipline

- A failing optional check counts the same as a failing required
  check inside a scorecard — there are no "optional" checks at
  the scorecard level. If a check isn't worth scoring, remove
  it.
- Scorecards are computed on a 15-minute tick by a backend job.
  Real-time scoring is a feature people regret.
- A scorecard with 0/N is shown as red, not greyed-out. Empty
  catalogs hide problems; explicit red surfaces them.

## References

- Backstage scorecard / TechInsights plugin (one of the
  upstream open-source implementations):
  <https://backstage.io/docs/features/tech-insights/>
- CNCF Platforms White Paper §"Measuring success":
  <https://tag-app-delivery.cncf.io/whitepapers/platforms/>
- Project-04 signing identity:
  [`projects/project-04-model-registry/signing/verify.py`](../../project-04-model-registry/)
