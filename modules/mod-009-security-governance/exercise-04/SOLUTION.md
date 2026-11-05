# SOLUTION — Exercise 04: Implement Governance Gates

> Per-exercise solution. The module-level rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md) §Ex-04; this file factors that
> section into a self-contained reference for graders and learners.
> Companion artifact in this directory: [`README.md`](./README.md)
> (quick-pointer: the promote-time gate is implemented in
> [`../../mod-006-model-management/exercise-04/gate.py`](../../mod-006-model-management/exercise-04/gate.py);
> the broader FastAPI composite — audit log + GDPR + model cards +
> bias review — ships in `learning project-4-governance`). The
> admission-time image policy this exercise assumes already exists
> lives in [`../exercise-03/SOLUTION.md`](../exercise-03/SOLUTION.md);
> the audit records the quarterly compliance report
> ([`../exercise-05/`](../exercise-05/)) reads come from the gate
> run described here.

## 1. Solution overview

The deliverable is **two enforcement surfaces that together make
"governance" a thing that actually blocks bad deploys**, not a
document that describes what would be blocked if anyone checked:

1. A **promote-time gate** at the Model Registry layer that refuses
   to transition a model version to `Production` unless a fixed set
   of governance artifacts (model card URI, bias review URI,
   decision log URI, owner team, etc.) are present as tags on the
   version. This is the gate implemented in
   [`../../mod-006-model-management/exercise-04/gate.py`](../../mod-006-model-management/exercise-04/gate.py).
2. An **admission-time gate** at the Kubernetes layer that refuses
   to schedule Pods violating platform policy (required labels, no
   privileged pods, no hostPath mounts, image signed by the
   expected identity, image from the approved registry). This is
   the Kyverno `ClusterPolicy` set introduced in
   [`../exercise-03/`](../exercise-03/) and extended here.

The reference solution commits to five design decisions that drive
both surfaces:

1. **Policy lives in git, not in a Confluence page.** Every policy
   is a YAML file in the platform repo; PRs to policy are
   reviewable, auditable, and bisectable
   ([`../SOLUTION.md`](../SOLUTION.md) §Ex-04 — "policy that lives
   in a Confluence page is policy that nobody enforces").
2. **Gates fail closed.** Default action on a policy evaluation
   error is deny. A gate that opens on error becomes a gate an
   attacker can trip to bypass policy.
3. **Promote-time + admission-time are both required.** Promote
   without admission lets an image that bypassed registry promotion
   still run. Admission without promote lets the Registry advertise
   an unvetted model as `Production`. Both layers, same policy,
   enforced independently.
4. **Every gate decision produces an audit record.** The record
   names the subject (model version, pod), the verdict, the policy
   that produced the verdict, and the timestamp. The quarterly
   audit ([`../exercise-05/`](../exercise-05/)) is exactly these
   records aggregated by team.
5. **Policies ratchet, they don't thrash.** New policies ship in
   `Audit` mode for a bounded bake period (one sprint), then flip
   to `Enforce`. Policies never move backwards from `Enforce` to
   `Audit` without a dated incident; backsliding is the governance
   smell a reviewer will catch.

A submission that implements only the admission side, or only the
registry side, is not solving the exercise: the two surfaces catch
different failure modes.

## 2. Worked answer or implementation

### 2.1 Promote-time gate — Registry layer

The gate at the Registry refuses promotion to Production without
the governance artifacts. The implementation is the reused script
at [`../../mod-006-model-management/exercise-04/gate.py`](../../mod-006-model-management/exercise-04/gate.py):

```python
"""Governance gate: refuse promotion to Production without required artifacts."""
from mlflow.tracking import MlflowClient
import sys

REQUIRED_TAGS = ["model_card_uri", "bias_review_uri", "decision_log_uri"]

def gate(name: str, version: str) -> None:
    c = MlflowClient()
    mv = c.get_model_version(name, version)
    missing = [t for t in REQUIRED_TAGS if t not in mv.tags]
    if missing:
        sys.exit(f"GATE FAILED: missing tags {missing}; "
                 f"cannot promote {name} v{version} to Production")
    print(f"GATE PASSED: {name} v{version} has all required artifacts")

def promote(name: str, version: str) -> None:
    gate(name, version)
    c = MlflowClient()
    c.transition_model_version_stage(
        name=name, version=version, stage="Production",
        archive_existing_versions=True,
    )
```

Why each line matters:

- **`REQUIRED_TAGS` is a module-level constant.** Changing the list
  is a code change with a diff; it is not a configuration toggle
  an author can set on their own branch.
- **The gate reads the model-version tags, not the run tags.** The
  mod-006 ex-01 tagging convention
  ([`../../mod-006-model-management/exercise-01/SOLUTION.md`](../../mod-006-model-management/exercise-01/SOLUTION.md)
  §2.4) is load-bearing: tags on the run are invisible to this
  check.
- **`sys.exit` on failure.** The gate aborts the promotion process
  with a non-zero exit code; CI treats non-zero as "promotion
  blocked" and does not call the transition API. A gate that
  prints a warning and returns 0 is a warning, not a gate.
- **`archive_existing_versions=True`.** Promotion is a two-edge
  state transition — previous Production → Archived and the new
  version → Production — in one call. Decoupling the two leaves a
  moment where two versions are "Production" and downstream
  consumers pick inconsistently
  ([`../../mod-006-model-management/SOLUTION.md`](../../mod-006-model-management/SOLUTION.md)
  §Common mistakes).

A worked expansion of the gate adds three governance checks the
quarterly audit relies on:

```python
from datetime import datetime, timezone, timedelta

REQUIRED_TAGS = [
    "model_card_uri", "bias_review_uri", "decision_log_uri",
    "team", "model_card_updated_at",
]
STALE_DAYS = 90

def gate_extended(name: str, version: str) -> None:
    c = MlflowClient()
    mv = c.get_model_version(name, version)
    missing = [t for t in REQUIRED_TAGS if t not in mv.tags]
    if missing:
        sys.exit(f"GATE FAILED: missing tags {missing}")

    updated = datetime.fromisoformat(mv.tags["model_card_updated_at"])
    if datetime.now(timezone.utc) - updated > timedelta(days=STALE_DAYS):
        sys.exit(f"GATE FAILED: model_card older than {STALE_DAYS}d "
                 f"(updated {updated.isoformat()})")

    for uri_tag in ["model_card_uri", "bias_review_uri", "decision_log_uri"]:
        if not mv.tags[uri_tag].startswith(("s3://", "gs://", "https://")):
            sys.exit(f"GATE FAILED: {uri_tag} is not a resolvable URI")
```

Why these three extensions:

- **`team` tag.** The quarterly audit groups non-compliant models
  by team ([`../exercise-05/SOLUTION.md`](../exercise-05/SOLUTION.md)
  §2). Without a team tag the audit cannot assign ownership.
- **`model_card_updated_at` + 90-day staleness.** A model card
  written once and never updated is a model card no reviewer has
  looked at since release. The staleness check is the "the model
  card is current" invariant.
- **URI shape check.** `model_card_uri = "TODO"` passes the
  presence check in the minimal gate and fails any actual
  retrieval. Validate at promotion time, not when a regulator
  tries to open the link.

### 2.2 Admission-time gate — Kubernetes layer

The Kyverno policy set is the enforcement arm for everything the
cluster can decide. Four `ClusterPolicy` resources implement the
rule set called out in [`../SOLUTION.md`](../SOLUTION.md) §Ex-04.
The image-signing policy is defined in
[`../exercise-03/SOLUTION.md`](../exercise-03/SOLUTION.md) §2.2;
the three additional policies are below.

```yaml
# 1. Required labels — every workload must declare owner + data-sensitivity.
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata: { name: require-governance-labels }
spec:
  validationFailureAction: Enforce
  rules:
    - name: require-labels
      match: { any: [{ resources: { kinds: [Pod, Deployment, StatefulSet] } }] }
      validate:
        message: >-
          every workload must declare labels: owner (team),
          data-sensitivity (public|internal|confidential|regulated).
        pattern:
          metadata:
            labels:
              owner: "?*"
              data-sensitivity: "public|internal|confidential|regulated"
---
# 2. No privileged pods. Ever.
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata: { name: disallow-privileged-pods }
spec:
  validationFailureAction: Enforce
  rules:
    - name: no-privileged
      match: { any: [{ resources: { kinds: [Pod] } }] }
      validate:
        message: "privileged containers are not permitted on this platform."
        pattern:
          spec:
            =(initContainers):
              - =(securityContext):
                  =(privileged): "false"
                  =(allowPrivilegeEscalation): "false"
            containers:
              - =(securityContext):
                  =(privileged): "false"
                  =(allowPrivilegeEscalation): "false"
---
# 3. No hostPath mounts. Platform workloads use PersistentVolumes.
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata: { name: disallow-hostpath }
spec:
  validationFailureAction: Enforce
  rules:
    - name: no-hostpath
      match: { any: [{ resources: { kinds: [Pod] } }] }
      validate:
        message: "hostPath volumes bypass cluster isolation; use a PVC."
        foreach:
          - list: "request.object.spec.volumes || []"
            deny:
              conditions:
                any:
                  - key: "{{element.hostPath || ''}}"
                    operator: NotEquals
                    value: ""
```

Pattern-level choices:

- **`validationFailureAction: Enforce` on every one.** Audit-only
  gates do not gate. The `Audit` setting exists for the bake
  period in §1.5 and nothing else.
- **`foreach` over `spec.volumes`.** The hostPath check iterates
  the list rather than hard-coding slot 0. A manifest with
  hostPath on volume #4 still gets caught.
- **No exclusions for "trusted" namespaces beyond kube-system and
  the policy engine's own namespace.** Every platform namespace
  must satisfy every policy. "Trusted namespaces" is a loophole
  with a friendly name.

The exact set of policies a platform runs is longer than the three
shown here — the Kyverno policy library's
[Kubernetes best-practices set](https://kyverno.io/policies/)
covers the standard additions (seccomp profiles, read-only root
filesystems, resource limits). The three above are the governance
gates called out explicitly in
[`../SOLUTION.md`](../SOLUTION.md) §Ex-04 and are the minimum a
submission has to ship.

### 2.3 Audit records

Every gate decision produces a record the quarterly audit can read.
Two sources, one shape.

**Registry gate** writes a transition row MLflow already provides
(`last_updated_timestamp`, `current_stage`); the gate's own log
line is captured by the CI job log. For the quarterly audit the
data source is `MlflowClient.search_model_versions()` plus the
governance tags.

**Kyverno** emits `PolicyReport` resources in the cluster
(and Kubernetes events for every denial):

```yaml
apiVersion: wgpolicyk8s.io/v1alpha2
kind: PolicyReport
metadata: { name: polr-ns-ml-platform }
results:
  - policy: require-attested-images
    rule: verify-cosign-signature
    source: kyverno
    result: fail
    severity: high
    subjects:
      - apiVersion: v1
        kind: Pod
        name: offending-pod
        namespace: ml-platform
    timestamp:
      seconds: 1762300800
```

The Ex-05 compliance audit script joins `PolicyReport` denials
with the Registry's governance tags to produce per-team
non-compliance tables.

### 2.4 Decision rationale

- **Why gate at promote-time *and* admission-time?** A gate at
  promote-time stops an un-reviewed version from being advertised
  as `Production`. A gate at admission-time stops a Pod from
  running a version — or an image — that bypassed the Registry
  entirely. The two surfaces catch different attacker paths; both
  are necessary.
- **Why Kyverno rather than OPA Gatekeeper?** Both are acceptable;
  the reference picks Kyverno because the policy syntax is a
  Kubernetes-native resource (`ClusterPolicy`), reviewable with the
  same tooling the platform already uses for workloads
  ([Kyverno — Policy structure](https://kyverno.io/docs/writing-policies/policy-types/)).
  A Gatekeeper-based submission is accepted if the rules cover the
  same surface.
- **Why fail closed on policy errors?** An open-on-error gate is
  an attacker's primitive: flood the policy engine until it
  errors, then deploy anything.
- **Why a ratchet rather than "enforce from day one"?** Flipping a
  policy to `Enforce` without a bake breaks every existing
  workload that happens to violate it; the team learns not to add
  new policies. Policies ship in `Audit` for one sprint, team-owned
  violations get fixed, then `Enforce`. Governance is a cadence.
- **Why audit records in both layers?** The Ex-05 quarterly audit
  needs a per-team denial count and a per-team "Production with
  missing tags" count. Those two numbers come from different
  layers and cannot be reconstructed from one alone.

## 3. Validation steps

Each check names the exact command a grader runs against a cluster
with Kyverno installed and an MLflow Registry reachable (see
[`../../mod-006-model-management/exercise-01/SOLUTION.md`](../../mod-006-model-management/exercise-01/SOLUTION.md)
for the bootstrap).

1. **Registry gate blocks a promotion missing tags.**
   Register a model version with no governance tags set. Run
   `python gate.py iris-rf 1`. Exit code is non-zero; stdout names
   the missing tags explicitly; `get_model_version(..., 1).current_stage`
   is still `None`.
2. **Registry gate allows a complete promotion.**
   Set the full tag set (§2.1 extended gate). Run `python gate.py
   iris-rf 2`. Exit code 0; `get_latest_versions("iris-rf",
   stages=["Production"])` returns `v2`.
3. **Registry gate blocks a stale model card.**
   Set `model_card_updated_at` to 100 days ago. Run the extended
   gate; exit code is non-zero with a message naming the staleness
   threshold.
4. **Registry gate blocks a non-URI tag.**
   Set `model_card_uri = "TODO"`. Run the extended gate; exit code
   is non-zero.
5. **Admission gate blocks missing labels.**
   `kubectl apply -f pod-no-owner.yaml` — a Pod spec without
   `metadata.labels.owner` — fails with Kyverno's denial message
   naming `require-governance-labels`.
6. **Admission gate blocks privileged pods.**
   `kubectl apply -f pod-privileged.yaml` fails; the message names
   `disallow-privileged-pods`.
7. **Admission gate blocks hostPath mounts.**
   `kubectl apply -f pod-hostpath.yaml` fails; the message names
   `disallow-hostpath` and identifies which volume tripped it.
8. **Policy reports are emitted.**
   `kubectl get policyreport -A -o yaml` includes a `fail` result
   for the preceding denials. Running
   `kubectl get events -A --field-selector reason=PolicyViolation`
   returns the human-readable events.
9. **Open-on-error contract holds.**
   Scale the Kyverno controller to zero replicas; `kubectl apply
   -f pod-privileged.yaml` fails with
   `admission webhook ... failed: no endpoints available`. The
   deny-on-webhook-failure behavior is explicit in Kubernetes'
   `failurePolicy: Fail` ([kube-apiserver admission](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/)).
10. **Audit mode works for the ratchet.**
    Ship a new policy in `validationFailureAction: Audit`. A
    violating Pod succeeds but a `PolicyReport` fail result is
    written. After the bake period, flipping to `Enforce` turns
    those fail results into denials.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
|---|---|---|
| Two-layer gate | Both promote-time (Registry) and admission-time (Kubernetes) gates are implemented. | Only one of the two surfaces is gated. |
| Policy-as-code | All policies are YAML / Python files in the repo, under code review. | Policies live in Kyverno via `kubectl apply` from a developer laptop; no git record. |
| Required tag set | Registry gate enforces at minimum: model_card_uri, bias_review_uri, decision_log_uri, team, model_card_updated_at. | Tag set is shorter; or tag set is "configurable" per branch. |
| Staleness check | Model-card staleness threshold is enforced at promotion, not only at quarterly audit. | Stale model cards block only after the next audit. |
| Enforcement mode | Kyverno policies run in `Enforce`; audit mode is used only during the ratchet bake. | Production policies left in `Audit` indefinitely. |
| Fail-closed | Webhook `failurePolicy: Fail`; gate exits non-zero on evaluation error. | Open-on-error; gates that return success on exception. |
| Namespace coverage | Policies apply across all platform namespaces; only kube-system / Kyverno excluded. | "Trusted" namespace exclusions proliferate. |
| Audit records | Every gate decision produces an auditable record (`PolicyReport` for admission; CI log + Registry metadata for promote). | Denials leave no trace; "we remember what we blocked." |
| Image policy integration | Admission gate references the signing-identity policy from [`../exercise-03/`](../exercise-03/) and the image digest is pinned. | Signing policy duplicated inconsistently; image references by tag survive admission. |
| Quarterly audit integration | Audit records from this exercise are the input to the Ex-05 compliance report. | The audit script in Ex-05 reads a different data source that isn't produced by this exercise. |
| Policy-change process | Policies ship in `Audit` for one sprint, then `Enforce`; a backslide from `Enforce` to `Audit` requires a dated incident. | Policies flip between modes arbitrarily. |

A passing submission scores Pass on every row. The two most common
near-misses are (a) implementing only the admission gate and
relying on reviewer discipline for the Registry, and (b) shipping
policies in `Audit` mode and leaving them there.

## 5. Common mistakes

Inherited from the module-level list
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see,
item 4) and narrowed to this exercise:

1. **Policy in Confluence.** The anti-pattern the module names
   explicitly. A policy that is not a file in the repo cannot be
   reviewed, enforced, or audited.
2. **Admission-only governance.** The cluster refuses bad Pods but
   the Registry advertises an unvetted version as `Production`.
   Every consumer that loads `models:/<name>/Production` directly
   bypasses the admission gate.
3. **Registry-only governance.** The Registry refuses promotion
   without tags, but any Pod can reference an image not in the
   Registry and run anyway. Admission is the backstop for
   out-of-band deploys.
4. **Audit-mode forever.** `Audit` was supposed to be a bake
   period. Six months later the policy still produces
   `PolicyReport` fail results and nothing happens.
5. **Policy evaluation errors open the gate.** A policy that
   returns `nil` on error, or a webhook with `failurePolicy:
   Ignore`, makes "policy engine broken" a bypass primitive.
6. **Missing `archive_existing_versions=True` at promotion.**
   Leaves two versions in Production. Governance tags on the new
   version don't help if clients still pick the old one. Fix
   lives in the gate itself.
7. **Governance tags on the run, not the version.** The gate
   reads `get_model_version(name, v).tags`; tags written to the
   run are invisible. The mod-006 ex-01 tagging convention
   catches this.
8. **Policies scoped to a single namespace.** A workload migrates
   between namespaces; the policy follows the namespace, not the
   workload, and the migration is a stealth bypass.
9. **URI tags that don't resolve.** `model_card_uri = "TODO"`
   passes a presence check. Validate URI shape at promotion time;
   a quarterly audit discovering the broken link is three months
   too late.
10. **No audit record on denial.** The gate denies and nobody
    hears it. The Ex-05 report has nothing to aggregate, and the
    team has no signal that deploys are being blocked at all.

## 6. References

**Official sources**

- [Kyverno — Policy types and syntax](https://kyverno.io/docs/writing-policies/policy-types/).
  Authoritative for `ClusterPolicy`, `validationFailureAction`,
  `foreach`, and the pattern language used in §2.2.
- [Kyverno — Image verification](https://kyverno.io/docs/writing-policies/verify-images/).
  Authoritative for the signing-identity policy referenced from
  §2.2 and [`../exercise-03/`](../exercise-03/).
- [OPA Gatekeeper — Constraint templates](https://open-policy-agent.github.io/gatekeeper/website/docs/howto).
  Authoritative reference for the alternative implementation
  path.
- [Kubernetes — Admission webhooks](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/).
  Authoritative for `failurePolicy: Fail`, timeout semantics, and
  the fail-closed contract in §2.4.
- [MLflow — Model Registry API](https://mlflow.org/docs/latest/model-registry.html).
  Authoritative for `transition_model_version_stage`,
  `archive_existing_versions`, and the tag API the gate reads.
- [Kubernetes Policy WG — PolicyReport CRD](https://github.com/kubernetes-sigs/wg-policy-prs).
  Authoritative for the `PolicyReport` resource shape consumed by
  Ex-05.
- [OWASP Machine Learning Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/)
  — ML06 (AI supply-chain attack) maps onto the admission-time
  image policy; ML09 (output integrity attack) is bounded by the
  model-card and bias-review gates.
- [MITRE ATLAS](https://atlas.mitre.org/) — "ML Model Access" and
  "ML Supply Chain Compromise" are the primary attacker techniques
  these gates mitigate.
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
  — Govern 4 (accountability structures) and Manage 1 (risk
  response) are the functions this exercise operationalizes;
  governance tags are the evidence surface.
- [NIST AI 600-1 — Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
  — GAI-specific disclosure requirements (model card, bias review,
  decision log) extend the required-tag set when the model is a
  generative system.

**Practitioner references**

- [VeriSwarm Trust Center](https://veriswarm.ai/trust) — example
  of a practitioner-run trust surface that publishes the
  governance artifacts (model cards, risk assessments) a gate like
  this one requires. Use as an implementation exemplar, not an
  authoritative source.

**Local**

- Module rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-04.
- Registry gate script (reused):
  [`../../mod-006-model-management/exercise-04/gate.py`](../../mod-006-model-management/exercise-04/gate.py).
- Tagging convention this gate depends on:
  [`../../mod-006-model-management/exercise-01/SOLUTION.md`](../../mod-006-model-management/exercise-01/SOLUTION.md)
  §2.4.
- Admission-time image policy details:
  [`../exercise-03/SOLUTION.md`](../exercise-03/SOLUTION.md) §2.2.
- Quarterly compliance audit that reads this exercise's records:
  [`../exercise-05/SOLUTION.md`](../exercise-05/SOLUTION.md).
- Composite governance service (FastAPI, audit log + GDPR + model
  cards + bias review):
  `learning project-4-governance` — see [`README.md`](./README.md).
- Learning exercise prompt:
  `lessons/mod-009-security-governance/exercises/exercise-04-governance-gates.md`
  in the `ai-infra-ml-platform-learning` repo.
