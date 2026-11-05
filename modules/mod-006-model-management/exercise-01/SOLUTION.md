# SOLUTION — Exercise 01: MLflow Registry Deep Dive

> Per-exercise solution. The module-level rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md) §Ex-01; this file factors that
> section into a self-contained reference for graders and learners.
> Companion artifacts in this directory: [`README.md`](./README.md)
> (quick-pointer to the engineer-tier worked implementation) and the
> sibling exercises' scripts
> ([`../exercise-02/rollback.py`](../exercise-02/rollback.py),
> [`../exercise-04/gate.py`](../exercise-04/gate.py),
> [`../exercise-05/quarterly_audit.py`](../exercise-05/quarterly_audit.py))
> that depend on this exercise's choices.

## 1. Solution overview

The deliverable is **a working MLflow Model Registry deployment that
treats the Registry as a state machine, not a folder**. Everything
else is implementation detail.

The reference solution commits to four design decisions that drive
every artifact in this exercise and every downstream exercise in the
module:

1. **Tracking server + Registry run against a real relational
   backend** (Postgres), not the default SQLite. Only the database
   backend supports the Model Registry
   ([MLflow Model Registry docs](https://mlflow.org/docs/latest/model-registry.html)).
2. **Artifacts live in object storage**
   (S3-compatible — the reference uses MinIO for local dev). The
   tracking DB holds metadata + URIs; the DB never stores bytes.
3. **`None → Staging → Production` is a directed state graph,
   not a tag soup** (see [`../SOLUTION.md`](../SOLUTION.md) §Ex-01).
   `Archived` is a **one-way terminal state**; a version coming out
   of `Archived` requires explicit re-registration, which is a new
   audit event.
4. **The transition is the audit event, not the model upload.**
   Every `transition_model_version_stage` call is the row the
   compliance exercise ([`../exercise-05`](../exercise-05/))
   reads.

A registry that stores many versions but never transitions them is
not solving the exercise — the state transitions are the whole
point. The engineer-tier worked implementation
([`README.md`](./README.md)) wires Postgres + MinIO + autolog +
signatures + a `pyfunc` wrapper around a scikit-learn baseline so
every downstream exercise (rollback, canary, gate, audit) has a
concrete fixture to operate on.

## 2. Worked answer or implementation

The worked implementation uses an Iris classifier as the fixture.
Nothing about the choice of model matters to the Registry story; the
five artifacts below are what the Registry grader scores.

### 2.1 Deployment topology

```
┌───────────────────────┐        ┌────────────────────┐
│  MLflow Tracking +    │        │  Postgres          │
│  Model Registry API   │────────│  (metadata store)  │
└──────────┬────────────┘        └────────────────────┘
           │
           │ artifact URIs
           ▼
    ┌────────────────┐
    │  MinIO (S3)    │  ← artifact store
    └────────────────┘
```

`MLFLOW_TRACKING_URI` points at the tracking server; the server is
started with `--backend-store-uri postgresql://…` and
`--default-artifact-root s3://mlflow-artifacts/`. The MinIO bucket
is created out of band and the tracking server's AWS credentials
target MinIO.

### 2.2 Training + registration script

The registration script does four things in order, each of which the
rubric checks:

1. Infers a **model signature** from the training frame
   (`mlflow.models.infer_signature`). Without a signature the
   `pyfunc` serving path cannot validate inputs; graders treat a
   missing signature as a failing submission because it breaks the
   contract every downstream exercise assumes.
2. Logs an **input example** so the Registry UI can render a
   smoke-test payload.
3. Enables **autolog** before training so hyperparameters, metrics,
   and the fitted artifact are captured without hand-written log
   calls.
4. Calls `mlflow.sklearn.log_model(..., registered_model_name=NAME)`,
   which both logs the artifact *and* creates (or appends) a version
   row in the Registry in one call.

```python
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

NAME = "iris-rf"

X, y = load_iris(return_X_y=True, as_frame=True)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)

mlflow.sklearn.autolog()
with mlflow.start_run():
    clf = RandomForestClassifier(n_estimators=50, random_state=0).fit(Xtr, ytr)
    sig = infer_signature(Xtr, clf.predict(Xtr))
    mlflow.sklearn.log_model(
        clf,
        artifact_path="model",
        signature=sig,
        input_example=Xtr.iloc[:1],
        registered_model_name=NAME,
    )
```

### 2.3 State-machine transitions (the audit-event step)

Promotion is a `MlflowClient` call, not a tag mutation. The
`archive_existing_versions=True` flag is what makes
`Production → Archived` a **one-way terminal transition** for the
displaced version and preserves the module's "Archived is terminal"
invariant.

```python
from mlflow.tracking import MlflowClient
c = MlflowClient()

# Author promotes to Staging after smoke tests pass.
c.transition_model_version_stage(name=NAME, version="1", stage="Staging")

# Governance gate (see ../exercise-04/gate.py) promotes to Production.
# archive_existing_versions=True is what writes the one-way edge:
# whatever was in Production goes to Archived in the same call.
c.transition_model_version_stage(
    name=NAME, version="1", stage="Production",
    archive_existing_versions=True,
)
```

Three facts about this call matter to the rubric:

- **Stage names are enumerated** (`None | Staging | Production |
  Archived`) by MLflow; free-form strings are rejected by the API.
  That enumeration is the state machine.
- **`archive_existing_versions=True` is the switch** that makes the
  module-level invariant hold. Omitting it leaves two versions in
  Production, which is the "tag soup" failure mode the rubric
  catches.
- **The call is the audit record.** Downstream exercises (rollback,
  gate, quarterly audit) read `MlflowClient.search_model_versions`
  and `client.get_model_version_stages`; they do not need a
  separate audit log. If a transition did not happen through the
  API, it did not happen.

### 2.4 Tags as governance metadata

Stage transitions carry the state; **tags carry the evidence**. The
governance tags set in this exercise are the exact keys the Ex-04
gate script
([`../exercise-04/gate.py`](../exercise-04/gate.py))
refuses to promote without:

```python
c.set_model_version_tag(NAME, "1", "model_card_uri", "s3://model-cards/iris-rf/v1.md")
c.set_model_version_tag(NAME, "1", "bias_review_uri", "s3://bias/iris-rf/v1.pdf")
c.set_model_version_tag(NAME, "1", "decision_log_uri", "s3://decisions/iris-rf/v1.md")
c.set_model_version_tag(NAME, "1", "team", "ml-platform")
c.set_model_version_tag(NAME, "1", "model_card_updated_at", "2026-01-15T00:00:00+00:00")
```

The `model_card_updated_at` tag feeds the staleness check in
[`../exercise-05/quarterly_audit.py`](../exercise-05/quarterly_audit.py).
Tags are the integration point across the module; the exercise is
not complete until those keys are present.

### 2.5 Pyfunc serving contract

The fitted model is loaded through the generic `pyfunc` interface,
not a framework-specific loader. This is the contract canary and
rollback both depend on:

```python
import mlflow.pyfunc
model = mlflow.pyfunc.load_model(f"models:/{NAME}/Production")
model.predict(payload_df)
```

`models:/<name>/<stage>` URIs — the Registry-aware form of a model
URI — are what make rollback trivial: changing the version in
Production flips what every `models:/.../Production` loader
resolves to on the next load. That is the mechanism
[`../exercise-02/rollback.py`](../exercise-02/rollback.py) relies on.

### 2.6 Decision rationale

- **Why Postgres (not SQLite)?** The Model Registry requires a
  database-backed tracking server
  ([MLflow Model Registry docs](https://mlflow.org/docs/latest/model-registry.html));
  the file-store backend does not implement registry endpoints.
  SQLite works locally but the reference deploys Postgres so the
  code that runs in CI is identical to the code that runs in prod.
- **Why MinIO (not local filesystem)?** The artifact URI shape
  (`s3://…`) is the same in dev as it is in cloud; swapping to real
  S3 is a credential change, not a code change. The reference
  solution deliberately avoids the `file://` artifact root because
  it hides the S3-shaped bug class until the first cloud deploy.
- **Why autolog + explicit `log_model`?** Autolog captures the
  training run's parameters and metrics; `log_model` with an
  explicit signature pins the serving contract. Relying on autolog
  alone gets you the run but not a reliable `pyfunc` loader.
- **Why `archive_existing_versions=True` at promotion time?**
  See §2.3 — this is the switch that keeps the state machine
  honest. The module-level common-mistakes list calls out the
  opposite pattern ("tag-based promotion") by name
  ([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see).

## 3. Validation steps

A submission is valid when **every one of the following observable
checks passes against the running Registry**. Each check names the
exact API call the grader runs.

1. **Registry is reachable and backed by Postgres.**
   `mlflow.get_registry_uri()` returns the tracking URI, and
   `c.search_registered_models()` succeeds. A SQLite backend fails
   this step because `search_registered_models` is not implemented
   against the file store.
2. **A registered model exists with at least one version.**
   `c.search_model_versions("name='iris-rf'")` returns ≥ 1 row.
3. **Every version has a signature and an input example.**
   `c.get_model_version_download_uri(...)` leads to an `MLmodel`
   file whose YAML contains both `signature` and `saved_input_example_info`.
4. **Governance tags are present.** For each Production version:
   `set(c.get_model_version(name, v).tags) ⊇
   {"model_card_uri", "bias_review_uri", "decision_log_uri",
   "model_card_updated_at", "team"}`.
   This is exactly what `../exercise-04/gate.py` enforces.
5. **State transitions work and are observable through the API.**
   Promote `v1` → Staging → Production, then register `v2` and
   promote with `archive_existing_versions=True`.
   Observe:
   - `c.get_latest_versions("iris-rf", stages=["Production"])` returns
     exactly one version, and it is `v2`.
   - `v1.current_stage == "Archived"` (the displaced version moved
     to the terminal state in the same call).
6. **Pyfunc serving contract is honored.**
   `mlflow.pyfunc.load_model("models:/iris-rf/Production").predict(Xte.iloc[:5])`
   returns five labels. Breaking the signature (e.g. dropping a
   column) raises a validation error at `predict` time — this is
   the contract downstream exercises rely on.
7. **Rollback drill.**
   Running
   [`../exercise-02/rollback.py iris-rf`](../exercise-02/rollback.py)
   after a promotion puts the previous version back into Production
   in one transaction (current → Archived, previous → Production).
   A rollback drill that cannot complete this cycle is a failing
   Ex-01 submission, because the Registry state machine is what
   rollback relies on.
8. **Audit view over transitions.**
   `c.search_model_versions("name='iris-rf'")` plus
   `c.get_model_version(name, v).last_updated_timestamp` is enough
   to reconstruct the sequence of transitions. No separate audit
   table is required — the Registry itself is the audit trail.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
|---|---|---|
| Backend topology | Postgres tracking DB + S3-compatible artifact store; `MLFLOW_TRACKING_URI` points at the tracking server. | SQLite backend; file-system artifact root; tracking URI hard-coded in the training script. |
| Registration | `log_model(..., registered_model_name=…)` with explicit `signature` and `input_example`. | `log_artifact` + manual `create_registered_model` call; missing signature; no input example. |
| State machine | Only `None → Staging → Production → Archived` transitions used; `Production` is unique per model name. | Free-form stage strings; multiple `Production` versions coexisting; tag-based "promotion". |
| Promotion semantics | `archive_existing_versions=True` on every `→ Production` transition. | Promotions leave two versions in `Production`; or the displaced version is transitioned by hand in a separate call that can fail independently. |
| Governance tags | `model_card_uri`, `bias_review_uri`, `decision_log_uri`, `team`, `model_card_updated_at` all set on every Production version. | Tags on the run, not on the model version; tags only on the latest version; stale `model_card_updated_at`. |
| Serving contract | `mlflow.pyfunc.load_model("models:/<name>/Production")` loads and predicts; signature validates inputs. | Loader hard-codes a run ID; `pyfunc` not exercised; signature absent. |
| Rollback-ready | `rollback.py` succeeds end-to-end against the Registry. | Rollback requires manual DB edits or a side table. |
| Audit observability | Transitions reconstructable from `search_model_versions` + `get_model_version` alone. | Submission ships a parallel audit log the Registry doesn't already provide. |
| Reproducibility | Training script is deterministic (seeds set); CI runs the same code as local. | Random seeds unset; environment drift between CI and local. |

A passing submission scores Pass on every row. Dimension failures
are not interchangeable — a working rollback cannot compensate for a
broken state machine.

## 5. Common mistakes

Inherited from the module-level list
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see) and
narrowed to the registry exercise:

1. **Treating the Registry as a folder structure.** Logging
   artifacts to `s3://bucket/models/iris-rf/v1/` outside of MLflow
   and then "registering" by inserting a row loses the state
   machine, the tag API, the signature contract, and every
   downstream exercise's integration point.
2. **Tag-based promotion** (`"stage" = "prod"` as a tag). Does not
   fire the archive transition, does not increment
   `last_updated_timestamp` in a way downstream code recognizes,
   and is invisible to `get_latest_versions(stages=[…])`.
3. **Missing signature or input example.** The `pyfunc` loader
   still works, but input validation at serving time silently
   stops — exactly the failure mode the canary exercise is
   designed to catch *after* it has already shipped bad predictions.
4. **Omitting `archive_existing_versions=True`.** Leaves two
   versions in Production at the same time. Every query that reads
   "the current Production version" now has to pick one; different
   callers will pick differently.
5. **Setting governance tags on the *run* instead of the *version*.**
   The Ex-04 gate reads `MlflowClient.get_model_version(name, v).tags`.
   Tags on the run are invisible to that call.
6. **Rolling back by uploading a new model with the old weights.**
   Breaks lineage, breaks the version history, and shows up in the
   quarterly audit as a suspicious new registration with no
   training run attached. Use the state-machine rollback path
   ([`../exercise-02/rollback.py`](../exercise-02/rollback.py)).
7. **Forgetting that `Archived` is terminal.** Trying to promote
   an `Archived` version straight back to `Production` without
   re-registering drops the audit event; the reference solution
   treats "un-archiving" as a new version registration with
   lineage back to the prior version, not a stage transition.

## 6. References

**Official sources**

- [MLflow Model Registry — official docs](https://mlflow.org/docs/latest/model-registry.html).
  Authoritative for the stage set, the `MlflowClient` surface, and
  the backend-store requirement.
- [MLflow Models — signatures and input examples](https://mlflow.org/docs/latest/models.html#model-signature-and-input-example).
  Authoritative for the serving contract used in §2.5.
- [OWASP Machine Learning Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/)
  — ML06 (AI supply chain) motivates signing the artifacts whose
  URIs the Registry records.
- [MITRE ATLAS](https://atlas.mitre.org/) — model-registry
  manipulation is explicitly in scope for ML platform threat models.
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
  — Govern/Map/Measure/Manage; the tagging scheme in §2.4 is the
  evidence surface the Measure function reads.

**Local**

- Module rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-01.
- Downstream consumers of this exercise's choices:
  [`../exercise-02/rollback.py`](../exercise-02/rollback.py),
  [`../exercise-04/gate.py`](../exercise-04/gate.py),
  [`../exercise-05/quarterly_audit.py`](../exercise-05/quarterly_audit.py).
- Quick-pointer worked implementation:
  [`README.md`](./README.md).
- Learning exercise prompt:
  `lessons/mod-006-model-management/exercises/exercise-01-mlflow-registry-deep-dive.md`
  in the `ai-infra-ml-platform-learning` repo.
