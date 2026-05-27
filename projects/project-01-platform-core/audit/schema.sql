-- Audit chain (requirement F8). A hash-chained, insert-only log: each
-- row commits to the previous one, so any later edit or deletion is
-- detectable by re-walking the chain (see audit/verify.py).
--
-- The insert-only property is enforced at the database level, not in
-- application code, because the auditor's question is "can a privileged
-- DB user rewrite history?" — and the honest answer must be "no, the
-- engine itself rejects UPDATE and DELETE on this table."
--
-- Apply:  psql "$PLATFORM_DB_URL" -f audit/schema.sql

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    identity    TEXT         NOT NULL,   -- signing workload identity
    tenant      TEXT,
    action      TEXT         NOT NULL,
    resource    TEXT,
    payload     JSONB        NOT NULL,
    payload_hash CHAR(64)    NOT NULL,   -- sha256(canonical_payload)
    prev_hash   CHAR(64)     NOT NULL,   -- payload_hash of id-1 (or 64 zeros)
    entry_hash  CHAR(64)     NOT NULL    -- sha256(payload_hash || prev_hash)
);

-- Reject any attempt to mutate or remove an existing entry. This fires
-- for every row of an UPDATE/DELETE, including bulk statements, and
-- cannot be bypassed without dropping the trigger (a DDL change that is
-- itself auditable).
CREATE OR REPLACE FUNCTION audit_log_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is insert-only (% rejected)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

-- Truncation bypasses row triggers, so block it separately.
DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;
CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable();
