# SPDX-License-Identifier: Apache-2.0
"""structlog wiring — JSON Lines for files, key=value for stderr."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog


def configure(
    *,
    level: str = "INFO",
    log_dir: Path | None = None,
    component: str = "akvc",
) -> structlog.stdlib.BoundLogger:
    """Configure structlog + stdlib logging for one process."""

    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = []

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    handlers.append(stderr_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / f"{component}.log", encoding="utf-8"
        )
        handlers.append(file_handler)

    logging.basicConfig(level=log_level, handlers=handlers, force=True)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=False)

    pre_chain: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=pre_chain
        + [
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger(component)
