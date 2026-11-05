# SOLUTION — Exercise 03: SLSA L2 Supply Chain

> Per-exercise solution. The module-level rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md) §Ex-03; this file factors that
> section into a self-contained reference for graders and learners.
> Companion artifact in this directory: [`README.md`](./README.md)
> (quick-pointer to the engineer-tier worked implementation —
> buildx + syft SBOM + grype scan + cosign keyless sign +
> SBOM-attestation + Kyverno admission gate). See the signing key
> lifecycle in [`../exercise-02/`](../exercise-02/) and the
> admission-time verification that gates deploys in
> [`../exercise-04/`](../exercise-04/).

## 1. Solution overview

The deliverable is **a build pipeline that produces an attested
artifact — a container image with a cryptographic provenance
statement — and a cluster that refuses to run images missing a
valid attestation**. This is SLSA Build Level 2, no more and no
less: hosted build service, signed provenance, verification at
deploy. SLSA L3 (hermetic, isolated builds) is explicitly deferred
to the security track ([`../SOLUTION.md`](../SOLUTION.md) §Ex-03).

The reference solution commits to five design decisions that drive
every artifact in this exercise and every downstream consumer:

1. **Build runs on a hosted build service** (GitHub Actions in the
   reference), not on a developer laptop. The runner identity is
   what Sigstore issues the signing certificate to; a laptop
   identity is not trustworthy enough
   ([SLSA v1.0 — Build L2 requirements](https://slsa.dev/spec/v1.0/levels#build-l2)).
2. **Every build produces four artifacts, not one:** the container
   image, an SBOM, a vulnerability scan report, and a signed
   provenance attestation. Shipping the image alone is the "we
   built it" claim; the other three are the evidence.
3. **Signing is keyless (OIDC → Fulcio).** The identity on the
   certificate is the workload identity of the CI job that produced
   the build; no long-lived signing key to rotate, lose, or leak
   ([Sigstore — keyless signing](https://docs.sigstore.dev/signing/overview/)).
   This is the application of [`../SOLUTION.md`](../SOLUTION.md)
   §Cross-exercise design decisions ("no long-lived credentials")
   to the signing pipeline.
4. **Attestations are stored in the registry alongside the image**
   (OCI 1.1 referrers API or cosign's tag-based convention) so the
   admission gate only has to talk to the registry
   ([cosign — attestation storage](https://docs.sigstore.dev/signing/other_types/#in-toto-attestations)).
5. **Verification happens at admission time, not at promotion
   time.** A Kyverno or Gatekeeper policy evaluates the attestation
   on every Pod create. An image without a valid attestation —
   signed by the expected issuer+subject, with provenance matching
   the expected source repo — is rejected. Signing without
   verification is theater
   ([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes #3).

A pipeline that signs but does not verify, or verifies but trusts
any signer, is not solving the exercise: the gate at admission is
the whole point.

## 2. Worked answer or implementation

The worked implementation targets a Python-based model-serving
image, but the pipeline shape is identical for any image. The
engineer-tier worked implementation
([`README.md`](./README.md)) extends this with buildx multi-arch
builds and a Kyverno policy variant.

### 2.1 Build + attest pipeline (GitHub Actions)

Why GitHub Actions: it provides OIDC tokens to third parties
(Sigstore's Fulcio) via the `id-token: write` permission, which
makes keyless signing possible without any long-lived credential
([GitHub — OIDC federation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)).

```yaml
name: build-sign-attest
on:
  push: { tags: ['v*.*.*'] }

permissions:
  contents: read
  packages: write        # push to GHCR
  id-token: write        # mint OIDC token for Sigstore / Fulcio

jobs:
  build:
    runs-on: ubuntu-24.04
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
        with: { persist-credentials: false }

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}
          # Build args pinned to a commit; no :latest base images.
          provenance: false   # we generate SLSA provenance ourselves below

      # SBOM: syft produces an SPDX JSON document the attestation
      # will carry as its in-toto subject.
      - name: syft SBOM
        uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/${{ github.repository }}@${{ steps.push.outputs.digest }}
          format: spdx-json
          output-file: sbom.spdx.json

      # Scan: fail the pipeline on high/critical vulnerabilities.
      # The SBOM is the scan input so the scan evaluates the same
      # bill of materials the attestation records.
      - name: grype scan
        uses: anchore/scan-action@v4
        with:
          sbom: sbom.spdx.json
          fail-build: true
          severity-cutoff: high

      # Install cosign; sign the image by digest (never by tag).
      - uses: sigstore/cosign-installer@v3

      - name: cosign sign (keyless)
        env: { COSIGN_EXPERIMENTAL: "1" }
        run: |
          cosign sign --yes \
            ghcr.io/${{ github.repository }}@${{ steps.push.outputs.digest }}

      # Attach the SBOM as an in-toto SPDX attestation signed by the
      # same keyless identity.
      - name: cosign attest SBOM
        env: { COSIGN_EXPERIMENTAL: "1" }
        run: |
          cosign attest --yes \
            --predicate sbom.spdx.json \
            --type spdxjson \
            ghcr.io/${{ github.repository }}@${{ steps.push.outputs.digest }}

  # SLSA provenance via the official reusable workflow. The
  # generator runs in its own job with an isolated OIDC token so
  # the provenance cannot be forged by a compromised build step.
  provenance:
    needs: [build]
    permissions: { id-token: write, contents: read, packages: write }
    uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@v2.0.0
    with:
      image: ghcr.io/${{ github.repository }}
      digest: ${{ needs.build.outputs.digest }}
      registry-username: ${{ github.actor }}
    secrets:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
```

Field-by-field rationale:

- **`permissions:` scoped.** Only the three the job needs; no `write-all`.
  OIDC token minting (`id-token: write`) is the critical one — this
  is what lets Fulcio issue the signing certificate without a
  secret key.
- **`persist-credentials: false` on checkout.** Keeps the
  short-lived GitHub token out of `.git/config` where a later step
  could read it. Defense-in-depth for the signing identity.
- **Sign by digest, not by tag.** Tags are mutable; a digest is the
  content address. Signing a tag signs "whatever this points at
  right now," which is not a durable attestation.
- **SBOM is the scan input and the attestation subject.** One
  bill of materials across scan + attest; the scan and the
  attestation evaluate the same reality.
- **Provenance job isolated.** The SLSA provenance generator
  runs in its own reusable workflow with its own OIDC token. A
  compromised build step can push a bad image but cannot forge
  provenance for it — that is the SLSA L2 integrity property
  ([SLSA v1.0 — build integrity](https://slsa.dev/spec/v1.0/requirements#build-l2)).

### 2.2 Admission-time verification (Kyverno)

Signing an image that no cluster verifies is signature theater
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes #3). The
Kyverno `ClusterPolicy` below rejects any Pod whose image is
either unsigned or signed by an identity the platform does not
expect
([Kyverno — image verification](https://kyverno.io/docs/writing-policies/verify-images/)).

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-attested-images
spec:
  validationFailureAction: Enforce
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-cosign-signature
      match:
        any:
          - resources: { kinds: [Pod] }
      exclude:
        any:
          - resources: { namespaces: [kube-system, kyverno] }
      verifyImages:
        - imageReferences:
            - "ghcr.io/ai-infra-curriculum/*"
          mutateDigest: true   # pin the resolved digest into the PodSpec
          verifyDigest: true
          required: true
          attestors:
            - entries:
                - keyless:
                    subject: "https://github.com/ai-infra-curriculum/*/.github/workflows/*@refs/tags/v*"
                    issuer:  "https://token.actions.githubusercontent.com"
                    rekor:
                      url: "https://rekor.sigstore.dev"
          attestations:
            - type: "https://slsa.dev/provenance/v1"
              attestors:
                - entries:
                    - keyless:
                        subject: "https://github.com/slsa-framework/slsa-github-generator/*"
                        issuer:  "https://token.actions.githubusercontent.com"
              conditions:
                - all:
                    - key: "{{ buildDefinition.buildType }}"
                      operator: Equals
                      value: "https://slsa-framework.github.io/container-generator"
                    - key: "{{ buildDefinition.externalParameters.source }}"
                      operator: Equals
                      value: "git+https://github.com/ai-infra-curriculum/{{ images.containers.server.registry }}"
```

Why each field is where it is:

- **`validationFailureAction: Enforce`.** The gate rejects; it does
  not warn. A warn-only gate is a policy nobody enforces
  ([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes #4).
- **`mutateDigest: true` and `verifyDigest: true`.** Pod specs
  often carry a tag reference; Kyverno resolves it to the digest
  that actually passed verification and rewrites the spec. This
  closes the TOCTOU window where the tag could repoint after
  verification.
- **`subject` is a pattern, not a wildcard.** Only tagged
  workflows from the platform's GitHub org, cut from a `v*` tag,
  can produce an acceptable signature. A fork cannot sign and get
  its images admitted. This is the "image must come from approved
  registry + approved builder" rule from
  ([`../SOLUTION.md`](../SOLUTION.md) §Ex-04).
- **Provenance checked against the SLSA provenance generator's own
  identity**, not the build job's. This separates "the build
  happened" from "the build was a hosted build." The build job can
  be compromised; the provenance generator is the independent
  attester.
- **`conditions:` on the provenance payload.** Verifies the
  `buildType` is the expected generator and `source` is the
  expected repo. An attacker who compromises a build job in
  *another* repo and produces valid signatures cannot satisfy
  these predicates.

### 2.3 Decision rationale

- **Why SLSA L2 and not L3?** L3 requires isolated and hermetic
  builds — the build runs in an environment that cannot reach the
  Internet during build. GitHub Actions' hosted runners don't meet
  L3's isolation guarantees out of the box
  ([SLSA v1.0 — Build L3 requirements](https://slsa.dev/spec/v1.0/levels#build-l3)).
  L2 is the achievable target for a platform team; L3 is on the
  security track.
- **Why keyless over KMS?** Keyless signing rotates the signing
  identity on every job (OIDC token has a lifetime of minutes).
  KMS keys must be rotated out of band; a leaked KMS key signs
  forever until someone notices. Keyless aligns with the module's
  "no long-lived credentials" invariant.
- **Why SPDX for the SBOM over CycloneDX?** Either works at the
  format level; the reference picks SPDX JSON because the ISO
  standard is SPDX
  ([ISO/IEC 5962:2021](https://www.iso.org/standard/81870.html))
  and the admission policy's provenance predicates are easier to
  write against the SPDX schema. A submission using CycloneDX
  passes as long as the attestation type is declared correctly.
- **Why `rekor` in the verification?** Rekor is Sigstore's
  transparency log. Including it binds the signature to a public,
  append-only record; a signer who revokes or alters an entry
  leaves a tamper-evident trail. Policies that skip Rekor accept
  signatures that cannot be audited after the fact.
- **Why verify provenance and signature separately?** The
  signature proves "this image was signed by identity X." The
  provenance proves "identity X performed a build matching
  this description." A policy that checks only signature accepts
  valid signatures over tampered builds; a policy that checks only
  provenance accepts valid provenance over unsigned images. Both
  are necessary.

## 3. Validation steps

Each check names the exact command a grader runs against a local
`k3s` cluster with Kyverno installed and `cosign`, `syft`, `grype`
on PATH.

1. **Pipeline runs end-to-end on a tagged push.**
   `git tag v0.1.0 && git push --tags` triggers the workflow; all
   four jobs (build, attest, provenance, publish) complete green.
2. **Image is signed by the expected keyless identity.**
   `cosign verify --certificate-identity-regexp 'https://github.com/ai-infra-curriculum/.*@refs/tags/v.*' --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' ghcr.io/ai-infra-curriculum/model-serving@sha256:<digest>`
   succeeds. The same command run against an unsigned image fails
   with a clear error.
3. **SBOM attestation resolves and parses.**
   `cosign verify-attestation --type spdxjson --certificate-identity-regexp '…' ghcr.io/…@sha256:<digest> | jq .payload | base64 -d | jq .predicate.name`
   returns the image name recorded in the SBOM. An image without
   an SBOM attestation returns "no matching attestations."
4. **SLSA provenance attestation resolves and parses.**
   `cosign verify-attestation --type slsaprovenance --certificate-identity-regexp '.*slsa-github-generator.*' …@sha256:<digest> | jq '.payload | fromjson | .predicate.buildDefinition.buildType'`
   returns `https://slsa-framework.github.io/container-generator`.
5. **Vulnerability gate works.**
   Introduce a known-CVE package into `requirements.txt`, push the
   tag; the `grype scan` step fails and the pipeline stops before
   signing. The registry never sees the vulnerable image.
6. **Admission policy admits a valid image.**
   `kubectl apply -f pod-using-attested-image.yaml` succeeds. The
   resulting Pod's `image:` field is the digest Kyverno resolved
   to (`kubectl get pod -o jsonpath='{.spec.containers[0].image}'`
   returns `…@sha256:<digest>`).
7. **Admission policy rejects an unsigned image.**
   `kubectl apply -f pod-unsigned.yaml` fails with
   `admission webhook ... denied the request: image is not signed`.
   The Pod is not created; `kubectl get pod pod-unsigned` returns
   NotFound.
8. **Admission policy rejects a signed-by-stranger image.**
   Build an image on a fork, sign with the fork's OIDC identity,
   push, and try to deploy. Kyverno rejects:
   `subject does not match` is in the denial message. This is the
   check that distinguishes "any signature" from "the right
   signer."
9. **Admission policy rejects an image missing provenance.**
   Sign an image with cosign but skip the `cosign attest`
   provenance step. `kubectl apply` fails with a message naming
   the missing attestation type.
10. **Transparency log is consulted.**
    `rekor-cli search --sha <image-digest>` returns at least one
    entry. An attacker who produces a signature off-log cannot
    satisfy §2.2's `rekor:` clause.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
|---|---|---|
| Versioned source | Builds trigger only on tagged refs; tag pattern enforced. | `on: push` to any branch triggers signed builds; `latest` tag signed. |
| Hosted build | Build runs on the CI service; developer laptops cannot produce a signed artifact. | Any `cosign sign` in the repo can be run locally and pushed. |
| SBOM | SBOM produced per image and attached as an attestation. | SBOM generated but not attached, or attached unsigned. |
| Vulnerability scan | Scan runs against the SBOM and fails the build on high/critical CVEs. | Scan runs but doesn't fail the pipeline; scan runs against the image not the SBOM. |
| Keyless signing | `cosign sign --yes` with no key material; identity is the CI job. | Long-lived cosign key stored in CI secrets. |
| Provenance | SLSA provenance attestation produced in an isolated job; `buildType` and `source` present. | No provenance attestation; provenance produced in the same job as the build. |
| Signing identity | Signature's cert identity is pinned to the repo + workflow + tag pattern. | Signer wildcard accepts any GitHub OIDC identity. |
| Admission gate | Kyverno / Gatekeeper policy in `Enforce` mode blocks unsigned, mis-signed, and missing-provenance images. | Policy in `Audit`/`Warn` mode; policy skipped for some namespace that hosts workloads. |
| Transparency log | Rekor consulted on verify; signatures off-log rejected. | Rekor skipped; "offline" verification only. |
| Digest-pinning | Admission mutates the PodSpec to reference the verified digest. | Pod runs a tag; the image that was verified may not be the image that runs. |
| Rollback | Downgrading to a previous signed+attested image works; downgrading to an unsigned image is rejected. | Only forward deploys verified. |

A passing submission scores Pass on every row. The two most common
near-misses are (a) signing without verification at admission, and
(b) a signer-pattern wildcard that accepts any OIDC identity, not
just the platform's.

## 5. Common mistakes

Inherited from the module-level list
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see,
item 3) and narrowed to this exercise:

1. **Sign-but-don't-verify.** The pipeline produces signatures;
   the cluster accepts anything. This is the single most common
   failure mode. The gate at admission is what makes signing
   meaningful.
2. **Signer wildcard.** A policy that accepts `issuer:
   https://token.actions.githubusercontent.com` with no `subject`
   pattern admits any GitHub user's images. Pin the subject.
3. **Signing tags, not digests.** `cosign sign ghcr.io/x/y:latest`
   signs whatever the tag points at *at sign time*. The next tag
   push repoints the content without invalidating the signature.
   Sign by digest.
4. **SBOM generated but not attested.** An SBOM in CI artifacts is
   not an SBOM an admission gate can consult. The attestation —
   signed by the same identity, stored in the registry, readable
   by cosign — is what counts.
5. **Vulnerability scan that doesn't fail the build.** A pipeline
   that scans and ships anyway produces a scan report, not a
   security control. The pipeline must exit non-zero on
   high/critical findings.
6. **Long-lived KMS key for signing.** Converts the "no long-lived
   credentials" story into a "the KMS key is the long-lived
   credential" story. Use keyless.
7. **Admission gate scoped only to a single namespace.** Workloads
   migrate between namespaces. A policy that applies only to
   `prod/` leaves a loophole whenever a workload lands in
   `staging/` or an experimentation namespace.
8. **Provenance generated in the same job as the build.** A
   compromised build step can forge both the artifact and the
   provenance in a single job. The SLSA L2 integrity property
   requires an isolated attester.
9. **Rekor skipped for "performance."** Verification without the
   transparency log admits signatures that cannot be audited. The
   latency cost is small; the audit cost is large.

## 6. References

**Official sources**

- [SLSA v1.0 — Levels](https://slsa.dev/spec/v1.0/levels).
  Authoritative definition of Build Levels 1–3 and the
  requirements this exercise meets at L2.
- [SLSA v1.0 — Requirements](https://slsa.dev/spec/v1.0/requirements).
  Field-level reference for the provenance attestation the pipeline
  emits.
- [Sigstore — Keyless signing overview](https://docs.sigstore.dev/signing/overview/).
  Authoritative for the OIDC → Fulcio → cosign flow in §2.1.
- [Sigstore — In-toto attestations](https://docs.sigstore.dev/signing/other_types/).
  Authoritative for `cosign attest` and the predicate types
  referenced in §2.2.
- [slsa-framework/slsa-github-generator](https://github.com/slsa-framework/slsa-github-generator)
  — official reusable workflow for isolated provenance generation.
- [Kyverno — Image verification](https://kyverno.io/docs/writing-policies/verify-images/).
  Authoritative for `verifyImages`, `attestors`, and the Rekor
  binding in §2.2.
- [OCI Image Specification 1.1 — Referrers API](https://github.com/opencontainers/image-spec/blob/main/manifest.md).
  Authoritative for the attestation-storage pattern.
- [GitHub Actions — OpenID Connect for Sigstore](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect).
  Authoritative for `id-token: write` and the identity the
  signing certificate carries.
- [OWASP Machine Learning Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/)
  — ML06 (AI supply chain attack) is the primary threat this
  exercise mitigates; signed+attested artifacts bound the "any
  image is trusted" blast radius.
- [MITRE ATLAS](https://atlas.mitre.org/) — "Publish Poisoned
  Models" / "Supply Chain Compromise" techniques map onto the
  signed-image + verified-provenance control.
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
  — Measure 2.7 (supply-chain assurance) and Manage 2.4
  (component provenance) scope this exercise's attestation
  requirements.
- [NIST AI 600-1 — Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
  — GAI-specific supply-chain considerations (model weights,
  checkpoints) extend the container-image provenance pattern to
  model artifacts.

**Practitioner references**

- [VeriSwarm Trust Center](https://veriswarm.ai/trust) — example of
  a practitioner-run trust surface that publishes the attestation
  shapes their platform emits. Use as an implementation exemplar,
  not an authoritative source.

**Local**

- Module rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-03.
- Signing-identity lifecycle (keyless OIDC trust, or KMS as an
  alternative): [`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md).
- Admission-time verification detail sits inside the governance
  gates exercise: [`../exercise-04/SOLUTION.md`](../exercise-04/SOLUTION.md).
- Model-registry integration (the artifact that gets signed is
  both the image *and* the Registry entry that references its
  digest): [`../../mod-006-model-management/exercise-01/SOLUTION.md`](../../mod-006-model-management/exercise-01/SOLUTION.md).
- Quick-pointer worked implementation: [`README.md`](./README.md).
- Learning exercise prompt:
  `lessons/mod-009-security-governance/exercises/exercise-03-supply-chain-attestation.md`
  in the `ai-infra-ml-platform-learning` repo.
