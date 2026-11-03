# SPDX-License-Identifier: MIT OR Apache-2.0
"""Decode the bounded distribution portion of an offline doctor request."""

from __future__ import annotations

from typing import Any, cast

from arras._doctor_types import DistributionInvalid, telemetry_fields
from arras.branding import Brand
from arras.distribution import DistributionConfig, TelemetryNames


def distribution_request(value: Any) -> DistributionConfig:
    if type(value) is not dict:
        raise ValueError("distribution must be an object")
    fields = cast(dict[str, Any], value)
    allowed = {
        "brand",
        "mcp_server_name",
        "mcp_tool_prefix",
        "env_prefix",
        "telemetry",
        "view_vocabulary_aliases",
        "graph_format_aliases",
    }
    if set(fields) - allowed:
        raise ValueError("distribution has unknown fields")
    brand_value: Any = fields.get("brand", {})
    if type(brand_value) is not dict:
        raise ValueError("brand must be an object")
    brand_fields = cast(dict[str, Any], brand_value)
    if set(brand_fields) - {"name", "title", "wordmark", "tagline", "logo"}:
        raise ValueError("brand has unknown fields")
    for name, raw in brand_fields.items():
        if (name == "name" and not isinstance(raw, str)) or (
            name != "name" and raw is not None and not isinstance(raw, str)
        ):
            raise ValueError("brand fields have invalid types")
    for name in ("mcp_server_name", "mcp_tool_prefix", "env_prefix"):
        if name in fields and not isinstance(fields[name], str):
            raise ValueError("distribution fields have invalid types")
    selected_telemetry = telemetry_fields(fields.get("telemetry", {}))
    for field_name in ("view_vocabulary_aliases", "graph_format_aliases"):
        if field_name in fields and (
            type(fields[field_name]) is not list
            or any(type(alias) is not str for alias in fields[field_name])
        ):
            raise ValueError("distribution alias fields must be arrays of strings")
    try:
        return DistributionConfig(
            brand=Brand(**brand_fields),
            mcp_server_name=fields.get("mcp_server_name", "arras"),
            mcp_tool_prefix=fields.get("mcp_tool_prefix", ""),
            env_prefix=fields.get("env_prefix", "ARRAS"),
            telemetry=TelemetryNames(**selected_telemetry),
            view_vocabulary_aliases=tuple(fields.get("view_vocabulary_aliases", ())),
            graph_format_aliases=tuple(fields.get("graph_format_aliases", ())),
        )
    except (TypeError, ValueError) as exc:
        raise DistributionInvalid from exc
