# Multi-tenancy policy -- reference solution for F7

The registry is multi-tenant by namespace. Every model, version,
promotion, deployment, and audit-chain entry belongs to exactly one
tenant namespace, and the API enforces tenant scope at three layers:

1. **Identity layer**: the bearer token (JWT or workload identity)
   carries the caller's tenant. The auth middleware extracts it
   once per request.
2. **Query layer**: every SQL statement filters by
   `models.namespace = :caller_tenant`. This is enforced by an
   ORM scope or a row-level-security policy on `models`,
   `model_versions`, and `deployments` -- the *table*, not just the
   handler, refuses to return another tenant's rows.
3. **Response layer**: list endpoints return a homogeneous list of
   the caller's models; cross-namespace IDs handed in via path are
   404'd before any join.

## RLS policy (Postgres)

```sql
-- Applied per tenant; identity flows in via SET LOCAL platform.tenant.
ALTER TABLE models           ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_versions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployments      ENABLE ROW LEVEL SECURITY;
ALTER TABLE promotions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineage_edges    ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_models ON models
  USING (namespace = current_setting('platform.tenant'));

CREATE POLICY tenant_isolation_versions ON model_versions
  USING (model_id IN (SELECT id FROM models));

CREATE POLICY tenant_isolation_deployments ON deployments
  USING (model_version_id IN (SELECT id FROM model_versions));

-- Lineage rows ride on the version policy because they reference
-- model_version_id; the FK + RLS combination means a cross-tenant
-- edge is invisible even if it exists.
CREATE POLICY tenant_isolation_lineage ON lineage_edges
  USING (model_version_id IN (SELECT id FROM model_versions));
```

The handler does `SET LOCAL platform.tenant = :caller_tenant` at the
start of every request transaction. If the SET is forgotten, the
policy returns zero rows -- a hard fail-closed default. (Compare:
forgetting an application-layer `WHERE tenant = ?` returns every
tenant's rows.)

## Cross-tenant share

Sharing a model across tenants is an *explicit* action recorded in
its own audit-chain entry. The contract:

```
POST /v1/models/{model_id}/share
{
  "to_tenant": "team-payments",
  "scope":     "read",           // read | promote | deploy
  "expires_at": "2026-12-31T00:00:00Z"
}
```

Rules:

- Only the model's `owner` can initiate a share.
- Every share emits an audit-chain event with both tenants named.
- A `to_tenant = from_tenant` share is rejected (400).
- Reads from the `to_tenant` are still audited as cross-tenant
  reads, not as native ones -- the audit trail makes the difference
  visible to the compliance team.

A `shares` table holds the active grants; the RLS policy on
`models` is widened (in production deployments) to include
`namespace = current_setting('platform.tenant')
 OR id IN (SELECT model_id FROM shares WHERE to_tenant = ...)`.
The default repository ships without `shares` populated; the
learner adds it when implementing the share endpoint.

## Test bar (rubric F7)

The acceptance bar is two pages:

1. Tenant A's bearer token requests `GET /v1/models` and sees only
   tenant A's models; never tenant B's.
2. Tenant A's bearer token requests
   `GET /v1/models/{tenant_b_model_id}/versions/...` -- the response
   is **404**, not 403. (403 leaks that the model exists.)

If both pass, the F7 row grades as `Pass`. If 1 leaks any of
tenant B's rows, the row is a hard `Fail`.
