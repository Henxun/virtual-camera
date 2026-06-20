# SPDX-License-Identifier: Apache-2.0
"""Error model — namespace mirrors `virtualcam/shared/akvc_errors.h`."""

from __future__ import annotations

from typing import Any, Optional


class AkvcError(Exception):
    """Base class for all AKVC errors."""

    code: str = "E_AKVC_INTERNAL"

    def __init__(
        self,
        message: str,
        *,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:  # pragma: no cover
        if self.details:
            return f"[{self.code}] {self.message} {self.details}"
        return f"[{self.code}] {self.message}"


class FrameBusError(AkvcError):
    code = "E_AKVC_FRAMEBUS_PUBLISH_FAILED"


class FrameBusOpenError(FrameBusError):
    code = "E_AKVC_FRAMEBUS_OPEN_FAILED"


class FrameBusSchemaMismatch(FrameBusError):
    code = "E_AKVC_FRAMEBUS_SCHEMA_MISMATCH"


class FormatNotSupportedError(AkvcError):
    code = "E_AKVC_FORMAT_NOT_SUPPORTED"


class DeviceBusyError(AkvcError):
    code = "E_AKVC_DEVICE_BUSY"


class ConfigInvalidError(AkvcError):
    code = "E_AKVC_CONFIG_INVALID"


class HelperUnavailableError(AkvcError):
    code = "E_AKVC_HELPER_NOT_RUNNING"
