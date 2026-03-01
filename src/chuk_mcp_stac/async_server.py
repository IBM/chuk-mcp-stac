#!/usr/bin/env python3
"""
Async STAC MCP Server using chuk-mcp-server

Satellite imagery discovery and retrieval via STAC catalogs.
Searches Earth Search / Planetary Computer, downloads bands as
Cloud-Optimised GeoTIFFs, and stores them in chuk-artifacts for
downstream analysis by chuk-mcp-geo.

Storage is managed through chuk-mcp-server's built-in artifact store context.
"""

import logging

from chuk_mcp_server import ChukMCPServer

from .core.catalog_manager import CatalogManager
from .tools.discovery import register_discovery_tools
from .tools.download import register_download_tools
from .tools.map import register_map_tools

# Import tool registration modules
from .tools.search import register_search_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server instance
mcp = ChukMCPServer("chuk-mcp-stac")

# Create catalog manager instance
manager = CatalogManager()

# Register all tool modules
register_search_tools(mcp, manager)
register_download_tools(mcp, manager)
register_discovery_tools(mcp, manager)
register_map_tools(mcp, manager)

# Run the server
if __name__ == "__main__":
    logger.info("Starting STAC MCP Server...")
    logger.info("Storage: Using chuk-mcp-server artifact store context")
    mcp.run(stdio=True)
