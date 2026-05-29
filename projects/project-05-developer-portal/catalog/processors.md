# Catalog processors and entity providers

The catalog has two ingestion paths. The split is the load-bearing
design decision of the catalog phase.

## Static `catalog-info.yaml`

Backstage's GitHub discovery processor scans the org for
`catalog-info.yaml` and registers every entity it finds.

- One descriptor per repo, committed under the repo root.
- Multi-document YAML: one `---` block per entity.
- Validated by Backstage's built-in `EntityPolicies` *plus* the
  custom `MLModelEntityValidator` and `DatasetEntityValidator`.

Static descriptors are the path for:

- SDKs, CLIs, services (`Component`)
- API specs (`API`)
- Documentation hubs (`Component` with TechDocs)
- Teams (`Group`)

Static descriptors are *not* the path for things the platform
creates dynamically — a TrainingRun's lifetime is hours, not
weeks; nobody commits a YAML file for it.

## API-driven entity providers

Two entity providers run on the catalog backend, each on a
configurable poll interval (30 s default):

### `TrainingRunEntityProvider`

```text
GET <project-01 control plane>/v1/trainingruns
  ──▶  emit kind: Resource, spec.type: training-run, lifecycle by status
```

- One `Resource` per TrainingRun.
- `metadata.namespace` = the TrainingRun's tenant.
- `spec.dependsOn` includes the dataset and base model the run
  consumed (read from the CR annotations the SDK populates).
- `lifecycle` derived from CR status:
  `Pending|Running → experimental`,
  `Succeeded → production`,
  `Failed → deprecated`.
- Finished-and-tombstoned after 30 days; see "Tombstoning"
  below.

### `ModelVersionEntityProvider`

```text
GET <project-04 registry>/v1/models?include=versions
  ──▶  emit kind: MLModel, one per (model, version)
```

- One `MLModel` per registered model version.
- `metadata.annotations['ml-platform.example.com/model-version-id']`
  is the registry's UUID — immutable.
- `spec.trainingRun` references the corresponding `Resource`.
- `spec.dataset` references the corresponding `Dataset`.
- Promotion state from the registry maps to `lifecycle`
  (`Registered|Staging → experimental`,
  `Production → production`,
  `Deprecated|Decommissioned → deprecated`).

## Failure-mode discipline

The processor pipeline is one of the most-frequently-broken
parts of a Backstage deployment. The reference solution pins
four invariants:

1. **Per-entity try/except.** A processor that throws on one
   bad entity must not poison the rest of the import. Wrap each
   entity in try/except, emit a catalog *error* (visible in the
   portal as a red badge on the entity), continue with the
   next.
2. **No silent drops.** If a TrainingRun returns from the
   project-01 API but the validator rejects it, surface the
   rejection on the catalog error page. Silent drops mean the
   catalog is incomplete *and* the user has no idea.
3. **Backoff on upstream errors.** A 5xx from project-01 must
   not stampede the cluster on the next tick. Exponential
   backoff up to 5 min; emit a metric on the failure for the
   on-call dashboard.
4. **Idempotent re-emission.** The provider re-emits the full
   entity set every tick. The catalog backend dedupes by
   `(kind, namespace, name)`. Don't try to compute deltas — let
   the backend do it.

## Tombstoning

A model version removed from the registry, or a TrainingRun
deleted from the cluster, must *not* disappear from the catalog
on the next tick. Users searching for "what used to be here"
must find it.

The provider tracks a "last seen at" timestamp per entity. When
the upstream stops returning the entity:

- For 30 days, the provider keeps emitting the entity with
  `lifecycle: deprecated` and an
  `ml-platform.example.com/tombstoned-at` annotation.
- After 30 days, the provider stops emitting; the catalog
  backend's normal stale-entity cleanup removes it.

The TTL is a knob; 30 days mirrors the project-04 model
registry's deprecation window so users see consistent state
across both surfaces.

## Tenant scope

Every entity carries `metadata.namespace = <tenant>` (or
`default` for platform-owned entities). The catalog's frontend
filter respects this by default; backend plugins enforce it on
read by intersecting the user's allowed tenants (from the auth
token claim) with the entity's namespace.

Cross-tenant entity lookup behaves the same way the
project-04 registry does: returns the equivalent of 404 (the
catalog backend returns an empty result), never 403. The
existence of an entity in another tenant is itself information
we don't disclose.

## References

- Backstage external integrations + processors:
  <https://backstage.io/docs/integrations/>
- Backstage entity provider interface:
  <https://backstage.io/docs/features/software-catalog/external-integrations>
- CNCF TAG App Delivery Platforms White Paper §"Discoverability":
  <https://tag-app-delivery.cncf.io/whitepapers/platforms/>
