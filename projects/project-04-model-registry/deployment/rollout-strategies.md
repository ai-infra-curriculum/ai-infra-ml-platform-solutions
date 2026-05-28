# Rollout strategies + rollback -- reference solution for F4, F5

This is the registry-side reference for how each rollout strategy is
*recorded* and *transitioned*. The actual traffic-splitting is the
mesh's job (Istio, Linkerd, Flagger, Argo Rollouts). The registry's
contribution is:

1. Picking the right strategy at deployment time.
2. Tracking the current state (`Active | Rolled-back | Decommissioned`).
3. Knowing the prior `Production` version per target environment, so
   rollback is one API call instead of a manual archaeology session.

## Strategy semantics

| Strategy | What it does | Registry behavior | When to use |
|---|---|---|---|
| **rolling** | Replace pods one-by-one in the same Deployment object. Default. | Single row in `deployments`; `traffic_share` is NULL. | Default for stateless serving where the model contract has not changed. |
| **blue-green** | Bring up new fleet at full capacity in parallel; swap the service selector at the LB. | Two rows live temporarily (`Active` blue + `Active` green); flip is a swap of selectors, not a registry mutation; the old row goes `Decommissioned` after bake. | Schema changes, batching changes, framework upgrades -- anywhere you want a hard cutover. |
| **canary** | Send a fraction of traffic to the new version, ramp up if metrics hold. | Two `Active` rows: old at `traffic_share = 1 - p`, new at `traffic_share = p`. Ramp = update both rows in one transaction. | Any change to model weights where output-distribution drift could surprise downstream consumers. |
| **shadow** | Send 100% of traffic to old; mirror to new. New version's output is logged + compared, **never** reaches clients. | New row at `traffic_share = 0`, `rollout_strategy = shadow`. | Risk-bearing changes where you want offline diff before any customer exposure. |

> The most common mistake is treating shadow as a 0% canary -- they
> are not the same. A 0% canary is just "deployed but no traffic"; a
> shadow run *receives mirrored traffic* and produces output that's
> compared offline. Get this wrong and you ship silent customer
> impact.

## Canary ramp

The registry does **not** push the ramp; it records each ramp step.
The mesh or rollout operator does the actual traffic shift; once it
confirms, the platform calls the registry to update `traffic_share`.

```
POST /v1/deployments/{old_id}    { "traffic_share": 0.95 }
POST /v1/deployments/{new_id}    { "traffic_share": 0.05 }
```

Both updates happen in one transaction (`BEGIN; UPDATE…; UPDATE…; COMMIT;`)
because a window where shares do not sum to 1.0 is a window where the
registry is lying to whoever is reading `production_deployments`.

Recommended steps (mirrors industry defaults; tune per workload):

```
5% -> bake 10 min -> 25% -> bake 15 min -> 50% -> bake 30 min -> 100%
```

If any bake fails its analysis criteria (model-output drift, not
HTTP error rate), the rollout pipeline calls the rollback endpoint.

## Rollback contract (F5)

The rollback endpoint takes a `deployment_id` (the *current* active
deployment) plus a required `reason` field, and produces a *new*
deployment row that re-activates the previous `Production`-status
version for the same target environment.

```sql
-- pseudo-implementation; lives in the FastAPI handler
WITH cur AS (
    SELECT target_environment, model_version_id
      FROM deployments
     WHERE id = $1 AND status = 'Active'
), prior AS (
    SELECT d.model_version_id
      FROM deployments d
      JOIN model_versions mv ON mv.id = d.model_version_id
     WHERE d.target_environment = (SELECT target_environment FROM cur)
       AND mv.status = 'Production'
       AND d.model_version_id <> (SELECT model_version_id FROM cur)
       AND d.deployed_at < (SELECT deployed_at FROM deployments WHERE id = $1)
     ORDER BY d.deployed_at DESC
     LIMIT 1
)
INSERT INTO deployments (model_version_id, target_environment,
                         rollout_strategy, deployed_by, status,
                         audit_chain_entry_id)
SELECT model_version_id, (SELECT target_environment FROM cur),
       'rolling', current_user, 'Active', $audit_id
  FROM prior
RETURNING *;
```

After the new row is inserted, the prior `Active` row is updated to
`status = 'Rolled-back'` with `rollback_reason` populated. Both writes
share a single transaction; the audit-chain entry is emitted only
after `COMMIT`.

**Rollback SLO**: API call to traffic restored < 5 minutes
(single-cluster). The slow part is the rollout operator's reconcile;
the registry itself is < 100 ms. If a learner's rollback misses the
5-minute budget, the bottleneck is in the mesh wiring, not here.

## State-machine reminder

```
                  registerModelVersion
                          v
            (Registered) -->  promote staging  --> (Staging)
                          v                            v
                          v                    staging_to_production
                          v                            v
                  (signed, gates pass, approvals)      v
                                                       v
                                              (Production)
                                                       v
                                              deprecate / decommission
```

A version cannot go `Registered -> Production` directly; the gate set
runs at `registered_to_staging` as well, but `signature` and
`human_approval` only run on `staging_to_production`. The
`evaluate_gates(transition=...)` API is what enforces this.

## What NOT to do

- **Update existing deployment rows during a canary ramp by deleting
  and re-inserting.** Keep one row per (target, version, lifecycle);
  ramp is an UPDATE of `traffic_share`. Deleting kills traceability.
- **Skip the audit-chain entry when rolling back.** A rollback that
  isn't on the chain doesn't exist for the auditor.
- **Allow rollback without a reason.** Compliance wants to read the
  reason field; the API contract refuses an empty string.
- **Verify signatures only at promotion.** Verify again at deployment
  (the F2 "double-verify" requirement).
