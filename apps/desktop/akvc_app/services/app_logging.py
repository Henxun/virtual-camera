# SPDX-License-Identifier: Apache-2.0
"""Stdlib logging setup for desktop worker processes."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).isoformat(timespec="seconds")
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return f"{timestamp} {record.levelname} {record.name} {message}"


def configure(
    *,
    level: str = "INFO",
    log_dir: Path | None = None,
    component: str = "akvc",
) -> logging.Logger:
    log_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setLevel(log_level)
    stderr_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(stderr_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / f"{component}.log", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JsonLineFormatter())
        root_logger.addHandler(file_handler)

    logger = logging.getLogger(component)
    logger.setLevel(log_level)
    return logger
