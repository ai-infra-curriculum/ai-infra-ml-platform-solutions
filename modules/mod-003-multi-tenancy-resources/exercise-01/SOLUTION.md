# SOLUTION — Exercise 01: Namespace-per-Team Setup

Reference for [learning ex-01](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-003-multi-tenancy-resources/exercises/exercise-01-namespace-per-team-setup.md).

Read alongside the module-level rationale in
[`../SOLUTION.md`](../SOLUTION.md) §Ex-01 — Namespace-per-team
setup. This file factors that section into a self-contained
reference for graders.

## 1. Solution overview

The deliverable of Ex-01 is **the organizational boundary** for
a tenant on the ML platform: one Kubernetes namespace per team,
with the labels, ServiceAccount, RBAC, and defaults that make
every later control (quota, NetworkPolicy, fair-share, cost
attribution) line up against a single primary key — the team.

The rule the module enforces:

> Namespace is the **organizational** boundary, not the security
> boundary. ([`../SOLUTION.md`](../SOLUTION.md#ex-01--namespace-per-team-setup))

That means:

- One namespace per **team**, not per environment or project.
- Every object inside the namespace carries a `team` label.
- A single `team-platform` ServiceAccount is the identity the
  team's CI uses to deploy — individual humans do not apply
  manifests by hand.
- A `LimitRange` fills in per-container CPU/memory requests and
  limits when a manifest omits them, so sloppy specs still land
  inside the quota.

Security isolation is Ex-03's job (NetworkPolicy). This exercise
only sets up the boundary those later exercises attach to.

## 2. Worked implementation

The template that follows is one team (`team-a`). Repeat for
each tenant. A production rollout drives this from a `teams.yaml`
file through a thin apply script (see the link in
[`README.md`](./README.md) for the full template-driven version
in the engineer-track reference).

### 2.1 Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: team-a
  labels:
    team: a
    cost-center: team-a
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
```

Rationale:

- `team: a` is the selector other objects (NetworkPolicy,
  ResourceQuota targeting labels, cost rollups) key off.
- `cost-center: team-a` is the label the Ex-05 cost pipeline
  enforces and groups by. Setting it on the namespace lets
  admission policies copy it down to child objects.
- `pod-security.kubernetes.io/enforce: restricted` activates the
  Pod Security Admission `restricted` profile — the
  [upstream baseline/restricted policies](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
  that block `hostNetwork`, `hostPID`, privileged containers,
  and other primitives that would void later NetworkPolicy and
  isolation work.

### 2.2 ServiceAccount, Role, RoleBinding

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: team-platform
  namespace: team-a
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: team-deployer
  namespace: team-a
rules:
  - apiGroups: [""]
    resources: [pods, services, configmaps, secrets, persistentvolumeclaims]
    verbs: [get, list, watch, create, update, patch, delete]
  - apiGroups: [apps]
    resources: [deployments, statefulsets, replicasets]
    verbs: [get, list, watch, create, update, patch, delete]
  - apiGroups: [batch]
    resources: [jobs, cronjobs]
    verbs: [get, list, watch, create, update, patch, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-platform-deployer
  namespace: team-a
subjects:
  - kind: ServiceAccount
    name: team-platform
    namespace: team-a
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: team-deployer
```

Rationale:

- The team's CI authenticates as `team-platform`, not as a
  cluster-admin. A compromised pipeline token stays scoped to
  one namespace.
- The Role is deliberately **namespace-scoped** — no `ClusterRole`
  or `ClusterRoleBinding`. See the Kubernetes
  [RBAC reference](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
  for the scoping rules.
- No `escalate`, no `bind` verbs, no access to
  `roles`/`rolebindings` themselves — teams cannot grant
  themselves more.

### 2.3 LimitRange defaults

```yaml
---
apiVersion: v1
kind: LimitRange
metadata:
  name: defaults
  namespace: team-a
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      max:
        cpu: "4"
        memory: "8Gi"
```

Rationale:

- Containers without explicit requests get the
  `defaultRequest`; without that, ResourceQuota (Ex-02) rejects
  those pods at admission because unrequested resources count as
  unbounded. The behaviour is documented in the Kubernetes
  [LimitRange reference](https://kubernetes.io/docs/concepts/policy/limit-range/).
- `max` caps the size of a single container so a team cannot
  consume its entire quota with one pod — a soft guard that
  pairs with the hard caps in Ex-02.

### 2.4 Label enforcement (cross-link)

Objects without the `team` label are rejected by the admission
policy introduced in Ex-05 (the same Kyverno policy that enforces
`cost-center`). Shipping the namespace without that policy is
Mistake #5 from the module common-mistakes list; the attribution
pipeline silently mis-attributes everything the moment any team
forgets a label.

### Decision rationale (why these shapes)

- **Namespace-per-team, not per-environment.** Environments are
  configuration; teams are people. Mapping boundary to people
  keeps RBAC, quotas, and cost rollups aligned to who signs the
  bill. See [`../SOLUTION.md`](../SOLUTION.md#ex-01--namespace-per-team-setup).
- **Pod Security Admission over custom admission.** PSA is
  upstream, cheap, and composable with NetworkPolicy in Ex-03.
  Custom admission is reserved for label enforcement (Ex-05),
  not for baseline pod hardening.
- **ServiceAccount, not user bindings.** Humans rotate; CI
  tokens rotate; namespaces do not. Binding the role to the
  namespace's ServiceAccount means onboarding a new engineer is
  a group-membership change in the identity provider, not a
  manifest change.
- **LimitRange before ResourceQuota.** If quotas land first,
  teams hit confusing "forbidden: must specify requests" errors
  on their first deploy. LimitRange fills defaults so the quota
  bites on *total* usage rather than on missing fields.

## 3. Validation steps

Apply the manifests to a cluster and verify each control is
actually in effect. All commands are standard `kubectl`.

```bash
# 3.1 Namespace exists with the required labels.
kubectl get ns team-a -o jsonpath='{.metadata.labels}' | tee /tmp/ns-labels
grep -q '"team":"a"' /tmp/ns-labels
grep -q '"cost-center":"team-a"' /tmp/ns-labels
grep -q '"pod-security.kubernetes.io/enforce":"restricted"' /tmp/ns-labels

# 3.2 ServiceAccount + Role + RoleBinding present and namespace-scoped.
kubectl -n team-a get sa team-platform
kubectl -n team-a get role team-deployer
kubectl -n team-a get rolebinding team-platform-deployer

# 3.3 Impersonation check — the SA can deploy inside team-a but not
# outside. `auth can-i` is the documented RBAC probe.
kubectl auth can-i create deployments \
  --as=system:serviceaccount:team-a:team-platform -n team-a   # yes
kubectl auth can-i create deployments \
  --as=system:serviceaccount:team-a:team-platform -n team-b   # no
kubectl auth can-i create clusterrolebindings \
  --as=system:serviceaccount:team-a:team-platform             # no

# 3.4 LimitRange defaults are applied to pods without requests.
kubectl -n team-a run probe --image=nginx --restart=Never --dry-run=server -o yaml \
  | grep -E 'cpu|memory'
# Expect the pod spec to come back with requests cpu=100m, memory=128Mi.

# 3.5 Pod Security Admission blocks a privileged pod.
kubectl -n team-a apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata: { name: priv }
spec:
  containers:
    - name: c
      image: nginx
      securityContext: { privileged: true }
EOF
# Expect admission error citing pod-security.kubernetes.io/enforce=restricted.
```

Each step is pass/fail. A step that errors or that returns the
wrong value fails the exercise — do not patch past the failure.

## 4. Rubric / review checklist

| Dimension | Pass criterion |
| --- | --- |
| Boundary choice | Namespace is per **team**, not per environment or project. |
| Labels | Namespace carries at minimum `team` and `cost-center`; both are also enforced on child objects (via Kyverno in Ex-05). |
| Identity | A `team-platform` ServiceAccount exists and is the only identity bound to the deploy Role. No `ClusterRoleBinding` is created for the team. |
| RBAC scope | Role is namespaced; no `escalate`/`bind`; no access to `roles`/`rolebindings`. |
| Defaults | `LimitRange` supplies `defaultRequest` so manifests without explicit requests still deploy *and* still count against ResourceQuota. |
| Pod hardening | `pod-security.kubernetes.io/enforce: restricted` is set on the namespace; a privileged pod is rejected at admission. |
| Cross-exercise fit | The namespace is ready to accept ResourceQuota (Ex-02), NetworkPolicy (Ex-03), Volcano queues (Ex-04), and cost-attribution rollups (Ex-05) without modification. |

A submission must pass every row. A missing `team` or
`cost-center` label is a fail, not a nit, because every later
control keys off those labels.

## 5. Common mistakes

Carried from [`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see)
and what graders consistently see on this exercise:

1. **Namespace-per-environment** (`team-a-dev`, `team-a-prod`).
   Doubles the surface area, splits RBAC and cost attribution,
   and still doesn't give you a security boundary. Use labels
   for environment inside the team's namespace; the namespace
   stays team-scoped.
2. **ClusterRoleBinding where a RoleBinding would do.** Even a
   read-only `ClusterRoleBinding` lets the team's CI read every
   other tenant's namespace. If a team genuinely needs a
   cluster-wide read, give them a separate, auditable
   `ClusterRole` reviewed outside this template.
3. **Omitting the `LimitRange`.** Teams hit admission errors on
   their first deploy against the Ex-02 quota, blame the
   platform, and start adding explicit requests that are too
   high "to be safe". Quotas then bite on paper, not in
   practice.
4. **No Pod Security Admission.** Namespaces without PSA let
   pods opt into `hostNetwork` or `privileged: true`, which
   voids the NetworkPolicy work in Ex-03 before it starts.
5. **Forgetting the `cost-center` label.** The attribution
   pipeline in Ex-05 silently mis-attributes anything unlabeled.
   Enforce on the namespace, let Kyverno copy it down to child
   objects.

## 6. References

**Local**

- Module-level rationale:
  [`../SOLUTION.md`](../SOLUTION.md) §Ex-01.
- Sibling exercises that key off this boundary:
  [`../exercise-02`](../exercise-02/) (ResourceQuota),
  [`../exercise-03`](../exercise-03/) (NetworkPolicy),
  [`../exercise-04`](../exercise-04/) (Volcano fair-share),
  [`../exercise-05`](../exercise-05/) (Cost attribution).
- Learning exercise prompt:
  `lessons/mod-003-multi-tenancy-resources/exercises/exercise-01-namespace-per-team-setup.md`
  in the `ai-infra-ml-platform-learning` repo.
- Engineer-track reference with the full template-driven apply
  script: see link in [`README.md`](./README.md).

**External — upstream Kubernetes docs**

- [Namespaces concept](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/)
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
  and [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)
- [RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [LimitRange](https://kubernetes.io/docs/concepts/policy/limit-range/)

**External — frameworks that justify the control shape**

- NIST AI Risk Management Framework —
  <https://www.nist.gov/itl/ai-risk-management-framework>
  (the `MANAGE` and `GOVERN` functions call for tenant-scoped
  identity and auditable boundaries; namespace-per-team is one
  implementation of that control).
