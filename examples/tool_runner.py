"""
Shared helper for running chuk-mcp-stac MCP tools directly from Python.

Provides a ToolRunner class that registers all MCP tools and sets up
an in-memory artifact store, without requiring a full MCP transport layer.
Demo scripts use this to call tools as plain async functions.

Usage:
    from tool_runner import ToolRunner

    async def main():
        runner = ToolRunner()
        result = await runner.run("stac_search", bbox=[0.85, 51.85, 0.95, 51.93])
        print(result)
"""

from __future__ import annotations

import json
import os
from typing import Any

from chuk_mcp_stac.core.catalog_manager import CatalogManager
from chuk_mcp_stac.tools.discovery import register_discovery_tools
from chuk_mcp_stac.tools.download import register_download_tools
from chuk_mcp_stac.tools.search import register_search_tools


class _MiniMCP:
    """Minimal MCP server that captures tools registered via @mcp.tool."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def tool(self, fn: Any) -> Any:
        self._tools[fn.__name__] = fn
        return fn

    def get_tool(self, name: str) -> Any:
        return self._tools[name]

    def get_tools(self) -> list[Any]:
        return list(self._tools.values())


def _init_artifact_store() -> None:
    """Initialize an in-memory artifact store for demo use."""
    os.environ.setdefault("CHUK_ARTIFACTS_PROVIDER", "memory")
    try:
        from chuk_artifacts import ArtifactStore
        from chuk_mcp_server import set_global_artifact_store

        store = ArtifactStore(storage_provider="memory", session_provider="memory")
        set_global_artifact_store(store)
    except ImportError as e:
        print(f"Warning: could not init artifact store: {e}")
        print("  Downloads will fail. Install chuk-artifacts and chuk-mcp-server.")


class ToolRunner:
    """
    Run chuk-mcp-stac MCP tools directly from Python.

    All 16 tools are registered and callable via run(tool_name, **kwargs).
    Returns parsed JSON (dict/list) by default. Use run_text() for
    human-readable output. An in-memory artifact store is initialized
    automatically.
    """

    def __init__(self) -> None:
        _init_artifact_store()
        self._mcp = _MiniMCP()
        self.manager = CatalogManager()
        register_search_tools(self._mcp, self.manager)
        register_download_tools(self._mcp, self.manager)
        register_discovery_tools(self._mcp, self.manager)

    @property
    def tool_names(self) -> list[str]:
        return list(self._mcp._tools.keys())

    async def run(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Call a tool by name and return parsed JSON."""
        fn = self._mcp.get_tool(tool_name)
        raw = await fn(**kwargs)
        return json.loads(raw)

    async def run_text(self, tool_name: str, **kwargs: Any) -> str:
        """Call a tool by name with output_mode='text' and return plaintext."""
        fn = self._mcp.get_tool(tool_name)
        return await fn(output_mode="text", **kwargs)

    async def run_raw(self, tool_name: str, **kwargs: Any) -> str:
        """Call a tool by name and return the raw JSON string."""
        fn = self._mcp.get_tool(tool_name)
        return await fn(**kwargs)
