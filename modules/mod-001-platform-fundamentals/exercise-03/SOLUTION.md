# SOLUTION — Exercise 03: Resource Quota Management for Teams

> Per-exercise solution. The cross-exercise rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md); this file factors the Ex-03
> section into a self-contained reference for graders and
> implementers. Companion artifact:
> [`quota.yaml`](./quota.yaml).

## 1. Solution overview

Exercise 03 asks the learner to put a resource budget on a
tenant namespace using a Kubernetes `ResourceQuota`, and to
decide explicitly whether to pair it with a `LimitRange`. The
tenant namespace from Ex-02 (`team-a`) is the input; a committed
`quota.yaml` that applies cleanly against that namespace is the
output.

The module solution ([`../SOLUTION.md`](../SOLUTION.md#ex-03--resource-quota-management))
takes a sharp position the rubric enforces:

> Set `limits.cpu` and `limits.memory` quotas at the namespace
> level **with no default LimitRange**. This forces every
> Deployment to specify requests + limits explicitly, which
> surfaces the missing-resource-request bug before deploy.

The quota is the *forcing function*, not just a cap. Omitting
the `LimitRange` is a deliberate choice: in a cluster with a
`ResourceQuota` that constrains a compute resource, Kubernetes
requires every pod spec to set a request + limit for that
resource — otherwise the pod is rejected at admission
([Kubernetes ResourceQuota docs][k8s-quota]). That rejection at
`kubectl apply` time is the lesson. A default `LimitRange` makes
the rejection go away by injecting defaults, which hides the
bug it was supposed to expose.

The companion manifest in [`quota.yaml`](./quota.yaml) is a
complete, applyable spec for the `team-a` namespace defined in
[Ex-02](../exercise-02/namespace.yaml).

## 2. Worked answer / implementation

The committed worked example sets, for the `team-a` namespace,
three categories of quota:

1. **Compute quota** — `requests.cpu`, `requests.memory`,
   `limits.cpu`, `limits.memory`, `requests.nvidia.com/gpu`.
   Compute is the hard cap the platform actually bills against
   (ex-02's module §Ex-03).
2. **Object-count quota** — `count/pods`, `count/services`,
   `count/configmaps`, `count/secrets`,
   `count/persistentvolumeclaims`. Without these, a
   misconfigured controller that creates objects in a loop can
   exhaust the API server, taking down the cluster instead of
   just the tenant (mod-003 §Ex-02 calls this out
   explicitly). Object-count quotas use the
   `count/<resource>.<group>` syntax
   ([Kubernetes ResourceQuota docs][k8s-quota]).
3. **Storage quota** — `requests.storage` plus a per-StorageClass
   breakdown (`<class>.storageclass.storage.k8s.io/requests.storage`).
   Lumping storage classes together charges io2 like gp3; splitting
   them keeps the expensive classes visible.

### Decision rationale

- **No `LimitRange` by design.** The exercise's whole value is
  forcing explicit requests/limits in every workload the team
  deploys. A default `LimitRange` silently fills them in and
  erases the signal. The companion Ex-02 workloads must set
  resources explicitly or fail admission.
- **Both `requests.*` and `limits.*`.** `requests.*` is what
  scheduler accounts against node capacity; `limits.*` is the
  cgroup ceiling. A quota that caps only `requests.*` lets a
  tenant schedule a pod requesting 0.5 CPU but with a 32-core
  limit and starve the node. Cap both. Kubernetes `ResourceQuota`
  supports the paired fields directly ([k8s-quota]).
- **GPU as `requests.nvidia.com/gpu`.** Extended resources are
  quotable but only via `requests.<resource>`; there is no
  `limits.<extended-resource>` because extended resources have
  no overcommit model
  ([Kubernetes extended resources][k8s-extended]).
- **Numbers are placeholders, not platform truths.** The
  specific values in `quota.yaml` are a demonstration for a
  single-team onboarding. Real platforms size these against the
  team's purchased budget; mod-003 ex-02 covers the sizing
  discipline ("80% of purchased budget for headroom"). This
  exercise is about shape, not number-picking.
- **No `scopeSelector`.** Quotas scoped to `PriorityClass` or
  `NotTerminating` are a mod-003 / fair-share concern. Stay on
  the floor manifest here.

### What this exercise deliberately does NOT do

- **No `LimitRange`.** Deliberate. See above. A learner who
  adds one must explain in writing why — if they can't, it's a
  miss.
- **No per-PriorityClass quotas, no scope selectors.** Priority
  arrives with scheduling in mod-003.
- **No cost-attribution labels.** Labels land in mod-003 Ex-05.

## 3. Validation steps

Apply against the Ex-02 namespace and verify both the hard-cap
and the forcing-function behaviours:

```bash
# Preconditions: Ex-02 applied first.
kubectl apply -f ../exercise-02/namespace.yaml
kubectl apply -f ../exercise-02/rbac.yaml

# 1. Apply the quota.
kubectl apply -f quota.yaml

# 2. Confirm the quota shape.
kubectl -n team-a get resourcequota team-a-quota -o yaml

# 3. Confirm the quota is initially empty (used == 0).
kubectl -n team-a describe resourcequota team-a-quota | grep Used
# Expect: Used values of 0 (or 0m / 0Gi / 0).

# 4. Forcing-function check — a pod with no resources is
#    REJECTED at admission.
kubectl -n team-a apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: no-resources
spec:
  containers:
    - name: c
      image: nginx
EOF
# Expect: error — must specify requests.cpu / requests.memory /
# limits.cpu / limits.memory.

# 5. Hard-cap check — a pod with resources set, below quota,
#    is ADMITTED.
kubectl -n team-a apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: sized
spec:
  containers:
    - name: c
      image: nginx
      resources:
        requests: { cpu: "500m", memory: "256Mi" }
        limits:   { cpu: "1",    memory: "512Mi" }
EOF
# Expect: created.

# 6. Hard-cap check — a pod that pushes over the quota is
#    REJECTED at admission.
kubectl -n team-a apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: too-big
spec:
  containers:
    - name: c
      image: nginx
      resources:
        requests: { cpu: "100", memory: "256Mi" }
        limits:   { cpu: "100", memory: "512Mi" }
EOF
# Expect: error — exceeded quota: team-a-quota, requested cpu,
# used, limited.

# 7. Clean up.
kubectl -n team-a delete pod sized --ignore-not-found
```

Steps 4, 5, and 6 are the three validation modes every quota
must satisfy: the rejection of under-specified pods, the
admission of properly-sized pods, and the rejection of
over-quota pods. A submission that passes 5 but not 4 has a
quiet `LimitRange` hiding somewhere.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
| --- | --- | --- |
| Forcing-function posture | `ResourceQuota` present; `LimitRange` intentionally absent; rationale written down. | `LimitRange` present without an explicit written reason, or quota missing. |
| Compute coverage | Both `requests.*` and `limits.*` capped for cpu + memory. | Only `requests.*` capped. |
| GPU coverage | `requests.nvidia.com/gpu` (or the appropriate extended-resource name) capped. | GPUs uncapped. |
| Object-count coverage | At least `count/pods`, `count/services`, `count/configmaps`, `count/secrets`, `count/persistentvolumeclaims` capped. | No object-count caps — a runaway controller can exhaust the API server. |
| Storage classes | Storage quota split by StorageClass (`<class>.storageclass.storage.k8s.io/requests.storage`) when more than one class is in play. | One lumped `requests.storage` used across all classes. |
| Validation evidence | All six validation steps executed and their outputs recorded. | Only "it applied" demonstrated; no rejection evidence. |
| Documentation | Writeup names the Kubernetes primitives used and justifies the `LimitRange` omission. | No written rationale or claims not tied to Kubernetes docs. |

A submission must pass every row to be considered complete.

## 5. Common mistakes

Carried forward from the module-level common-mistakes list
([`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see))
and the patterns this exercise is built to catch:

1. **Default `LimitRange` injected "to be nice."** Erases the
   forcing-function the quota was meant to be. Pods with no
   resources set silently get defaults, and the team never
   learns it should be sizing its workloads.
2. **`requests.cpu` capped but not `limits.cpu`.** Lets a pod
   schedule tiny and burst huge. The bursting pod can starve
   the node while staying under the requests quota.
3. **No object-count quotas.** A misconfigured Operator that
   creates one `ConfigMap` per reconcile is the most common
   cluster-killer in multi-tenant platforms (mod-003 §Common
   mistakes). `ResourceQuota` can cap `count/configmaps`;
   use it.
4. **Lumped `requests.storage`.** io2-class storage can be
   >5x the price of gp3-class storage; quoting them together
   both over-charges cheap tenants and under-charges expensive
   ones.
5. **Hard-coding team numbers in the committed manifest.** The
   numbers in the worked example are a demonstration shape. In
   a real platform, parameterise via Kustomize or Helm and let
   the budgeting pipeline write the values. mod-003 Ex-02
   covers that workflow.
6. **Treating `ResourceQuota` as a security control.** It is a
   fairness and billing control. A hostile tenant can still
   degrade the node via syscall-level abuse; the security
   boundary lives in NetworkPolicy + Pod Security Standards
   (mod-003).

## 6. References

**Local**

- Module-level rationale:
  [`../SOLUTION.md`](../SOLUTION.md) §Ex-03.
- Companion manifest:
  [`quota.yaml`](./quota.yaml).
- Precursor exercise (namespace + RBAC this quota applies to):
  [`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md).
- Follow-on module (quota sizing, scope selectors, audit):
  [`../../mod-003-multi-tenancy-resources/exercise-02/`](../../mod-003-multi-tenancy-resources/exercise-02/).
- Learning lesson:
  `lessons/mod-001-platform-fundamentals/exercises/exercise-03-resource-quota-management.md`
  in the `ai-infra-ml-platform-learning` repo.

**External (official project documentation)**

- Kubernetes — Resource Quotas:
  <https://kubernetes.io/docs/concepts/policy/resource-quotas/>
  [k8s-quota]
- Kubernetes — Limit Ranges:
  <https://kubernetes.io/docs/concepts/policy/limit-range/>
- Kubernetes — Managing Resources for Containers
  (requests, limits, extended resources):
  <https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/>
  [k8s-extended]
- Kubernetes — Multi-tenancy (quota as the fairness primitive):
  <https://kubernetes.io/docs/concepts/security/multi-tenancy/>

[k8s-quota]: https://kubernetes.io/docs/concepts/policy/resource-quotas/
[k8s-extended]: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
