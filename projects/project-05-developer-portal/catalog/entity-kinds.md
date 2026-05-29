# Catalog entity kinds — ML platform

Backstage ships eight standard entity kinds: `Component`, `API`,
`Resource`, `System`, `Domain`, `Group`, `User`, `Location`. The
ML platform extends this set with two custom kinds — `MLModel`
and `Dataset` — registered on the catalog backend via a custom
`EntityProcessor` + `EntityPolicy`.

The choice to *extend* rather than *abuse* `Component` is
deliberate. Treating a model as a `Component` works for one
quarter and breaks the moment scorecards, search filters, and
plugin entity pages need ML-specific facets (framework, model
version ID, signing identity, lineage edges) that the standard
kind does not carry.

## Standard kinds — how the platform uses them

| Kind | Used for | Notes |
|---|---|---|
| `Domain` | The `ml-platform` umbrella. | One per major surface (platform, data, app). |
| `System` | A bounded subsystem (control plane, registry, feature store). | The integration unit a team thinks about. |
| `Component` | SDKs, CLIs, services, backend plugins, frontend plugins. | The "code that runs" surface. |
| `API` | OpenAPI specs for every platform API. | `definition` is inlined or refs an in-repo file. |
| `Resource` | TrainingRuns (live runs), namespaces, S3 buckets. | Dynamic resources the platform manages. |
| `Group` | Tenants and the platform team itself. | `spec.type: team`. The tenant claim in the auth flow resolves to a Group. |
| `User` | Engineers. | Sourced from the IdP, not committed. |
| `Location` | Catalog discovery roots. | One per source repo / org. |

## Custom kinds

### `MLModel`

A registered model version, surfaced from the project-04 model
registry.

```yaml
apiVersion: ml-platform.example.com/v1alpha1
kind: MLModel
metadata:
  name: <model-name>
  namespace: <tenant>
  annotations:
    ml-platform.example.com/registry-url: <stable-url>
    ml-platform.example.com/model-version-id: <uuid>
spec:
  type: classifier | regressor | embedding | generator
  lifecycle: experimental | production | deprecated
  framework: <pytorch-2.1 | tensorflow-2.15 | onnx-1.16 | ...>
  owner: group:<team>
  system: <system-name>
  trainingRun: resource:<namespace>/<training-run-name>
  dataset: dataset:<namespace>/<dataset-name>
```

`spec.trainingRun` and `spec.dataset` are typed cross-references
the catalog backend resolves on read. They are the lineage edges
project-04 exposes through `lineage/queries.sql`; the portal
walks them on the entity page to render the lineage graph.

`metadata.annotations['ml-platform.example.com/model-version-id']`
is the immutable identity the registry assigned; the portal
treats it as the primary key when the entity name changes.

### `Dataset`

A training dataset version. Surfaced either from the feature
store (project-02) or from a versioned-data system (DVC, LakeFS).

```yaml
apiVersion: ml-platform.example.com/v1alpha1
kind: Dataset
metadata:
  name: <dataset-name>
  namespace: <tenant>
spec:
  type: tabular | image | text | timeseries | mixed
  lifecycle: experimental | production | deprecated
  owner: group:<team>
  system: <system-name>
```

`Dataset` is the target of the `MLModel.spec.dataset` reference;
reverse-lineage queries from a dataset to the models trained on
it walk this graph.

## Validators

Each custom kind has a validator implementing the upstream
`KindValidator` interface. Validators:

- Reject entities with a missing `spec.framework` (MLModel) or
  `spec.type` (Dataset).
- Reject `lifecycle` values outside the enum.
- Reject `owner` that does not resolve to an existing `Group`.

A validator that does not reject yet has been wrong before;
the catalog will silently swallow the bad entity and surface it
in the portal with no warning. Reject loud.

## Why not just use `Component` with extra annotations?

Three reasons the rubric expects custom kinds:

1. **Search and filtering.** Backstage's standard `kind` filter
   is the single biggest UX win in the catalog; users search
   `kind:MLModel owner:group:team-recs` not
   `kind:Component spec.type:model owner:group:team-recs`.
2. **Plugin entity pages.** The model-registry plugin only
   wants to render on `MLModel`, never on a generic
   `Component`. Custom kinds are the contract that lets the
   plugin attach without a runtime sniff.
3. **Scorecards.** The Compliance scorecard only applies to
   `MLModel`. Without the kind, every scorecard has to inspect
   annotations to decide if it applies — that's the kind of
   abstraction leak the catalog model exists to prevent.

## References

- Backstage descriptor format:
  <https://backstage.io/docs/features/software-catalog/descriptor-format>
- Backstage extending the model (custom kinds + validators):
  <https://backstage.io/docs/features/software-catalog/extending-the-model>
- Project-04 lineage queries:
  [`projects/project-04-model-registry/lineage/queries.sql`](../../project-04-model-registry/)
