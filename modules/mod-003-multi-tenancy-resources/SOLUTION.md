# SOLUTION — Module 03: Multi-Tenancy & Resource Management

> Read after the per-exercise solutions. Explains the cross-
> exercise design rationale.

## What the module is really teaching

Multi-tenancy is the single hardest discipline in platform
engineering, and the one platform teams get wrong most often.
The reference exercises are shaped around the three failure
modes that bite real platforms:

1. **Noisy neighbors** — one tenant's runaway job starves the
   others.
2. **Lateral movement** — a compromise in one tenant reaches
   another.
3. **Unclear ownership** — when costs explode, no one knows whose
   job did it.

Each of the five exercises addresses one of those, with the last
one (cost attribution) closing the loop the first three create.

## Exercise-by-exercise rationale

### Ex-01 — Namespace-per-team setup

Namespace is the **organizational** boundary, not the security
boundary. The reference solution ships:

- One namespace per team (not per environment, not per project).
- A `Team` label on every object inside the namespace.
- A `team-platform` ServiceAccount that the team's CI uses to
  deploy.
- Defaults via `LimitRange` so resources without explicit
  requests get sane minimums.

Why namespace-per-team and not namespace-per-environment? Because
environments are configuration; teams are people. People are
forever; environments rotate.

### Ex-02 — ResourceQuota enforcement

Quotas constrain a tenant's total cluster resource consumption.
The reference numbers:

- CPU + memory quotas sized at **80% of the team's purchased
  budget** — gives headroom for bursts within the budget.
- Storage class quotas separated by class (gp3 vs io2 — io2 is
  much more expensive, can't be lumped together).
- Object count quotas (max Pods, max Services, max ConfigMaps) to
  prevent runaway controller bugs from exhausting the API server.

Quotas without object-count limits is the bug-of-the-quarter
report. A misconfigured Operator that creates a million ConfigMaps
takes down the entire cluster, not just the offending namespace.

### Ex-03 — NetworkPolicy isolation

This is the **actual security boundary**. The reference policy
shape:

- Default-deny all ingress in every team namespace.
- Allow-list specific tenant-to-platform-service flows
  (model registry, feature store, monitoring scrape).
- Allow-list intra-namespace pod-to-pod (otherwise tenants can't
  build their own multi-pod services).
- Allow-list egress to known external endpoints (PyPI mirror,
  internal Git, etc.), default-deny everything else.

NetworkPolicy is the single highest-leverage object in a multi-
tenant cluster. Most platforms ship without it; most platforms
have lateral-movement vulnerabilities.

### Ex-04 — Fair-share scheduling with Volcano

Quotas are *hard caps*. Fair-share is *soft prioritization*: when
the cluster is contested, who wins. The reference uses Volcano (or
Kueue) with:

- A `Queue` per team, weight = budget share.
- `PriorityClass` per workload tier (interactive notebook > batch
  job > backfill).
- Gang scheduling for distributed training so half a job doesn't
  block waiting for the other half.

Without fair-share, the team with the most jobs wins. With it,
the team with the highest *weighted* job-need wins.

### Ex-05 — Cost attribution pipeline

The capstone. Cost attribution requires:

- Per-pod resource accounting (CPU-hours, memory-GB-hours,
  GPU-hours, storage-GB-hours).
- A labeling discipline (cost-center label on every object,
  enforced by Kyverno admission policy).
- A rollup pipeline (Airflow / scheduled job) producing the
  monthly per-team cost report.
- A query interface so teams can see *their* cost without seeing
  others'.

A platform team that can't answer "how much did Team X spend last
month?" cannot defend its own budget.

## Cross-exercise design decisions

- **Namespace == team, period.** Don't reuse the boundary for
  other purposes.
- **Default-deny everything**; allow-list specific flows.
- **Labels are not optional.** Enforce via admission webhook.
- **Cost attribution is a platform deliverable**, not an
  add-on.

## Common mistakes graders see

1. **Namespace as security boundary** without NetworkPolicy.
2. **Quotas without object-count limits**. A million Pods can
   land on you.
3. **NetworkPolicy in audit-only mode forever**. Audit teaches
   you what flows exist; enforce is what blocks the bad ones.
4. **Fair-share scheduling without gang scheduling**.
   Distributed training breaks subtly.
5. **No cost-center label enforcement**. The attribution pipeline
   silently mis-attributes everything.

## Related curriculum touchpoints

- `engineer/mod-104/ex-04-k8s-cluster-autoscaler` — scaling
  decisions interact with quotas.
- `ml-platform/mod-008` — observability that surfaces tenant-
  level signals.
- `security/mod-003` — the security-track version of the same
  isolation discipline.
- `architect/mod-301` — multi-tenancy at enterprise scale.
