-- Lineage queries -- reference solution for F6.
--
-- Validates with:
--   psql -d registry -f queries.sql --single-transaction --set ON_ERROR_STOP=1
--
-- Convention: for a `base_model` edge, `source_identifier` is the
-- UUID (text-serialised) of the upstream `model_versions.id`. For
-- `training_data` and `feature_snapshot` it is the data version
-- string. For `training_run` it is the run ID string. This lets
-- the recursive walk follow `base_model` edges by an unambiguous
-- JOIN, while `training_data` and friends are leaves.
--
-- Two queries:
--   1. Forward: walk from a version through its base_model chain;
--      collect every upstream edge along the way.
--   2. Reverse: given a data source, return every version that
--      depends on it -- directly via lineage_edges, or transitively
--      through fine-tuning chains of base_model edges.
--
-- Both queries cap depth at 8 hops to defend against accidental
-- cycles. The schema does not enforce acyclicity, so the query must.

-- =====================================================================
-- 1) Forward: full edge set rooted at one model_version_id.
-- =====================================================================
PREPARE forward_lineage (uuid) AS
WITH RECURSIVE walk AS (
    -- Seed: direct edges from the root version.
    SELECT
        le.model_version_id,
        le.source_kind,
        le.source_identifier,
        1 AS depth
      FROM lineage_edges le
     WHERE le.model_version_id = $1

    UNION ALL

    -- Recurse through `base_model` edges: each such edge tells us
    -- the upstream version, whose own lineage_edges we want too.
    SELECT
        next_le.model_version_id,
        next_le.source_kind,
        next_le.source_identifier,
        w.depth + 1
      FROM walk w
      JOIN lineage_edges next_le
        ON next_le.model_version_id = w.source_identifier::uuid
     WHERE w.source_kind = 'base_model'
       AND w.depth < 8
)
SELECT walk.depth,
       walk.model_version_id,
       walk.source_kind,
       walk.source_identifier
  FROM walk
 ORDER BY depth ASC, source_kind, source_identifier;


-- =====================================================================
-- 2) Reverse: every model_version_id that depends on (kind, id).
-- =====================================================================
-- Step a: versions with a direct edge to the data source.
-- Step b: versions whose `base_model` edge points at any version
--         already in the dependents set (transitive fine-tunes).
PREPARE reverse_lineage (text, text) AS
WITH RECURSIVE dependents AS (
    SELECT
        le.model_version_id,
        1 AS depth
      FROM lineage_edges le
     WHERE le.source_kind = $1
       AND le.source_identifier = $2

    UNION

    SELECT
        le.model_version_id,
        d.depth + 1
      FROM dependents d
      JOIN lineage_edges le
        ON le.source_kind = 'base_model'
       AND le.source_identifier = d.model_version_id::text
     WHERE d.depth < 8
)
SELECT
    d.model_version_id,
    m.namespace,
    m.name,
    mv.version,
    mv.status,
    MIN(d.depth) AS shortest_path
  FROM dependents d
  JOIN model_versions mv ON mv.id = d.model_version_id
  JOIN models m          ON m.id = mv.model_id
 GROUP BY d.model_version_id, m.namespace, m.name, mv.version, mv.status
 ORDER BY shortest_path, m.namespace, m.name;


-- Usage:
--   EXECUTE forward_lineage('00000000-0000-0000-0000-000000000001');
--   EXECUTE reverse_lineage('training_data', 'recs-curated-2026-05');
