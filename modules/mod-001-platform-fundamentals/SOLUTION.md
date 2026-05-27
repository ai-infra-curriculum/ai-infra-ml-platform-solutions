# SOLUTION — Module 01: Platform Fundamentals

> Read this *after* the per-exercise solutions. This file explains
> the cross-exercise design rationale: why these five exercises in
> this order, what discipline the module collectively teaches, and
> the trade-offs the reference solutions accept.

## What the module is really teaching

A platform team's deliverable is not "infrastructure." It is **a
contract that other engineering teams build against**. Before any
of the technology choices in later modules matter, the platform
team has to decide:

- What is the unit of provisioning we hand back?
- Who can ask for what, and how do we know it was them?
- When the contract is wrong, how do we change it without breaking
  every consumer?
- When two consumers want incompatible things, who arbitrates?

Module 01 is shaped to make these questions land before the
engineer falls into framework choices.

## Exercise-by-exercise rationale

### Ex-01 — Design an API for resource provisioning

The OpenAPI document, not the implementation, is the artifact. The
reference spec deliberately uses:

- **Tenant in a header**, not in the path. Eliminates one
  combinatorial axis from the route table.
- **Idempotency-Key on POST**. Provisioning is expensive; double-
  posts under retry must not double-provision.
- **Cursor pagination**, not offset. Cursor tolerates list mutation
  mid-query.
- **`:extend` action verb** (Google-style colon syntax). Non-CRUD
  actions belong on a separate path shape that signals "this is
  not just a write."

The point: API shape is forever. Picking sloppy now creates the
deprecation work that consumes mod-002.

### Ex-02 — Namespace isolation in Kubernetes

This is the *minimum credible* isolation primitive. The exercise
isn't asking for Pod Security Admission or NetworkPolicies (those
come in mod-003). It's asking the engineer to internalize that
*namespace is not a security boundary* — it's a naming + RBAC +
quota boundary. Treating it as a security boundary is the most
common multi-tenancy bug in junior platform teams.

### Ex-03 — Resource quota management

Quotas are how the platform forces engineering teams to make their
own resource budgeting decisions. Without quotas, every team's
defaults expand until the cluster is full and the platform team
spends its time arbitrating. With quotas, the consumers do the
budgeting.

The reference solution sets `limits.cpu` and `limits.memory`
quotas at the namespace level **with no default LimitRange**. This
forces every Deployment to specify requests + limits explicitly,
which surfaces the missing-resource-request bug before deploy.

### Ex-04 — Build a simple plugin system

Platforms that don't have a plugin model become bottlenecks: every
new training framework, every new feature-store backend, becomes
a change the platform team has to ship. The plugin model lets
consumers extend the platform without depending on the platform
team's release calendar.

The reference plugin shape is intentionally **minimal**: a Python
entry-point group, a typed Protocol the plugin must satisfy, and a
hot-reloadable registry. Three-line `setup.py` to register; no
plugin SDK to learn. This is the floor; later modules show how the
shape grows as the platform matures.

### Ex-05 — Case-study analysis: Michelangelo / Metaflow

The capstone of the module is **not building anything**; it is
reading the two canonical platform-design papers and writing a
structured analysis. The reference solution's analysis follows the
template:

1. What problem did the team solve?
2. What technical decisions did they make?
3. Which decisions would *not* survive a re-derivation today?
4. What did they get wrong, and how did they recover?

Junior platform engineers under-read. The point of ex-05 is to set
the expectation that **reading other people's platforms** is the
single highest-leverage activity in this discipline.

## Design decisions the module shares

- **OpenAPI specs are version-controlled artifacts**, not generated
  output. The spec is the source of truth.
- **Kubernetes primitives directly**, not abstractions over them.
  An ML platform engineer must understand the underlying objects
  before adopting any abstraction.
- **No platform-specific code samples** in the exercises. The
  solutions use stock Python + standard Kubernetes manifests, on
  purpose. Vendor SDKs come in later modules.

## Common mistakes graders see

1. **Path-segmented tenancy**. `/tenants/{id}/resources` looks
   tidy until you have ten resource types and forty routes that
   all need the tenant check.
2. **Treating namespace as a security boundary**. Namespace
   provides naming + RBAC + quotas. NetworkPolicy provides
   isolation.
3. **No `LimitRange`**, no `ResourceQuota`. Free-for-all is the
   default and the worst.
4. **Plugin systems with twenty hooks**. Start with one. Add the
   second when the second is forced. Two hooks is enough for the
   first ten plugins.
5. **Case-study writeup with no critique section**. Reading
   uncritically is reading badly.

## Related curriculum touchpoints

- `engineer/mod-104` — the Kubernetes primitives this module
  builds on.
- `ml-platform/mod-002` — API design that picks up where ex-01
  stops.
- `ml-platform/mod-003` — multi-tenancy that hardens the
  namespace boundary set up here.
- `architect/mod-301` — what an enterprise-scale version of the
  same platform looks like.
