# SOLUTION — Module 09: Security & Governance

> Read after the per-exercise solutions. Cross-exercise rationale.

## What the module is really teaching

Security on an ML platform is **the same security as any
platform** plus three ML-specific concerns:

1. **Model artifacts are code**, and trusted code paths apply.
2. **Training data is sensitive**, and exfiltration paths exist.
3. **Inference outputs are leakage vectors** (membership-
   inference, prompt-injection on LLMs).

The five exercises ladder up from foundational identity through to
the operational audit cadence.

## Exercise-by-exercise rationale

### Ex-01 — OIDC + RBAC

The reference identity model:

- **OIDC** as the only identity source. SSO, no local accounts.
- **Group-based RBAC**: groups come from the OIDC provider,
  permissions attach to groups.
- **Service accounts** for non-human identities, with short-
  lived tokens.
- **No long-lived credentials** anywhere — token rotation is
  enforced at the IdP.

Long-lived credentials are the canonical breach root cause. The
reference solution refuses to ship one.

### Ex-02 — Vault rotation

The reference shape:

- **HashiCorp Vault** as the secret manager.
- Every secret has a TTL.
- Every secret has a rotation procedure documented in code.
- The application uses the Vault Agent sidecar; secrets never
  enter the application's process environment directly.

Vault without rotation is just an expensive password vault.
The rotation procedures are the operational discipline that
makes the platform breach-resilient.

### Ex-03 — SLSA L2 supply-chain

The reference solution achieves SLSA Level 2 by:

- **Versioned source**: every build comes from a tagged commit.
- **Build service**: builds run on a hosted CI, not on developer
  laptops.
- **Provenance**: every artifact has an attached attestation
  (Sigstore / Cosign) signed by the build service.
- **Verification at deploy**: the admission controller refuses
  to schedule an image without a valid attestation.

SLSA is the supply-chain hygiene standard. L2 is achievable; L3
requires hermetic builds (a senior-engineer exercise).

### Ex-04 — Governance gates

These are the **enforcement** mechanism for the policies the
team defines:

- **Admission webhook** (Kyverno / OPA Gatekeeper) blocks deploys
  that violate policy.
- Policies cover: required labels, no privileged pods, no
  hostPath mounts, image must be signed, image must come from
  approved registry.
- Policies are versioned in git; the webhook is also versioned
  in git.

Policy that lives in a Confluence page is policy that nobody
enforces.

### Ex-05 — Quarterly compliance audit

The capstone document. Sections:

- Identity hygiene: rotation cadence, dormant-account purge.
- Secrets hygiene: rotation evidence, leaked-secret incident
  reports.
- Supply chain: unsigned-image attempts, attestation coverage.
- Governance gate: violations attempted, violations blocked.
- Access reviews: who has access, when was it last reviewed.

The reference audit doc is the artifact a regulator reads. A
platform that can't produce it is a platform that's failing the
compliance job.

## Cross-exercise design decisions

- **No long-lived credentials**, ever.
- **Vault for secrets**, secrets never in env vars directly.
- **Sign + verify** every image.
- **Policy lives in code**, enforced by admission.
- **Audit is a quarterly cadence**, not an ad-hoc effort.

## Common mistakes graders see

1. **Local accounts** as a fallback "for emergencies." They are
   the most-used compromise vector.
2. **Vault without rotation**. Static secrets just behind a
   newer wall.
3. **Image signing without admission verification**. Signature
   without enforcement is theater.
4. **Policy in Confluence**. Nobody reads it; nobody enforces it.
5. **Annual audit cadence**. Drift accumulates.

## Related curriculum touchpoints

- `security/mod-005-secrets-management` — the security-track
  deep-dive.
- `security/mod-010-supply-chain-security` — the security-track
  SLSA + attestation exercises.
- `security/mod-009-policy-as-code` — Kyverno / OPA Gatekeeper
  patterns.
- `architect/project-305-security-framework` — enterprise-scale
  security framework.
