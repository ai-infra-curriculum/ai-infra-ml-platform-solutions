# STEP_BY_STEP — Reproducing & validating the reference solution

The learning brief's
[STEP_BY_STEP.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/STEP_BY_STEP.md)
walks the *build* in ten phases. This file is the complement: how to
**reproduce and validate** the reference artifacts in this directory and
run the graded acceptance demo. Read [`SOLUTION.md`](./SOLUTION.md)
first for the rationale behind each step.

## 0. Prerequisites

- A local cluster: `kind create cluster --name smartrecs` or
  `k3d cluster create smartrecs`.
- `kubectl`, `python` 3.11+, `psql`, and (optional) `kubeconform`.
- A Postgres reachable at `$PLATFORM_DB_URL` (the platform DB also holds
  the audit log).

## 1. Validate the artifacts statically (no cluster state changed)

```bash
# CRD + tenant manifests parse and are accepted by the API server
kubectl apply --dry-run=server -f crd/trainingrun-crd.yaml
kubectl apply --dry-run=server -f tenant/tenant-namespace.yaml
# or offline, against bundled schemas:
kubeconform -strict crd/trainingrun-crd.yaml tenant/tenant-namespace.yaml

# Python artifacts byte-compile
python -m py_compile operator/reconcile.py \
    control-plane/training_runs.py audit/verify.py
```

## 2. Install the CRD and prove schema validation (F1)

```bash
kubectl apply -f crd/trainingrun-crd.yaml
kubectl get crd trainingruns.platform.smartrecs.io

# Rejected: bare image (no tag/digest) and missing required fields
kubectl apply -f - <<'EOF'
apiVersion: platform.smartrecs.io/v1alpha1
kind: TrainingRun
metadata: {name: bad, namespace: default}
spec: {image: ghcr.io/x/trainer}      # no tag/digest, no resources/dataset
EOF
# Expected: admission error on spec.image pattern + missing required fields

# Accepted: a minimal valid run
kubectl apply -f - <<'EOF'
apiVersion: platform.smartrecs.io/v1alpha1
kind: TrainingRun
metadata: {name: ok, namespace: default}
spec:
  image: ghcr.io/x/trainer:v1
  resources: {requests: {cpu: "1", memory: 1Gi}}
  dataset: {name: demo}
EOF
```

## 3. Onboard tenants (F4)

```bash
kubectl apply -f tenant/tenant-namespace.yaml          # example: recs-team
# For the acceptance demo, render the same bundle for team-a and team-b
# (the control plane / provisioner does this from the tenant record).
kubectl -n recs-team get resourcequota,limitrange,networkpolicy,serviceaccount
```

## 4. Apply the audit schema and prove immutability (F8)

```bash
psql "$PLATFORM_DB_URL" -f audit/schema.sql

# Insert-only is DB-enforced: each of these MUST raise an error
psql "$PLATFORM_DB_URL" -c "UPDATE audit_log SET action='tamper' WHERE id=1;"
psql "$PLATFORM_DB_URL" -c "DELETE FROM audit_log WHERE id=1;"
psql "$PLATFORM_DB_URL" -c "TRUNCATE audit_log;"

# After a run has produced entries, the chain verifies
python audit/verify.py     # prints "verified (N entries)" or first tampering
```

## 5. Run the operator and control plane

```bash
# Operator (fast local iteration against the cluster):
kopf run operator/reconcile.py --verbose
# Control plane:
uvicorn training_runs:app --app-dir control-plane --port 8080
# OpenAPI is then at http://localhost:8080/docs (NF4: generated spec)
```

## 6. The graded acceptance demo (requirements.md)

Mirrors [requirements.md §"Acceptance demo"](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/requirements.md):

1. Fresh cluster, `make up`.
2. Create `team-a` and `team-b` via the CLI.
3. Submit one run per tenant; both reach `Running`.
4. Submit a `team-a` run over its GPU-hour quota → **HTTP 429**,
   `code: quota_exceeded` (F5).
5. From a `team-a` pod, read `team-b`'s bucket prefix → denied at IAM;
   call a `team-b` service → denied by NetworkPolicy (F4).
6. `python audit/verify.py` → **`verified`** (F8).
7. Restart the operator → in-flight runs continue, state converges in
   <30s (F3).

## 7. What a full submission adds beyond these artifacts

The reference artifacts cover the load-bearing, hardest-to-get-right
pieces. A complete capstone submission additionally ships (per
[requirements.md](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/projects/project-01-platform-core/requirements.md)):
the Python SDK + CLI and `examples/`; `/metrics` endpoints with the five
named series plus a Grafana dashboard JSON (F7); `make up` and a
`deploy/` manifest set (NF1); unit/operator/e2e tests (NF2);
non-root + Cosign-signed images and ESO-managed secrets (NF3); and the
README/ARCHITECTURE/onboarding/runbook docs (NF4). See the rubric in
[`SOLUTION.md` §4](./SOLUTION.md#4-rubric--review-checklist).
