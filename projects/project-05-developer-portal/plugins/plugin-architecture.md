# Plugin architecture

The portal extends Backstage cleanly: one plugin per platform
component, a frontend half and a backend half each, all wired
through the Backstage plugin system.

## Plugin set

| Plugin | Covers |
|---|---|
| `@ml-platform/plugin-training-runs` | project-01 control plane: TrainingRun entity page, submit form, live status. |
| `@ml-platform/plugin-feature-store` | project-02 feature store: FeatureSet browser, freshness, owners. |
| `@ml-platform/plugin-workflows` | project-03 orchestrator: pipeline runs, retry/skip, gates. |
| `@ml-platform/plugin-model-registry` | project-04 model registry: MLModel page (metadata, lineage graph, deployment timeline, promotion approvers, signing identity). |

Each plugin is a separate Yarn workspace with its own
`package.json`, its own tests, and its own version. Coupling
them collapses the plugin model and makes plugin upgrades a
big-bang release.

## Frontend / backend split

### Frontend plugin (`packages/plugin-<name>`)

- Renders entity pages and standalone pages.
- Talks **only** to its own backend plugin via the Backstage
  fetch API. Never to platform APIs directly — the browser
  cannot hold a service identity.
- Imports the Backstage Material UI theme; does not ship its
  own colors.

### Backend plugin (`packages/plugin-<name>-backend`)

- Proxies + caches against the platform API.
- Performs the RFC 8693 token exchange (see
  [`auth/identity.md`](../auth/identity.md)) on every request,
  binding the user's identity into the downstream token.
- Caches per-user with a 30 s TTL and a stale-on-error
  fallback. The cache key includes the user's tenant claim so a
  tenant-boundary breach is impossible.

## Patterns the reference solution standardizes

- **Per-user cache, not global.** A global cache that strips
  the user dimension is the most common security regression in
  Backstage backend plugins. Cache key = (path, user-sub,
  tenant-claim).
- **Stale-on-error.** When the platform API returns 5xx, the
  cache returns the last successful response with a warning
  banner in the frontend. A platform API outage must not blank
  every entity page.
- **No long polls.** The frontend polls the backend on a 10 s
  tick; the backend serves from cache. WebSockets are
  attractive and out of scope for the rubric — they add a state
  machine that adds zero adoption value.
- **Tests as a merge gate.** Every plugin ships with a Jest
  suite; the platform team rejects plugin PRs without tests at
  review.
- **Plugin contract is the catalog kind.** Frontend plugins
  attach to entity pages by kind (`MLModel`, `Component` of
  `type: training-job`, etc.). Free-floating "render on
  everything" plugins are how UI collisions happen.

## Plugin proxy vs. iframe

Embedding external dashboards (Grafana, Kibana, Jaeger) is a
common request. Two paths:

- **Plugin proxy** (preferred): the Backstage backend proxies
  the third-party request, rewrites the HTML, and serves it
  same-origin. CSP and `X-Frame-Options` stay intact.
- **iframe** (avoid): requires an `X-Frame-Options` exemption on
  the third party and a CSP relaxation on the portal. Each
  exemption is a future incident.

The reference solution uses the proxy plugin's HTML rewriting
path for Grafana embeds; iframe is documented as the fallback
only when the third party refuses to be proxied.

## Plugin governance

The platform team owns the plugin contract; tenants do not ship
their own plugins to the central portal. A team that wants to
extend the portal goes through:

1. Open a discovery doc in the platform team's RFC repo.
2. Get review for catalog kind, API surface, security
   implications.
3. The platform team writes the plugin (or pair-codes with the
   requester). Maintenance ownership is documented in the
   plugin's `catalog-info.yaml`.

Tenant-specific UIs live in the tenant's own apps, not the
central portal. The portal is a shared product; one tenant's
weird workflow does not get to ride in the trunk build.

## References

- Backstage backend system (the modern plugin architecture):
  <https://backstage.io/docs/backend-system/>
- Backstage proxy plugin:
  <https://backstage.io/docs/plugins/proxying/>
- CNCF Platforms White Paper §"Extensibility":
  <https://tag-app-delivery.cncf.io/whitepapers/platforms/>
