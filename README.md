# AI Infrastructure ML Platform Engineer — Solutions Repository

> **Status**: ✅ **Published** — 9 modules, 45 reference solutions live as of 2026-05. Project-layer build-out is ongoing.
> Content is AI-assisted and undergoing human review; treat as a learning reference and cross-check with primary sources.

Reference implementations for the **AI Infrastructure ML Platform Engineer** learning track ([ai-infra-ml-platform-learning](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning)).

For the authoritative list of what is covered (including cross-references to the Engineer track), see [`SOLUTIONS_INDEX.md`](./SOLUTIONS_INDEX.md).

## What's new — 2026-05-27

Module-level `SOLUTION.md` design-rationale docs for all 9 modules (`mod-001-platform-fundamentals` through `mod-009-security-governance`). Each doc explains *why* the platform-engineering reference implementations are shaped the way they are — the API contracts, multi-tenancy primitives, governance patterns that scale across many teams. Audit score: 54 → 66.

## What's in here

- **`modules/`** — Per-exercise solutions, one directory per exercise. Modules in scope today:
  - `mod-001-platform-fundamentals`
  - `mod-002-api-design`
  - `mod-003-multi-tenancy-resources`
  - `mod-004-feature-store`
  - `mod-005-workflow-orchestration`
  - `mod-006-model-management`
  - `mod-007-developer-experience`
  - `mod-008-observability`
  - `mod-009-security-governance`
- **`projects/`** — Capstone-grade reference architectures. This layer is still being built out; expect more depth here over time.
- **`guides/`** — Implementation notes and cross-cutting walkthroughs.
- **`resources/`** — Shared references used across modules.
- **[`LEARNING_GUIDE.md`](./LEARNING_GUIDE.md)** — Recommended path through the solutions.
- **[`CURRICULUM.md`](./CURRICULUM.md)** — Mapping back to the learning track's module structure.

## How to use this repository

1. **Attempt the exercise yourself first** in the learning repo.
2. **Compare your approach** to the solution. Look at API surface, multi-tenancy boundaries, and observability hooks — not just whether the code runs.
3. **Read the linked Engineer-track exercise** when the topic overlaps. The `SOLUTIONS_INDEX.md` cross-reference table calls out where the engineer-solutions repo has the deeper hands-on coverage.
4. **Extend the solution** with the bonus challenges or by hardening the production surface (rate limiting, SLOs, cost attribution).

## Prerequisites

You should have completed (or be working through):

- The [Engineer track](https://github.com/ai-infra-curriculum/ai-infra-engineer-learning) and the [MLOps track](https://github.com/ai-infra-curriculum/ai-infra-mlops-learning).
- Production Kubernetes experience and comfort with multi-tenancy patterns (namespaces, quotas, network policy).

**Experience level**: Advanced (4–6 years engineering, 2+ years in ML infrastructure).
**Time commitment**: 600–700 hours across the track.

## Learning objectives

The ML Platform Engineer track prepares you to:

- Design and build complete ML platforms from scratch.
- Enable many data scientists to deploy models independently and safely.
- Implement multi-tenant ML infrastructure with hard and soft isolation.
- Build platform APIs and SDKs that scale beyond a single team.
- Manage costs across teams with attribution and quotas.
- Operate platform-grade SLOs for training, serving, and feature data.

## Related repositories

- [ai-infra-ml-platform-learning](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning) — companion learning materials.
- [ai-infra-mlops-learning](https://github.com/ai-infra-curriculum/ai-infra-mlops-learning) — recommended prerequisite track.
- [ai-infra-engineer-solutions](https://github.com/ai-infra-curriculum/ai-infra-engineer-solutions) — overlapping deep dives referenced in `SOLUTIONS_INDEX.md`.
- [ai-infra-principal-engineer-learning](https://github.com/ai-infra-curriculum/ai-infra-principal-engineer-learning) — natural progression for platform leads.

## Known limitations

- **Content is AI-assisted and partly under human review.** Validate vendor-specific claims (Kueue, Kubeflow, Ray, SageMaker, Vertex) against current upstream docs before adopting patterns in production.
- The project layer is still shallower than the module layer; expect more capstone build-out in future passes.
- Some `Dockerfile`/`compose`/`k8s` manifests are illustrative rather than fully runnable in your environment without configuration.

## Contributing

Issues, corrections, and pull requests are welcome. See [`CONTRIBUTING.md`](./CONTRIBUTING.md). The most useful contributions right now are:

- Fixing factual errors, especially upstream-vendor-specific claims.
- Filling out the `projects/` layer with end-to-end reference architectures.
- Adding `SOLUTION.md` notes that explain the *why* behind each reference implementation.

## License

See [`LICENSE`](./LICENSE).

---

**Last updated**: 2026-05-25
**Maintainer**: AI Infrastructure Curriculum Project
