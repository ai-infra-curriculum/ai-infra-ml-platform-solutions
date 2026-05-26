# SOLUTION_OVERVIEW — ML Platform Engineering Track

> Read this *after* skimming the module solutions. This file explains
> the design philosophy across the ml-platform track. For the per-exercise
> content index, see [`SOLUTIONS_INDEX.md`](./SOLUTIONS_INDEX.md).

## What this track is teaching

An ML platform is **not** "Kubernetes plus ML tools." It is a
*product*: data scientists and ML engineers are the users, the
platform is the product, and the platform team is the product team.
Every architectural decision in this track is best read through that
lens — "does this make our users' work easier, faster, safer, or
more attributable?"

The solutions here are unified by one principle:

> The platform exposes higher-order primitives ("submit a training
> run", "register a model", "deploy v2 to staging"), not Kubernetes
> objects. If users are writing pod specs, you do not have a
> platform; you have a Kubernetes cluster with extra steps.

## How the modules relate

| Module | Role in the track |
|---|---|
| `mod-001-platform-fundamentals` | Foundational vocabulary: what a platform *is*, multi-tenancy, abstraction design. |
| `mod-002-api-design` | The platform's contract with its users. Versioning, deprecation, evolvability. |
| `mod-003-multi-tenancy-resources` | Tenancy patterns from soft (RBAC) to hard (cluster-per-team). Quotas, queues, fair share. |
| `mod-004-feature-store` | The single largest source of training/serving skew, addressed with a unified store. |
| `mod-005-workflow-orchestration` | Pipelines as a platform primitive, not a per-team concern. |
| `mod-006-model-management` | Registry, lineage, governance integrated. |
| `mod-007-developer-experience` | The thing that separates *used* platforms from *unused* ones. |
| `mod-008-observability` | Platform-grade SLOs across training, serving, features. |
| `mod-009-security-governance` | The compliance + security surface the platform owns on behalf of users. |

Modules 001, 002, and 007 are non-negotiable foundations. The rest
can be sequenced based on what your environment already has.

## How a "solution" looks in this track

A platform-engineering solution typically demonstrates:

- **A higher-order primitive** — the user-facing concept (e.g.,
  "TrainingRun", "ServedModel").
- **The control-plane implementation** — what translates the
  primitive into infrastructure.
- **The contract** — the API or SDK the user actually programs
  against.
- **The boundaries** — what the platform owns vs. what the user owns.

A solution that only shows infrastructure is incomplete for this
track. Without the user-facing primitive and the contract, it's a
deployment, not a platform.

## Cross-cutting principles

### Self-service is the success metric

A platform that requires a ticket-and-wait interaction for common
operations is failing its product mission, regardless of how
technically elegant its infrastructure is.

### Tenant isolation is a property of the platform, not a property of
each application

Application-layer multi-tenancy puts the same compliance question on
every application team. Platform-layer multi-tenancy answers it once.

### Cost attribution from day one

Per-tenant cost visibility cannot be retrofitted onto a platform that
wasn't designed for it. The solutions embed `tenant` labels, run-IDs,
and OpenCost integration from the foundation modules.

### Backward compatibility is non-optional for any user-facing
contract

The platform's API is depended on by every team. Breaking it breaks
all of them. The `mod-002-api-design` solutions show versioning,
deprecation, and migration as core platform-engineering disciplines.

### Observability is the platform's own product responsibility

Platforms that expose raw infrastructure metrics to users push
debugging cost onto them. Platforms that expose
*platform-meaningful* signals (training-run state, feature freshness,
serving SLO compliance) absorb that cost on behalf of users.

## Where the projects live

This repo is module-focused by design. The project layer of the
ml-platform track is still being built out (see the org-level README's
"Missing / Incomplete Content" section). For end-to-end platform
build-outs, the closest current reference is
[`architect-solutions/projects/project-301-enterprise-mlops/`](../ai-infra-architect-solutions/projects/project-301-enterprise-mlops/).

## Cross-references

| Topic | Deeper reference |
|---|---|
| Engineering-level implementation depth | `engineer-solutions/mod-104` through `mod-110` |
| Per-overlap deep dive (cross-ref table) | [`SOLUTIONS_INDEX.md`](./SOLUTIONS_INDEX.md) |
| Architecture-level reasoning for enterprise platforms | `architect-solutions/projects/project-301/SOLUTION.md` |
| Multi-cloud platform considerations | `architect-solutions/projects/project-302/SOLUTION.md` |
| Senior-engineer-level platform components | `senior-engineer-solutions/projects/project-204-k8s-operator/SOLUTION.md` |

## Production gap checklist (track-wide)

A reader who has worked through every module still needs the
following to build a real platform:

- [ ] A staffed platform team with product-management discipline
- [ ] An internal user-feedback loop (surveys, design partners,
      adoption metrics)
- [ ] An SLO framework with measurable per-tenant commitments
- [ ] Cost-attribution that finance accepts
- [ ] A versioning + deprecation contract published and respected
- [ ] An on-call rotation owning *platform* incidents, not just
      infrastructure incidents
- [ ] Compliance-control coverage matrix for regulated tenants

## Time budget for the track

- **Surveyor read**: 1 week.
- **Practitioner read**: 3–4 months (work the exercises, build a
  small platform on top).
- **Adoption read**: 12–24 months to take an org from
  "Kubernetes + scripts" to "self-service ML platform".
