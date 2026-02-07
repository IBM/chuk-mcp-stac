"""
MCP tools for downloading satellite band data from STAC scenes.

Tools delegate to CatalogManager.download_bands() which handles the
full pipeline: COG reading -> in-memory GeoTIFF -> artifact storage.
Tools validate parameters and format responses — they never touch bytes.
"""

import asyncio
import logging

from ...constants import (
    DEFAULT_CATALOG,
    DEFAULT_COLLECTION,
    DEFAULT_COMPOSITE_NAME,
    MAX_CLOUD_COVER,
    RGB_BANDS,
    RGB_COMPOSITE_TYPE,
    ErrorMessages,
    STACProperty,
    SuccessMessages,
)
from ...models import (
    BandDownloadResponse,
    CompositeResponse,
    ErrorResponse,
    MosaicResponse,
    TimeSeriesEntry,
    TimeSeriesResponse,
)
from ...models.stac import STACItem

logger = logging.getLogger(__name__)


def register_download_tools(mcp: object, manager: object) -> None:
    """
    Register download tools with the MCP server.

    Args:
        mcp: ChukMCPServer instance
        manager: CatalogManager instance
    """

    def _response_bbox(scene_id: str, user_bbox: list[float] | None) -> list[float]:
        """Resolve the bbox to include in the response."""
        if user_bbox:
            return user_bbox
        cached = manager.get_cached_scene(scene_id)  # type: ignore[union-attr]
        return cached.bbox if cached else []

    @mcp.tool  # type: ignore[union-attr]
    async def stac_download_bands(
        scene_id: str,
        bands: list[str],
        bbox: list[float] | None = None,
    ) -> str:
        """
        Download specific bands from a scene as a GeoTIFF.

        Reads band COGs via HTTP, windows to the requested bbox,
        and stores the result in chuk-artifacts. The bbox should be
        in EPSG:4326 — CRS reprojection to the raster's native CRS
        is handled automatically.

        Args:
            scene_id: Scene identifier from a previous search
            bands: Band names to download (e.g., ["red", "green", "blue", "nir"])
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north]

        Returns:
            JSON with artifact_ref for the downloaded data

        Example:
            result = await stac_download_bands(
                scene_id="S2B_...",
                bands=["red", "nir"],
                bbox=[0.85, 51.85, 0.95, 51.92]
            )
        """
        try:
            result = await manager.download_bands(scene_id, bands, bbox)  # type: ignore[union-attr]

            return BandDownloadResponse(
                scene_id=scene_id,
                bands=bands,
                artifact_ref=result.artifact_ref,
                bbox=_response_bbox(scene_id, bbox),
                crs=result.crs,
                shape=result.shape,
                dtype=result.dtype,
                message=SuccessMessages.DOWNLOAD_COMPLETE.format(len(bands)),
            ).model_dump_json()

        except (ValueError, RuntimeError) as e:
            return ErrorResponse(error=str(e)).model_dump_json()
        except Exception as e:
            logger.error(f"Band download failed: {e}")
            return ErrorResponse(
                error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))
            ).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_download_rgb(
        scene_id: str,
        bbox: list[float] | None = None,
    ) -> str:
        """
        Download a true-color RGB composite from a scene.

        Convenience wrapper around stac_download_bands that
        automatically selects red, green, blue bands.

        Args:
            scene_id: Scene identifier from a previous search
            bbox: Optional crop bbox in EPSG:4326

        Returns:
            JSON with artifact_ref for the RGB composite

        Example:
            rgb = await stac_download_rgb(scene_id="S2B_...")
        """
        try:
            result = await manager.download_bands(scene_id, RGB_BANDS, bbox)  # type: ignore[union-attr]

            return CompositeResponse(
                scene_id=scene_id,
                composite_type=RGB_COMPOSITE_TYPE,
                bands=RGB_BANDS,
                artifact_ref=result.artifact_ref,
                bbox=_response_bbox(scene_id, bbox),
                crs=result.crs,
                shape=result.shape,
                message=SuccessMessages.COMPOSITE_COMPLETE.format("RGB", 3),
            ).model_dump_json()

        except (ValueError, RuntimeError) as e:
            return ErrorResponse(error=str(e)).model_dump_json()
        except Exception as e:
            logger.error(f"RGB download failed: {e}")
            return ErrorResponse(
                error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))
            ).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_download_composite(
        scene_id: str,
        bands: list[str],
        composite_name: str = DEFAULT_COMPOSITE_NAME,
        bbox: list[float] | None = None,
    ) -> str:
        """
        Download a multi-band composite from a scene.

        Creates a composite from any combination of bands (e.g., false
        colour infrared: nir, red, green).

        Args:
            scene_id: Scene identifier from a previous search
            bands: Band names for the composite (e.g., ["nir", "red", "green"])
            composite_name: Name for the composite (e.g., "false_color_ir")
            bbox: Optional crop bbox in EPSG:4326

        Returns:
            JSON with artifact_ref for the composite

        Example:
            false_color = await stac_download_composite(
                scene_id="S2B_...",
                bands=["nir", "red", "green"],
                composite_name="false_color_ir"
            )
        """
        try:
            result = await manager.download_bands(scene_id, bands, bbox)  # type: ignore[union-attr]

            return CompositeResponse(
                scene_id=scene_id,
                composite_type=composite_name,
                bands=bands,
                artifact_ref=result.artifact_ref,
                bbox=_response_bbox(scene_id, bbox),
                crs=result.crs,
                shape=result.shape,
                message=SuccessMessages.COMPOSITE_COMPLETE.format(composite_name, len(bands)),
            ).model_dump_json()

        except (ValueError, RuntimeError) as e:
            return ErrorResponse(error=str(e)).model_dump_json()
        except Exception as e:
            logger.error(f"Composite download failed: {e}")
            return ErrorResponse(
                error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))
            ).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_mosaic(
        scene_ids: list[str],
        bands: list[str],
        bbox: list[float] | None = None,
    ) -> str:
        """
        Create a mosaic from multiple scenes.

        Combines overlapping scenes into a single raster, using
        later scenes to fill gaps/cloud cover from earlier ones.

        Args:
            scene_ids: List of scene identifiers to mosaic
            bands: Bands to include
            bbox: Output bounding box (union of scenes if not specified)

        Returns:
            JSON with artifact_ref for the mosaic

        Example:
            mosaic = await stac_mosaic(
                scene_ids=["S2B_001", "S2B_002"],
                bands=["red", "green", "blue"]
            )
        """
        try:
            result = await manager.download_mosaic(  # type: ignore[union-attr]
                scene_ids, bands, bbox
            )

            return MosaicResponse(
                scene_ids=scene_ids,
                bands=bands,
                artifact_ref=result.artifact_ref,
                bbox=bbox or [],
                crs=result.crs,
                shape=result.shape,
                message=SuccessMessages.MOSAIC_COMPLETE.format(len(scene_ids)),
            ).model_dump_json()

        except (ValueError, RuntimeError) as e:
            return ErrorResponse(error=str(e)).model_dump_json()
        except Exception as e:
            logger.error(f"Mosaic failed: {e}")
            return ErrorResponse(error=str(e)).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_time_series(
        bbox: list[float],
        bands: list[str],
        date_range: str,
        collection: str | None = None,
        max_cloud_cover: int | None = None,
        max_items: int | None = None,
        catalog: str | None = None,
    ) -> str:
        """
        Extract a time series of band data over an area.

        Searches for all scenes in the date range, downloads the
        requested bands for each, and returns references to the
        full temporal stack.

        Args:
            bbox: Area of interest [west, south, east, north]
            bands: Bands to extract (e.g., ["red", "nir"])
            date_range: Date range "YYYY-MM-DD/YYYY-MM-DD"
            collection: STAC collection (default: sentinel-2-l2a)
            max_cloud_cover: Maximum cloud cover 0-100 (default: 20)
            max_items: Maximum scenes to include (default: 50)
            catalog: Catalog name (default: earth_search)

        Returns:
            JSON with per-date artifact references

        Example:
            ts = await stac_time_series(
                bbox=[0.85, 51.85, 0.95, 51.92],
                bands=["red", "nir"],
                date_range="2024-01-01/2024-12-31",
                max_cloud_cover=10
            )
        """
        try:
            if len(bbox) != 4:
                return ErrorResponse(error=ErrorMessages.INVALID_BBOX).model_dump_json()

            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG
            coll = collection or DEFAULT_COLLECTION
            cloud_max = max_cloud_cover if max_cloud_cover is not None else MAX_CLOUD_COVER
            items_max = max_items if max_items is not None else 50

            def _search_time_series() -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                search = client.search(
                    collections=[coll],
                    bbox=bbox,
                    datetime=date_range,
                    query={STACProperty.CLOUD_COVER: {"lt": cloud_max}},
                    max_items=items_max,
                )
                items = list(search.items())
                items.sort(key=lambda x: x.properties.get(STACProperty.DATETIME, ""))
                return items

            items = await asyncio.to_thread(_search_time_series)

            # Cache scenes first
            cached_items: list[tuple[str, STACItem]] = []
            for item in items:
                stac_item = STACItem.model_validate(item.to_dict())
                manager.cache_scene(item.id, stac_item, catalog_name)  # type: ignore[union-attr]
                cached_items.append((item.id, stac_item))

            # Download bands for all scenes concurrently
            async def _download_one(scene_id: str, stac_item: STACItem) -> TimeSeriesEntry:
                dl_result = await manager.download_bands(  # type: ignore[union-attr]
                    scene_id, bands, bbox
                )
                return TimeSeriesEntry(
                    datetime=stac_item.properties.datetime,
                    scene_id=scene_id,
                    artifact_ref=dl_result.artifact_ref,
                    cloud_cover=stac_item.properties.cloud_cover,
                )

            entries: list[TimeSeriesEntry] = list(
                await asyncio.gather(*[_download_one(sid, si) for sid, si in cached_items])
            )

            return TimeSeriesResponse(
                bbox=bbox,
                collection=coll,
                bands=bands,
                date_count=len(entries),
                entries=entries,
                message=SuccessMessages.TIME_SERIES.format(len(entries)),
            ).model_dump_json()

        except Exception as e:
            logger.error(f"Time series extraction failed: {e}")
            return ErrorResponse(error=str(e)).model_dump_json()
