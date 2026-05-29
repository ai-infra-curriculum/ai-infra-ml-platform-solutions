# Golden-path templates

The Scaffolder is the platform team's opinion on "the right way
to start", encoded as Software Templates. Three default
templates ship with the reference solution.

## `training-run-from-scratch`

The most-used template: "I want to train a model and I have
nothing yet."

Inputs:

- `name` — repo and component name (kebab-case, regex-validated).
- `owner` — picker bound to `kind: Group`.
- `tenant` — picker derived from the user's allowed tenants
  (from the auth token claim).
- `framework` — enum: `pytorch`, `tensorflow`, `jax`.
- `dataset` — picker bound to `kind: Dataset` filtered by tenant.

Steps:

1. Fetch the language-specific repo skeleton (one Cookiecutter
   per supported framework).
2. Apply `template:variables` (name, owner, tenant).
3. Publish to GitHub under the tenant's GitHub App installation.
4. Open a PR with the scaffolded code and the required
   `catalog-info.yaml`.
5. **Register the entity in the catalog.** Final step;
   non-optional.

Output: a Component entity in the catalog whose
`techdocs-ref: dir:.` ships docs alongside code, whose CI runs
training through project-01's control plane, and whose owner
group is correct from minute zero.

## `fine-tune-from-base`

The "I want to start from a registered base model" path.

Same shape as `training-run-from-scratch`, with one
parameter-time picker that matters:

- `baseModel` — picker bound to `kind: MLModel`, filtered by
  `lifecycle: production`. The picker queries the live registry
  (project-04) for the up-to-date list.

The picker returns the immutable `model-version-id`, not the
name. The skeleton bakes that ID into the training config so
"the base model" is unambiguous across renames.

Steps add one item over `training-run-from-scratch`:

- Inject the base model URI into the new repo's training
  config, pinned to the immutable ID.

## `onboard-tenant`

Admin-only path. The form is gated by a platform-team RBAC
check.

Inputs:

- `tenant` — kebab-case, validated against the existing tenant
  set for uniqueness.
- `parentGroup` — the engineering org node the tenant rolls up
  to.
- `regulated` — boolean; when true, the Compliance scorecard
  applies to the tenant's MLModels.

Steps:

1. Create the Kubernetes namespace.
2. Apply the default-deny `NetworkPolicy` (see
   project-01 `multi-tenancy/`).
3. Bind the SPIFFE workload identity for the tenant.
4. Write the tenant row in the project-01 audit chain.
5. Generate the welcome-page TechDocs entity.
6. Register the new `Group` in the catalog.

Output: a new tenant boundary, fully isolated from existing
tenants by the time step 6 commits. The order matters: NetworkPolicy
*before* the SPIFFE identity *before* the audit row; if step 3
or step 4 fails, the namespace is rolled back.

## Template hygiene the rubric expects

- **`catalog:register` is the final step.** Templates without it
  ship un-cataloged services. F2 hard fail.
- **`publish:github` uses per-tenant GitHub App installations.**
  Not a shared PAT. The bot identity in `git log` should be the
  tenant's installation, not "platform-bot".
- **Pickers are bound to catalog kinds.** Free-text `owner` or
  `tenant` lets users type non-existent values that the catalog
  rejects an hour later, with no breadcrumb back to the form.
- **JSON Schema validation is on every input.** Backstage uses
  the upstream JSON Schema draft the user's Software Template
  version supports; spell-check your regexes.
- **No template embeds secrets.** Tokens come from the runtime
  via the Backstage scaffolder secrets store, never from the
  template YAML.
- **Templates have their own TechDocs.** The template itself is
  a Component with `kind: Template`; its TechDocs page tells the
  user what they get and what they don't.

## References

- Backstage Software Templates:
  <https://backstage.io/docs/features/software-templates/>
- Backstage Scaffolder builtin actions:
  <https://backstage.io/docs/reference/plugin-scaffolder-backend-module-bitbucket-cloud/>
  (and sibling pages per provider)
- CNCF Platforms White Paper §"Golden paths":
  <https://tag-app-delivery.cncf.io/whitepapers/platforms/>
