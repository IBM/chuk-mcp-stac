"""
MCP tools for downloading satellite band data from STAC scenes.

Tools delegate to CatalogManager.download_bands() which handles the
full pipeline: COG reading -> in-memory GeoTIFF -> artifact storage.
Tools validate parameters and format responses — they never touch bytes.
"""

import asyncio
import logging

from ...constants import (
    COLLECTION_CATALOGS,
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
    collection_has_cloud_cover,
)
from ...models import (
    ArtifactResponse,
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

    def _aws_error_hint(scene_id: str, error: str) -> str:
        """Append catalog-switching hint when S3 access fails."""
        aws_keywords = ("AWS_SECRET_ACCESS_KEY", "AWS_NO_SIGN_REQUEST", "AccessDenied")
        if not any(kw in str(error) for kw in aws_keywords):
            return str(error)

        catalog = manager.get_scene_catalog(scene_id)  # type: ignore[union-attr]
        item = manager.get_cached_scene(scene_id)  # type: ignore[union-attr]
        collection = item.collection if item else ""
        alt_catalogs = [c for c in COLLECTION_CATALOGS.get(collection, []) if c != catalog]

        msg = f"S3 access denied for this scene (catalog: {catalog}). "
        if alt_catalogs:
            msg += (
                f"Try re-searching with catalog='{alt_catalogs[0]}' — "
                f"it provides authenticated access to {collection} data."
            )
        else:
            msg += "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for requester-pays access."
        return msg

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
            scene_id: Scene identifier from a previous stac_search call
            bands: Band names to download. Common names:
                - Sentinel-2: red, green, blue, nir, swir16, swir22, rededge1-3, scl
                - Landsat: red, green, blue, nir08, swir16, swir22, coastal, qa_pixel
                - Sentinel-1: vv, vh
                - DEM: data
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north].
                Strongly recommended to avoid downloading full tiles
            output_format: "geotiff" (default, lossless, for analysis) or
                "png" (8-bit lossy with percentile stretch, for preview/display)
            cloud_mask: Apply SCL-based cloud masking (Sentinel-2 only).
                Masked pixels become 0 (integer) or NaN (float)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref, shape, dtype, and optional preview_ref

        Tips for LLMs:
            - Use stac_describe_scene first to see available band names
            - Always provide a bbox to limit download size
            - Use output_format="png" when the user wants to see the image
            - GeoTIFF preserves full radiometric precision for analysis
            - A PNG preview is auto-generated alongside GeoTIFF downloads
            - For RGB visualisation, prefer stac_download_rgb (simpler)
            - For spectral indices, prefer stac_compute_index (automatic)

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
            error_msg = _aws_error_hint(scene_id, str(e))
            return format_response(
                ErrorResponse(error=error_msg),
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
        automatically selects red, green, blue bands. This is the
        simplest way to get a visual satellite image.

        Args:
            scene_id: Scene identifier from a previous stac_search call
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north].
                Strongly recommended to avoid downloading full tiles
            output_format: "geotiff" (default, lossless) or
                "png" (8-bit lossy, suitable for inline display by LLMs)
            cloud_mask: Apply SCL-based cloud masking (Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref for the RGB composite

        Tips for LLMs:
            - Use output_format="png" when the user wants to see the image —
              PNG can be rendered inline
            - GeoTIFF preserves full 16-bit precision but cannot be displayed inline
            - For false-color composites (e.g., NIR/Red/Green), use
              stac_download_composite instead
            - Only works for optical collections (Sentinel-2, Landsat) that
              have red, green, blue bands

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
            error_msg = _aws_error_hint(scene_id, str(e))
            return format_response(
                ErrorResponse(error=error_msg),
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

        Creates a composite from any combination of bands. Band order
        determines RGB channel mapping (first=R, second=G, third=B).

        Args:
            scene_id: Scene identifier from a previous stac_search call
            bands: Band names for the composite (order = R,G,B channels).
                Common recipes:
                - ["nir", "red", "green"] — false colour infrared (vegetation=red)
                - ["swir16", "nir", "red"] — agriculture (crops=bright green)
                - ["swir16", "swir22", "red"] — geology/minerals
            composite_name: Label for the composite (e.g., "false_color_ir")
            bbox: Optional crop bbox in EPSG:4326 [west, south, east, north]
            output_format: "geotiff" (default, lossless) or "png" (8-bit preview)
            cloud_mask: Apply SCL-based cloud masking (Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref for the composite

        Tips for LLMs:
            - Use stac_describe_collection to see pre-defined composite recipes
            - Band order matters: first band → Red, second → Green, third → Blue
            - For true-colour RGB, use stac_download_rgb instead (simpler)
            - For single-value analysis, use stac_compute_index (e.g., NDVI)

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
                ErrorResponse(error=_aws_error_hint(scene_id, str(e))),
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

        Combines overlapping scenes into a single seamless raster.
        Useful when your area of interest spans multiple satellite tiles.

        Args:
            scene_ids: List of scene identifiers to mosaic (from stac_search)
            bands: Bands to include (e.g., ["red", "green", "blue"])
            bbox: Output bounding box [west, south, east, north] in EPSG:4326.
                Defaults to union of all scenes if not specified
            output_format: "geotiff" (default, lossless) or "png" (8-bit preview)
            cloud_mask: Apply SCL-based cloud masking per scene before merge
                (Sentinel-2 only)
            method: Merge method:
                - "last" (default): later scenes overwrite earlier in overlap areas
                - "quality": SCL-based best-pixel selection — picks the clearest
                  pixel from overlapping scenes (Sentinel-2 only)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with artifact_ref for the mosaic raster

        Tips for LLMs:
            - Use stac_coverage_check first to verify scenes cover the target area
            - Use method="quality" for cloud-free mosaics from Sentinel-2 data
            - Use method="last" for quick mosaics or non-optical data
            - For temporal compositing (e.g., seasonal median), use
              stac_temporal_composite instead

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

        Tips for LLMs:
            - Use stac_capabilities to see all available indices and required bands
            - Interpretation guide:
              - NDVI: >0.6 dense vegetation, 0.2-0.6 moderate, <0.2 bare/water
              - NDWI: >0 water, <0 land; useful for flood mapping
              - NDBI: >0 built-up, <0 natural land cover
              - EVI: similar to NDVI but corrects for atmospheric and soil effects
              - SAVI: like NDVI but better in areas with sparse vegetation
              - BSI: >0 bare soil, <0 vegetated
            - Only works for optical collections (Sentinel-2, Landsat)
            - Enable cloud_mask=True for cleaner results with Sentinel-2 data
            - For temporal change analysis, compute the same index on multiple
              dates and compare value_range

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
                ErrorResponse(error=_aws_error_hint(scene_id, str(e))),
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

        Tips for LLMs:
            - Use for monitoring change over time (vegetation growth, flood extent,
              urban expansion)
            - Pair with stac_compute_index on each date's artifact for temporal
              index analysis (e.g., NDVI over a growing season)
            - Keep bbox small — each date downloads full band data
            - Use max_cloud_cover=10 for cleaner optical time series
            - For a single cloud-free image from a date range, use
              stac_temporal_composite with method="median" instead
            - max_items limits the number of dates; set higher for dense
              temporal sampling or lower to reduce download volume
            - Cloud cover filter is automatically skipped for non-optical
              collections (sentinel-1-grd, cop-dem-glo-30)

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
            has_cloud = collection_has_cloud_cover(coll)

            def _search_time_series() -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                search_kwargs: dict[str, object] = {
                    "collections": [coll],
                    "bbox": bbox,
                    "datetime": date_range,
                    "max_items": items_max,
                }
                if has_cloud:
                    search_kwargs["query"] = {
                        STACProperty.CLOUD_COVER: {"lt": cloud_max},
                    }
                search = client.search(**search_kwargs)
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

        Tips for LLMs:
            - Call this BEFORE large downloads to check feasibility
            - If estimated_mb > 500, suggest a smaller bbox or fewer bands
            - No pixel data is read — only COG headers, so this is very fast
            - Use the per-band breakdown to see which bands are largest
              (e.g., 10m bands are ~4x larger than 20m bands)
            - Useful for planning stac_mosaic or stac_temporal_composite
              where multiple scenes multiply the total data volume

        Example:
            estimate = await stac_estimate_size(
                scene_id="S2B_...",
                bands=["red", "nir"],
                bbox=[0.85, 51.85, 0.95, 51.92]
            )
        """
        try:
            result = await manager.estimate_size(scene_id, bands, bbox)  # type: ignore[union-attr]

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

        Tips for LLMs:
            - Method selection:
              - "median" (default): best for cloud-free composites — robust to
                outliers from clouds/shadows
              - "mean": smooth average, good for general baselines
              - "max": captures peak values (e.g., peak NDVI in a growing season)
              - "min": captures minimum values (e.g., lowest water extent)
            - Enable cloud_mask=True with Sentinel-2 for best results — masks
              clouds before compositing so they don't affect the statistics
            - Use a 2-3 month date range for seasonal composites
            - For per-date outputs instead of a single composite, use
              stac_time_series
            - Cloud cover filter is automatically skipped for non-optical
              collections (sentinel-1-grd, cop-dem-glo-30)
            - max_items defaults to 10 — increase for denser temporal sampling

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
            has_cloud = collection_has_cloud_cover(coll)

            def _search() -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                search_kwargs: dict[str, object] = {
                    "collections": [coll],
                    "bbox": bbox,
                    "datetime": date_range,
                    "max_items": items_max,
                }
                if has_cloud:
                    search_kwargs["query"] = {
                        STACProperty.CLOUD_COVER: {"lt": cloud_max},
                    }
                search = client.search(**search_kwargs)
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

    @mcp.tool  # type: ignore[union-attr]
    async def stac_get_artifact(
        artifact_ref: str,
        output_mode: str = "json",
    ) -> str:
        """
        Retrieve a stored artifact and save it as a local file for viewing.

        Downloads the artifact bytes from the artifact store and writes
        them to a local file. Returns the file path so the image can
        be opened in any viewer.

        Args:
            artifact_ref: Artifact ID from a previous download tool call
                (the artifact_ref or preview_ref value)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with file_path, mime type, size, and artifact metadata

        Tips for LLMs:
            - Use the preview_ref (PNG) from download results for quick viewing
            - Use the artifact_ref (GeoTIFF) for full-resolution geospatial data
            - The file is saved to a temporary directory and can be opened
              with any image viewer or GIS application
            - PNG files can be opened with: open <file_path> (macOS)
            - GeoTIFF files can be opened with QGIS, rasterio, or similar

        Example:
            result = await stac_get_artifact(
                artifact_ref="a7c666e6555548aea2d5351cc65bf173"
            )
            # Returns: {"file_path": "/tmp/stac_artifacts/a7c666...png", ...}
        """
        import os

        try:
            store = manager._get_store()  # type: ignore[union-attr]
            if not store:
                return format_response(
                    ErrorResponse(error="No artifact store available."),
                    output_mode,
                )

            # Retrieve artifact data and metadata
            data: bytes = await store.retrieve(artifact_ref)
            meta: dict = {}
            mime = "application/octet-stream"
            try:
                meta_obj = await store.metadata(artifact_ref)
                if hasattr(meta_obj, "mime") and meta_obj.mime:
                    mime = meta_obj.mime
                if hasattr(meta_obj, "meta") and meta_obj.meta:
                    meta = meta_obj.meta
            except Exception:
                pass

            # Determine file extension from mime type
            ext = ".bin"
            if "png" in mime:
                ext = ".png"
            elif "tiff" in mime or "tif" in mime:
                ext = ".tif"

            # Save to a local directory
            out_dir = os.path.join(os.path.expanduser("~"), ".stac_artifacts")
            os.makedirs(out_dir, exist_ok=True)
            file_path = os.path.join(out_dir, f"{artifact_ref}{ext}")

            with open(file_path, "wb") as f:
                f.write(data)

            return format_response(
                ArtifactResponse(
                    artifact_ref=artifact_ref,
                    file_path=file_path,
                    mime=mime,
                    size_bytes=len(data),
                    metadata=meta,
                    message=f"Artifact saved to {file_path}",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Artifact retrieval failed: {e}")
            return format_response(
                ErrorResponse(error=f"Could not retrieve artifact: {str(e)}"),
                output_mode,
            )
