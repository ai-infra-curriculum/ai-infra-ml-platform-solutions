# SOLUTION — Exercise 03: Canary Deployment via Argo Rollouts

> Per-exercise solution. The module-level rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md) §Ex-03; this file factors that
> section into a self-contained reference for graders and learners.
> Companion artifact in this directory: [`README.md`](./README.md)
> (quick-pointer to the engineer-tier worked YAML). See also the
> registry-side canary semantics in
> [`../../../projects/project-04-model-registry/deployment/rollout-strategies.md`](../../../projects/project-04-model-registry/deployment/rollout-strategies.md).

## 1. Solution overview

The deliverable is **an Argo Rollouts manifest that progresses a
model-serving Deployment through weighted traffic steps, bakes at
each step, and auto-rolls-back on a model-output metric — not just
HTTP errors**. Everything else is a configuration choice around
that shape.

The reference solution commits to four decisions, each of which the
rubric scores independently:

1. **Progressive weights with real bake-time between steps.**
   The reference ramp is `5% → 25% → 50% → 100%` with explicit
   `pause: {duration: …}` entries at every step
   (see [`../SOLUTION.md`](../SOLUTION.md) §Ex-03). Zero-duration
   pauses or a single "manual pause" halfway through are not
   progressive delivery; they are a two-step rollout with extra
   YAML.
2. **The analysis gate evaluates a *model-output* metric,** not
   only container-level signals. HTTP 500s and latency are
   necessary but not sufficient — the failure mode this exercise
   is built to catch is prediction-distribution drift that a load
   balancer cannot see. The reference uses a Prometheus query over
   the serving pod's `predictions_total{label=…}` histogram as the
   primary analysis metric.
3. **Auto-rollback on analysis failure is wired in the `Rollout`
   spec**, not left to operator judgement. An Argo Rollouts
   `AnalysisTemplate` referenced from the canary step runs on
   every pause; a failed run aborts the Rollout and the controller
   scales the canary back to zero. If a human has to click
   "Rollback" for safety to engage, the gate is theater.
4. **Stable and canary are addressable separately** via a
   `canaryService` / `stableService` pair, so observability can
   tell "canary pod p95" from "stable pod p95" without parsing
   pod labels in the dashboard.

A canary that watches only container health and promotes on
`pause:` without a metric check is not solving the exercise —
promotion on *elapsed time alone* was the pre-progressive-delivery
default and is exactly what Argo Rollouts exists to replace
([Argo Rollouts — Canary with Analysis](https://argoproj.github.io/argo-rollouts/features/analysis/)).

## 2. Worked answer or implementation

The worked implementation assumes the serving container exports two
Prometheus signals the AnalysisTemplate can read:

- `http_requests_total{service="model",status=~"5.."}` — infra
  signal.
- `predictions_total{service="model",label="<class>"}` — prediction
  signal, aggregated over a 5-minute window and bucketed by
  predicted class.

The second one is what makes the canary catch output drift. A
canary emitting a very different class distribution than the stable
fleet trips the analysis before 25% of traffic sees it.

### 2.1 Rollout manifest

The canonical `Rollout` CRD below encodes the four design decisions
in §1. Field-by-field rationale follows the YAML.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: model-serving
spec:
  replicas: 10
  selector:
    matchLabels:
      app: model-serving
  template:
    metadata:
      labels:
        app: model-serving
    spec:
      containers:
        - name: server
          image: registry.local/model-serving:${IMAGE_TAG}
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
  strategy:
    canary:
      canaryService: model-serving-canary
      stableService: model-serving-stable
      maxSurge: 25%
      maxUnavailable: 0
      steps:
        - setWeight: 5
        - pause: { duration: 10m }
        - analysis:
            templates:
              - templateName: model-output-health
            args:
              - name: service
                value: model-serving-canary
        - setWeight: 25
        - pause: { duration: 15m }
        - analysis:
            templates:
              - templateName: model-output-health
            args:
              - name: service
                value: model-serving-canary
        - setWeight: 50
        - pause: { duration: 30m }
        - analysis:
            templates:
              - templateName: model-output-health
            args:
              - name: service
                value: model-serving-canary
        - setWeight: 100
```

Why each field is where it is:

- **`canaryService` + `stableService`.** Two headless Services with
  distinct label selectors. Prometheus scrapes both; dashboards
  can compare `canary` vs `stable` without label gymnastics.
- **`maxUnavailable: 0`.** Guarantees the stable capacity stays
  intact during ramp. Saves 5% of pods ≠ saves 5% of capacity if
  stable loses pods to make room for canary.
- **`setWeight` → `pause (duration)` → `analysis` triplet** at every
  step. The pause buys bake-time; the analysis is the gate that
  runs *during* the pause. If analysis fails, the Rollout aborts
  before the next `setWeight` is read.
- **`args.service: model-serving-canary`.** The AnalysisTemplate
  measures the canary Service, not the aggregate, so a small canary
  footprint cannot be drowned out by majority-stable traffic.

### 2.2 AnalysisTemplate

The gate itself. Two providers — error rate and prediction-class
distribution — both must pass for the step to promote.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: model-output-health
spec:
  args:
    - name: service
  metrics:
    - name: error-rate
      interval: 1m
      count: 5
      successCondition: result[0] < 0.01
      failureLimit: 2
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(http_requests_total{service="{{args.service}}",status=~"5.."}[2m]))
              /
            sum(rate(http_requests_total{service="{{args.service}}"}[2m]))
    - name: prediction-class-shift
      interval: 1m
      count: 5
      successCondition: result[0] < 0.15
      failureLimit: 2
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            abs(
              sum(rate(predictions_total{service="{{args.service}}",label="positive"}[5m]))
                /
              sum(rate(predictions_total{service="{{args.service}}"}[5m]))
              -
              sum(rate(predictions_total{service="model-serving-stable",label="positive"}[5m]))
                /
              sum(rate(predictions_total{service="model-serving-stable"}[5m]))
            )
```

The second metric is the one that justifies this exercise existing.
It compares the **predicted-positive rate** of the canary against
the stable fleet. A canary that is much more or much less confident
than stable — regardless of 500s — fails the gate. That is the
*prediction distribution drift* [`../SOLUTION.md`](../SOLUTION.md)
§Ex-03 calls out as invisible to the LB.

The `failureLimit: 2` is deliberate: a single noisy sample should
not abort the Rollout, but a sustained shift should. Setting
`failureLimit: 0` turns the gate into a tripwire on noise;
`failureLimit: 10` turns it into a decoration.

### 2.3 Kubernetes Service shape

```yaml
apiVersion: v1
kind: Service
metadata:
  name: model-serving-stable
spec:
  selector:
    app: model-serving
  ports: [{ name: http, port: 80, targetPort: http }]
---
apiVersion: v1
kind: Service
metadata:
  name: model-serving-canary
spec:
  selector:
    app: model-serving
  ports: [{ name: http, port: 80, targetPort: http }]
```

Argo Rollouts mutates the selectors on these two Services at
runtime to point at the correct ReplicaSet for the current weight;
the manifest stays declarative on the author's side
([Argo Rollouts — Canary traffic management](https://argoproj.github.io/argo-rollouts/features/traffic-management/)).

### 2.4 Decision rationale

- **Why `5 → 25 → 50 → 100` and not `1 → 10 → 50 → 100`?** The
  prediction-class-shift metric needs a minimum traffic volume to
  be statistically meaningful at the 1-minute `interval`. At 1%
  weight, the canary sees too few samples per interval to trip a
  15% delta reliably. 5% is the smallest weight at which the
  metric has signal across the serving workloads this module
  targets. If a learner's traffic profile is different, they are
  expected to justify the first weight in writing.
- **Why bake 10 → 15 → 30 minutes, not uniform?** The cost of a
  missed failure scales with the fraction of traffic exposed, so
  the later steps deserve longer observation windows. Uniform
  bakes undervalue late-step blast radius.
- **Why the AnalysisTemplate, not Flagger?** Either works; the
  module standardizes on Argo Rollouts because the wider platform
  already runs Argo Workflows for Ex-04's governance gate
  ([`../SOLUTION.md`](../SOLUTION.md) §Ex-04). Flagger would be a
  valid alternative but adds an operator that solves the same
  problem.
- **Why two metrics and not one?** The infra metric
  (`error-rate`) catches crashes the model metric cannot see
  (a canary that always returns 500 cannot shift its prediction
  distribution because it produces no predictions). The model
  metric catches silent regressions the infra metric cannot see.
  Both are required; either alone is insufficient — this is the
  central lesson of the exercise.

## 3. Validation steps

Each check names the exact command a grader runs against a local
`k3s` or `kind` cluster with Argo Rollouts and Prometheus already
installed.

1. **Install Argo Rollouts and verify the plugin.**
   `kubectl argo rollouts version` succeeds.
   `kubectl get crd rollouts.argoproj.io` returns the CRD.
2. **Apply the manifests.**
   `kubectl apply -f rollout.yaml -f services.yaml -f analysis-template.yaml`
   returns zero errors. The Rollout appears in
   `kubectl argo rollouts list rollouts`.
3. **Ramp to canary.**
   `kubectl argo rollouts set image model-serving server=registry.local/model-serving:v2`
   kicks off the canary. `kubectl argo rollouts get rollout model-serving --watch`
   shows the step sequence advancing `setWeight 5 → pause → analysis`.
4. **Verify weight actually routes traffic.**
   During the first pause, `curl` the Service enough times to
   observe the canary pod answering 5% of requests. If every
   request still hits the stable fleet, the trafficRouting shim
   or the Service selectors are misconfigured. (Without a mesh,
   Argo Rollouts approximates weights via replica counts; the
   `maxSurge: 25%` + `replicas: 10` combo gives a working
   approximation for this exercise.)
5. **Verify the analysis gate actually gates.**
   Inject a failure by scaling the stable pods down so the canary
   error rate climbs, or by swapping the canary image for one that
   returns a skewed label distribution. Observe:
   `kubectl argo rollouts get rollout model-serving` shows the
   AnalysisRun in state `Failed` and the Rollout in state `Degraded`;
   `kubectl argo rollouts status model-serving` returns non-zero.
6. **Verify auto-rollback.**
   On the failed AnalysisRun, Argo Rollouts aborts the Rollout and
   the canary ReplicaSet scales back to zero *without* operator
   action. `kubectl argo rollouts abort` was not called; `aborted`
   in the Rollout status is set by the controller.
7. **Verify the full promotion path.**
   Deploy a known-good image. All four steps advance through
   analysis. The final step promotes to 100% and the Rollout
   reports `Healthy`. Stable Service selector now resolves to the
   new ReplicaSet.
8. **Verify observability contract.**
   Prometheus returns non-empty results for the two queries in the
   AnalysisTemplate when scoped to `service="model-serving-canary"`
   during the ramp. A canary with no metric signal fails §1
   decision 2 regardless of what the Rollout status says.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
|---|---|---|
| Traffic steps | ≥ 3 weighted steps with real bake-time between each. | One big step; zero-duration pauses; manual `pause: {}`-only pattern. |
| Analysis gate | `AnalysisTemplate` referenced from at least one `pause`; `successCondition` is explicit, not a comment. | No analysis; analysis only on the final step; `successCondition: always-passes`. |
| Model-output signal | At least one analysis metric reads a prediction-level quantity (class shift, score distribution, calibration delta, shadow-vs-live agreement). | Only `http_requests_total` / latency / CPU; no signal that could detect a silent model regression. |
| Auto-rollback | Rollout aborts without operator action when analysis fails; verified in §3 step 5. | Rollback requires `kubectl argo rollouts undo`; failed analysis leaves canary at the current weight. |
| Services | Distinct `stableService` and `canaryService`; Prometheus can scope queries to one or the other. | Single Service; observability cannot distinguish canary from stable. |
| Weight choice justified | First weight is defended against the metric's minimum-signal requirement (see §2.4). | First weight is `1%` with a 5-min interval metric and no discussion of statistical power. |
| Reproducible failure injection | A deliberately bad image or shifted-distribution image triggers the gate in CI. | Only the happy path is demonstrated. |
| Registry alignment | The image tag deployed corresponds to the Production version in the Registry (Ex-01). Rollback at the Rollout layer leaves the Registry pointing at the previous Production version. | Rollout rolls back Kubernetes but the Registry still names the broken version as Production. |

A passing submission scores Pass on every row. The two most common
"nearly passing" failure modes are (a) analysis only on infra
signals, (b) auto-rollback not demonstrated in CI.

## 5. Common mistakes

Inherited from the module-level list
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see,
item 4) and narrowed to this exercise:

1. **Canary using only HTTP-level signals.** The LB cannot see
   prediction distribution; a model that silently shifts to
   "always predict positive" has 0% error rate at the LB. This is
   the module's signature failure mode and the one the
   prediction-class-shift metric exists to catch.
2. **`pause: {}` without an analysis block.** A pause without a
   metric check is a time delay, not a gate. Promotion still
   happens whether the canary is behaving or not.
3. **Setting `failureLimit` to `0` or to a very large number.**
   Zero turns noise into aborts and the canary never promotes.
   Very large values turn the gate into a decoration. The
   reference uses `2` and justifies it per-metric.
4. **One shared Service for canary and stable.** Observability
   collapses; dashboards cannot show the two populations side by
   side; the AnalysisTemplate cannot scope its query to the canary.
5. **Rolling back at the Rollout layer but not at the Registry.**
   The pods go back but the Registry still advertises the bad
   version as `Production`. The next deploy — or any client that
   loads `models:/<name>/Production` directly — re-ships the bad
   model. The rollback must happen at both layers; the Registry
   rollback script lives at
   [`../exercise-02/rollback.py`](../exercise-02/rollback.py).
6. **Uniform bake-time across all steps.** A missed failure at
   50% weight hurts ten times more than a missed failure at 5%.
   Bakes should widen as blast radius grows.
7. **Starting the ramp at 1% without checking the metric's
   signal.** The gate silently passes because the canary sees too
   few samples per interval to move the metric. The canary looks
   healthy because it is invisible.

## 6. References

**Official sources**

- [Argo Rollouts — Canary strategy](https://argoproj.github.io/argo-rollouts/features/canary/).
  Authoritative for `setWeight`, `pause`, `steps`, and the canary
  state machine.
- [Argo Rollouts — Analysis](https://argoproj.github.io/argo-rollouts/features/analysis/).
  Authoritative for `AnalysisTemplate`, `successCondition`,
  `failureLimit`, and the abort semantics the reference depends on.
- [Argo Rollouts — Traffic management](https://argoproj.github.io/argo-rollouts/features/traffic-management/).
  Covers the stable/canary Service pair and the behavior without
  a service mesh.
- [MITRE ATLAS](https://atlas.mitre.org/) — the canary gate is the
  deployment-time mitigation for the "evade ML model" tactic
  (ATLAS Tactic: Evade ML Model) when the evasion manifests as
  distribution shift post-release.
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
  — the Measure / Manage functions call for continuous
  monitoring of deployed models; the AnalysisTemplate in §2.2 is
  the Measure instrument inside the deployment pipeline.
- [OWASP Machine Learning Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/)
  — ML07 (transfer-learning attack) and ML02 (data poisoning)
  surface at deployment as prediction distribution shifts; the
  canary metric is the deployment-time detector.

**Local**

- Module rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-03.
- Registry-side canary semantics and transaction shape:
  [`../../../projects/project-04-model-registry/deployment/rollout-strategies.md`](../../../projects/project-04-model-registry/deployment/rollout-strategies.md).
- Dependency on the Registry's state machine (Ex-01):
  [`../exercise-01/SOLUTION.md`](../exercise-01/SOLUTION.md).
- Registry-layer rollback used alongside this manifest:
  [`../exercise-02/rollback.py`](../exercise-02/rollback.py).
- Quick-pointer worked YAML: [`README.md`](./README.md).
- Learning exercise prompt:
  `lessons/mod-006-model-management/exercises/exercise-03-canary-via-argo.md`
  in the `ai-infra-ml-platform-learning` repo.
