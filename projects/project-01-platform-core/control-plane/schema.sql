-- control-plane/schema.sql -- relational state of the platform.
--
-- The control plane stores three things:
--
--   1. Tenants                -- the team a request belongs to.
--   2. ResourceClaims         -- a tenant's quota grant.
--   3. TrainingRuns           -- submitted asynchronous work.
--
-- Every state-changing handler also writes one row to
-- `audit_log` (see `audit/schema.sql`) and carries the resulting
-- `audit_chain_entry_id` back on the resource row, so any query
-- can join from a resource to the chain entry that proves "who
-- said it was OK".
--
-- Tenant scope is enforced by Postgres row-level security; the
-- handler sets `platform.tenant_id` on the session and the policy
-- below uses it. The handler MUST set it; forgetting yields zero
-- rows (fail-closed), not the whole table.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -------------------------------------------------------------------
-- Tenants
-- -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenants (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          TEXT         NOT NULL UNIQUE,
    display_name  TEXT,
    owner_group   TEXT         NOT NULL,    -- OIDC group claim
    namespace     TEXT         NOT NULL UNIQUE,   -- K8s namespace name
    status        TEXT         NOT NULL DEFAULT 'Provisioning',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    audit_chain_entry_id UUID  NOT NULL,
    CHECK (status IN ('Provisioning','Active','Suspended','Deprovisioning','Deleted')),
    CHECK (slug ~ '^[a-z][a-z0-9-]{1,38}[a-z0-9]$')
);

-- -------------------------------------------------------------------
-- ResourceClaims
-- -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS resource_claims (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID         NOT NULL REFERENCES tenants(id),
    cpu           TEXT         NOT NULL,   -- K8s quantity, validated by control-plane
    memory        TEXT         NOT NULL,
    gpu           TEXT         NOT NULL DEFAULT '0',
    priority      TEXT         NOT NULL DEFAULT 'batch',
    status        TEXT         NOT NULL DEFAULT 'Pending',
    requested_by  TEXT         NOT NULL,
    approved_by   TEXT,
    expires_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    audit_chain_entry_id UUID  NOT NULL,
    CHECK (priority IN ('interactive','batch','backfill')),
    CHECK (status   IN ('Pending','Approved','Active','Rejected','Expired'))
);

CREATE INDEX IF NOT EXISTS resource_claims_tenant_status_idx
    ON resource_claims (tenant_id, status);

-- -------------------------------------------------------------------
-- TrainingRuns
-- -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS training_runs (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID         NOT NULL REFERENCES tenants(id),
    image         TEXT         NOT NULL,
    command       JSONB,
    cpu           TEXT         NOT NULL,
    memory        TEXT         NOT NULL,
    gpu           TEXT         NOT NULL DEFAULT '0',
    priority      TEXT         NOT NULL DEFAULT 'batch',
    phase         TEXT         NOT NULL DEFAULT 'Pending',
    submitted_by  TEXT         NOT NULL,
    submitted_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    exit_code     INTEGER,
    artifact_uri  TEXT,
    cancel_reason TEXT,
    audit_chain_entry_id UUID  NOT NULL,
    CHECK (priority IN ('interactive','batch','backfill')),
    CHECK (phase    IN ('Pending','Scheduled','Running','Succeeded','Failed','Cancelled')),
    CHECK ((phase IN ('Succeeded','Failed') AND finished_at IS NOT NULL) OR
           (phase NOT IN ('Succeeded','Failed')))
);

CREATE INDEX IF NOT EXISTS training_runs_tenant_phase_idx
    ON training_runs (tenant_id, phase);

CREATE INDEX IF NOT EXISTS training_runs_submitted_at_idx
    ON training_runs (submitted_at);

-- -------------------------------------------------------------------
-- Idempotency keys (24 h replay window for every POST).
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key             TEXT        NOT NULL,
    tenant_id       UUID        NOT NULL REFERENCES tenants(id),
    request_hash    BYTEA       NOT NULL,
    response_status INTEGER     NOT NULL,
    response_body   JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, key)
);

CREATE INDEX IF NOT EXISTS idempotency_keys_created_at_idx
    ON idempotency_keys (created_at);

-- -------------------------------------------------------------------
-- Row-level security: tenant scope is enforced by the database,
-- not just by the handler. Forget to `SET LOCAL platform.tenant_id`
-- and a SELECT returns zero rows (fail-closed).
-- -------------------------------------------------------------------

ALTER TABLE tenants            ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_claims    ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_runs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys   ENABLE ROW LEVEL SECURITY;

-- Admin-only role bypasses scope.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_admin') THEN
        CREATE ROLE platform_admin;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
        CREATE ROLE platform_app;
    END IF;
END
$$;

GRANT SELECT, INSERT, UPDATE                ON tenants            TO platform_app;
GRANT SELECT, INSERT, UPDATE                ON resource_claims    TO platform_app;
GRANT SELECT, INSERT, UPDATE                ON training_runs      TO platform_app;
GRANT SELECT, INSERT, DELETE                ON idempotency_keys   TO platform_app;

DROP POLICY IF EXISTS tenants_scope            ON tenants;
DROP POLICY IF EXISTS resource_claims_scope    ON resource_claims;
DROP POLICY IF EXISTS training_runs_scope      ON training_runs;
DROP POLICY IF EXISTS idempotency_keys_scope   ON idempotency_keys;

CREATE POLICY tenants_scope ON tenants
    FOR ALL
    TO platform_app
    USING       (id::text = current_setting('platform.tenant_id', true))
    WITH CHECK  (id::text = current_setting('platform.tenant_id', true));

CREATE POLICY resource_claims_scope ON resource_claims
    FOR ALL
    TO platform_app
    USING       (tenant_id::text = current_setting('platform.tenant_id', true))
    WITH CHECK  (tenant_id::text = current_setting('platform.tenant_id', true));

CREATE POLICY training_runs_scope ON training_runs
    FOR ALL
    TO platform_app
    USING       (tenant_id::text = current_setting('platform.tenant_id', true))
    WITH CHECK  (tenant_id::text = current_setting('platform.tenant_id', true));

CREATE POLICY idempotency_keys_scope ON idempotency_keys
    FOR ALL
    TO platform_app
    USING       (tenant_id::text = current_setting('platform.tenant_id', true))
    WITH CHECK  (tenant_id::text = current_setting('platform.tenant_id', true));

-- Admin bypass: the platform_admin role sees everything.
ALTER TABLE tenants            FORCE ROW LEVEL SECURITY;
ALTER TABLE resource_claims    FORCE ROW LEVEL SECURITY;
ALTER TABLE training_runs      FORCE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys   FORCE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenants            TO platform_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON resource_claims    TO platform_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON training_runs      TO platform_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON idempotency_keys   TO platform_admin;

CREATE POLICY tenants_admin            ON tenants            FOR ALL TO platform_admin USING (true) WITH CHECK (true);
CREATE POLICY resource_claims_admin    ON resource_claims    FOR ALL TO platform_admin USING (true) WITH CHECK (true);
CREATE POLICY training_runs_admin      ON training_runs      FOR ALL TO platform_admin USING (true) WITH CHECK (true);
CREATE POLICY idempotency_keys_admin   ON idempotency_keys   FOR ALL TO platform_admin USING (true) WITH CHECK (true);
