# SOLUTION — Module 06: Model Management

> Read after the per-exercise solutions. Cross-exercise rationale.

## What the module is really teaching

A model registry is a **governance system**, not a storage system.
The five exercises are shaped around the four governance
questions every model deployment must answer:

1. **What changed?** (registry + versioning)
2. **What do we do when it goes wrong?** (rollback)
3. **How do we ship it safely?** (canary + progressive rollout)
4. **Who said it was OK to ship?** (governance gate + audit)

## Exercise-by-exercise rationale

### Ex-01 — MLflow Registry deep dive

The reference solution emphasizes the **state machine**:

- `None` → `Staging` → `Production` is a directed graph, not a
  tag soup.
- `Archived` is a one-way terminal state (no model in Archived
  can return to Production without explicit re-registration).
- The transition is the audit event, not the model upload.

Junior engineers treat the Registry as a fancy artifact store.
The reference solution treats it as a workflow engine that
happens to store artifacts.

### Ex-02 — Rollback procedure

A document + a tested mechanism:

- **The rollback path is the same path as the promotion path**,
  in reverse. No special "rollback API."
- The previous Production version's MLflow URI is captured at
  promotion time.
- A `mlctl model rollback <name>` command exists, has been
  exercised in drills, and works.

A rollback procedure that's never been tested is a rollback
procedure that doesn't exist. The reference solution requires
the team to drill it quarterly.

### Ex-03 — Canary via Argo Rollouts

The deployment:

- Argo Rollouts (or Flagger) routes 5% → 25% → 50% → 100% with
  bake-time at each step.
- The bake-time analyzes model-output metrics (not infra metrics)
  to decide promotion.
- Auto-rollback fires if the analysis fails any step.

The point: a canary deployment that only watches HTTP 500s isn't
watching for the failure modes that matter for ML — *prediction
distribution drift* is invisible to the LB.

### Ex-04 — Governance gate

The reference gate:

- **Pre-promotion checklist** (rendered from a YAML template):
  did training pass GE expectations? did fairness eval pass? is
  the model card complete? are tests green?
- **Approval matrix**: who has to sign off for which model tier
  (low-risk auto-approve, high-risk requires named human, high-
  regulatory tier requires named human + compliance review).
- **Audit log**: every promotion records who signed off and when.

A governance gate that doesn't block promotion is a security
theater gate. The reference gate is implemented as an Argo
WorkflowTemplate that fails closed on incomplete sign-offs.

### Ex-05 — Quarterly compliance audit

The deliverable is a written audit report template + an example
run. Sections:

- All Production models, their owners, last evaluation date.
- All promotions in the quarter, who approved them, gate exit
  status.
- All rollbacks, root cause, time-to-rollback.
- Drift detections, time-to-detection, action taken.

This is what a regulator (or an internal compliance team) reads.
A registry that can't produce this is a registry that's failing
the governance job.

## Cross-exercise design decisions

- **State transitions are the audit event**, not the upload.
- **Rollback uses the same path as promotion**, just reversed.
- **Canary watches model metrics**, not just HTTP errors.
- **Governance gates fail closed**.

## Common mistakes graders see

1. **Treating the Registry as a folder structure**. Loses
   audit-ability.
2. **Tag-based promotion** (`v1.2.3 → prod` is a label). No state
   machine, no audit trail.
3. **Rollback as a special path**. Always behind the canonical
   promotion path in maintenance.
4. **Canary using only HTTP-level signals**. Misses the failure
   modes that matter.
5. **Governance gate that's a markdown checklist on Confluence**.
   Not enforced means not done.

## Related curriculum touchpoints

- `engineer/mod-106/ex-02-model-registry` — the next-tier MLflow
  registry exercise.
- `engineer/mod-106/ex-03-canary-deployment` — canary-rollouts
  exercise.
- `engineer/mod-106/ex-08-governance-gates` — the gate enforcement
  pattern.
- `architect/project-301-enterprise-mlops` — same shape at
  enterprise scale.
