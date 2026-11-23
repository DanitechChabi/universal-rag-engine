"""File de tâches PostgreSQL (ADR-0003) : SKIP LOCKED, priorités, reprises, déduplication."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError


@dataclass(frozen=True)
class Job:
    id: int
    org_id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def enqueue(
    conn: Connection,
    org_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
    dedup_key: str | None = None,
    priority: int = 100,
    max_attempts: int = 5,
) -> int | None:
    """Ajoute une tâche. Renvoie None si une tâche active a déjà la même clé de déduplication."""
    try:
        with conn.begin_nested():
            return conn.execute(
                text("""
                INSERT INTO jobs (org_id, kind, payload, dedup_key, priority, max_attempts)
                VALUES (:o, :k, CAST(:p AS jsonb), :d, :pr, :m) RETURNING id"""),
                {"o": org_id, "k": kind, "p": json.dumps(payload), "d": dedup_key, "pr": priority, "m": max_attempts},
            ).scalar_one()
    except IntegrityError:
        return None


def take(conn: Connection, worker: str, kinds: tuple[str, ...] | None = None) -> Job | None:
    """Prend la prochaine tâche prête de l'organisation courante, sans bloquer les autres workers."""
    row = conn.execute(
        text("""
        WITH next AS (
            SELECT id FROM jobs
            WHERE status = 'queued' AND run_after <= now()
              AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
            ORDER BY priority, run_after, id
            FOR UPDATE SKIP LOCKED LIMIT 1)
        UPDATE jobs SET status = 'running', locked_by = :w, locked_at = now(), heartbeat_at = now(),
                        attempts = attempts + 1
        FROM next WHERE jobs.id = next.id
        RETURNING jobs.id, jobs.org_id, jobs.kind, jobs.payload, jobs.attempts, jobs.max_attempts"""),
        {"w": worker, "kinds": list(kinds) if kinds else None},
    ).first()
    return Job(*row) if row else None


def complete(conn: Connection, job_id: int) -> None:
    conn.execute(
        text(
            "UPDATE jobs SET status = 'succeeded', finished_at = now(), progress = 1, last_error = NULL WHERE id = :i"
        ),
        {"i": job_id},
    )


def fail(conn: Connection, job: Job, error: str, retryable: bool = True) -> None:
    """Échec : nouvelle tentative avec attente croissante, ou échec définitif."""
    final = not retryable or job.attempts >= job.max_attempts
    delay = min(3600, 15 * 2 ** max(0, job.attempts - 1))
    conn.execute(
        text("""
        UPDATE jobs SET status = CAST(:s AS job_status), last_error = left(:e, 2000), locked_by = NULL,
               run_after = now() + make_interval(secs => :d),
               finished_at = CASE WHEN :final THEN now() END
        WHERE id = :i"""),
        {"s": "failed" if final else "queued", "e": error, "d": delay, "final": final, "i": job.id},
    )


def requeue_stale(conn: Connection, stale_after_seconds: int = 600) -> int:
    """Remet en file les tâches dont le worker ne donne plus signe de vie (reprise après interruption)."""
    return conn.execute(
        text("""
        UPDATE jobs SET status = 'queued', locked_by = NULL
        WHERE status = 'running' AND heartbeat_at < now() - make_interval(secs => :s)"""),
        {"s": stale_after_seconds},
    ).rowcount


def new_worker_name() -> str:
    return f"worker-{uuid.uuid4().hex[:8]}"
