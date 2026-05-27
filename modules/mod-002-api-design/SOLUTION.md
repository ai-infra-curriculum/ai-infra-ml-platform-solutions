# SOLUTION — Module 02: API Design

> Read after the per-exercise solutions. Explains the cross-
> exercise design rationale.

## What the module is really teaching

ML platform APIs are forever. The contract you ship in v1 is what
every training pipeline, every CI job, every notebook ends up
coupled to — and the cost of changing it scales superlinearly
with adoption. This module is shaped around the three skills that
distinguish a platform engineer from someone who can call
`@app.post("/job")`:

1. **Designing for change you can't predict yet** (versioning,
   deprecation, opt-in semantics).
2. **Making the SDK indistinguishable from any other client** so
   you don't fork your own contract.
3. **Reviewing API designs critically** — the most important code
   review on a platform team.

## Exercise-by-exercise rationale

### Ex-01 — Design the training-jobs API

The reference OpenAPI spec deliberately:

- Treats `Job` as a resource, not a workflow. `POST /jobs` creates
  one; `GET /jobs/{id}` reads it; the workflow state lives *on the
  resource*, not in a separate engine call.
- Returns `202 Accepted` on submit, not `201 Created`, because
  the job exists asynchronously.
- Uses a typed `phase` enum, not free-form strings, for the state
  machine.
- Documents *every* phase transition in the spec, so consumers
  can write state-machine-aware clients.

### Ex-02 — Versioning + deprecation plan

The plan ships as a document, not code. The structure:

- **Versioning policy**: SemVer-on-API. Breaking changes require
  major bump. Additive changes (new optional fields, new endpoints)
  are minor.
- **Deprecation lifecycle**: announce → headers (`Deprecation:
  true`, `Sunset: <date>`) → log warnings → 410 Gone after sunset.
- **Migration window**: 90 days minimum, 12 months for major
  breaking changes.
- **Communication channels**: changelog, in-tool warnings,
  email to consumers.

The point: deprecation is a *process*, not a code change. The
plan exists so the engineer who breaks the change six months
later knows what to do.

### Ex-03 — Implement the FastAPI server

The implementation uses the same OpenAPI spec from ex-01 as the
*source*. The FastAPI app generates its routes from the spec via
`@app.get("/...", response_model=...)`, and the validation
happens at the framework boundary. No code lives outside the
spec.

**Anti-pattern to avoid**: writing the server first, then
reverse-engineering the spec. The spec drifts the moment one
handler signature changes silently.

### Ex-04 — Build the Python SDK

The SDK is **generated from the OpenAPI spec**, then hand-
extended. `openapi-generator-cli` produces a typed client; the
hand-extension adds retry logic, pagination helpers, and the
SDK's idiomatic interface.

Two key design rules in the reference SDK:

- The SDK can ship a feature only after the spec ships the
  endpoint. No special internal-only APIs.
- The SDK is dogfooded by the platform's own CLI in ex-02 of
  mod-007. If the SDK isn't usable enough for the platform
  team's own tools, it's not usable enough.

### Ex-05 — API design review

The reference solution is the *review template*, not a review.
Sections:

- Versioning + deprecation posture.
- Authentication + tenant isolation.
- Idempotency for write endpoints.
- Pagination + filtering shape.
- Error response taxonomy.
- Backwards-compatibility statement.

Critical reviews catch the deprecation bug six months in advance.
This template is the artifact the platform team uses for every
future API.

## Cross-exercise design decisions

- **OpenAPI 3.1**, not 3.0 (better JSON Schema alignment).
- **Generate the SDK**, don't hand-write it.
- **Cursor pagination** everywhere, not offset.
- **Typed enums** for every state field; no magic strings.
- **`Idempotency-Key`** required on every POST that mutates.

## Common mistakes graders see

1. **Spec-after-implementation**. Always drifts.
2. **No `Sunset` header**, just "deprecation notice in docs".
   Consumers don't read docs; they read headers their tooling
   parses.
3. **SDK that adds endpoints the server doesn't expose**.
   Eventually someone uses them; eventually they break.
4. **Free-form `status: string`** instead of a typed enum.
   Forecloses every machine-readable client.
5. **`POST /v2/jobs` as a versioning strategy**. Routes-as-
   versioning works for one bump and then breaks.

## Related curriculum touchpoints

- `ml-platform/mod-001` — the OpenAPI-as-artifact discipline this
  module extends.
- `ml-platform/mod-007` — the CLI in ex-02 of that module is the
  SDK's first dogfood consumer.
- `engineer/mod-110/ex-01-production-llm-serving` — what
  OpenAI-compatible API design looks like at the LLM tier.
- `architect/mod-301` — API versioning at enterprise scale.
