# SOLUTION — Exercise 05: API Design Review (Pair Exercise)

> Per-exercise solution. The cross-exercise rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md); this file factors the Ex-05
> section into a self-contained reference for graders and pair
> reviewers. The companion artifact is
> [`REVIEW.md`](./REVIEW.md), a worked sample review.

## 1. Solution overview

The deliverable of Ex-05 is **a review, not a redesign**. The
exercise teaches the third platform-engineering skill the module
calls out: *reviewing API designs critically — the most important
code review on a platform team* (see
[`../SOLUTION.md`](../SOLUTION.md#what-the-module-is-really-teaching)).

The reference solution is therefore a **review template** plus a
**worked example** that applies it to the Ex-01 OpenAPI spec
(`../exercise-01/openapi.yaml`) and `STATE_MACHINE.md`.

The template's six sections — taken directly from the module
solution — are the axes every API review on this platform must
cover:

- Versioning + deprecation posture.
- Authentication + tenant isolation.
- Idempotency for write endpoints.
- Pagination + filtering shape.
- Error response taxonomy.
- Backwards-compatibility statement.

A review is **complete** when every axis has either a finding or
an explicit "no issues found, here's why" line. Silence on an
axis is a failed review, not a passing one.

## 2. Worked answer

The sample review against the Ex-01 spec is in
[`REVIEW.md`](./REVIEW.md). Summary of the worked example:

**Strengths surfaced**

1. Cursor pagination — won't break under list mutation.
2. `Idempotency-Key` on POST — prevents accidental duplicates.
3. Tenant header consistency — every endpoint requires it.
4. Clear state machine in `STATE_MACHINE.md`.
5. Rate-limit headers documented in spec.

**Issues raised**

1. **No `If-Match` for cancel** — cancel races with status
   transitions; suggest ETag.
2. **Pagination cursor is an opaque integer** — encode as base64
   and sign to prevent tampering.
3. **`gpu_count: int` will need v2** for fractional GPUs;
   exercise-02 already addresses this.
4. **No `_links` in responses** — clients hardcode URLs.
5. **Error responses underspecified** — use
   [RFC 7807 Problem Details](https://datatracker.ietf.org/doc/html/rfc7807).

**Resolutions recorded by the author**

- Accept: add ETag + `If-Match` on cancel.
- Defer: opaque-integer cursor is fine for v1 data sizes; revisit
  in v2.
- Accept: fractional-GPU shape already in the v2 plan.
- Accept: add `_links` to responses.
- Accept: refactor error schemas to RFC 7807.

### Decision rationale

The worked resolutions illustrate the only two valid review
outcomes per finding: **accept** (with an owner and a tracking
issue) or **defer with a written reason and a revisit
condition**. "Won't fix" without a revisit condition is treated
as accept-and-forget and fails the rubric.

The `gpu_count` finding is deliberately resolved by pointing at
Ex-02's deprecation/versioning plan. A reviewer who notices a
future-breaking field but does not name the migration mechanism
has only done half the job.

## 3. Implementation

The "implementation" for this pair exercise is the artifact pair
that produces the review, not running code:

1. **Template file — `REVIEW.md` skeleton.** The six review
   axes (versioning, auth/tenant isolation, idempotency,
   pagination, error taxonomy, backwards-compatibility) each get
   a top-level `##` heading with the same name across every
   review on this platform. Reviewers fill each section with at
   least one explicit line — a finding *or* a "no issues found,
   here's why" line. The skeleton is reused verbatim across
   future API reviews so graders and authors share one shape.
2. **Worked review — `REVIEW.md` populated.** Apply the skeleton
   to `../exercise-01/openapi.yaml` and
   `../exercise-01/STATE_MACHINE.md`. Each finding cites a
   concrete spec location (operation ID or JSON path) and ends
   with `accept` / `defer (reason + revisit condition)` /
   `reject (reason)`. The committed `REVIEW.md` is the canonical
   worked example.
3. **Pair-review workflow.** One author drafts the review
   against the skeleton; the partner walks the axes and
   challenges silent sections. Resolutions are recorded inline,
   not in a separate doc, so the artifact is self-contained.
4. **Cross-links to sibling exercises.** Findings that touch
   versioning (e.g. `gpu_count` needing a major bump) link to
   the Ex-02 migration plan rather than re-deriving the
   deprecation policy. This keeps the review focused on the
   contract and avoids duplicating Ex-02's content.

No code is written or executed; the deliverable is the populated
`REVIEW.md` and the resolutions table it carries.

## 4. Validation steps

A review passes when *all* of the following hold:

1. **Every template section has at least one line of explicit
   commentary.** Empty sections fail.
2. **Each issue references a concrete spec location** (file +
   path or operation ID) — not "the API in general".
3. **Each issue has a resolution** of `accept`, `defer (reason +
   revisit condition)`, or `reject (reason)`.
4. **The strengths list is honest** — no padding. If fewer than
   five strengths are real, list fewer. Inflated strengths erode
   trust in the rest of the review.
5. **The review cites at least one external standard or RFC**
   where applicable (e.g. RFC 7807 for the error-taxonomy axis)
   rather than personal preference.

Re-run the review against
[`../exercise-01/openapi.yaml`](../exercise-01/openapi.yaml) using
the rubric below; the worked example in `REVIEW.md` should score
full marks on coverage and partial marks only on the deferred
pagination cursor item.

## 5. Rubric / review checklist

Use this as the grading rubric for a pair-submitted review.

| Axis | Pass criterion | Worked-example evidence |
| --- | --- | --- |
| Versioning + deprecation | Names the policy (e.g. SemVer-on-API) and any field/endpoint that will need a major bump. | `gpu_count` flagged for v2; routes back to Ex-02 plan. |
| Auth + tenant isolation | Confirms tenant identity is carried on every operation and that no endpoint trusts a path parameter alone. | Strength #3 — tenant header consistency. |
| Idempotency on writes | Every state-mutating POST/PUT/DELETE has either `Idempotency-Key`, ETag/`If-Match`, or a written justification for omission. | Strength #2; Issue #1 — missing `If-Match` on cancel. |
| Pagination + filtering | Cursor is opaque to clients and tamper-resistant; filter parameters are typed. | Strength #1; Issue #2 — sign the cursor. |
| Error taxonomy | Errors use a structured schema (RFC 7807 is the default) with stable codes consumers can branch on. | Issue #5 — adopt RFC 7807. |
| Backwards compatibility | Each accepted change is classified additive vs. breaking; breaking changes link to the deprecation plan. | Resolutions section pairs accepts with the v2 plan. |
| Resolution discipline | Every finding has accept / defer-with-reason / reject-with-reason. | Resolutions list — five findings, five outcomes. |

A passing review covers all seven rows. A review that misses any
row is sent back regardless of how good the surfaced findings
are.

## 6. Common mistakes

Carried forward from the module-level common-mistakes list
([`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see))
and the patterns this exercise is built to catch:

1. **Reviewing the implementation, not the spec.** The contract
   is the artifact under review. Pointing at `app.py` from Ex-03
   when the spec is wrong inverts the source of truth.
2. **"No `Sunset` header, just a deprecation notice in docs."**
   Reviews that accept docs-only deprecation miss the most
   common breaking-change failure mode.
3. **Free-form `status: string` slipping through.** A typed-enum
   check on every state field belongs in the versioning axis;
   reviewers who skip it forclose machine-readable clients.
4. **Treating "looks fine" as a review.** Silence on an axis
   fails the rubric (see Validation §1).
5. **Listing issues without resolutions.** A review without
   accept/defer/reject decisions is a complaint, not a review.

## 7. References

- Module solution rationale —
  [`../SOLUTION.md`](../SOLUTION.md), section "Ex-05 — API design
  review".
- Sibling artifacts the worked review reads:
  [`../exercise-01/openapi.yaml`](../exercise-01/openapi.yaml),
  [`../exercise-01/STATE_MACHINE.md`](../exercise-01/STATE_MACHINE.md),
  [`../exercise-02/MIGRATION.md`](../exercise-02/MIGRATION.md).
- Worked review sample — [`REVIEW.md`](./REVIEW.md).
- Learning exercise prompt —
  `lessons/mod-002-api-design/exercises/exercise-05-api-design-review.md`
  in the `ai-infra-ml-platform-learning` repo.
- [RFC 7807 — Problem Details for HTTP APIs](https://datatracker.ietf.org/doc/html/rfc7807)
  (cited in the error-taxonomy axis).
