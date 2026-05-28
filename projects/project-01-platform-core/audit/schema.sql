-- audit/schema.sql -- platform audit chain (project-01-platform-core)
--
-- The audit chain is the platform's single source of truth for
-- "who said it was OK, when, on what". Every state-changing
-- operation on the control plane (tenant created, ResourceClaim
-- approved, TrainingRun submitted, model promoted in project-04,
-- deployment rolled back) emits exactly one row here.
--
-- Design commitments:
--
-- 1. The log is append-only. UPDATE and DELETE are blocked by
--    triggers. Rotation is by partition, not by mutation.
-- 2. Every row carries `entry_hash = sha256(prev_hash || payload)`,
--    so an attacker who can reach the database still cannot
--    silently edit history -- the chain breaks on the next call to
--    `verify_audit_chain`.
-- 3. The hash is computed by an INSERT trigger, not by the caller.
--    A caller that forgets to compute the hash, or computes it
--    wrong, is impossible.
-- 4. Tenant scope (`tenant_id`) is required on every row;
--    cross-tenant lookups in the control plane go through this
--    table the same way every other tenanted read does.
--
-- Project-04 (model registry) carries `audit_chain_entry_id` on
-- `promotions`, `deployments`, and `shares`, and calls
-- `verify_audit_chain(start, end)` on demand. Do not redefine
-- this table in any other project.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    seq             BIGSERIAL   NOT NULL UNIQUE,
    tenant_id       TEXT        NOT NULL,
    actor           TEXT        NOT NULL,        -- OIDC subject or SPIFFE ID
    actor_kind      TEXT        NOT NULL,        -- 'user' | 'service' | 'system'
    action          TEXT        NOT NULL,        -- e.g. 'tenant.create', 'training_run.submit'
    resource_kind   TEXT        NOT NULL,        -- e.g. 'Tenant', 'TrainingRun', 'ModelVersion'
    resource_id     TEXT        NOT NULL,        -- the resource the action acted on
    payload         JSONB       NOT NULL,        -- structured before/after diff
    request_id      TEXT        NOT NULL,        -- platform-wide correlation ID
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_hash       BYTEA       NOT NULL,        -- 32 bytes; set by trigger
    entry_hash      BYTEA       NOT NULL,        -- 32 bytes; set by trigger
    CHECK (actor_kind IN ('user', 'service', 'system')),
    CHECK (octet_length(prev_hash)  = 32),
    CHECK (octet_length(entry_hash) = 32)
);

CREATE INDEX IF NOT EXISTS audit_log_tenant_seq_idx
    ON audit_log (tenant_id, seq);

CREATE INDEX IF NOT EXISTS audit_log_resource_idx
    ON audit_log (resource_kind, resource_id);

CREATE INDEX IF NOT EXISTS audit_log_occurred_at_idx
    ON audit_log (occurred_at);

-- A sentinel row (seq = 0, hash = 32 zero bytes) so the very first
-- real entry can link to a deterministic predecessor without a
-- special case in the trigger. Inserted once, never again.
INSERT INTO audit_log (id, seq, tenant_id, actor, actor_kind, action,
                       resource_kind, resource_id, payload, request_id,
                       prev_hash, entry_hash)
VALUES ('00000000-0000-0000-0000-000000000000',
        0, '_system', '_genesis', 'system', 'chain.genesis',
        'AuditChain', 'genesis', '{}'::jsonb, '00000000-genesis',
        decode('0000000000000000000000000000000000000000000000000000000000000000', 'hex'),
        decode('0000000000000000000000000000000000000000000000000000000000000000', 'hex'))
ON CONFLICT (id) DO NOTHING;

-- audit_chain_link: BEFORE INSERT trigger that
--   * reads the prior row's entry_hash (by max(seq))
--   * sets NEW.prev_hash to that value
--   * sets NEW.entry_hash = sha256(prev_hash || canonical_payload)
-- where canonical_payload is the JSON-canonicalized columns the
-- chain commits to. The caller MUST NOT set prev_hash or entry_hash;
-- if they try, the trigger overwrites their value (the chain is
-- the system's word, not the caller's).
CREATE OR REPLACE FUNCTION audit_chain_link() RETURNS TRIGGER AS $$
DECLARE
    prior          BYTEA;
    canonical_blob BYTEA;
BEGIN
    SELECT entry_hash INTO prior
    FROM audit_log
    WHERE seq = (SELECT max(seq) FROM audit_log);

    IF prior IS NULL THEN
        -- The genesis row guarantees this never fires in practice.
        RAISE EXCEPTION 'audit_chain: prior hash missing; chain not initialized';
    END IF;

    NEW.prev_hash := prior;

    -- Commit to the columns that matter. `id`, `seq`, and `occurred_at`
    -- are deliberately excluded: id is random, seq is server-assigned
    -- after the hash is computed, occurred_at is wall-clock and can
    -- skew on replicas. The chain commits to the *content*, not the
    -- transport.
    canonical_blob := convert_to(
        jsonb_build_object(
            'tenant_id',     NEW.tenant_id,
            'actor',         NEW.actor,
            'actor_kind',    NEW.actor_kind,
            'action',        NEW.action,
            'resource_kind', NEW.resource_kind,
            'resource_id',   NEW.resource_id,
            'payload',       NEW.payload,
            'request_id',    NEW.request_id,
            'prev_hash',     encode(NEW.prev_hash, 'hex')
        )::text,
        'UTF8'
    );

    NEW.entry_hash := digest(canonical_blob, 'sha256');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_chain_link_trg ON audit_log;
CREATE TRIGGER audit_chain_link_trg
    BEFORE INSERT ON audit_log
    FOR EACH ROW
    WHEN (NEW.seq <> 0)            -- skip the genesis row
    EXECUTE FUNCTION audit_chain_link();

-- Append-only: every UPDATE or DELETE on this table is a bug. The
-- triggers below make that bug loud instead of silent.
CREATE OR REPLACE FUNCTION audit_chain_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only (% % not permitted)',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_chain_no_update_trg ON audit_log;
CREATE TRIGGER audit_chain_no_update_trg
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_chain_immutable();

DROP TRIGGER IF EXISTS audit_chain_no_delete_trg ON audit_log;
CREATE TRIGGER audit_chain_no_delete_trg
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_chain_immutable();

-- verify_audit_chain(start_seq, end_seq) returns one row per break.
--
-- Empty result = chain intact across the range. Any returned row
-- names the broken seq, the expected hash, and the actual hash.
-- Project-04 calls this with end_seq = max(seq) on a schedule and
-- pages on any non-empty result.
CREATE OR REPLACE FUNCTION verify_audit_chain(start_seq BIGINT, end_seq BIGINT)
RETURNS TABLE (
    broken_seq    BIGINT,
    expected_hash BYTEA,
    actual_hash   BYTEA,
    note          TEXT
) AS $$
DECLARE
    rec            RECORD;
    prior_hash     BYTEA;
    canonical_blob BYTEA;
    expected       BYTEA;
BEGIN
    IF start_seq > end_seq THEN
        RAISE EXCEPTION 'verify_audit_chain: start_seq (%) > end_seq (%)',
            start_seq, end_seq;
    END IF;

    -- Seed prior_hash from the row immediately before start_seq.
    SELECT entry_hash INTO prior_hash
    FROM audit_log
    WHERE seq = start_seq - 1;

    IF prior_hash IS NULL THEN
        broken_seq    := start_seq;
        expected_hash := NULL;
        actual_hash   := NULL;
        note          := 'no predecessor row; cannot anchor verification';
        RETURN NEXT;
        RETURN;
    END IF;

    FOR rec IN
        SELECT seq, tenant_id, actor, actor_kind, action, resource_kind,
               resource_id, payload, request_id, prev_hash, entry_hash
        FROM audit_log
        WHERE seq BETWEEN start_seq AND end_seq
        ORDER BY seq
    LOOP
        IF rec.prev_hash <> prior_hash THEN
            broken_seq    := rec.seq;
            expected_hash := prior_hash;
            actual_hash   := rec.prev_hash;
            note          := 'prev_hash does not match prior entry_hash';
            RETURN NEXT;
            RETURN;                -- a single break invalidates the rest
        END IF;

        canonical_blob := convert_to(
            jsonb_build_object(
                'tenant_id',     rec.tenant_id,
                'actor',         rec.actor,
                'actor_kind',    rec.actor_kind,
                'action',        rec.action,
                'resource_kind', rec.resource_kind,
                'resource_id',   rec.resource_id,
                'payload',       rec.payload,
                'request_id',    rec.request_id,
                'prev_hash',     encode(rec.prev_hash, 'hex')
            )::text,
            'UTF8'
        );

        expected := digest(canonical_blob, 'sha256');

        IF expected <> rec.entry_hash THEN
            broken_seq    := rec.seq;
            expected_hash := expected;
            actual_hash   := rec.entry_hash;
            note          := 'entry_hash does not match recomputed hash';
            RETURN NEXT;
            RETURN;
        END IF;

        prior_hash := rec.entry_hash;
    END LOOP;
END;
$$ LANGUAGE plpgsql STABLE;

-- Convenience caller: verify the entire chain.
CREATE OR REPLACE FUNCTION verify_audit_chain_all()
RETURNS TABLE (
    broken_seq    BIGINT,
    expected_hash BYTEA,
    actual_hash   BYTEA,
    note          TEXT
) AS $$
    SELECT * FROM verify_audit_chain(1, COALESCE((SELECT max(seq) FROM audit_log), 0));
$$ LANGUAGE sql STABLE;
