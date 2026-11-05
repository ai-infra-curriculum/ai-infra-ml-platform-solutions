# SOLUTION — Exercise 05: Cost Attribution Pipeline

Reference for [learning ex-05](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-003-multi-tenancy-resources/exercises/exercise-05-cost-attribution-pipeline.md).

Read alongside the module-level rationale in
[`../SOLUTION.md`](../SOLUTION.md) §Ex-05 — Cost attribution
pipeline. The engineer-track per-model collector and Kyverno
policy referenced in [`README.md`](./README.md) are the runnable
companion to this reference.

## 1. Solution overview

Ex-05 is the module capstone. It closes the loop that Ex-01–04
create: the earlier exercises set up isolation and hard caps;
this one answers "**how much did Team X spend last month, and
how do we know?**"

The module's statement of why that matters:

> A platform team that can't answer "how much did Team X spend
> last month?" cannot defend its own budget.
> ([`../SOLUTION.md`](../SOLUTION.md#ex-05--cost-attribution-pipeline))

The reference pipeline is four parts:

1. **Label enforcement.** A `cost-center` label is mandatory on
   every workload-bearing object (Pod, Deployment, StatefulSet,
   Job, PVC). Admission-time enforcement via Kyverno — Ex-01 set
   up the namespace label; this exercise forces it down to
   children.
2. **Metric collection.** cAdvisor + kube-state-metrics (already
   present on every conformant cluster) expose per-pod CPU,
   memory, GPU, and PVC-bound storage. Prometheus scrapes them.
3. **Rollup.** A scheduled job joins resource-usage metrics
   with the `cost-center` label and the platform's unit rates to
   produce per-team monthly totals.
4. **Query interface.** Teams can read their own cost (a
   namespaced Grafana folder or a per-team API endpoint) but not
   each other's.

The exercise is **not** a cloud-bill reconciliation. It is a
**per-tenant unit-economics** pipeline — the number the platform
team cites when a team asks "why is my chargeback that high?"
Cloud-bill reconciliation is a different control plane
(Kubecost, Vantage, cloud-native cost explorers); this pipeline
produces numbers you can defend from first principles, which the
cloud bill cannot.

## 2. Worked implementation

### 2.1 Label enforcement (Kyverno)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-cost-center
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: cost-center-on-workloads
      match:
        any:
          - resources:
              kinds:
                - Pod
                - Deployment
                - StatefulSet
                - DaemonSet
                - Job
                - CronJob
                - PersistentVolumeClaim
      validate:
        message: "Every workload object must carry a 'cost-center' label."
        pattern:
          metadata:
            labels:
              cost-center: "?*"
    - name: copy-cost-center-from-namespace
      match:
        any:
          - resources:
              kinds: [Pod]
      mutate:
        patchStrategicMerge:
          metadata:
            labels:
              cost-center: "{{ request.namespace.metadata.labels.\"cost-center\" }}"
```

Rationale:

- `validationFailureAction: Enforce` is non-negotiable.
  Audit-only mode teaches you about violations; it does not stop
  them (see module Common Mistakes #3). The learning cost is
  that teams who forget the label see an admission error on
  their first deploy — that is cheap compared to a month of
  silently mis-attributed spend.
- The `copy-cost-center-from-namespace` mutate rule provides a
  **soft landing**: if a Pod omits the label but its namespace
  carries one (from Ex-01), Kyverno fills it in. The validate
  rule above still catches the case where neither the Pod nor
  its namespace is labeled.
- `background: true` scans existing workloads at install time so
  the policy's effective coverage is auditable from day one.

Kyverno documents both the enforce/audit split and the
background-scan behaviour in the
[policy types reference](https://kyverno.io/docs/policy-types/)
and the
[auto-gen / background scan reference](https://kyverno.io/docs/writing-policies/autogen/).

### 2.2 Metric collection — unit model

The pipeline bills four resources per pod. All four are already
exposed by the standard
[cAdvisor](https://github.com/google/cadvisor) +
[kube-state-metrics](https://github.com/kubernetes/kube-state-metrics)
stack that ships with every conformant Kubernetes distribution.

| Dimension | Prometheus series | Unit |
| --- | --- | --- |
| CPU | `rate(container_cpu_usage_seconds_total{container!="",image!=""}[5m])` summed → CPU-seconds | CPU-hour |
| Memory | `avg_over_time(container_memory_working_set_bytes[5m])` → bytes ⋅ time | GB-hour |
| GPU | `DCGM_FI_DEV_GPU_UTIL` time-weighted, or simpler: pods carrying `nvidia.com/gpu` request > 0 (see [NVIDIA DCGM exporter](https://github.com/NVIDIA/dcgm-exporter)) | GPU-hour |
| Storage | `kube_persistentvolumeclaim_resource_requests_storage_bytes` by PVC, joined to the namespace's cost-center | GB-hour (by StorageClass) |

The rollup joins the per-pod series with the
`kube_pod_labels{label_cost_center=~".+"}` label projection from
kube-state-metrics — that is the join column cost attribution
hinges on. Every row the rollup emits also carries a
`cost_center_source` field: `pod-label`, `namespace-label`, or
`unknown`. `unknown` is the diagnostic that proves the
enforcement loop is working; it should stay at 0.

### 2.3 Rollup — scheduled job

PromQL that produces monthly CPU-hours per cost-center:

```promql
# CPU-hours attributed to each cost-center over the billing window.
sum by (cost_center) (
  sum_over_time(
    sum by (pod, namespace) (
      rate(container_cpu_usage_seconds_total{container!="",image!=""}[5m])
    )
    * on (pod, namespace) group_left(cost_center)
      max by (pod, namespace, cost_center) (
        kube_pod_labels{label_cost_center!=""}
      )
    [30d:5m]
  )
) / 3600
```

Multiply the per-dimension totals by the platform's published
unit rates (CPU-$/hour, memory-$/GB-hour, GPU-$/hour,
storage-$/GB-hour-by-class). Store the output in the platform's
warehouse keyed by `(cost_center, billing_period)`.

Running the join as a scheduled
[CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
once an hour — not once at the end of the month — means the
pipeline is **self-reconciling**: a mis-labeled workload shows
up as `unknown` within the hour, not on the chargeback
statement.

### 2.4 Query interface

Give each team a Grafana folder keyed off their namespace label
and a read-only `ServiceAccount` scoped to their own cost series.
The pattern is:

- One Grafana data source per team, scoped to
  `cost_center="{team}"` via a Prometheus matcher injected
  server-side (so clients cannot widen it).
- Dashboards show CPU-hours, memory-GB-hours, GPU-hours, and
  storage-GB-hours over the billing window, broken out by
  Deployment / Job.
- A platform-admin folder aggregates across all teams.

Teams see their own cost; nobody sees their neighbor's. That is
the "query interface so teams can see *their* cost without
seeing others'" line from the module solution.

### Decision rationale (why these shapes)

- **Admission enforcement, not reports.** A quarterly "please
  label your workloads" email never worked for anyone. The
  cheapest moment to enforce is admission time, and that is
  before the first metric is scraped.
- **Resource-hours, not cloud-bill reconciliation.** The input
  stream is cluster-internal metrics, which are cheap, dense,
  and already present. Cloud-bill reconciliation is a different
  problem — it attributes shared costs (control plane, data
  egress) that this pipeline deliberately does not price. Pair
  the two; don't conflate them.
- **Namespace label as fallback, not primary.** Pods should
  carry the label directly (a Job may run outside its parent's
  namespace labelling convention). Fallback via mutate keeps
  friction low without hiding genuine gaps — the `unknown`
  diagnostic is the invariant that proves the policy is doing
  work.
- **Per-team read scope.** Cost data is sensitive. Teams
  comparing each other's spend is the fastest way to turn a
  platform deliverable into a political one; scope reads
  tightly.
- **NIST AI RMF alignment.** The `MANAGE` function calls for
  continuous accounting of AI system resource usage; this
  pipeline is one implementation of that control. See the
  [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework).

## 3. Validation steps

```bash
# 3.1 The Kyverno policy is installed and in enforce mode.
kubectl get clusterpolicy require-cost-center \
  -o jsonpath='{.spec.validationFailureAction}'
# Expect: Enforce

# 3.2 A Pod without cost-center is rejected.
kubectl -n team-a apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata: { name: no-label-pod }
spec:
  containers: [{ name: c, image: nginx }]
EOF
# Expect admission error from the require-cost-center policy.

# 3.3 A Pod whose namespace carries cost-center inherits it.
kubectl -n team-a apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata: { name: inherits-label }
spec:
  containers: [{ name: c, image: nginx }]
EOF
kubectl -n team-a get pod inherits-label \
  -o jsonpath='{.metadata.labels.cost-center}'
# Expect: team-a

# 3.4 kube-state-metrics projects the label.
# Prometheus query:
#   kube_pod_labels{namespace="team-a",label_cost_center!=""}
# Expect at least one series for every running Pod.

# 3.5 Per-team CPU-hours roll up correctly over a 1-hour window.
# PromQL (adjust for billing window):
#   sum by (cost_center) (
#     sum_over_time(
#       sum by (pod, namespace) (
#         rate(container_cpu_usage_seconds_total[5m])
#       )
#       * on (pod, namespace) group_left(cost_center)
#         kube_pod_labels{label_cost_center!=""}
#       [1h:5m]
#     )
#   ) / 3600
# Expect numeric output grouped by cost_center, with no 'unknown' row.

# 3.6 Unlabeled attribution is 0.
# PromQL:
#   count(kube_pod_info) - count(kube_pod_labels{label_cost_center!=""})
# Expect: 0. Non-zero means a Pod slipped past the policy — fix it
# before trusting the chargeback.

# 3.7 Query scope isolation — team-a's Grafana user cannot see team-b.
# Use Grafana's /api/dashboards/db and confirm the response filters
# to cost_center=team-a only.
```

Each step is pass/fail. Step 3.6 is the single most important
one: if `unknown` is ever non-zero, the pipeline is mis-attributing
spend, and no downstream chargeback should be sent until it is
back to zero.

## 4. Rubric / review checklist

| Dimension | Pass criterion |
| --- | --- |
| Label enforcement | Kyverno (or equivalent admission) policy in **enforce** mode on all workload kinds listed in §2.1. Audit-only fails. |
| Fallback discipline | Namespace label is a fallback via mutate, not the only source of truth. A Pod that omits the label *and* lives in an unlabeled namespace is rejected. |
| Metric coverage | At minimum CPU, memory, and storage are priced. GPU is priced if the cluster has GPUs. Each dimension cites its Prometheus series. |
| Join integrity | Per-pod metrics are joined to `cost_center` via `kube_pod_labels` (or equivalent), not via guessed namespace mapping. Unknowns are surfaced, not silently zeroed. |
| Schedule | Rollup runs at least hourly — not only monthly — so label gaps surface inside the billing window. |
| Read-scope isolation | Teams can read their own cost dashboard; they cannot read other teams'. Prove the restriction server-side, not just by hiding the UI. |
| Reconciliation story | Submission names at least one dimension this pipeline does *not* price (control-plane time, data egress, shared load balancers) and points at where those costs are reconciled instead. |

A submission must pass every row. An "it runs end-to-end" demo
that fails the join-integrity row is still a fail — a pipeline
that attributes confidently but wrongly is worse than no
pipeline.

## 5. Common mistakes

Carried from [`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see)
item 5 and what graders see on this exercise:

1. **Audit-only Kyverno forever.** The team ships the policy in
   `Audit`, promises to flip it next sprint, and never does.
   Enforce on day one; the one-time pain of fixing broken
   manifests is the entire point.
2. **Trusting namespace → cost-center as primary.** When
   someone runs a Job in the `default` namespace (because CI
   paved an exception), the fallback silently tags it as
   `default`'s center. Pods must carry the label directly;
   namespace is a fallback, not a source of truth.
3. **Pricing only CPU and memory.** GPU-hours are the single
   largest line item on an ML platform bill. Shipping a
   pipeline that skips GPU because "it's hard" sends teams a
   chargeback that under-reports the thing they actually care
   about.
4. **Monthly-only rollups.** Running the join once at month-end
   means the first time anyone notices a label gap is on the
   chargeback statement. Hourly rollups turn label gaps into
   immediate `unknown` alerts.
5. **One shared dashboard for everyone.** Team B seeing Team
   A's spend turns every chargeback dispute into a political
   fight. Scope reads at the data-source layer, not at the UI
   layer.
6. **Conflating this with cloud-bill reconciliation.** This
   pipeline produces unit-economics *you can defend from first
   principles*. It does not reproduce the cloud bill — that is
   a separate job and should not be conflated. Submissions that
   claim bit-exact cloud-bill agreement are over-claiming.

## 6. References

**Local**

- Module-level rationale:
  [`../SOLUTION.md`](../SOLUTION.md) §Ex-05.
- Upstream dependencies in this module:
  [`../exercise-01`](../exercise-01/) (namespace + `cost-center`
  label origin),
  [`../exercise-02`](../exercise-02/) (ResourceQuota — the
  dimensions this pipeline prices are the same ones the quota
  caps).
- Learning exercise prompt:
  `lessons/mod-003-multi-tenancy-resources/exercises/exercise-05-cost-attribution-pipeline.md`
  in the `ai-infra-ml-platform-learning` repo.
- Engineer-track reference — per-model collector + Kyverno
  label enforcement: see link in [`README.md`](./README.md).

**External — upstream tooling**

- [Kyverno — policy types](https://kyverno.io/docs/policy-types/)
  and [background scans](https://kyverno.io/docs/writing-policies/autogen/).
- [kube-state-metrics](https://github.com/kubernetes/kube-state-metrics)
  — the `kube_pod_labels` projection.
- [cAdvisor](https://github.com/google/cadvisor) — per-container
  CPU and memory series.
- [NVIDIA DCGM exporter](https://github.com/NVIDIA/dcgm-exporter)
  — per-GPU utilization series.
- [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
  — the scheduler for the hourly rollup.

**External — frameworks that justify the control**

- NIST AI Risk Management Framework —
  <https://www.nist.gov/itl/ai-risk-management-framework>
  (the `MANAGE` function calls for continuous accounting of AI
  system resource usage).
- OWASP Machine Learning Security Top 10 —
  <https://owasp.org/www-project-machine-learning-security-top-10/>
  (tenant-labeled accounting is a prerequisite for the
  monitoring and access-control controls referenced throughout
  the project).
