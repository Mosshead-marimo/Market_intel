from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

SENSITIVE_KEYS = {"authorization", "token", "api_key", "password", "secret"}


def redact_sensitive(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    del logger, method_name
    for key in tuple(event_dict):
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
            event_dict[key] = "[REDACTED]"
    return event_dict


def add_context(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    del logger, method_name
    if request_id := request_id_var.get():
        event_dict["request_id"] = request_id
    if run_id := run_id_var.get():
        event_dict["run_id"] = run_id
    return event_dict


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_context,
            redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )
