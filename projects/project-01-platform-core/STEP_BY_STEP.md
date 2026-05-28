# STEP_BY_STEP -- Project 01 Solution

Solution-side walk-through. The learning repo's
[`STEP_BY_STEP.md`](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/STEP_BY_STEP.md)
prescribes the phases; this document mirrors them and pins what
each phase yields *in this solution's terms*. Use it to sequence
your build and to know when each phase is "done enough" to move
on.

Each phase below points at the artifact in this directory that
captures its contract. Build implementations to meet those
contracts; the curated files are the rubric.

## Phase 0 -- Setup (1-2 h)

**Yield**: a kind/k3d cluster, PostgreSQL, an OIDC stub (Dex or
Keycloak), and the repo skeleton from the learning
`STEP_BY_STEP.md` §0.

Solution-side check: `kubectl get nodes` Ready;
`psql -d platform -c '\dt'` shows zero tables;
`curl https://idp.local/.well-known/openid-configuration` returns
the OIDC discovery document.

## Phase 1 -- Audit chain (4-5 h)

**Yield**: `audit/schema.sql` applied; the genesis row in place;
the BEFORE INSERT trigger blocking caller-supplied hashes; the
two append-only triggers blocking UPDATE/DELETE;
`verify_audit_chain` callable from psql.

Pin: the genesis row + the canonical-payload construction.
Project-04 depends on both, and any drift between
`audit_chain_link()` (SQL) and `audit/verify.py` (Python) breaks
the chain for everyone.

Done when:

```bash
psql -d platform -f audit/schema.sql --single-transaction --set ON_ERROR_STOP=1
psql -d platform -c "INSERT INTO audit_log (tenant_id, actor, actor_kind, action, resource_kind, resource_id, payload, request_id) VALUES ('t1', 'alice', 'user', 'demo', 'Demo', '1', '{}'::jsonb, 'req-1');"
psql -d platform -c "UPDATE audit_log SET payload = '{\"x\":1}'::jsonb WHERE seq = 1;"
# -> ERROR: audit_log is append-only
psql -d platform -c "SELECT * FROM verify_audit_chain_all();"
# -> 0 rows
```

## Phase 2 -- Control-plane schema (3-4 h)

**Yield**: `control-plane/schema.sql` applied; row-level security
attached to `tenants`, `resource_claims`, `training_runs`, and
`idempotency_keys`; `platform_app` and `platform_admin` roles
created.

Pin: the four `*_scope` policies. Connecting as `platform_app`
without `SET LOCAL platform.tenant_id = '...'` MUST return zero
rows. That is the fail-closed property.

Done when:

```bash
psql -d platform -U platform_app -c "SELECT count(*) FROM tenants;"
# -> 0 rows (RLS scope unset)
psql -d platform -U platform_app -c "SET LOCAL platform.tenant_id = 'some-uuid'; SELECT count(*) FROM tenants;"
# -> the count for that tenant
```

## Phase 3 -- Control-plane API (10-12 h)

**Yield**: FastAPI app implementing every operation in
`control-plane/openapi.yaml`. `redocly lint` and
`openapi-spec-validator` both pass on the served spec. The
generated SDK from `mod-002/ex-04` works against this server
end-to-end.

Pin: the `Idempotency-Key` middleware. A POST without the header
returns **400**; a replayed key with the same body returns the
original response; a replayed key with a different body returns
**409**.

Pin: the `:cancel` and `:verify` action verbs use the Google-
style colon syntax. Don't smuggle them into `PUT` or `PATCH`.

Done when the four contract tests pass:

- happy-path TrainingRun submit -> 202, run row + audit row.
- second TrainingRun submit with the same `Idempotency-Key` ->
  200, prior body, no new run.
- second TrainingRun submit with the same `Idempotency-Key` but a
  different `image` -> 409.
- `GET /tenants/{other-tenant-id}` with a token scoped to a
  different tenant -> 404 (not 403).

## Phase 4 -- Operator (10-12 h)

**Yield**: `operator/crds.yaml` applied; `kubeconform -strict`
clean; the reconcile loop in `operator/reconcile.py` ported into
the learner's framework of choice; `TrainingRun` Pod created and
labeled per `_build_pod_manifest`.

Pin: terminal phases (`Succeeded`, `Failed`, `Cancelled`) do not
get re-reconciled into a new Pod. Re-creating a Pod after a
SUCCEEDED run is the F4 hard fail.

Pin: the operator never sets `tenant_id` from request input; it
reads it from the spec field the control-plane admission webhook
populated.

Done when:

```bash
kubeconform -strict -summary -kubernetes-version 1.29 operator/crds.yaml
kubectl apply -f operator/crds.yaml
kubectl get crds | grep platform.example.com
# -> trainingruns.platform.example.com   <ts>
# -> resourceclaims.platform.example.com <ts>
```

## Phase 5 -- Multi-tenancy bundle (4-5 h)

**Yield**: `multi-tenancy/namespace-template.yaml` substituted and
applied per tenant. Per-tenant ResourceQuota, LimitRange, the
three NetworkPolicies, the Role + RoleBinding, and the workload
ServiceAccount all visible in `kubectl get all -n tenant-<slug>`.

Pin: default-deny is real. The acceptance demo step 6 (an `exec`
from `team-alpha` to `team-beta` times out) is the smoking-gun
test.

Done when:

```bash
kubeconform -strict -summary -kubernetes-version 1.29 \
    multi-tenancy/namespace-template.yaml
```

## Phase 6 -- Identity + RBAC wiring (4-5 h)

**Yield**: OIDC discovery URL wired into the API server's bearer-
token validator; group claim mapping that maps `alpha-mlops` to
the `tenant-team-alpha` RoleBinding; service tokens for the
operator-to-control-plane call are SPIFFE-issued and short-lived.

Reminder: F7 grades on the absence of long-lived static tokens,
not just the presence of OIDC. A token-rotation procedure that has
never been drilled grades Partial.

## Phase 7 -- Self-service CLI (3-4 h)

**Yield**: the CLI from `mod-007/ex-02` invokes the generated SDK
from `mod-002/ex-04`. The 10-minute onboarding flow is the F8 bar.

The CLI is the platform team's own first customer. If the
platform team cannot run `platform run submit` happily, no one
else will.

## Phase 8 -- Acceptance demo (2-3 h)

**Yield**: a single screencast covering the eight steps in
`rubric.md` §Acceptance demo. Steps 7 and 8 together prove F6 is
real; everything else proves F1-F5 and F8.
