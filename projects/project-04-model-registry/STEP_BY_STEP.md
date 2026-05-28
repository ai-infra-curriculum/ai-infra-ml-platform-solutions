# STEP_BY_STEP -- Project 04 Solution

Solution-side walk-through. The learning repo's
[`STEP_BY_STEP.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-04-model-registry/STEP_BY_STEP.md)
prescribes ten phases over ~70 hours; this document mirrors those
phases and pins what each one yields *in this solution's terms*. Use
it to sequence your build and to know when each phase is "done
enough" to move on.

Each phase below points at the artifact in this directory that
captures its contract. Build implementations to meet those
contracts; the curated files are the rubric.

## Phase 0 -- Setup (1-2 h)

**Yield**: a kind/k3d cluster, PostgreSQL, MinIO (or any S3-compatible
storage), the repo skeleton from the learning `STEP_BY_STEP.md` §0.

Solution-side check: `kubectl get nodes` Ready; `psql -d registry -c '\dt'`
shows zero tables; `aws --endpoint-url ... s3 ls` succeeds against MinIO.

## Phase 1 -- Data model + registry API (10-12 h)

**Yield**: `registry/schema.sql` migration applied; CRUD endpoints in
the FastAPI app behind `registry/openapi.yaml`; the list endpoint
filters by `status`, `training_data_version`, and `accuracy_gte`; a
PUT/PATCH on an existing `ModelVersion` returns **405**.

Pin: the `model_versions_immutable` trigger in `registry/schema.sql`.
The compliance bar -- "what model is in production right now,
deterministically" -- depends on this property being enforced *in
the DB*, not in the handler.

Done when:

```bash
psql -d registry -f registry/schema.sql --single-transaction --set ON_ERROR_STOP=1
openapi-spec-validator registry/openapi.yaml
psql -c "UPDATE model_versions SET artifact_uri = 's3://evil' WHERE id = '...'"
# -> ERROR: model_versions is immutable except for status
```

## Phase 2 -- Signature integration (5-6 h)

**Yield**: SDK signs on registration (Cosign keyless via OIDC);
signature blob stored alongside the artifact in object storage;
`signing/verify.py`-style verification function invoked at the
promotion and deployment paths.

Pin: `signing/verify.py`. The `ExpectedIdentity` dataclass is the
"no random signer" check; the function rejects on issuer or subject
mismatch even when the cryptographic signature itself is valid.

Reminder: verify at registration is **not** sufficient. F2 + the
common mistake in `SOLUTION.md` §5 require verification at *every*
promotion and at *every* deployment.

## Phase 3 -- Promotion gates (10-12 h)

**Yield**: gate definitions in `gates/gates.yaml`; programmatic
evaluator in `gates/evaluate.py`; promotion API returns 202 with the
pending state when human approval is required; failed gate response
includes the failing gate's name and the evaluated value.

Pin: the `Decision` enum + `next_state` function. The state machine
is the single source of truth. Don't sneak transitions into the
handler.

Done when the four test cases pass:

- all gates passed -> 201 ALLOW.
- one threshold failed -> 422 with the failing gate name.
- signature failed -> 422 (no override available).
- human-approval pending -> 202 PENDING.

## Phase 4 -- Deployment + rollout (12-14 h)

**Yield**: `Deployment` CRUD; rolling, blue-green, canary, shadow all
representable as rows; canary ramp via API; shadow never reaches
clients.

Pin: `deployment/rollout-strategies.md`. The "what NOT to do"
section is the rubric for F4 -- a shadow that affects customer
output is a hard fail.

Acceptance vibe-check: in a single transaction, you can update both
the old and the new deployment's `traffic_share` so the sum is
always 1.0. If you can't, your ramp will eventually leave the
registry telling everyone different versions are "active".

## Phase 5 -- Rollback (4-5 h)

**Yield**: rollback endpoint that re-activates the prior `Production`
version; required `reason` field; audit-chain entry; < 5-minute SLO.

Pin: the SQL in `deployment/rollout-strategies.md` §Rollback contract.
The query is the contract; the FastAPI handler is just plumbing.

Drill it. A rollback that's never been exercised under time pressure
isn't a rollback procedure.

## Phase 6 -- Lineage (7-8 h)

**Yield**: `lineage_edges` populated by the SDK on registration;
`lineage/queries.sql` (or its translation in your ORM) for forward
and reverse traversal.

Pin: the recursive CTE in `lineage/queries.sql`. The depth limit
(8 hops) is a safety belt for cycles; don't remove it because "we
won't have cycles" -- one accidental cycle in production stalls
your registry until someone runs `psql`.

Done when: register a synthetic chain
`base -> fine-tune-1 -> fine-tune-2`, then `EXECUTE reverse_lineage(...)`
on the dataset of `base` -- the result includes all three versions.

## Phase 7 -- Multi-tenancy (4-5 h)

**Yield**: tenant scope on every query (RLS preferred); cross-tenant
share mechanism; tests prove tenant A's queries never see tenant B's
data.

Pin: `multi-tenancy/policy.md`. The RLS policy is fail-closed by
default. Cross-tenant ID lookup returns **404**, not 403 -- 403
leaks existence.

## Phase 8 -- Audit + observability (5-6 h)

**Yield**: audit-chain entries from project-01 reused; metrics +
Grafana dashboard live.

Pin: `observability/metrics.md` for label conventions and the
"forbidden labels" list. The single most common F8 failure is
putting `model_name` or `version` on `registry_models_total` --
cardinality explosion follows within a quarter.

## Phase 9 -- Testing + docs (6-8 h)

**Yield**: unit + integration tests, plus one end-to-end script that
runs the nine-step acceptance demo unattended (plus a screencast or
gif for the rubric reviewer).

The acceptance demo from `requirements.md` is the only test that
*proves* the registry. Everything else is a precondition.

## Time-budget recap

| Phase | Hours |
|---|---|
| 0 -- Setup | 1-2 |
| 1 -- Data model + API | 10-12 |
| 2 -- Signature | 5-6 |
| 3 -- Gates | 10-12 |
| 4 -- Deployment + rollout | 12-14 |
| 5 -- Rollback | 4-5 |
| 6 -- Lineage | 7-8 |
| 7 -- Multi-tenancy | 4-5 |
| 8 -- Audit + observability | 5-6 |
| 9 -- Testing + docs | 6-8 |
| **Total** | **~70** |

## When you're done

The registry is the system of record for production models. Every
model in production has a documented lineage, a verified signature,
recorded promotion approvals, and a known rollback target. Every
state transition is on the audit chain. Tenants see only their own
models.

This is the management layer the rest of the platform stack
ties into.
