Both blockers addressed:

- `operator/reconcile.py:76` — added a `uid` field to `ReconcileInputs` and changed the ownerReference UID to read from `inputs.uid` (the CR's `metadata.uid`) instead of the nonexistent `status.ownerUid`. No callers construct `ReconcileInputs` yet, so the dataclass change is safe.
- `control-plane/openapi.yaml:168` — flipped the `IdempotencyKey` header parameter to `required: true` and tightened the description to match the F6 retry-safety contract.
