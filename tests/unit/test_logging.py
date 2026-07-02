# SPDX-License-Identifier: Apache-2.0
"""Logging configuration tests."""

from __future__ import annotations

import json
import logging

from apps.desktop.akvc_app.services import app_logging as akvc_logging


def test_configure_returns_stdlib_logger_and_writes_json_file(tmp_path) -> None:
    logger = akvc_logging.configure(log_dir=tmp_path, component="akvc.test")

    assert isinstance(logger, logging.Logger)

    logger.info("hello world")

    log_file = tmp_path / "akvc.test.log"
    assert log_file.is_file()

    payload = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "akvc.test"
    assert payload["message"] == "hello world"
