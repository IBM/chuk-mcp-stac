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
        and artifact store status. Use this to verify the server is running
        and check storage configuration.

        Args:
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with server status including version, storage provider, and default catalog

        Tips for LLMs:
            - Call stac_capabilities instead if you need to plan a workflow
              (it returns collections, bands, and indices too)
            - Check artifact_store_available before attempting downloads

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
        including supported catalogs, satellite collections, band names
        per platform, and available spectral indices with required bands.

        Args:
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with catalogs, collections, band mappings, and spectral indices

        Tips for LLMs:
            - Call this FIRST to understand what the server can do before
              planning any analysis workflow
            - Use band_mappings to know which band names to pass to download tools
            - Use spectral_indices to see which indices are available and what
              bands they require
            - Typical workflow: stac_capabilities → stac_search → stac_describe_scene
              → stac_download_bands or stac_compute_index
            - Collections: sentinel-2-l2a (optical, 10m), landsat-c2-l2 (optical, 30m),
              sentinel-1-grd (SAR radar, 10m), cop-dem-glo-30 (elevation, 30m)

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
