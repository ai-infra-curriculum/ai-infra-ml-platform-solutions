"""Cosign keyless signature verification -- reference solution for F2.

Validates with:
  python3 -m py_compile signing/verify.py

The registry verifies signatures at **two** points (F2):

  1. Promotion gate `signature` -- before a version moves to
     Production, the gate evaluates `signature_valid` from this
     module.
  2. Deployment time -- the deploy handler calls this module *again*
     just before writing the `deployments` row. Verifying only at
     promotion lets an attacker who can write to the artifact bucket
     swap the bytes between promotion and deployment (see Sigstore
     blog on artifact-pin attacks); double-verification closes that.

This file is the **contract**, not the wiring. The learner picks one
of the official Cosign Python bindings (`sigstore-python` for
keyless, or shells out to the `cosign` CLI) and fills in
`_verify_with_cosign`. The signature of `verify_signature` and the
shape of `VerificationResult` are graded; the body is up to the
learner.

References:
  - Sigstore Cosign:        https://docs.sigstore.dev/cosign/
  - sigstore-python README: https://github.com/sigstore/sigstore-python
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    detail: str
    signing_identity: str | None = None
    issuer: str | None = None


@dataclass(frozen=True)
class ExpectedIdentity:
    """The OIDC identity that *should* have signed this artifact.

    For the registry, this is the training-pipeline's workload
    identity. Mismatch is a hard fail (someone else signed it, even
    if Sigstore says the signature is technically valid).
    """
    issuer: str
    subject_pattern: str  # regex, e.g. r"^https://github\\.com/<org>/training/\\.github/workflows/release\\.yml@refs/tags/v.*$"


def verify_signature(
    *,
    artifact_uri: str,
    artifact_digest: str,
    signature_uri: str,
    expected_identity: ExpectedIdentity,
    cosign_verify: Any | None = None,
) -> VerificationResult:
    """Verify the Cosign signature against `expected_identity`.

    Steps (per Sigstore docs):
      1. Fail fast on a malformed digest.
      2. Resolve the artifact and its signature blob (object storage).
      3. Call `cosign verify` (or sigstore-python equivalent) with the
         Sigstore root + Rekor transparency log; this confirms the
         signature was produced by *some* OIDC identity through Fulcio.
      4. Reject if the signing identity does not match
         `expected_identity` -- this is the "no random signer" check.

    `cosign_verify` is injected to make this testable without network.
    Production callers leave it None; the function uses the default
    Sigstore binding configured at process start.
    """
    if not _DIGEST_RE.match(artifact_digest):
        return VerificationResult(
            valid=False,
            detail=f"artifact_digest not in sha256:<hex64> form: {artifact_digest}",
        )

    backend = cosign_verify or _verify_with_cosign
    raw = backend(
        artifact_uri=artifact_uri,
        artifact_digest=artifact_digest,
        signature_uri=signature_uri,
    )
    if not raw.get("valid"):
        return VerificationResult(
            valid=False,
            detail=f"cosign rejected signature: {raw.get('detail', '<no detail>')}",
        )

    issuer = raw.get("issuer")
    subject = raw.get("subject")
    if issuer != expected_identity.issuer:
        return VerificationResult(
            valid=False,
            detail=(
                f"OIDC issuer mismatch: signed by {issuer!r}, "
                f"expected {expected_identity.issuer!r}"
            ),
            signing_identity=subject,
            issuer=issuer,
        )
    if not subject or not re.match(expected_identity.subject_pattern, subject):
        return VerificationResult(
            valid=False,
            detail=(
                f"OIDC subject mismatch: signed by {subject!r}, "
                f"expected pattern {expected_identity.subject_pattern!r}"
            ),
            signing_identity=subject,
            issuer=issuer,
        )

    return VerificationResult(
        valid=True,
        detail=f"signed by {subject} via {issuer}",
        signing_identity=subject,
        issuer=issuer,
    )


def _verify_with_cosign(
    *,
    artifact_uri: str,
    artifact_digest: str,
    signature_uri: str,
) -> dict[str, Any]:
    """Default backend stub.

    Learner replaces this with a real Cosign keyless verify call:

        # Shelling out to the `cosign` CLI binary:
        subprocess.run([
            "cosign", "verify-blob",
            "--signature", signature_uri,
            "--certificate-identity-regexp", expected_identity.subject_pattern,
            "--certificate-oidc-issuer", expected_identity.issuer,
            artifact_uri,
        ], check=True, capture_output=True, text=True)

        # OR using sigstore-python:
        from sigstore.verify import Verifier, VerificationMaterials, policy
        verifier = Verifier.production()
        verifier.verify(materials=..., policy=policy.Identity(
            identity=expected_identity.subject_pattern,
            issuer=expected_identity.issuer,
        ))

    The dict shape this function returns is the contract evaluator
    rows above grade against.
    """
    raise NotImplementedError(
        "Replace _verify_with_cosign with a real Cosign keyless verify "
        "call (sigstore-python or `cosign verify-blob`)."
    )
