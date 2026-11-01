"""Logging that carries the request id from the surrounding middleware."""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        return True


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    if getattr(root, "_grove_configured", False):
        root.setLevel(level.upper())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(RequestIdFilter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    root._grove_configured = True  # type: ignore[attr-defined]

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
