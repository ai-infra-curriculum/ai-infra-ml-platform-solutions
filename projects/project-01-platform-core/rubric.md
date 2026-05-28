# Grading rubric -- project-01-platform-core

Graders mark each row Pass / Partial / Fail. The rule of thumb:
**two Fails or four Partials means the project does not pass; one
Fail with otherwise-Pass rows means "return for revision".** Each
row maps to one curated artifact in this directory; the artifact
is the bar.

## Functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| F1 | Higher-order primitive API | `Tenant`, `ResourceClaim`, and `TrainingRun` are first-class resources, not thin wrappers over K8s objects. Users do not write Pod specs, NetworkPolicies, or ResourceQuotas; the platform does. Submission references `control-plane/openapi.yaml`. |
| F2 | Idempotent writes | Every POST requires `Idempotency-Key`; a duplicate call inside the 24 h window returns the original response, not a new resource. A reused key with a different body returns **409**. Storage is the `idempotency_keys` table in `control-plane/schema.sql`. |
| F3 | OpenAPI 3.1 contract | Spec-first, not spec-after. The FastAPI app generates routes from `control-plane/openapi.yaml`; `redocly lint` and `openapi-spec-validator` both pass; the SDK in `mod-002/ex-04` is generated from this same spec. |
| F4 | Operator reconciliation | CRDs from `operator/crds.yaml` are admission-validated. The reconciler is idempotent (ten runs == one run), emits audit rows only on phase transitions (not per reconcile), and creates Pods with the security context shown in `operator/reconcile.py`. |
| F5 | Multi-tenancy is platform-owned | Every namespace bundle from `multi-tenancy/namespace-template.yaml` is applied when a tenant goes Active: ResourceQuota, LimitRange, default-deny NetworkPolicies, RoleBinding. Tenants never have to write these themselves. Cross-tenant lookups via the API return **404**, not 403. |
| F6 | Tamper-evident audit chain | `audit/schema.sql` runs cleanly; the BEFORE INSERT trigger refuses to honor a caller-supplied `prev_hash` / `entry_hash`; UPDATE and DELETE both raise. `verify_audit_chain(start, end)` returns zero rows on an honest chain, and the affected `seq` plus the recomputed hash on a tampered one. |
| F7 | OIDC + RBAC identity | The platform accepts only OIDC-issued bearer tokens. Group claims drive RBAC; service-to-service auth uses short-lived tokens (SPIFFE or workload-identity). There are no static long-lived credentials shipped with the platform. References `mod-009/ex-01`. |
| F8 | Self-service onboarding | A new team is from "zero account" to "first TrainingRun submitted" in <= 10 minutes via the platform CLI (`mod-007/ex-02`). Time-to-first-TrainingRun is the platform team's headline DX metric. |

## Non-functional

| ID | Requirement | What "Pass" looks like |
|---|---|---|
| NF1 | Reproducibility | `make up` brings the control plane + operator + Postgres + an OIDC stub up on a fresh kind/k3d cluster. `.env.example` enumerates required config. |
| NF2 | Testing | Unit + integration tests; one end-to-end acceptance run covers the 8 steps in §Acceptance demo below; chain-verify in CI nightly. |
| NF3 | Security | Images non-root; pods drop `ALL` capabilities; `automountServiceAccountToken: false`; restricted Pod Security Admission enforced on every tenant namespace; OpenAPI spec auto-generated. |
| NF4 | Documentation + runbook | Onboarding guide for new platform teams; runbook for the three failure modes (control-plane down, operator queue stalled, audit verify break). The tenant-deprovision drill has been run, not just documented. |

## Acceptance demo checklist

Each step is one screencast cut. A learner who can demonstrate all
eight on one screencast gets the rubric's Pass on `Acceptance
demo`. Skipping the screencast is a Partial regardless of how
complete the code is.

1. [ ] `platform tenant create team-alpha --group=alpha-mlops`
       returns 201 with the new tenant; the operator-created
       namespace `tenant-team-alpha` appears with the quota +
       NetworkPolicies bundle from `multi-tenancy/namespace-template.yaml`.
2. [ ] `platform claim create team-alpha --cpu=32 --memory=128Gi --gpu=4`
       returns 201 (or 202 if over base budget); the matching
       ResourceQuota in the namespace shows the new limits.
3. [ ] `platform run submit team-alpha --image=...` returns 202;
       the operator creates the Pod; phase transitions
       Pending -> Scheduled -> Running -> Succeeded.
4. [ ] **Idempotent replay**: replaying step 3 with the same
       `Idempotency-Key` returns 200 with the original run, not a
       new one.
5. [ ] **Cross-tenant 404**: a token scoped to `team-beta` asking
       for `team-alpha`'s tenant returns 404, not 403.
6. [ ] **Default-deny works**: a `kubectl exec` from `team-alpha`
       to `team-beta`'s pods (by IP) times out.
7. [ ] **Audit verify clean**: `POST /v1/audit:verify` with
       `start_seq=1, end_seq=max(seq)` returns `breaks: []`.
8. [ ] **Audit verify breaks**: a manual `UPDATE audit_log SET
       payload = ...` (against the policy trigger; admin only)
       fails with the "append-only" error; if the row is forced in
       via superuser, the next verify call returns the broken
       `seq` and the recomputed hash.

Steps 7 and 8 together are the proof that F6 is real. A learner
who only ships step 7 has not demonstrated tamper detection; only
that the happy path runs.
