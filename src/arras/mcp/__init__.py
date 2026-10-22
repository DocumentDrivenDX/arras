# SPDX-License-Identifier: MIT OR Apache-2.0
"""The MCP binding: `python -m arras.mcp` speaks MCP over stdio (CONTRACT-007)."""

from arras.mcp.identity import TokenSource, principal_from_token
from arras.mcp.server import McpServer, serve

__all__ = ["McpServer", "TokenSource", "principal_from_token", "serve"]
