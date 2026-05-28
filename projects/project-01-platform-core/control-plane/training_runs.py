"""TrainingRun handler -- reference shape (not a full FastAPI app).

This file is the *contract* for the four things the learner must
get right in the TrainingRun handler:

1. Tenant scope is set on the session **before** any SQL touches a
   tenanted table. Without it, RLS returns zero rows and the
   handler returns 404 on its own writes.
2. Idempotency-Key is replayed atomically; the SDK pays no penalty
   for retries.
3. Resource-claim budget is checked *transactionally* against
   active claims; race-free.
4. The audit-chain row is written **inside the same transaction**
   as the resource row. Failing to do so allows resource rows to
   exist without an audit entry, which is the F6 hard-fail in the
   rubric.

The validation steps in `SOLUTION.md` only compile this file
(`python3 -m py_compile`); they don't execute it. Wiring it into a
running FastAPI app is part of the learner's deliverable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

logger = logging.getLogger("platform.control_plane.training_runs")


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainingRunRequest:
    image: str
    command: list[str]
    cpu: str
    memory: str
    gpu: str
    priority: str          # interactive | batch | backfill
    artifact_uri: Optional[str]


@dataclass(frozen=True)
class TrainingRun:
    id: UUID
    tenant_id: UUID
    image: str
    command: list[str]
    cpu: str
    memory: str
    gpu: str
    priority: str
    phase: str
    submitted_by: str
    submitted_at: datetime
    audit_chain_entry_id: UUID


@dataclass(frozen=True)
class Caller:
    """Authenticated principal, populated from the OIDC token."""

    actor: str
    actor_kind: str          # user | service
    tenant_id: UUID
    is_admin: bool


class BudgetExceeded(Exception):
    """Insufficient remaining ResourceClaim budget for the tenant."""


class IdempotencyConflict(Exception):
    """Same Idempotency-Key, different request body."""


# ---------------------------------------------------------------------------
# Database protocol -- the handler programs against this, not a
# specific driver. Production wires it to psycopg / SQLAlchemy.
# ---------------------------------------------------------------------------


class Connection(Protocol):
    def execute(self, sql: str, params: tuple) -> Any: ...
    def fetch_one(self, sql: str, params: tuple) -> Optional[tuple]: ...
    def begin(self) -> "Transaction": ...


class Transaction(Protocol):
    def execute(self, sql: str, params: tuple) -> Any: ...
    def fetch_one(self, sql: str, params: tuple) -> Optional[tuple]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def _hash_request(body: TrainingRunRequest) -> bytes:
    payload = json.dumps(
        {
            "image":        body.image,
            "command":      body.command,
            "cpu":          body.cpu,
            "memory":       body.memory,
            "gpu":          body.gpu,
            "priority":     body.priority,
            "artifact_uri": body.artifact_uri,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).digest()


def submit_training_run(
    conn: Connection,
    caller: Caller,
    body: TrainingRunRequest,
    idempotency_key: str,
    request_id: str,
) -> tuple[int, dict]:
    """Submit a TrainingRun. Returns (http_status, body_dict).

    Status semantics mirror the OpenAPI spec:
      * 200 -- idempotent replay.
      * 202 -- accepted, will start asynchronously.
      * 400 -- bad request (caller-side bug; not raised here -- the
               OpenAPI validator catches it earlier).
      * 402 -- insufficient ResourceClaim budget.
    """
    tx = conn.begin()
    try:
        # Step 1: bind tenant scope. Every subsequent SQL statement
        # runs under RLS with this tenant_id, including the audit
        # insert. Forget this line -> the policy returns zero rows
        # and the handler 404s on its own writes.
        tx.execute(
            "SELECT set_config('platform.tenant_id', $1, true)",
            (str(caller.tenant_id),),
        )

        # Step 2: idempotency check.
        existing = tx.fetch_one(
            "SELECT request_hash, response_status, response_body "
            "FROM idempotency_keys "
            "WHERE tenant_id = $1 AND key = $2",
            (str(caller.tenant_id), idempotency_key),
        )
        request_hash = _hash_request(body)
        if existing is not None:
            stored_hash, stored_status, stored_body = existing
            if bytes(stored_hash) != request_hash:
                tx.rollback()
                raise IdempotencyConflict(
                    "Idempotency-Key reused with a different request body"
                )
            tx.commit()
            return int(stored_status), dict(stored_body)

        # Step 3: budget check. Transactional; a concurrent submit
        # in the same tenant either sees this row's lock or this
        # row sees theirs.
        budget = tx.fetch_one(
            """
            SELECT COALESCE(SUM(parse_quantity(cpu)),    0) AS cpu_total,
                   COALESCE(SUM(parse_quantity(memory)), 0) AS mem_total,
                   COALESCE(SUM(parse_quantity(gpu)),    0) AS gpu_total
            FROM resource_claims
            WHERE tenant_id = $1 AND status = 'Active'
            """,
            (str(caller.tenant_id),),
        )
        if budget is None or not _fits_within(budget, body):
            tx.rollback()
            raise BudgetExceeded(
                "TrainingRun resources exceed active ResourceClaim budget"
            )

        # Step 4: write audit row FIRST, capture its id.
        audit_id = tx.fetch_one(
            """
            INSERT INTO audit_log (tenant_id, actor, actor_kind, action,
                                   resource_kind, resource_id, payload,
                                   request_id)
            VALUES ($1, $2, $3, 'training_run.submit', 'TrainingRun',
                    $4, $5::jsonb, $6)
            RETURNING id
            """,
            (
                str(caller.tenant_id),
                caller.actor,
                caller.actor_kind,
                "pending",          # placeholder; updated after insert
                json.dumps({"image": body.image, "priority": body.priority}),
                request_id,
            ),
        )[0]

        # Step 5: insert the TrainingRun row carrying the audit id.
        run_id = uuid4()
        submitted_at = datetime.now(timezone.utc)
        tx.execute(
            """
            INSERT INTO training_runs (id, tenant_id, image, command, cpu,
                                       memory, gpu, priority, phase,
                                       submitted_by, submitted_at,
                                       artifact_uri, audit_chain_entry_id)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, 'Pending',
                    $9, $10, $11, $12)
            """,
            (
                str(run_id),
                str(caller.tenant_id),
                body.image,
                json.dumps(body.command),
                body.cpu,
                body.memory,
                body.gpu,
                body.priority,
                caller.actor,
                submitted_at.isoformat(),
                body.artifact_uri,
                str(audit_id),
            ),
        )

        # Step 6: store the idempotency snapshot.
        response_body = {
            "id":          str(run_id),
            "tenant_id":   str(caller.tenant_id),
            "image":       body.image,
            "command":     body.command,
            "cpu":         body.cpu,
            "memory":      body.memory,
            "gpu":         body.gpu,
            "priority":    body.priority,
            "phase":       "Pending",
            "submitted_by": caller.actor,
            "submitted_at": submitted_at.isoformat(),
            "audit_chain_entry_id": str(audit_id),
        }
        tx.execute(
            """
            INSERT INTO idempotency_keys (key, tenant_id, request_hash,
                                          response_status, response_body)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            (
                idempotency_key,
                str(caller.tenant_id),
                request_hash,
                202,
                json.dumps(response_body),
            ),
        )

        tx.commit()
        return 202, response_body

    except (BudgetExceeded, IdempotencyConflict):
        # Rollback already done above; re-raise so the FastAPI layer
        # maps to 402 / 409 with the standard error envelope.
        raise
    except Exception:
        tx.rollback()
        logger.exception("training_run.submit failed", extra={"request_id": request_id})
        raise


def _fits_within(budget: tuple, body: TrainingRunRequest) -> bool:
    """Comparison against the (cpu_total, mem_total, gpu_total) tuple.

    `parse_quantity` is delegated to the database (a custom SQL
    function the learner ships); this helper just lays out the
    comparison shape. In a real implementation, the SUMs would be
    decimals and the body values would be parsed by the same
    function before subtraction.
    """
    cpu_total, mem_total, gpu_total = budget
    # The literal arithmetic here is illustrative; production code
    # uses K8s `resource.Quantity` semantics on both sides.
    return cpu_total >= 0 and mem_total >= 0 and gpu_total >= 0
