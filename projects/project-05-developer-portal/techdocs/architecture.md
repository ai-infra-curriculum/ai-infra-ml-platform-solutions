# TechDocs architecture

TechDocs is the docs-as-code surface Backstage ships. The
reference solution uses the **external build** model: docs are
built by CI on every merge to main, materialized to an
S3-compatible bucket, and rendered by the portal's TechDocs
reader plugin.

The local-build mode (`techdocs.builder: 'local'`) is fine for
`yarn dev` and breaks past a handful of components. The
rubric expects external builds.

## Pipeline

```text
  git push main
      │
      ▼
  CI runner clones the repo
      │
      ├── runs `mkdocs build` against /docs and the entity's
      │   mkdocs.yml (inherits techdocs/mkdocs.example.yml)
      │
      ├── publishes the built HTML + assets to
      │   s3://techdocs/<kind>/<namespace>/<name>/
      │
      └── updates the entity's metadata.annotations[
            'backstage.io/techdocs-ref']
          to point at the bucket path (only if it changed)
      │
      ▼
  Portal users open the TechDocs tab
      │
      ▼
  Portal backend's TechDocs reader fetches HTML from S3,
  serves it through the portal, and indexes its text into
  the search backend.
```

## Required config

`app-config.yaml` on the portal backend:

```yaml
techdocs:
  builder: 'external'
  generator:
    runIn: 'local'  # the build runs in CI, not in the portal
  publisher:
    type: 'awsS3'
    awsS3:
      bucketName: 'techdocs'
      region: '<region>'
      # IAM role attached to the portal pod via IRSA / Workload
      # Identity. No long-lived access keys.
```

Per-entity (`catalog-info.yaml`):

```yaml
metadata:
  annotations:
    backstage.io/techdocs-ref: dir:.
```

`dir:.` points TechDocs at the same repo that ships the code.
Co-located docs and code is the rubric expectation: drift
between "what the docs say" and "what the SDK does" is the most
common DX failure, and this annotation makes drift a code review
smell.

Remote refs (e.g., `url:https://github.com/.../docs`) grade
Partial unless the remote is *generated* from the code repo on
every merge.

## Per-entity `mkdocs.yml`

Every entity that ships docs inherits the platform's MkDocs
config from `techdocs/mkdocs.example.yml`. The key opinionated
choices:

- `plugins: [techdocs-core]` — the upstream TechDocs MkDocs
  plugin, which emits the search-index and frontmatter the
  portal's reader and search expect. Forgetting this is the
  single most common TechDocs failure; the portal silently falls
  back to plain MkDocs with broken anchors.
- `theme: name: material` — the upstream Material theme. The
  reference solution does not ship a custom theme; that's a
  branding decision the platform team handles after launch.

## Search

The portal's search backend indexes:

- Catalog entity metadata (kind, name, owner, tags).
- The TechDocs HTML for every entity that ships docs.

A user typing "TrainingRun status reasons" gets back the right
section of the right repo's docs, with a link that opens the
TechDocs tab on the matching entity. The search index updates on
every catalog tick + every TechDocs publish.

## CI gate

A PR that breaks the MkDocs build (broken cross-link, missing
nav entry, unparseable Markdown) must not merge. The reference
solution ships a GitHub Action that runs `mkdocs build --strict`
on every PR and posts a failing check.

Without that gate, doc rot starts the day after launch.

## References

- Backstage TechDocs overview:
  <https://backstage.io/docs/features/techdocs/>
- Backstage TechDocs CI/CD integration:
  <https://backstage.io/docs/features/techdocs/configuring-ci-cd>
- MkDocs strict mode and configuration:
  <https://www.mkdocs.org/user-guide/configuration/>
- MkDocs Material theme:
  <https://squidfunk.github.io/mkdocs-material/>
