# SPDX-License-Identifier: MIT OR Apache-2.0
"""Explicit, inert distribution identity selected by an embedding host or launcher."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from arras.branding import Brand

_SERVER_NAME = re.compile(r"[^\x00-\x1f\x7f]+")
_TOOL_PREFIX = re.compile(r"[a-z][a-z0-9_]{0,15}")
_ENV_PREFIX = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*")
_TELEMETRY_PREFIX = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*")
_SERVICE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


def _is_text(value: object) -> bool:
    return isinstance(value, str)


def _is_brand(value: object) -> bool:
    return isinstance(value, Brand)


@dataclass(frozen=True)
class TelemetryNames:
    """Explicit, non-secret downstream signal names; never inferred from identity."""

    service_name: str | None = None
    attribute_namespace: str = "arras"
    log_prefix: str = "arras"
    event_prefix: str = "arras"

    def __post_init__(self) -> None:
        if self.service_name is not None and (
            not _is_text(self.service_name)
            or self.service_name != self.service_name.strip()
            or not _SERVICE_NAME.fullmatch(self.service_name)
        ):
            raise ValueError("service_name: expected a bounded service name")
        for field_name in ("attribute_namespace", "log_prefix", "event_prefix"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, str)
                or len(value) > 64
                or not _TELEMETRY_PREFIX.fullmatch(value)
            ):
                raise ValueError(f"{field_name}: expected a bounded dotted prefix")


def _is_telemetry_names(value: object) -> bool:
    return isinstance(value, TelemetryNames)


@dataclass(frozen=True)
class DistributionConfig:
    """Distribution-specific presentation and process-name settings; performs no host I/O."""

    brand: Brand = field(default_factory=Brand)
    mcp_server_name: str = "arras"
    mcp_tool_prefix: str = ""
    env_prefix: str = "ARRAS"
    telemetry: TelemetryNames = TelemetryNames()

    def __post_init__(self) -> None:
        if not _is_brand(self.brand):
            raise ValueError("brand: a Brand value")
        if not _is_telemetry_names(self.telemetry):
            raise ValueError("telemetry: a TelemetryNames value")
        if (
            not _is_text(self.mcp_server_name)
            or not self.mcp_server_name.strip()
            or self.mcp_server_name != self.mcp_server_name.strip()
            or len(self.mcp_server_name.encode("utf-16-le")) // 2 > 80
            or not _SERVER_NAME.fullmatch(self.mcp_server_name)
        ):
            raise ValueError("mcp_server_name: trimmed text up to 80 characters without controls")
        if not _is_text(self.mcp_tool_prefix) or (
            self.mcp_tool_prefix and not _TOOL_PREFIX.fullmatch(self.mcp_tool_prefix)
        ):
            raise ValueError("mcp_tool_prefix: empty or [a-z][a-z0-9_]{0,15}")
        if (
            not _is_text(self.env_prefix)
            or len(self.env_prefix) > 32
            or not _ENV_PREFIX.fullmatch(self.env_prefix)
        ):
            raise ValueError("env_prefix: ASCII prefix [A-Z][A-Z0-9_]* up to 32 characters")
