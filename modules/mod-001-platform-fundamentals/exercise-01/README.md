# Resource Provisioning API — Solution

Reference for [learning ex-01](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-001-platform-fundamentals/exercises/exercise-01-design-api-for-resource-provisioning.md).

`openapi.yaml` is a complete spec. Validate + generate client:
```bash
openapi-generator-cli validate -i openapi.yaml
openapi-generator-cli generate -i openapi.yaml -g python -o sdk/
```

## Design decisions
- Tenant header required (not embedded in path) — fewer routes to manage
- Idempotency-Key on POST — prevents accidental duplicate provisioning
- Cursor pagination — tolerates list mutation
- Action verb `:extend` (Google-style colon syntax) for non-CRUD action
- Status enum documents the state machine; consumers can reason about it
