# API Design Review (Reference Example)

Reference for [learning ex-05](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-002-api-design/exercises/exercise-05-api-design-review.md).

## Top 5 strengths (sample feedback)
1. Cursor pagination — won't break under list mutation
2. Idempotency-Key on POST — prevents accidental duplicates
3. Tenant header consistency — every endpoint requires it
4. Clear state machine in `STATE_MACHINE.md`
5. Rate-limit headers documented in spec

## Top 5 issues
1. **No `If-Match` for cancel** — cancel races with status transitions; suggest ETag
2. **Pagination cursor is opaque integer** — encode as base64 + signed to prevent tampering
3. **`gpu_count: int` will need v2** for fractional GPUs — exercise 02 addressed this
4. **No `_links` in responses** — clients hardcode URLs
5. **Error responses underspecified** — use [RFC 7807 Problem Details](https://datatracker.ietf.org/doc/html/rfc7807)

## Resolutions
- 1: accept (add ETag + If-Match)
- 2: defer (works for v1 size of data; revisit in v2)
- 3: accept (already in v2 plan)
- 4: accept (add `_links` to responses)
- 5: accept (refactor error schemas to RFC 7807)
