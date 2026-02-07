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
    INDEX_BANDS,
    MAX_CLOUD_COVER,
    RGB_BANDS,
    RGB_COMPOSITE_TYPE,
    ErrorMessages,
    STACProperty,
    SuccessMessages,
)
from ...models import (
    BandDownloadResponse,
    BandSizeDetail,
    CompositeResponse,
    ErrorResponse,
    IndexResponse,
    MosaicResponse,
    SizeEstimateResponse,
    TemporalCompositeResponse,
    TimeSeriesEntry,
    TimeSeriesResponse,
    format_response,
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
        output_format: str = "geotiff",
        cloud_mask: bool = False,
        output_mode: str = "json",
    ) -> str:
        """
        Download specific bands from a scene as a GeoTIFF or PNG.

        Reads band COGs via HTTP, windows to the requested bbox,
        and stores the result in chuk-artifacts. The bbox should be
        in EPSG:4326 — CRS reprojection to the raster's native CRS
        is handled automatically.

        Args:
            scene_id: Scene identifier from a previous search
            bands: Band names to download (e.g., ["red", "green", "blue", "nir"])
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north]
            output_format: Output format - "geotiff" (default) or "png" (auto-stretched)
            cloud_mask: Apply SCL-based cloud masking (Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

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
            result = await manager.download_bands(  # type: ignore[union-attr]
                scene_id,
                bands,
                bbox,
                output_format=output_format,
                cloud_mask=cloud_mask,
            )

            return format_response(
                BandDownloadResponse(
                    scene_id=scene_id,
                    bands=bands,
                    artifact_ref=result.artifact_ref,
                    preview_ref=result.preview_ref,
                    bbox=_response_bbox(scene_id, bbox),
                    crs=result.crs,
                    shape=result.shape,
                    dtype=result.dtype,
                    output_format=output_format,
                    message=SuccessMessages.DOWNLOAD_COMPLETE.format(len(bands)),
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"Band download failed: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))),
                output_mode,
            )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_download_rgb(
        scene_id: str,
        bbox: list[float] | None = None,
        output_format: str = "geotiff",
        cloud_mask: bool = False,
        output_mode: str = "json",
    ) -> str:
        """
        Download a true-color RGB composite from a scene.

        Convenience wrapper around stac_download_bands that
        automatically selects red, green, blue bands.

        Args:
            scene_id: Scene identifier from a previous search
            bbox: Optional crop bbox in EPSG:4326
            output_format: Output format - "geotiff" (default) or "png" (LLMs can render inline)
            cloud_mask: Apply SCL-based cloud masking (Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref for the RGB composite

        Example:
            rgb = await stac_download_rgb(scene_id="S2B_...", output_format="png")
        """
        try:
            result = await manager.download_bands(  # type: ignore[union-attr]
                scene_id,
                RGB_BANDS,
                bbox,
                output_format=output_format,
                cloud_mask=cloud_mask,
            )

            return format_response(
                CompositeResponse(
                    scene_id=scene_id,
                    composite_type=RGB_COMPOSITE_TYPE,
                    bands=RGB_BANDS,
                    artifact_ref=result.artifact_ref,
                    preview_ref=result.preview_ref,
                    bbox=_response_bbox(scene_id, bbox),
                    crs=result.crs,
                    shape=result.shape,
                    output_format=output_format,
                    message=SuccessMessages.COMPOSITE_COMPLETE.format("RGB", 3),
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"RGB download failed: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))),
                output_mode,
            )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_download_composite(
        scene_id: str,
        bands: list[str],
        composite_name: str = DEFAULT_COMPOSITE_NAME,
        bbox: list[float] | None = None,
        output_format: str = "geotiff",
        cloud_mask: bool = False,
        output_mode: str = "json",
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
            output_format: Output format - "geotiff" (default) or "png"
            cloud_mask: Apply SCL-based cloud masking (Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

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
            result = await manager.download_bands(  # type: ignore[union-attr]
                scene_id,
                bands,
                bbox,
                output_format=output_format,
                cloud_mask=cloud_mask,
            )

            return format_response(
                CompositeResponse(
                    scene_id=scene_id,
                    composite_type=composite_name,
                    bands=bands,
                    artifact_ref=result.artifact_ref,
                    preview_ref=result.preview_ref,
                    bbox=_response_bbox(scene_id, bbox),
                    crs=result.crs,
                    shape=result.shape,
                    output_format=output_format,
                    message=SuccessMessages.COMPOSITE_COMPLETE.format(composite_name, len(bands)),
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"Composite download failed: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))),
                output_mode,
            )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_mosaic(
        scene_ids: list[str],
        bands: list[str],
        bbox: list[float] | None = None,
        output_format: str = "geotiff",
        cloud_mask: bool = False,
        method: str = "last",
        output_mode: str = "json",
    ) -> str:
        """
        Create a mosaic from multiple scenes.

        Combines overlapping scenes into a single raster.

        Args:
            scene_ids: List of scene identifiers to mosaic
            bands: Bands to include
            bbox: Output bounding box (union of scenes if not specified)
            output_format: Output format - "geotiff" (default) or "png"
            cloud_mask: Apply SCL-based cloud masking per scene before merge (Sentinel-2 only)
            method: Merge method - "last" (default, later scenes fill gaps)
                or "quality" (SCL-based best-pixel selection, Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref for the mosaic

        Example:
            mosaic = await stac_mosaic(
                scene_ids=["S2B_001", "S2B_002"],
                bands=["red", "green", "blue"],
                method="quality"
            )
        """
        try:
            result = await manager.download_mosaic(  # type: ignore[union-attr]
                scene_ids,
                bands,
                bbox,
                output_format=output_format,
                cloud_mask=cloud_mask,
                method=method,
            )

            return format_response(
                MosaicResponse(
                    scene_ids=scene_ids,
                    bands=bands,
                    artifact_ref=result.artifact_ref,
                    preview_ref=result.preview_ref,
                    bbox=bbox or [],
                    crs=result.crs,
                    shape=result.shape,
                    output_format=output_format,
                    method=method,
                    message=SuccessMessages.MOSAIC_COMPLETE.format(len(scene_ids)),
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"Mosaic failed: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_compute_index(
        scene_id: str,
        index_name: str,
        bbox: list[float] | None = None,
        cloud_mask: bool = False,
        output_format: str = "geotiff",
        output_mode: str = "json",
    ) -> str:
        """
        Compute a spectral index (e.g., NDVI, NDWI) for a scene.

        Automatically downloads the required bands, computes the index
        formula, and stores the result as a single-band float32 raster.

        Supported indices:
        - ndvi: Vegetation (NIR - Red) / (NIR + Red)
        - ndwi: Water (Green - NIR) / (Green + NIR)
        - ndbi: Built-up (SWIR16 - NIR) / (SWIR16 + NIR)
        - evi: Enhanced Vegetation 2.5*(NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1)
        - savi: Soil-Adjusted Vegetation ((NIR - Red) / (NIR + Red + 0.5)) * 1.5
        - bsi: Bare Soil ((SWIR16 + Red) - (NIR + Blue)) / ((SWIR16 + Red) + (NIR + Blue))

        Args:
            scene_id: Scene identifier from a previous search
            index_name: Index to compute (ndvi, ndwi, ndbi, evi, savi, bsi)
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north]
            cloud_mask: Apply SCL-based cloud masking before computation (Sentinel-2 only)
            output_format: Output format - "geotiff" (default) or "png"
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref and value_range for the computed index

        Example:
            ndvi = await stac_compute_index(
                scene_id="S2B_...",
                index_name="ndvi",
                bbox=[0.85, 51.85, 0.95, 51.92]
            )
        """
        try:
            result = await manager.compute_index(  # type: ignore[union-attr]
                scene_id,
                index_name,
                bbox,
                cloud_mask=cloud_mask,
                output_format=output_format,
            )

            required_bands = INDEX_BANDS.get(index_name, [])

            return format_response(
                IndexResponse(
                    scene_id=scene_id,
                    index_name=index_name,
                    required_bands=required_bands,
                    value_range=result.value_range,
                    artifact_ref=result.artifact_ref,
                    preview_ref=result.preview_ref,
                    bbox=_response_bbox(scene_id, bbox),
                    crs=result.crs,
                    shape=result.shape,
                    output_format=output_format,
                    message=SuccessMessages.INDEX_COMPLETE.format(index_name.upper()),
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"Index computation failed: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.DOWNLOAD_FAILED.format(str(e))),
                output_mode,
            )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_time_series(
        bbox: list[float],
        bands: list[str],
        date_range: str,
        collection: str | None = None,
        max_cloud_cover: int | None = None,
        max_items: int | None = None,
        catalog: str | None = None,
        output_mode: str = "json",
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
            output_mode: Response format - "json" (default) or "text"

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
                return format_response(
                    ErrorResponse(error=ErrorMessages.INVALID_BBOX),
                    output_mode,
                )

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
                    preview_ref=dl_result.preview_ref,
                    cloud_cover=stac_item.properties.cloud_cover,
                )

            entries: list[TimeSeriesEntry] = list(
                await asyncio.gather(*[_download_one(sid, si) for sid, si in cached_items])
            )

            return format_response(
                TimeSeriesResponse(
                    bbox=bbox,
                    collection=coll,
                    bands=bands,
                    date_count=len(entries),
                    entries=entries,
                    message=SuccessMessages.TIME_SERIES.format(len(entries)),
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Time series extraction failed: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_estimate_size(
        scene_id: str,
        bands: list[str],
        bbox: list[float] | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        Estimate download size for bands from a scene (no pixel data read).

        Reads only COG headers to determine dimensions, dtype, and
        estimated file size. Use this before large downloads to
        understand how much data will be transferred.

        Args:
            scene_id: Scene identifier from a previous search
            bands: Band names to estimate (e.g., ["red", "green", "blue", "nir"])
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north]
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with per-band size details and total estimate

        Example:
            estimate = await stac_estimate_size(
                scene_id="S2B_...",
                bands=["red", "nir"],
                bbox=[0.85, 51.85, 0.95, 51.92]
            )
        """
        try:
            result = await manager.estimate_size(  # type: ignore[union-attr]
                scene_id, bands, bbox
            )

            per_band = [BandSizeDetail(**detail) for detail in result["per_band"]]

            return format_response(
                SizeEstimateResponse(
                    scene_id=scene_id,
                    band_count=len(bands),
                    per_band=per_band,
                    total_pixels=result["total_pixels"],
                    estimated_bytes=result["estimated_bytes"],
                    estimated_mb=result["estimated_mb"],
                    crs=result["crs"],
                    bbox=bbox or [],
                    warnings=result.get("warnings", []),
                    message=f"Estimated {result['estimated_mb']:.1f} MB for {len(bands)} band(s)",
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"Size estimation failed: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_temporal_composite(
        bbox: list[float],
        bands: list[str],
        date_range: str,
        method: str = "median",
        collection: str | None = None,
        max_cloud_cover: int | None = None,
        max_items: int | None = None,
        catalog: str | None = None,
        cloud_mask: bool = False,
        output_format: str = "geotiff",
        output_mode: str = "json",
    ) -> str:
        """
        Create a temporal composite by combining multiple scenes statistically.

        Searches for scenes in the date range, downloads bands from each,
        then combines them pixel-by-pixel using a statistical method.
        Useful for creating cloud-free composites from cloudy time series.

        Args:
            bbox: Area of interest [west, south, east, north] in EPSG:4326
            bands: Bands to composite (e.g., ["red", "green", "blue"])
            date_range: Date range "YYYY-MM-DD/YYYY-MM-DD"
            method: Statistical method - "median" (default), "mean", "max", "min"
            collection: STAC collection (default: sentinel-2-l2a)
            max_cloud_cover: Maximum cloud cover 0-100 (default: 20)
            max_items: Maximum scenes (default: 10)
            catalog: Catalog name (default: earth_search)
            cloud_mask: Apply SCL cloud masking per scene before compositing
            output_format: Output format - "geotiff" (default) or "png"
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref for the temporal composite

        Example:
            composite = await stac_temporal_composite(
                bbox=[0.85, 51.85, 0.95, 51.92],
                bands=["red", "green", "blue"],
                date_range="2024-06-01/2024-08-31",
                method="median"
            )
        """
        try:
            if len(bbox) != 4:
                return format_response(
                    ErrorResponse(error=ErrorMessages.INVALID_BBOX),
                    output_mode,
                )

            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG
            coll = collection or DEFAULT_COLLECTION
            cloud_max = max_cloud_cover if max_cloud_cover is not None else MAX_CLOUD_COVER
            items_max = max_items if max_items is not None else 10

            def _search() -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                search = client.search(
                    collections=[coll],
                    bbox=bbox,
                    datetime=date_range,
                    query={STACProperty.CLOUD_COVER: {"lt": cloud_max}},
                    max_items=items_max,
                )
                return list(search.items())

            items = await asyncio.to_thread(_search)

            if not items:
                return format_response(
                    ErrorResponse(error=ErrorMessages.NO_RESULTS),
                    output_mode,
                )

            # Cache scenes
            scene_ids: list[str] = []
            for item in items:
                stac_item = STACItem.model_validate(item.to_dict())
                manager.cache_scene(item.id, stac_item, catalog_name)  # type: ignore[union-attr]
                scene_ids.append(item.id)

            result = await manager.temporal_composite(  # type: ignore[union-attr]
                scene_ids,
                bands,
                method=method,
                bbox_4326=bbox,
                cloud_mask=cloud_mask,
                output_format=output_format,
            )

            return format_response(
                TemporalCompositeResponse(
                    scene_ids=scene_ids,
                    bands=bands,
                    method=method,
                    artifact_ref=result.artifact_ref,
                    preview_ref=result.preview_ref,
                    bbox=bbox,
                    crs=result.crs,
                    shape=result.shape,
                    date_range=date_range,
                    output_format=output_format,
                    message=f"Temporal {method} composite from {len(scene_ids)} scene(s)",
                ),
                output_mode,
            )

        except (ValueError, RuntimeError) as e:
            return format_response(ErrorResponse(error=str(e)), output_mode)
        except Exception as e:
            logger.error(f"Temporal composite failed: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)
