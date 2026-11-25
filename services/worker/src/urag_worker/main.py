"""Worker : prend les tâches prêtes, organisation par organisation, et les exécute.

Chaque tâche tourne hors transaction ; seules la prise et la clôture sont
transactionnelles. Une tâche en échec est reprise avec attente croissante ; un
échec n'arrête jamais le worker.
"""

from __future__ import annotations

import logging
import signal
import time
import uuid

from sqlalchemy import text
from urag_connectors_base import AuthenticationError, TransientError
from urag_core.config import Settings, get_settings
from urag_core.embeddings import Encoder, build_encoder
from urag_core.ingestion import IngestionService
from urag_core.jobs import Job, complete, fail, new_worker_name, requeue_stale, take
from urag_core.storage import Database, VectorStore

log = logging.getLogger("urag.worker")


class Worker:
    def __init__(self, db: Database, ingestion: IngestionService, name: str | None = None) -> None:
        self.db = db
        self.ingestion = ingestion
        self.name = name or new_worker_name()
        self._stop = False

    def handle(self, job: Job) -> None:
        payload = job.payload
        if job.kind == "sync_source":
            report = self.ingestion.sync_source(
                job.org_id, uuid.UUID(payload["source_id"]), payload.get("mode", "auto")
            )
            log.info("synchronisation %s : %s", payload["source_id"], report)
        elif job.kind == "ingest_document":
            report = self.ingestion.ingest_document(job.org_id, uuid.UUID(payload["document_id"]))
            log.info("document %s : %s", payload["document_id"], report.status)
        else:
            raise ValueError(f"type de tâche inconnu : {job.kind}")

    def run_once(self) -> int:
        """Traite toutes les tâches prêtes ; renvoie le nombre de tâches traitées."""
        done = 0
        with self.db.anonymous() as conn:
            orgs = conn.execute(text("SELECT * FROM urag_orgs_with_ready_jobs()")).scalars().all()
        for org_id in orgs:
            while not self._stop:
                with self.db.org(org_id) as conn:
                    job = take(conn, self.name)
                if job is None:
                    break
                try:
                    self.handle(job)
                except AuthenticationError as e:
                    with self.db.org(org_id) as conn:
                        fail(conn, job, f"authentification refusée : {e}", retryable=False)
                except TransientError as e:
                    with self.db.org(org_id) as conn:
                        fail(conn, job, str(e))
                except Exception as e:  # noqa: BLE001 - une tâche ne doit jamais arrêter le worker
                    log.exception("tâche %s en échec", job.id)
                    with self.db.org(org_id) as conn:
                        fail(conn, job, f"{type(e).__name__}: {e}")
                else:
                    with self.db.org(org_id) as conn:
                        complete(conn, job.id)
                done += 1
        return done

    def run_until_idle(self, max_rounds: int = 100) -> int:
        total = 0
        for _ in range(max_rounds):
            n = self.run_once()
            total += n
            if n == 0:
                break
        return total

    def run_forever(self, idle_sleep: float = 2.0) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_stop", True))
        last_stale_check = 0.0
        while not self._stop:
            if time.monotonic() - last_stale_check > 60:
                self._requeue_stale()
                last_stale_check = time.monotonic()
            if self.run_once() == 0:
                time.sleep(idle_sleep)

    def _requeue_stale(self) -> None:
        with self.db.anonymous() as conn:
            orgs = conn.execute(text("SELECT * FROM urag_orgs_with_ready_jobs()")).scalars().all()
        for org_id in orgs:
            with self.db.org(org_id) as conn:
                requeue_stale(conn)


def build(settings: Settings, encoder: Encoder | None = None) -> Worker:
    db = Database(settings.database_url, pool_size=4)
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    encoder = encoder or build_encoder(settings)
    from urag_core.ocr import build_engine

    ingestion = IngestionService(
        db,
        VectorStore(settings.qdrant_url, api_key),
        encoder,
        settings.tmp_dir,
        ocr=build_engine(settings.ocr_engine),
        tika_url=settings.tika_url,
    )
    return Worker(db, ingestion)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}')
    build(get_settings()).run_forever()
