"""
MCP tools for server discovery and status.
"""

import logging
import os

from chuk_mcp_server import has_artifact_store

from ...constants import (
    DEFAULT_CATALOG,
    INDEX_BANDS,
    LANDSAT_BANDS,
    SENTINEL2_BANDS,
    EnvVar,
    SatelliteCollection,
    ServerConfig,
    STACEndpoints,
    StorageProvider,
)
from ...models import (
    CapabilitiesResponse,
    CatalogInfo,
    ErrorResponse,
    SpectralIndexInfo,
    StatusResponse,
)

logger = logging.getLogger(__name__)


def register_discovery_tools(mcp: object, manager: object) -> None:
    """
    Register discovery tools with the MCP server.

    Args:
        mcp: ChukMCPServer instance
        manager: CatalogManager instance
    """

    @mcp.tool  # type: ignore[union-attr]
    async def stac_status() -> str:
        """
        Get server status and configuration.

        Returns information about the server version, available catalogs,
        and artifact store status.

        Returns:
            JSON with server status

        Example:
            status = await stac_status()
        """
        try:
            provider = os.environ.get(EnvVar.ARTIFACTS_PROVIDER, StorageProvider.MEMORY)
            return StatusResponse(
                server=ServerConfig.NAME,
                version=ServerConfig.VERSION,
                storage_provider=provider,
                default_catalog=DEFAULT_CATALOG,
                artifact_store_available=has_artifact_store(),
            ).model_dump_json()
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return ErrorResponse(error=str(e)).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_capabilities() -> str:
        """
        List server capabilities: catalogs, collections, and band info.

        Returns a comprehensive overview of what this server can do,
        useful for LLM planning of analysis workflows.

        Returns:
            JSON with full capability listing

        Example:
            caps = await stac_capabilities()
        """
        catalogs = [CatalogInfo(name=name, url=url) for name, url in STACEndpoints.ALL.items()]

        indices = [
            SpectralIndexInfo(name=name, required_bands=bands)
            for name, bands in INDEX_BANDS.items()
        ]

        return CapabilitiesResponse(
            server=ServerConfig.NAME,
            version=ServerConfig.VERSION,
            catalogs=catalogs,
            default_catalog=DEFAULT_CATALOG,
            known_collections=SatelliteCollection.ALL,
            spectral_indices=indices,
            tool_count=len(mcp.get_tools()),  # type: ignore[union-attr]
            band_mappings={
                "sentinel-2": list(SENTINEL2_BANDS.keys()),
                "landsat": list(LANDSAT_BANDS.keys()),
            },
        ).model_dump_json()
