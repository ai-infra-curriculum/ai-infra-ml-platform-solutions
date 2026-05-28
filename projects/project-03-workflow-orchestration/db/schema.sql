-- Project 03 workflow-orchestration engine: persistent state schema.
--
-- Extends the data model in the project's architecture.md with:
--   * audit_log table (insert-only via REVOKE), to back the audit-chain
--     transition guarantee described in SOLUTION.md.
--   * runs.parent_run_id (re-run-from-step lineage; see SOLUTION.md decision 2).
--   * Enum CHECK constraints on status columns so a bad state value cannot
--     reach the DB even if the state-machine module is bypassed.
--
-- Validate locally with: psql -X -f db/schema.sql -d postgres --single-transaction
--                       --set ON_ERROR_STOP=1
-- or with: pgsanity db/schema.sql

BEGIN;

CREATE TABLE pipelines (
    id          UUID PRIMARY KEY,
    name        TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    version     TEXT NOT NULL,
    spec        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (namespace, name, version)
);

CREATE INDEX pipelines_namespace_name_idx ON pipelines (namespace, name);

CREATE TABLE runs (
    id              UUID PRIMARY KEY,
    pipeline_id     UUID NOT NULL REFERENCES pipelines(id),
    parent_run_id   UUID REFERENCES runs(id),       -- set on re-run-from-step
    triggered_by    TEXT NOT NULL CHECK (triggered_by IN ('schedule', 'event', 'manual')),
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL CHECK (status IN (
                        'Pending', 'Running', 'Succeeded', 'Failed', 'Cancelled'
                    )),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX runs_pipeline_status_idx ON runs (pipeline_id, status);
CREATE INDEX runs_parent_idx           ON runs (parent_run_id);

CREATE TABLE step_states (
    run_id        UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_name     TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN (
                      'Pending', 'Running', 'Succeeded', 'Failed',
                      'Skipped', 'WaitingApproval'
                  )),
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    pod_name      TEXT,
    outputs       JSONB,
    error         TEXT,
    PRIMARY KEY (run_id, step_name)
);

CREATE INDEX step_states_status_idx ON step_states (status);

CREATE TABLE gate_evaluations (
    run_id        UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_name     TEXT NOT NULL,
    condition     TEXT NOT NULL,
    result        TEXT NOT NULL CHECK (result IN ('pass', 'fail', 'pending')),
    evaluated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    approver      TEXT,
    PRIMARY KEY (run_id, step_name, condition)
);

-- Audit chain: every state transition is mirrored here in the same
-- DB transaction that writes runs / step_states. The grant + revoke
-- pair below enforces "insert-only" at the role level. Production
-- deployments should add a hash-chain column (prev_hash, this_hash)
-- but that is out of scope for this capstone.
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    run_id        UUID NOT NULL,
    step_name     TEXT,
    event_type    TEXT NOT NULL,
    from_state    TEXT,
    to_state      TEXT NOT NULL,
    actor         TEXT NOT NULL,            -- 'system', user identity, or 'approver:<id>'
    details       JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX audit_log_run_idx ON audit_log (run_id);

-- The engine writes to audit_log under a dedicated role; the role
-- has INSERT but not UPDATE / DELETE. A DBA superuser can still
-- mutate the table - that is intentional, retention policies are
-- enforced separately. The point is to block the engine itself
-- from rewriting history through a bug.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'orchestrator') THEN
        CREATE ROLE orchestrator NOLOGIN;
    END IF;
END$$;

GRANT INSERT, SELECT ON audit_log TO orchestrator;
GRANT USAGE ON SEQUENCE audit_log_id_seq TO orchestrator;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM orchestrator;

COMMIT;
