# SPDX-License-Identifier: Apache-2.0
"""Pydantic v2 configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DeviceConfig(BaseModel):
    name: str = "AK Virtual Camera"
    vendor: str = "AK"
    width: int = Field(default=1280, ge=160, le=4096)
    height: int = Field(default=720, ge=120, le=2160)
    fps: int = Field(default=30, ge=5, le=60)


class PipelineConfig(BaseModel):
    fps_jitter_pct: float = 10.0
    color_space: str = "bt601_limited"


class AppConfig(BaseModel):
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    log_level: str = "INFO"
