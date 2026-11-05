# SOLUTION — Exercise 02: Namespace Isolation in Kubernetes

> Per-exercise solution. The cross-exercise rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md); this file factors the Ex-02
> section into a self-contained reference for graders and
> implementers. Companion artifacts are
> [`namespace.yaml`](./namespace.yaml) and
> [`rbac.yaml`](./rbac.yaml).

## 1. Solution overview

Exercise 02 asks the learner to stand up the *minimum credible
isolation primitive* an ML platform uses to separate tenant
teams: a Kubernetes namespace plus the RBAC objects that make it
usable. The deliverable is a set of manifests that create, for a
single tenant team, the scope the platform hands back in response
to "we need a space to run jobs."

The single most important thing this exercise teaches — and the
line graders check for — is the distinction the module solution
calls out ([`../SOLUTION.md`](../SOLUTION.md#ex-02--namespace-isolation-in-kubernetes)):

> Namespace is not a security boundary. It is a naming + RBAC +
> quota boundary. Treating it as a security boundary is the most
> common multi-tenancy bug in junior platform teams.

Namespaces group and name objects, scope `Role`/`RoleBinding`
grants, and bound `ResourceQuota` + `LimitRange` application.
They do *not* isolate network traffic, enforce pod security, or
prevent cross-namespace resource access on their own — those
primitives live in later modules (NetworkPolicy and PSA in
mod-003). A reference solution that claims otherwise fails the
rubric regardless of how clean the manifests look.

## 2. Worked answer / implementation

The committed worked example provisions one tenant team,
`team-a`, with the shape every tenant in the module gets:

- A dedicated namespace labelled with the team key so
  observability and cost tooling can pivot on it.
- A `ServiceAccount` the team's CI uses for `kubectl apply`
  (platform provides this; team does not create its own).
- A `Role` scoped to the namespace enumerating the verbs the
  team is allowed on the resource kinds it may touch.
- A `RoleBinding` that binds the team's SSO group *and* the CI
  `ServiceAccount` to the `Role`.

The manifests are in [`namespace.yaml`](./namespace.yaml) and
[`rbac.yaml`](./rbac.yaml); together they apply with a single
`kubectl apply -f .`.

### Decision rationale

- **Namespace-per-team, not per-environment or per-project.**
  Teams are durable; environments and projects churn. The module
  SOLUTION calls this out explicitly in
  [`../SOLUTION.md`](../SOLUTION.md#ex-02--namespace-isolation-in-kubernetes),
  and the Kubernetes "Multi-tenancy" guide treats team/tenant as
  the primary partitioning axis for soft multi-tenancy
  ([Kubernetes multi-tenancy docs][k8s-multitenancy]).
- **`Role` + `RoleBinding`, not `ClusterRole` + `RoleBinding`.**
  A `ClusterRole` grants cluster-wide verbs even when bound at
  namespace scope for non-namespaced resources, which widens the
  blast radius if the binding is ever mis-targeted. Keep
  tenant-facing grants in namespaced `Role` objects
  ([Kubernetes RBAC docs][k8s-rbac]).
- **Group-bound subjects, not user-bound.** `RoleBinding.subjects`
  points at the team's IdP group. User-level bindings rot the
  moment anyone joins, leaves, or changes teams.
- **ServiceAccount for CI, humans use SSO.** Humans get a
  kubeconfig produced by the cluster's OIDC flow and reach the
  API as themselves. CI pipelines use the namespace-scoped
  `ServiceAccount`. Never share a kubeconfig token between
  humans and CI ([Kubernetes ServiceAccount docs][k8s-sa]).
- **Explicit verb list in the `Role`.** `verbs: ["*"]` or
  `resources: ["*"]` fails the rubric. The reference `Role`
  enumerates the specific verbs the team's workflow needs
  (`get, list, watch, create, update, patch, delete` on
  `pods`, `deployments`, `jobs`, `services`, `configmaps`,
  `secrets`, `persistentvolumeclaims`).
- **No `ResourceQuota` in this exercise.** Quota authoring is
  Ex-03's responsibility; keeping them in separate files lets
  learners see the two concerns independently before Ex-03
  composes them.

### What this exercise deliberately does NOT do

- **No NetworkPolicy.** A learner who adds one here is mixing
  modules; the policy ships with mod-003 Ex-03 where it belongs.
- **No PodSecurity admission labels.** Pod Security Standards
  are a mod-003 concern.
- **No cross-namespace primitives (`HierarchyConfiguration`
  from HNC, etc.).** Keep the floor manifest standard
  Kubernetes; abstractions come later.

## 3. Validation steps

Apply and verify on a local cluster (kind, minikube, k3d —
anything RBAC-enabled):

```bash
# 1. Apply.
kubectl apply -f namespace.yaml
kubectl apply -f rbac.yaml

# 2. Confirm the namespace exists with the expected label.
kubectl get ns team-a -o jsonpath='{.metadata.labels}'
# Expect: {"team":"team-a", ...}

# 3. Confirm the RBAC objects live in the tenant namespace.
kubectl -n team-a get role,rolebinding,serviceaccount

# 4. Prove the Role is scoped by attempting a cross-namespace
#    read as the team's ServiceAccount — must be denied.
kubectl auth can-i list pods \
  --as=system:serviceaccount:team-a:team-a-ci \
  -n kube-system
# Expect: no

# 5. Prove the Role allows the intended verbs inside the
#    tenant namespace.
kubectl auth can-i create deployments \
  --as=system:serviceaccount:team-a:team-a-ci \
  -n team-a
# Expect: yes

# 6. Prove cluster-wide operations are denied.
kubectl auth can-i list nodes \
  --as=system:serviceaccount:team-a:team-a-ci
# Expect: no
```

A learner's submission is valid iff all six checks pass as
annotated. Any `yes` where the comment says `no`, or vice
versa, is a failed submission even if the YAML is syntactically
correct.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
| --- | --- | --- |
| Boundary framing | Writeup names namespace as naming + RBAC + quota boundary and explicitly flags that it is *not* a network/security boundary. | Submission claims namespace isolates tenants from each other. |
| Namespace shape | Exactly one namespace per team, labelled with a `team=<key>` label. | Namespace-per-environment, no team label, or multiple teams sharing one namespace. |
| Role scope | `kind: Role`, resources + verbs enumerated explicitly. | `ClusterRole` used for namespaced verbs, or any `verbs: ["*"]` / `resources: ["*"]`. |
| Subject shape | `RoleBinding` targets an IdP group and a namespace `ServiceAccount`; never a bare user. | User-bound `RoleBinding.subjects`, or group name invented without naming the IdP. |
| CI identity | A `ServiceAccount` in the tenant namespace is the CI principal. | CI uses a cluster-admin kubeconfig or a shared static token. |
| Cross-namespace denial | `can-i` against another namespace returns `no` for the team identity. | Any spill of permissions outside the tenant namespace. |
| Documentation | README/commit message names the Kubernetes primitives used and the ones intentionally deferred (NetworkPolicy, PSA). | No written rationale, or justifications invented without citation. |

A submission must pass every row to be considered complete.

## 5. Common mistakes

Carried forward from the module-level common-mistakes list
([`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see))
and the patterns this exercise is built to catch:

1. **Namespace treated as a security boundary.** The most common
   failure. Default Kubernetes does not block pod-to-pod traffic
   across namespaces; two pods in different namespaces can talk
   as if they were in the same one. NetworkPolicy (mod-003 ex-03)
   is what blocks it.
2. **Wildcard RBAC.** `verbs: ["*"]` passes every test the
   learner wrote. It also hands the team permission to delete
   every RBAC object in the namespace, including the binding
   they came in on. Enumerate verbs.
3. **`ClusterRole` for namespaced grants.** A `ClusterRole` bound
   via a `RoleBinding` works, but the moment someone converts
   that binding to a `ClusterRoleBinding` the grant becomes
   cluster-wide. Use `Role` for namespaced resources so the
   conversion is harder to do by accident.
4. **User-bound subjects.** `kind: User, name: alice@corp.example`
   is a people-churn time bomb. Bind to groups.
5. **No team label on the namespace.** Downstream tools (cost
   attribution, audit, dashboards) all pivot on this label.
   Without it the tenant is invisible to the rest of the
   platform.
6. **Shared CI kubeconfig across tenants.** A single CI principal
   that can `apply` into every namespace erases the whole
   boundary. One `ServiceAccount` per tenant, held by that
   tenant's pipeline.

## 6. References

**Local**

- Module-level rationale:
  [`../SOLUTION.md`](../SOLUTION.md) §Ex-02.
- Companion manifests:
  [`namespace.yaml`](./namespace.yaml),
  [`rbac.yaml`](./rbac.yaml).
- Follow-on exercise (quota layer):
  [`../exercise-03/SOLUTION.md`](../exercise-03/SOLUTION.md).
- Learning lesson:
  `lessons/mod-001-platform-fundamentals/exercises/exercise-02-namespace-isolation-in-kubernetes.md`
  in the `ai-infra-ml-platform-learning` repo.

**External (official project documentation)**

- Kubernetes concepts — Namespaces:
  <https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/>
- Kubernetes — RBAC authorization:
  <https://kubernetes.io/docs/reference/access-authn-authz/rbac/>
  [k8s-rbac]
- Kubernetes — ServiceAccounts:
  <https://kubernetes.io/docs/concepts/security/service-accounts/>
  [k8s-sa]
- Kubernetes — Multi-tenancy:
  <https://kubernetes.io/docs/concepts/security/multi-tenancy/>
  [k8s-multitenancy]
- Kubernetes — NetworkPolicy (for the "what namespace does NOT
  do" discussion only; implementation ships in mod-003 ex-03):
  <https://kubernetes.io/docs/concepts/services-networking/network-policies/>

[k8s-rbac]: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
[k8s-sa]: https://kubernetes.io/docs/concepts/security/service-accounts/
[k8s-multitenancy]: https://kubernetes.io/docs/concepts/security/multi-tenancy/
