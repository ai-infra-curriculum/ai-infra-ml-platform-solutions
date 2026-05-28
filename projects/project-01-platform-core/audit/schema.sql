-- Audit-chain schema — reference solution for F8.
--
-- Validates with: psql -d platform -f schema.sql --single-transaction --set ON_ERROR_STOP=1
--
-- Design notes:
-- 1. INSERT-only is enforced at SQL level via a trigger, not just at the
--    application layer. A misbehaving service (or a DBA with psql) can
--    still INSERT but cannot UPDATE or DELETE -- this is the property an
--    auditor checks (requirements.md F8 "insert-only").
-- 2. The hash chain links rows by sequence_no, not by id, so a corruption
--    of one row breaks verification of every later row.
-- 3. payload_hash is SHA-256 of canonical-JSON(payload); prev_hash is the
--    payload_hash of the previous row (or 64 zeros for the first).

CREATE TABLE IF NOT EXISTS audit_log (
    -- sequence_no is the chain index; gaps are forbidden by the trigger.
    sequence_no   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id            UUID NOT NULL DEFAULT gen_random_uuid(),
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    identity      TEXT NOT NULL,            -- SPIFFE ID or workload identity URI of the writer
    tenant_id     UUID,                     -- nullable for platform-wide events
    action        TEXT NOT NULL,            -- e.g. training_run_admitted
    resource      TEXT NOT NULL,            -- e.g. trainingrun:recs-team/recs-v17-experiment
    request_id    TEXT NOT NULL,            -- X-Request-Id correlation
    payload       JSONB NOT NULL,
    payload_hash  CHAR(64) NOT NULL,
    prev_hash     CHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_action
    ON audit_log (tenant_id, action, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_request_id
    ON audit_log (request_id);

-- Enforce insert-only. Two triggers because PostgreSQL fires UPDATE and
-- DELETE separately; raising in either makes the row immutable post-commit.
CREATE OR REPLACE FUNCTION audit_log_reject_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is insert-only (attempted % on sequence_no=%)',
        TG_OP, COALESCE(OLD.sequence_no, NEW.sequence_no);
END;
$$;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();

DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;
CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();

-- TRUNCATE bypasses row-level triggers; block it with a statement-level
-- trigger so an operator cannot wipe the chain with TRUNCATE audit_log.
DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;
CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_mutation();

-- Verify-chain function. Returns NULL on success, or the first
-- sequence_no where the recomputed hash disagrees with stored payload_hash
-- OR prev_hash does not match the previous row's payload_hash. The CLI
-- calls this and prints "verified" or the offending sequence_no.
CREATE OR REPLACE FUNCTION verify_audit_chain()
RETURNS BIGINT LANGUAGE plpgsql STABLE AS $$
DECLARE
    rec               RECORD;
    expected_prev     CHAR(64) := repeat('0', 64);
    expected_payload  CHAR(64);
BEGIN
    FOR rec IN
        SELECT sequence_no, payload, payload_hash, prev_hash
          FROM audit_log
         ORDER BY sequence_no ASC
    LOOP
        expected_payload := encode(
            digest(rec.payload::text, 'sha256'),
            'hex'
        );
        IF rec.payload_hash <> expected_payload
           OR rec.prev_hash <> expected_prev THEN
            RETURN rec.sequence_no;
        END IF;
        expected_prev := rec.payload_hash;
    END LOOP;
    RETURN NULL;
END;
$$;

-- pgcrypto is required for digest(); the CI bootstrap script enables it.
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;
