# SOLUTION — Exercise 02: Vault Secret Rotation

> Per-exercise solution. The module-level rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md) §Ex-02; this file factors that
> section into a self-contained reference for graders and learners.
> Companion artifact in this directory: [`README.md`](./README.md)
> (quick-pointer to the engineer-tier worked implementation —
> Vault policy + Terraform integration + ESO ClusterSecretStore +
> ExternalSecret with auto-rotation). See the identity story in
> [`../exercise-01/README.md`](../exercise-01/README.md) and the
> admission-time verification in
> [`../exercise-04/`](../exercise-04/) that assumes every workload
> is already brokered through Vault.

## 1. Solution overview

The deliverable is **a running Vault deployment where every secret
has a TTL, every secret has a rotation procedure that lives in code,
and no secret ever lands in a workload's process environment
directly**. The two failure modes this exercise exists to prevent
are (a) secrets that never rotate — "an expensive password vault"
([`../SOLUTION.md`](../SOLUTION.md) §Ex-02) — and (b) secrets that
leak through `env` dumps, container inspect, or crash reports.

The reference solution commits to five design decisions that drive
every artifact in this exercise and every downstream exercise in the
module:

1. **HashiCorp Vault is the only secret store.** No secret lives in
   a ConfigMap, a Kubernetes `Secret` that was hand-rolled from a
   `.env` file, or a CI variable. Static secrets outside Vault are
   out of scope of the rotation process and therefore violate
   decision 2.
2. **Every secret has an explicit TTL** configured at the secret
   engine or role level. A secret without a TTL is a secret that
   never rotates by definition
   ([Vault — token and lease TTLs](https://developer.hashicorp.com/vault/docs/concepts/tokens#token-time-to-live-periodic-tokens-and-explicit-max-ttls)).
3. **The rotation procedure is a runnable artifact.** For dynamic
   secrets, rotation is a Vault lease renewal/revoke cycle. For
   static secrets — the awkward case — rotation is a documented
   script that rotates the upstream credential (DB password, cloud
   key, signing key) and writes the new value into Vault in one
   transaction. Both paths are code, not a Confluence page.
4. **Secrets reach workloads through a broker, not via `env`.** The
   reference supports two equivalent brokers:
   - **Vault Agent sidecar** that templates the secret into a file
     the application reads
     ([Vault Agent — sidecar injector](https://developer.hashicorp.com/vault/docs/platform/k8s/injector)),
     or
   - **External Secrets Operator (ESO)** with a `ClusterSecretStore`
     that syncs Vault into Kubernetes `Secrets` with a `refreshInterval`
     and a mounted projected-volume
     ([External Secrets Operator — HashiCorp Vault provider](https://external-secrets.io/latest/provider/hashicorp-vault/)).
   Either way the application does not see the secret in its
   `environ`, and the secret rotates under it without a pod restart
   (or with a controlled rollout the operator drives).
5. **Authentication to Vault is identity-bound, not token-bound.**
   Kubernetes workloads authenticate via the
   [Kubernetes auth method](https://developer.hashicorp.com/vault/docs/auth/kubernetes)
   using the pod's ServiceAccount token projected and verified by
   Vault. CI workloads authenticate via short-lived OIDC trust (GitHub
   Actions OIDC, GitLab JWT) — never a long-lived root token. This is
   the "no long-lived credentials" invariant from
   [`../SOLUTION.md`](../SOLUTION.md) §Cross-exercise design decisions.

A submission that stores secrets in Vault but reads them from an
env var, or that defines TTLs but never renews leases, is not
solving the exercise: the rotation path is the entire point.

## 2. Worked answer or implementation

The worked implementation uses a Postgres database credential as the
canonical dynamic-secret fixture and an S3 access key as the
canonical static-secret fixture. The shapes generalize to every
other backend; the engineer-tier worked implementation
([`README.md`](./README.md)) extends this with a cloud KMS signing
key for Ex-03 cosign and a service-account PAT for Ex-01.

### 2.1 Deployment topology

```
                     ┌──────────────────────────┐
                     │  OIDC IdP (ex-01)        │
                     └───────────┬──────────────┘
                                 │ JWT with groups
                                 ▼
┌──────────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│  Workload pod        │──▶│  Vault Agent /   │──▶│  Vault server   │
│  (no secrets in env) │   │  ESO operator    │   │  (HA, Raft)     │
└──────────────────────┘   └────────┬─────────┘   └────────┬────────┘
       ▲                            │                      │
       │ reads from file /          │ lease renew          │ TTL-bound
       │ projected volume           │ or refreshInterval   │ leases
       │                            │                      │
       │                            ▼                      ▼
       │                 ┌──────────────────┐   ┌─────────────────┐
       └─────────────────│  Postgres        │   │  Audit log      │
                         │  (database       │   │  (append-only,  │
                         │  secret engine)  │   │  Ex-05 reads    │
                         └──────────────────┘   │  this)          │
                                                └─────────────────┘
```

Vault runs HA on Raft storage. The audit device is enabled before
any production policy is written (an unaudited Vault is unprovable).
The Kubernetes auth method is configured against the cluster's
ServiceAccount issuer and the JWT audience the operator expects
([Vault — Kubernetes auth](https://developer.hashicorp.com/vault/docs/auth/kubernetes)).

### 2.2 Dynamic secret: Postgres database credentials

Dynamic secrets are the ergonomic path: Vault issues a fresh,
TTL-bound DB role on every request, and lease revocation is the
rotation.

```hcl
# Enable the database secrets engine.
path "sys/mounts/database" {
  capabilities = ["create", "read", "update", "delete"]
}

# Configure the Postgres connection (Vault itself holds a rotating
# root credential — see §2.5 on rotate-root).
resource "vault_database_secret_backend_connection" "pg" {
  backend       = vault_mount.db.path
  name          = "platform-pg"
  allowed_roles = ["ml-platform-ro", "ml-platform-rw"]

  postgresql {
    connection_url = "postgresql://{{username}}:{{password}}@pg.svc:5432/platform?sslmode=verify-full"
    username       = var.pg_bootstrap_user
    password       = var.pg_bootstrap_password
  }
}

# A role that grants read-only access, max lease 1h, default lease 30m.
resource "vault_database_secret_backend_role" "ro" {
  backend     = vault_mount.db.path
  name        = "ml-platform-ro"
  db_name     = vault_database_secret_backend_connection.pg.name
  default_ttl = 1800
  max_ttl     = 3600
  creation_statements = [
    "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';",
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";",
  ]
  revocation_statements = [
    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM \"{{name}}\";",
    "DROP ROLE IF EXISTS \"{{name}}\";",
  ]
}
```

Why each knob is where it is:

- **`default_ttl: 1800`, `max_ttl: 3600`.** 30-minute default, 1-hour
  ceiling. Longer than one HTTP request (so Vault is not on the hot
  path) and shorter than a work shift (so a leaked credential ages
  out within an hour). This is the TTL the Ex-05 compliance audit
  checks against.
- **`revocation_statements` present.** The lease revoke is not a
  Vault abstraction — it has to issue the `DROP ROLE` to Postgres.
  A role without revocation statements leaves orphaned Postgres
  roles after every lease expiry and makes rotation unverifiable.
- **Role-scoped `creation_statements`.** The platform grants only
  what the role needs. Vault issuing `SUPERUSER` creds is Vault
  issuing a backdoor.

### 2.3 Static secret: cloud access key (and why it is harder)

Not every backend supports dynamic secrets. S3 access keys, signing
keys for Ex-03 cosign, and third-party API tokens are static — the
rotation procedure has to be explicit.

```python
# rotate_s3_key.py — the "rotation procedure in code" required by §1.3.
import boto3, hvac, sys, os

VAULT = hvac.Client(url=os.environ["VAULT_ADDR"])
VAULT.auth.approle.login(  # CI identity, OIDC-brokered elsewhere
    role_id=os.environ["ROLE_ID"], secret_id=os.environ["SECRET_ID"],
)
KV = VAULT.secrets.kv.v2

PATH, USER = "platform/artifacts", "svc-artifacts"

old = KV.read_secret_version(path=PATH)["data"]["data"]
iam = boto3.client("iam")

# 1. Create the new key alongside the old one.
new = iam.create_access_key(UserName=USER)["AccessKey"]

# 2. Publish the new key to Vault *before* retiring the old one.
#    Readers (Vault Agent, ESO) see the new version on their next
#    refresh. The TTL on the KV version is the rotation window.
KV.create_or_update_secret(
    path=PATH,
    secret={
        "access_key_id":     new["AccessKeyId"],
        "secret_access_key": new["SecretAccessKey"],
        "rotated_at":        new["CreateDate"].isoformat(),
        "previous_key_id":   old["access_key_id"],
    },
)

# 3. Only after the dependent workloads have picked up the new
#    version, deactivate the old key. Deletion is deferred to the
#    next scheduled run so the grace window is one rotation cycle.
iam.update_access_key(
    UserName=USER, AccessKeyId=old["access_key_id"], Status="Inactive",
)

print(f"rotated {USER}; new={new['AccessKeyId']}, previous={old['access_key_id']} inactive")
```

Three properties of this script matter to the rubric:

- **New key is created before the old one is retired.** The grace
  window is non-empty; a rollout that is slow to pick up the new
  version does not take an outage. Vault's own
  [credential-rotation guidance](https://developer.hashicorp.com/vault/docs/secrets/aws#root-credential-rotation)
  follows the same shape for the root AWS credential.
- **Deactivation, not deletion, on the first pass.** `Inactive`
  keys can be re-activated if the rollout surfaces a regression;
  deleted keys cannot. Deletion lives on a subsequent scheduled run
  gated on the previous rotation succeeding.
- **The rotation itself is auditable.** `previous_key_id` and
  `rotated_at` are written into the KV payload so the quarterly
  audit ([`../exercise-05/`](../exercise-05/)) can prove rotation
  happened.

### 2.4 How the workload reads the secret (the "no env" invariant)

Pattern A — **Vault Agent sidecar** writes the secret to a tmpfs
volume the app reads. The app never sees the secret in its environ
and cannot leak it via `env` dumps or crash reports.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: model-serving
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "model-serving"
    vault.hashicorp.com/agent-inject-secret-db.ini: "database/creds/ml-platform-ro"
    vault.hashicorp.com/agent-inject-template-db.ini: |
      {{- with secret "database/creds/ml-platform-ro" -}}
      [database]
      url = postgresql://{{ .Data.username }}:{{ .Data.password }}@pg.svc:5432/platform
      {{- end }}
spec:
  template:
    spec:
      serviceAccountName: model-serving
      containers:
        - name: server
          image: registry.local/model-serving:${IMAGE_TAG}
          # NO env: section for DB creds. The app reads /vault/secrets/db.ini.
```

Pattern B — **External Secrets Operator** syncs into a Kubernetes
`Secret` mounted as a projected volume:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata: { name: vault-platform }
spec:
  provider:
    vault:
      server: "https://vault.platform.svc:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "eso-reader"
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata: { name: artifacts-s3 }
spec:
  refreshInterval: "15m"       # pickup window for §2.3's rotation
  secretStoreRef: { name: vault-platform, kind: ClusterSecretStore }
  target: { name: artifacts-s3, creationPolicy: Owner }
  data:
    - secretKey: access_key_id
      remoteRef: { key: platform/artifacts, property: access_key_id }
    - secretKey: secret_access_key
      remoteRef: { key: platform/artifacts, property: secret_access_key }
```

Both patterns satisfy §1 decision 4. The reference solution picks
Vault Agent for workloads where a short pickup window matters (the
Agent renews leases on its own schedule) and ESO for workloads where
operational simplicity matters more (one operator, declarative
manifests, visible in standard Kubernetes RBAC).

### 2.5 Rotate-root: the bootstrap-credential problem

Vault itself holds a credential it uses to talk to Postgres (the
`username`/`password` in §2.2). If that credential never rotates,
Vault is the long-lived-credential anti-pattern the module forbids.

The reference calls `sys/rotate` on the database connection on a
schedule; Vault rewrites its own root credential to a value only
Vault knows and no human ever sees
([Vault — database rotate-root](https://developer.hashicorp.com/vault/api-docs/secret/databases#rotate-root-credentials)):

```bash
vault write -force database/rotate-root/platform-pg
```

This closes the loop: workload creds are short-lived (§2.2); the
master credential Vault uses to mint them is also rotated (§2.5);
no human has a credential that can masquerade as the platform.

### 2.6 Decision rationale

- **Why dynamic over static whenever possible?** Lease revocation
  is atomic and verifiable. Static-secret rotation is a dance across
  two systems where rollback is awkward. Prefer the engine that
  gives you atomicity.
- **Why TTLs this short?** NIST AI RMF (Manage 2.3) and the
  cross-cutting NIST AI 600-1 governance actions require "limiting
  exposure window for compromised credentials." A 30-minute TTL
  bounds the blast radius to the time between a compromise and the
  next renewal.
- **Why Vault Agent *or* ESO rather than picking one?** The team
  owns both patterns; standardizing on one would push a bad fit
  onto half the workloads. The invariant — "secret never in env" —
  is what matters. The transport is a workload choice.
- **Why Kubernetes auth method, not AppRole, for pod workloads?**
  AppRole requires issuing and distributing a `secret_id`, which is
  itself a long-lived credential. The Kubernetes auth method uses
  the projected ServiceAccount token the kubelet already rotates.
- **Why audit before policy?** An unaudited Vault cannot prove
  rotation happened. The quarterly audit
  ([`../exercise-05/`](../exercise-05/)) reads Vault's audit device
  to produce the rotation-evidence section.

## 3. Validation steps

Each check names the exact command a grader runs against a dev
Vault with the module's manifests applied.

1. **Audit is enabled before any production policy is written.**
   `vault audit list` returns at least one device (typically
   `file/`). A submission that writes policies first and enables
   audit later cannot prove the policies' first use.
2. **Secret engines are mounted with TTLs.**
   `vault read database/config/platform-pg` returns the role list
   and connection; `vault read database/roles/ml-platform-ro`
   returns `default_ttl = 1800`, `max_ttl = 3600`. A role missing
   `default_ttl` or `max_ttl` fails this step — "has a TTL" is the
   check; "no TTL" is the failure.
3. **Dynamic secret issuance works and is bounded.**
   `vault read database/creds/ml-platform-ro` returns a fresh
   username/password pair with `lease_duration: 1800`. The returned
   username exists in Postgres (`\du` lists it); revoking the lease
   (`vault lease revoke <id>`) drops the role from Postgres.
4. **Static secret rotation runs end-to-end.**
   `python rotate_s3_key.py` writes a new KV version, marks the
   previous key `Inactive` (not deleted), and records `previous_key_id`
   and `rotated_at` into the new KV payload.
5. **Kubernetes auth method authenticates a workload pod.**
   `kubectl exec` into the `model-serving` pod and run
   `cat /vault/secrets/db.ini`. The file exists, contains fresh
   credentials, and was written by the Vault Agent sidecar (not by
   the application). `env | grep -i pass` returns nothing.
6. **Pickup window is observable.**
   Rotate the S3 key (step 4). Within one `refreshInterval` the
   ESO-managed `Secret` resource's `.data.access_key_id` changes
   (`kubectl get secret artifacts-s3 -o jsonpath='{.data.access_key_id}'`
   decodes to the new ID). The pickup window is measured, not
   assumed.
7. **Rotate-root for the master credential succeeds.**
   `vault write -force database/rotate-root/platform-pg` returns
   success. The Terraform state's `pg_bootstrap_password` is no
   longer the password Postgres accepts — only Vault knows the new
   one. (This is the step that proves no human has a permanent
   platform-wide credential.)
8. **Workload keeps running across a rotation.**
   With a load generator running against `model-serving`, trigger
   the rotation (steps 4 and 7). Error rate stays within the
   AnalysisTemplate SLO from mod-006 ex-03. A rotation that takes
   an outage is a rotation the team will stop doing.
9. **Audit log records the rotation.**
   `grep database/creds/ml-platform-ro /var/log/vault/audit.log`
   shows the lease issue and revoke events; `grep rotate-root`
   shows the master rotation. The Ex-05 compliance audit relies on
   exactly these records.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
|---|---|---|
| Secret-store scope | Every production secret lives in Vault; ConfigMaps/hand-rolled Secrets are empty of sensitive data. | Any production credential found in a ConfigMap, a `.env`, a CI variable, or a container image layer. |
| TTL coverage | 100% of secret backends and roles have explicit `default_ttl` and `max_ttl`. | A backend missing a TTL; "unbounded" leases issued. |
| Dynamic preferred | Dynamic secret engines used for DB/cloud/PKI wherever supported; static KV used only when the backend truly lacks a dynamic engine. | Static KV used for a Postgres password when the `database/` engine supports it. |
| Rotation-as-code (static path) | A runnable script rotates every static secret; it creates-before-retires, records `rotated_at`, and defers deletion. | Rotation lives in a Confluence page; "we rotate manually each quarter"; delete-before-create cuts over with an outage. |
| Transport | No secret appears in a Pod's `env` section. Workloads read from Vault Agent file mounts or ESO-managed projected volumes. | DB password injected via `env:` from a Secret; `printenv` inside the pod reveals credentials. |
| Vault auth is identity-bound | Kubernetes auth method for pods; OIDC / short-lived JWT for CI. | AppRole `secret_id` committed to CI; root token in a CI variable; long-lived Vault token in a Secret. |
| Audit | Audit device enabled at bootstrap; audit log is append-only and shipped off-node; Ex-05 reads it. | Audit device added after policies; logs on the Vault node only; gaps in the log. |
| Rotate-root | Master credentials Vault uses to talk to upstreams rotate on a schedule; Terraform state cannot resurrect them. | The Terraform `password` is still the live Postgres password. |
| Grace window | Static-secret rotations have a non-zero pickup window and a verified rollback path. | Rotation deactivates old keys before new ones propagate; rollback is "redeploy from a backup." |
| Continuity | Workload keeps running across a rotation (§3 step 8). | Rotation requires a maintenance window. |

A passing submission scores Pass on every row. "Secrets in Vault
with TTLs" without a verified transport and a verified rotation
run is the classic near-miss; the gates are the transport, the
rotation, and the audit — each equally load-bearing.

## 5. Common mistakes

Inherited from the module-level list
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see,
item 2) and narrowed to this exercise:

1. **Vault with no TTLs.** The classic anti-pattern. A static KV
   value behind a newer wall is still a static value. Every secret
   gets a TTL or the exercise is not solved.
2. **Env-var transport.** `env: - name: DB_PASSWORD
   valueFrom: secretKeyRef:` leaks the secret into `environ`, into
   crash reports, into `docker inspect`, and into every
   observability stack that scrapes pod metadata. Use the Agent or
   ESO + a mounted volume.
3. **AppRole `secret_id` in CI.** Converts the long-lived API token
   problem into a long-lived `secret_id` problem. Use the Kubernetes
   auth method for pods and OIDC-brokered short-lived JWTs for CI.
4. **Rotation procedure in a wiki.** A procedure that is not a
   script cannot be scheduled, cannot be audited, and does not run
   when the author quits. Every static secret needs an
   `rotate_<name>.py` (or Terraform) next to it.
5. **Delete-before-create.** Drops the old key before verifying the
   new one is in use. Takes an outage on every rotation. The right
   shape is create → publish to Vault → wait for pickup → deactivate
   → (later) delete. See `rotate_s3_key.py` in §2.3.
6. **Skipping `database/rotate-root`.** The master credential Vault
   holds is itself a long-lived credential. Rotating workload creds
   from a static master is a short wall behind a tall wall.
7. **Audit added after policy.** The audit device has to be enabled
   before the first policy write or the first policy write is
   unlogged. Audit-first is the only reliable order
   ([Vault — enabling audit devices](https://developer.hashicorp.com/vault/docs/audit)).
8. **Storing secrets in the Terraform state file.** Terraform state
   contains plaintext `password` for dynamic engine bootstrap; the
   state backend must itself be encrypted-at-rest and
   access-controlled, and `database/rotate-root` must be called
   immediately after bootstrap to invalidate the state's copy.

## 6. References

**Official sources**

- [HashiCorp Vault — Kubernetes auth method](https://developer.hashicorp.com/vault/docs/auth/kubernetes).
  Authoritative for ServiceAccount-token-based workload auth and
  the TLS/audience configuration the reference depends on.
- [HashiCorp Vault — Vault Agent sidecar injector](https://developer.hashicorp.com/vault/docs/platform/k8s/injector).
  Authoritative for the annotations in §2.4 pattern A.
- [HashiCorp Vault — Database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases).
  Authoritative for `default_ttl`, `max_ttl`, creation/revocation
  statements, and rotate-root semantics.
- [HashiCorp Vault — Audit devices](https://developer.hashicorp.com/vault/docs/audit).
  Authoritative for the audit-first bootstrap order and the log
  format the Ex-05 audit consumes.
- [External Secrets Operator — HashiCorp Vault provider](https://external-secrets.io/latest/provider/hashicorp-vault/).
  Authoritative for the `ClusterSecretStore` + `ExternalSecret`
  shapes in §2.4 pattern B and `refreshInterval` semantics.
- [OWASP Machine Learning Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/)
  — ML06 (AI supply chain attack) and its credential-compromise
  precondition is the threat this exercise bounds.
- [MITRE ATLAS](https://atlas.mitre.org/) — "Valid Accounts" and
  "Credential Access" techniques (inherited from ATT&CK) map
  directly onto the leaked-secret failure mode Vault's TTLs are
  designed to shorten.
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
  — Manage 2.3 ("limiting exposure window") and Govern 1.5
  (credential governance) scope this exercise's TTL and
  rotation-cadence choices.
- [NIST AI 600-1 — Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
  — GAI-specific credential handling for model-weight and
  training-data access paths; the same rotation shape applies.

**Practitioner references**

- [VeriSwarm Trust Center](https://veriswarm.ai/trust) — example of
  a practitioner-run trust surface that publishes rotation cadence
  and audit coverage. Use as an implementation exemplar, not an
  authoritative source.

**Local**

- Module rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-02.
- Identity story this exercise builds on:
  [`../exercise-01/README.md`](../exercise-01/README.md) and
  [`../exercise-01/oidc_auth.py`](../exercise-01/oidc_auth.py).
- Downstream consumers:
  [`../exercise-03/`](../exercise-03/) (cosign key is a Vault secret),
  [`../exercise-04/`](../exercise-04/) (admission gate assumes Vault
  brokering), [`../exercise-05/`](../exercise-05/) (quarterly audit
  reads Vault's audit device for rotation evidence).
- Quick-pointer worked implementation: [`README.md`](./README.md).
- Learning exercise prompt:
  `lessons/mod-009-security-governance/exercises/exercise-02-vault-secret-rotation.md`
  in the `ai-infra-ml-platform-learning` repo.
