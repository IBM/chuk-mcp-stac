"""
MCP tools for server discovery and status.
"""

import logging
import os

from chuk_mcp_server import has_artifact_store

from ...constants import (
    DEFAULT_CATALOG,
    DEM_BANDS,
    INDEX_BANDS,
    LANDSAT_BANDS,
    SENTINEL1_BANDS,
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
    format_response,
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
    async def stac_status(
        output_mode: str = "json",
    ) -> str:
        """
        Get server status and configuration.

        Returns information about the server version, available catalogs,
        and artifact store status.

        Args:
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with server status

        Example:
            status = await stac_status()
        """
        try:
            provider = os.environ.get(EnvVar.ARTIFACTS_PROVIDER, StorageProvider.MEMORY)
            return format_response(
                StatusResponse(
                    server=ServerConfig.NAME,
                    version=ServerConfig.VERSION,
                    storage_provider=provider,
                    default_catalog=DEFAULT_CATALOG,
                    artifact_store_available=has_artifact_store(),
                ),
                output_mode,
            )
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_capabilities(
        output_mode: str = "json",
    ) -> str:
        """
        List server capabilities: catalogs, collections, and band info.

        Returns a comprehensive overview of what this server can do,
        useful for LLM planning of analysis workflows.

        Args:
            output_mode: Response format - "json" (default) or "text"

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

        return format_response(
            CapabilitiesResponse(
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
                    "sentinel-1": list(SENTINEL1_BANDS.keys()),
                    "dem": list(DEM_BANDS.keys()),
                },
            ),
            output_mode,
        )
