-- Model-registry schema -- reference solution for F1, F6, F7.
--
-- Validates with:
--   psql -d registry -f schema.sql --single-transaction --set ON_ERROR_STOP=1
--
-- Design notes
-- 1. `model_versions` is immutable once inserted. The trigger below
--    blocks UPDATE on every column other than the lifecycle status,
--    which is owned by the promotion state machine, not the SDK.
--    The compliance bar is "registry must answer 'which model is
--    in production right now' deterministically"; mutable versions
--    break that bar (architecture.md §Key design decision 2).
-- 2. Artifacts are stored in object storage; the registry stores
--    `artifact_uri` + `artifact_digest`. A row without a matching
--    digest in object storage is a registry bug -- but the digest
--    is what binds the row to a concrete byte sequence.
-- 3. Lineage is an edge list, not a column on `model_versions`.
--    Reverse traversal ("what models depend on dataset X?") is a
--    first-class query, not an afterthought.
-- 4. `promotions` and `deployments` carry the audit-chain entry
--    ID so the chain in [project-01-platform-core/audit/schema.sql]
--    is the source of truth for "who said it was OK".

CREATE TABLE IF NOT EXISTS models (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace   TEXT NOT NULL,            -- tenant namespace (F7)
    name        TEXT NOT NULL,
    owner       TEXT NOT NULL,            -- SPIFFE ID or principal
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (namespace, name)
);

CREATE INDEX IF NOT EXISTS idx_models_namespace ON models (namespace);

-- Lifecycle states for a model version (architecture.md §Key design
-- decision 3). Stored as TEXT with a CHECK constraint instead of
-- ENUM so that adding states is an ALTER CHECK, not an ALTER TYPE.
CREATE TABLE IF NOT EXISTS model_versions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id          UUID NOT NULL REFERENCES models(id),
    version           TEXT NOT NULL,                              -- semver
    artifact_uri      TEXT NOT NULL,                              -- s3://...
    artifact_digest   TEXT NOT NULL,                              -- sha256:...
    signature_uri     TEXT NOT NULL,                              -- Cosign blob in object storage
    metadata          JSONB NOT NULL,                             -- training metadata
    metrics           JSONB NOT NULL,                             -- accuracy / fairness / robustness
    status            TEXT NOT NULL DEFAULT 'Registered'
        CHECK (status IN ('Registered', 'Staging', 'Production',
                          'Deprecated', 'Decommissioned')),
    registered_by     TEXT NOT NULL,
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (model_id, version)
);

CREATE INDEX IF NOT EXISTS idx_model_versions_status
    ON model_versions (status);

CREATE INDEX IF NOT EXISTS idx_model_versions_metrics_accuracy
    ON model_versions (((metrics->>'accuracy')::numeric));

-- Reject mutation on everything but `status`. `status` itself can
-- only be updated by code running as the promotion role, enforced
-- by row-level security in production deployments.
CREATE OR REPLACE FUNCTION model_versions_reject_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.model_id        IS DISTINCT FROM OLD.model_id        OR
       NEW.version         IS DISTINCT FROM OLD.version         OR
       NEW.artifact_uri    IS DISTINCT FROM OLD.artifact_uri    OR
       NEW.artifact_digest IS DISTINCT FROM OLD.artifact_digest OR
       NEW.signature_uri   IS DISTINCT FROM OLD.signature_uri   OR
       NEW.metadata        IS DISTINCT FROM OLD.metadata        OR
       NEW.metrics         IS DISTINCT FROM OLD.metrics         OR
       NEW.registered_by   IS DISTINCT FROM OLD.registered_by   OR
       NEW.registered_at   IS DISTINCT FROM OLD.registered_at
    THEN
        RAISE EXCEPTION
            'model_versions is immutable except for status (model_id=% version=%)',
            OLD.model_id, OLD.version;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS model_versions_immutable ON model_versions;
CREATE TRIGGER model_versions_immutable
    BEFORE UPDATE ON model_versions
    FOR EACH ROW EXECUTE FUNCTION model_versions_reject_mutation();

-- Lineage is an edge list: many source kinds per version, joined
-- by the version FK. Reverse traversal is a recursive CTE; see
-- lineage/queries.sql.
CREATE TABLE IF NOT EXISTS lineage_edges (
    model_version_id   UUID NOT NULL REFERENCES model_versions(id),
    source_kind        TEXT NOT NULL
        CHECK (source_kind IN ('training_data', 'feature_snapshot',
                               'base_model', 'training_run')),
    source_identifier  TEXT NOT NULL,
    PRIMARY KEY (model_version_id, source_kind, source_identifier)
);

CREATE INDEX IF NOT EXISTS idx_lineage_source
    ON lineage_edges (source_kind, source_identifier);

-- Every state transition is recorded. `audit_chain_entry_id` is the
-- pointer into the platform audit chain (project-01 §F8).
CREATE TABLE IF NOT EXISTS promotions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version_id       UUID NOT NULL REFERENCES model_versions(id),
    from_status            TEXT NOT NULL,
    to_status              TEXT NOT NULL,
    approver               TEXT NOT NULL,
    approval_signature     TEXT NOT NULL,
    approved_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    audit_chain_entry_id   UUID NOT NULL,
    CHECK (from_status <> to_status)
);

CREATE INDEX IF NOT EXISTS idx_promotions_version
    ON promotions (model_version_id, approved_at DESC);

-- Deployments tie a model version to a target environment + rollout
-- strategy. F4 requires all four strategies.
CREATE TABLE IF NOT EXISTS deployments (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version_id       UUID NOT NULL REFERENCES model_versions(id),
    target_environment     TEXT NOT NULL,
    rollout_strategy       TEXT NOT NULL
        CHECK (rollout_strategy IN ('rolling', 'blue-green',
                                    'canary', 'shadow')),
    traffic_share          NUMERIC CHECK (traffic_share IS NULL
                                          OR (traffic_share >= 0
                                              AND traffic_share <= 1)),
    deployed_by            TEXT NOT NULL,
    deployed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                 TEXT NOT NULL DEFAULT 'Active'
        CHECK (status IN ('Active', 'Rolled-back', 'Decommissioned')),
    rollback_reason        TEXT,
    audit_chain_entry_id   UUID NOT NULL,
    CHECK (status <> 'Rolled-back' OR rollback_reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_deployments_target_active
    ON deployments (target_environment) WHERE status = 'Active';

-- View: the "what is in production right now" query that the platform
-- and ops folks ask most. Should return in < 50 ms at curriculum scale.
CREATE OR REPLACE VIEW production_deployments AS
SELECT
    m.namespace, m.name, mv.version, d.target_environment,
    d.rollout_strategy, d.traffic_share, d.deployed_at, d.deployed_by
FROM deployments d
JOIN model_versions mv ON mv.id = d.model_version_id
JOIN models m          ON m.id = mv.model_id
WHERE d.status = 'Active' AND mv.status = 'Production';
