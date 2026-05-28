"""Reference verifier for the platform audit chain.

This is the Python-side mirror of `verify_audit_chain` in
`audit/schema.sql`. It exists so an auditor with read-only access
to the database -- and no permission to install custom PL/pgSQL
functions -- can still independently verify the chain.

Two callers:

* The platform CI runs it nightly across `[max_seq_yesterday,
  max_seq_today]`. A non-empty result pages the on-call.
* Auditors run it ad-hoc against a Point-In-Time snapshot before
  signing off a quarterly compliance review.

The canonical-payload construction MUST match `audit_chain_link()`
in `schema.sql` byte-for-byte. If either side drifts, every chain
breaks at the next call -- which is the intended fail-loud
behavior, but during development the two definitions are kept in
sync by hand.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Protocol, Sequence


GENESIS_HASH = b"\x00" * 32


@dataclass(frozen=True)
class AuditRow:
    seq: int
    tenant_id: str
    actor: str
    actor_kind: str
    action: str
    resource_kind: str
    resource_id: str
    payload: dict
    request_id: str
    prev_hash: bytes
    entry_hash: bytes


@dataclass(frozen=True)
class ChainBreak:
    broken_seq: int
    expected_hash: Optional[bytes]
    actual_hash: Optional[bytes]
    note: str


class AuditRowSource(Protocol):
    """Read-only iterator over the audit_log rows in seq order.

    Implementations: psycopg cursor wrapper, SQLAlchemy session,
    a CSV export, a Point-In-Time recovery shadow.
    """

    def rows(self, start_seq: int, end_seq: int) -> Iterable[AuditRow]: ...

    def predecessor_hash(self, start_seq: int) -> Optional[bytes]: ...


def _canonical_blob(row: AuditRow) -> bytes:
    """Produce the exact byte string the SQL trigger hashes.

    The SQL trigger casts `jsonb_build_object(...)` to text; the
    JSONB text serialization sorts keys alphabetically at every
    level and inserts `", "` between items and `": "` between key
    and value. To match byte-for-byte:

      * `sort_keys=True` -- alphabetical at every nesting depth.
      * `separators=(", ", ": ")` -- exactly what JSONB emits.
      * `ensure_ascii=False` -- JSONB does not escape non-ASCII.

    If either side drifts, every chain breaks at the next
    verification, which is the intended fail-loud behavior.
    """
    obj = {
        "action": row.action,
        "actor": row.actor,
        "actor_kind": row.actor_kind,
        "payload": row.payload,
        "prev_hash": row.prev_hash.hex(),
        "request_id": row.request_id,
        "resource_id": row.resource_id,
        "resource_kind": row.resource_kind,
        "tenant_id": row.tenant_id,
    }
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(", ", ": "),
        ensure_ascii=False,
    ).encode("utf-8")


def verify_audit_chain(
    source: AuditRowSource,
    start_seq: int,
    end_seq: int,
) -> Iterator[ChainBreak]:
    """Verify the chain over [start_seq, end_seq].

    Yields one `ChainBreak` per detected break and stops at the
    first one. An empty iterator means the chain is intact.
    """
    if start_seq > end_seq:
        raise ValueError(f"start_seq ({start_seq}) > end_seq ({end_seq})")

    prior = source.predecessor_hash(start_seq)
    if prior is None:
        yield ChainBreak(
            broken_seq=start_seq,
            expected_hash=None,
            actual_hash=None,
            note="no predecessor row; cannot anchor verification",
        )
        return

    for row in source.rows(start_seq, end_seq):
        if row.prev_hash != prior:
            yield ChainBreak(
                broken_seq=row.seq,
                expected_hash=prior,
                actual_hash=row.prev_hash,
                note="prev_hash does not match prior entry_hash",
            )
            return

        expected = hashlib.sha256(_canonical_blob(row)).digest()
        if expected != row.entry_hash:
            yield ChainBreak(
                broken_seq=row.seq,
                expected_hash=expected,
                actual_hash=row.entry_hash,
                note="entry_hash does not match recomputed hash",
            )
            return

        prior = row.entry_hash


def verify_chain_clean(
    source: AuditRowSource,
    start_seq: int,
    end_seq: int,
) -> bool:
    """Convenience boolean wrapper for CI checks."""
    return next(verify_audit_chain(source, start_seq, end_seq), None) is None


# ---------------------------------------------------------------------------
# In-memory source used by the unit tests and by the rubric's
# acceptance demo. Production callers wire `AuditRowSource` to
# their database driver of choice.
# ---------------------------------------------------------------------------


class InMemorySource:
    """Materialized list of rows; predecessor lookup by seq."""

    def __init__(self, rows: Sequence[AuditRow]) -> None:
        self._by_seq = {row.seq: row for row in rows}

    def rows(self, start_seq: int, end_seq: int) -> Iterable[AuditRow]:
        for seq in range(start_seq, end_seq + 1):
            row = self._by_seq.get(seq)
            if row is not None:
                yield row

    def predecessor_hash(self, start_seq: int) -> Optional[bytes]:
        if start_seq <= 1:
            return GENESIS_HASH
        prev = self._by_seq.get(start_seq - 1)
        return prev.entry_hash if prev is not None else None
