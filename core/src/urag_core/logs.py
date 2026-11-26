"""Journaux JSON structurés (docs/DEPLOYMENT.md §5).

Une ligne JSON par évènement. Les messages ne contiennent jamais de contenu documentaire, de
question ni de secret : seuls des identifiants techniques, des états et des durées y figurent.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_STANDARD = set(vars(logging.makeLogRecord({})))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "t": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    # Journal d'accès d'uvicorn remplacé par le journal des requêtes, sans paramètres (API).
    logging.getLogger("uvicorn.access").disabled = True
    # Appels internes (Qdrant, Ollama) journalisés par httpx : trop verbeux.
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Configuration passée à uvicorn (chaque processus de l'API applique le même format).
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "urag_core.logs.JsonFormatter"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["stdout"], "level": "INFO"},
    "loggers": {
        "uvicorn": {"handlers": [], "propagate": True},
        "uvicorn.error": {"handlers": [], "propagate": True},
        "uvicorn.access": {"handlers": [], "propagate": False, "level": "WARNING"},
        "httpx": {"level": "WARNING"},
    },
}
