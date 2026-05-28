Twelve artifacts authored under `projects/project-01-platform-core/`, totaling ~2.7k lines. Summary of what was written:

**Top-level docs**
- `README.md` — landing page with artifact map and what's intentionally not here
- `SOLUTION.md` — 6-section AICG output contract (overview, worked answer, validation, rubric, common mistakes, references)
- `STEP_BY_STEP.md` — 9 phases mirroring the learning repo's build sequence
- `rubric.md` — F1–F8 + NF1–NF4 + 8-step acceptance demo

**audit/** (referenced by project-04)
- `schema.sql` — hash-chained `audit_log` with genesis row, BEFORE INSERT trigger that overwrites caller-supplied hashes, immutable triggers blocking UPDATE/DELETE, `verify_audit_chain(start, end)` + `verify_audit_chain_all()`
- `verify.py` — Python mirror of the SQL verifier; canonical-form alignment with JSONB's text serialization (sorted keys, `", "` / `": "` separators)

**control-plane/**
- `openapi.yaml` — OpenAPI 3.1 spec: tenants, ResourceClaims, TrainingRuns, audit read + verify; mandatory `Idempotency-Key`, cursor pagination, colon-action verbs (`:cancel`, `:verify`)
- `schema.sql` — `tenants`, `resource_claims`, `training_runs`, `idempotency_keys` + per-tenant row-level security policies
- `training_runs.py` — reference handler showing the tenant-scope/idempotency/audit-emit pattern in a single transaction

**operator/**
- `crds.yaml` — `TrainingRun` + `ResourceClaim` CRDs with structural OpenAPI v3 schemas, printer columns, status subresource
- `reconcile.py` — reconcile-loop skeleton with terminal-phase guard, one-audit-per-transition, locked-down Pod manifest

**multi-tenancy/**
- `namespace-template.yaml` — per-tenant bundle: Namespace (PSA: restricted), LimitRange, ResourceQuota, four NetworkPolicies (default-deny ingress/egress + intra-namespace + platform-services), Role/RoleBinding, workload ServiceAccount

The audit-chain artifacts close project-04's existing references to `project-01-platform-core/audit/schema.sql` and `verify_audit_chain()`. All artifacts are statically valid against the validators listed in `SOLUTION.md` §3.
