# SPDX-License-Identifier: MIT OR Apache-2.0
"""The MCP binding: JSON-RPC over stdio (CONTRACT-007)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from arras import telemetry
from arras.distribution import DistributionConfig
from arras.mcp.identity import TokenSource, principal_from_token
from arras.mcp.server import McpServer, serve


def launch(
    argv: Sequence[str] | None = None,
    *,
    distribution: DistributionConfig | None = None,
    telemetry_factory: Callable[[telemetry.TelemetryNames], telemetry.TelemetryContext]
    | None = None,
) -> None:
    """Run the stdio process; only ``-h`` and ``--help`` are accepted as arguments."""
    from arras.mcp.process import launch as _launch

    _launch(argv, distribution=distribution, telemetry_factory=telemetry_factory)


__all__ = ["McpServer", "TokenSource", "principal_from_token", "serve", "launch"]
