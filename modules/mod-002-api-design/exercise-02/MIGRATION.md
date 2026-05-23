# v1 → v2 Migration Plan

## What changed
v1 had `gpu_count: int` (whole GPUs only).
v2 has `gpu: { type, count, mig_slice? }` (fractional via MIG; explicit GPU type).

## Translation
v1:
```json
{ "model_uri": "...", "dataset_uri": "...", "gpu_count": 2 }
```
v2:
```json
{ "model_uri": "...", "dataset_uri": "...", "gpu": { "type": "l40s", "count": 2 } }
```

Default GPU type for migrated v1 calls: `l40s`. Document explicitly.

## Timeline

| T+ | Action |
|---|---|
| 0 | v2 GA; v1 marked deprecated in docs |
| 0 | `Deprecation: true` + `Sunset: 2027-05-23` headers on v1 responses |
| 90d | Email + Slack DM to active v1 users (from access logs) |
| 180d | Banner in console + warning on every v1 response |
| 270d | Individual outreach to remaining v1 users |
| 365d | v1 removed; migration tool provided |

## Rollback plan
- v1 endpoints stay live for the full deprecation period (1 year)
- v2 instances scale independently; v2 outage doesn't affect v1
- If a critical v2 bug surfaces, no rollback is needed — users can revert to v1

## Migration tool
`migrate.py` provides bidirectional translation:
```bash
python migrate.py v1-to-v2 < v1_request.json > v2_request.json
python migrate.py v2-to-v1 < v2_request.json > v1_request.json    # additive subset
```
