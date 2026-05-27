"""Audit-chain verifier (requirement F8).

Walks the audit_log in id order, recomputes each entry's hashes, and
returns the first tampering detected — or "verified" if the whole chain
is consistent. This is the command an auditor runs against the platform
DB after a test run.

The core (`verify_chain`) is pure and dependency-free so it is unit
testable without a database; ``main`` wires it to PostgreSQL.

Run:    python audit/verify.py            # reads $PLATFORM_DB_URL
Test:   python -m py_compile audit/verify.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

GENESIS_HASH = "0" * 64


@dataclass
class Entry:
    id: int
    payload: dict
    payload_hash: str
    prev_hash: str
    entry_hash: str


def canonical_payload_hash(payload: dict) -> str:
    """Hash of the payload, serialized canonically (sorted keys, no
    insignificant whitespace) so the hash is stable across writers."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def entry_hash(payload_hash: str, prev_hash: str) -> str:
    return hashlib.sha256((payload_hash + prev_hash).encode("utf-8")).hexdigest()


@dataclass
class VerifyResult:
    ok: bool
    checked: int
    first_bad_id: Optional[int] = None
    reason: Optional[str] = None

    def __str__(self) -> str:
        if self.ok:
            return f"verified ({self.checked} entries)"
        return f"TAMPERING at id={self.first_bad_id}: {self.reason}"


def verify_chain(entries: Iterable[Entry]) -> VerifyResult:
    prev = GENESIS_HASH
    checked = 0
    for e in entries:
        checked += 1
        # 1. payload still hashes to its stored payload_hash.
        if canonical_payload_hash(e.payload) != e.payload_hash:
            return VerifyResult(False, checked, e.id, "payload does not match payload_hash")
        # 2. the link to the previous entry is intact.
        if e.prev_hash != prev:
            return VerifyResult(False, checked, e.id, "prev_hash breaks the chain")
        # 3. the entry hash binds payload_hash to prev_hash.
        if entry_hash(e.payload_hash, e.prev_hash) != e.entry_hash:
            return VerifyResult(False, checked, e.id, "entry_hash recomputation mismatch")
        prev = e.entry_hash
    return VerifyResult(True, checked)


def _load_from_db(dsn: str) -> list[Entry]:                    # pragma: no cover
    import psycopg  # imported lazily so the pure path needs no driver.

    rows: list[Entry] = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, payload, payload_hash, prev_hash, entry_hash "
            "FROM audit_log ORDER BY id ASC")
        for rid, payload, ph, prev, eh in cur.fetchall():
            payload = payload if isinstance(payload, dict) else json.loads(payload)
            rows.append(Entry(rid, payload, ph, prev, eh))
    return rows


def main() -> int:                                             # pragma: no cover
    dsn = os.environ.get("PLATFORM_DB_URL")
    if not dsn:
        print("PLATFORM_DB_URL not set", file=sys.stderr)
        return 2
    result = verify_chain(_load_from_db(dsn))
    print(result)
    return 0 if result.ok else 1


if __name__ == "__main__":                                     # pragma: no cover
    raise SystemExit(main())
