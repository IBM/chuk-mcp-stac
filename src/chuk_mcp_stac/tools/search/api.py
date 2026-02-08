"""
MCP tools for searching STAC catalogs.

Provides scene search, describe, catalog/collection listing, and analysis tools.
"""

import asyncio
import json
import logging
import urllib.request

import numpy as np

from ...constants import (
    COLLECTION_CATALOGS,
    COLLECTION_INTELLIGENCE,
    CONFORMANCE_CLASSES,
    DEFAULT_CATALOG,
    DEFAULT_COLLECTION,
    INDEX_BANDS,
    MAX_CLOUD_COVER,
    MAX_ITEMS,
    METADATA_ASSET_KEYS,
    PREVIEW_ASSET_KEYS,
    THUMBNAIL_KEY,
    ErrorMessages,
    STACEndpoints,
    STACProperty,
    SuccessMessages,
    collection_has_cloud_cover,
)
from ...models import (
    BandDetail,
    CatalogInfo,
    CatalogsResponse,
    CollectionDetailResponse,
    CollectionInfo,
    CollectionsResponse,
    CompositeRecipe,
    ConformanceFeature,
    ConformanceResponse,
    CoverageCheckResponse,
    ErrorResponse,
    FindPairsResponse,
    PreviewResponse,
    QueryableProperty,
    QueryablesResponse,
    SceneAsset,
    SceneDetailResponse,
    SceneInfo,
    ScenePair,
    SearchResponse,
    format_response,
)
from ...models.stac import STACItem

logger = logging.getLogger(__name__)


def register_search_tools(mcp: object, manager: object) -> None:
    """
    Register search tools with the MCP server.

    Args:
        mcp: ChukMCPServer instance
        manager: CatalogManager instance
    """

    @mcp.tool  # type: ignore[union-attr]
    async def stac_list_catalogs(
        output_mode: str = "json",
    ) -> str:
        """
        List all known STAC catalogs.

        Returns pre-configured catalog endpoints that can be searched.
        Each catalog hosts different satellite collections.

        Args:
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with catalog names and endpoint URLs

        Tips for LLMs:
            - Use stac_capabilities instead for a full overview including
              collections, bands, and indices
            - Default catalog is earth_search (AWS Element 84)
            - planetary_computer requires no API key (auto-authenticated)

        Example:
            catalogs = await stac_list_catalogs()
        """
        catalogs = [CatalogInfo(name=name, url=url) for name, url in STACEndpoints.ALL.items()]
        return format_response(
            CatalogsResponse(
                catalogs=catalogs,
                default=DEFAULT_CATALOG,
                message=f"{len(catalogs)} catalog(s) available",
            ),
            output_mode,
        )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_list_collections(
        catalog: str | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        List available collections in a STAC catalog.

        Queries the catalog's live API to discover all hosted collections
        with titles, descriptions, and spatial/temporal extents.

        Args:
            catalog: Catalog name (default: earth_search).
                Options: earth_search, planetary_computer, usgs
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON list of collections with titles, descriptions, and extents

        Tips for LLMs:
            - Use this to discover what data is available in a specific catalog
            - For detailed band/composite info on a collection, follow up with
              stac_describe_collection
            - Different catalogs host different collections — if a collection
              isn't found, try another catalog

        Example:
            collections = await stac_list_collections(catalog="earth_search")
        """
        try:
            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG

            # Run STAC client in thread to avoid blocking
            def _list_collections() -> list[CollectionInfo]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                results: list[CollectionInfo] = []
                for coll in client.get_collections():
                    spatial = None
                    temporal = None
                    if coll.extent and coll.extent.spatial and coll.extent.spatial.bboxes:
                        spatial = list(coll.extent.spatial.bboxes[0])
                    if coll.extent and coll.extent.temporal and coll.extent.temporal.intervals:
                        interval = coll.extent.temporal.intervals[0]
                        temporal = [
                            interval[0].isoformat() if interval[0] else None,
                            interval[1].isoformat() if interval[1] else None,
                        ]
                    results.append(
                        CollectionInfo(
                            collection_id=coll.id,
                            title=coll.title,
                            description=coll.description,
                            spatial_extent=spatial,
                            temporal_extent=temporal,
                        )
                    )
                return results

            collections = await asyncio.to_thread(_list_collections)

            return format_response(
                CollectionsResponse(
                    catalog=catalog_name,
                    collection_count=len(collections),
                    collections=collections,
                    message=f"{len(collections)} collection(s) in {catalog_name}",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.CATALOG_ERROR.format(str(e))),
                output_mode,
            )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_search(
        bbox: list[float],
        collection: str | None = None,
        date_range: str | None = None,
        max_cloud_cover: int | None = None,
        max_items: int | None = None,
        catalog: str | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        Search for satellite scenes matching spatial and temporal criteria.

        This is the primary entry point for finding satellite imagery.
        Results are cached for follow-up describe/download operations.

        Args:
            bbox: Bounding box [west, south, east, north] in EPSG:4326.
                Example: [-0.7, 52.7, 0.5, 53.7] for Lincolnshire, UK
            collection: STAC collection (default: sentinel-2-l2a).
                Options:
                - sentinel-2-l2a: Optical imagery, 10-20m resolution, 13 bands
                - sentinel-2-c1-l2a: Reprocessed Sentinel-2 archive
                - landsat-c2-l2: Optical imagery, 30m resolution, 11 bands
                - sentinel-1-grd: SAR radar, 10m, sees through clouds (VV/VH)
                - cop-dem-glo-30: Global elevation data, 30m
            date_range: Date range as "YYYY-MM-DD/YYYY-MM-DD" (optional).
                Omit for cop-dem-glo-30 (no temporal dimension)
            max_cloud_cover: Maximum cloud cover percentage 0-100 (default: 20).
                Ignored for non-optical collections (sentinel-1-grd, cop-dem-glo-30).
                Increase to 30-50 if getting zero results
            max_items: Maximum results to return (default: 10)
            catalog: Catalog name (default: earth_search).
                Options: earth_search, planetary_computer, usgs
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with matching scenes sorted by cloud cover (optical) or date

        Tips for LLMs:
            - Typical workflow: stac_search → stac_describe_scene → stac_download_bands
            - For cloudy regions (e.g., UK autumn), increase max_cloud_cover to 50
              or use sentinel-1-grd (SAR radar, not affected by clouds)
            - For flood mapping: use sentinel-1-grd (water appears dark in VV/VH)
            - For vegetation analysis: use sentinel-2-l2a with NDVI index
            - For elevation/terrain: use cop-dem-glo-30 (no date_range needed)
            - If zero results, check the hints field for suggestions (try different
              catalog, increase cloud cover, widen date range)
            - Scenes are cached — use scene_id in subsequent describe/download calls

        Example:
            results = await stac_search(
                bbox=[0.8, 51.8, 1.0, 51.95],
                date_range="2024-06-01/2024-08-31",
                max_cloud_cover=10
            )
        """
        try:
            if len(bbox) != 4:
                return format_response(
                    ErrorResponse(error=ErrorMessages.INVALID_BBOX),
                    output_mode,
                )

            west, south, east, north = bbox
            if (
                west >= east
                or south >= north
                or not (-180 <= west <= 180)
                or not (-180 <= east <= 180)
                or not (-90 <= south <= 90)
                or not (-90 <= north <= 90)
            ):
                return format_response(
                    ErrorResponse(
                        error=ErrorMessages.INVALID_BBOX_VALUES.format(
                            west=west, east=east, south=south, north=north
                        )
                    ),
                    output_mode,
                )

            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG
            coll = collection or DEFAULT_COLLECTION
            cloud_max = max_cloud_cover if max_cloud_cover is not None else MAX_CLOUD_COVER
            items_max = max_items if max_items is not None else MAX_ITEMS
            has_cloud = collection_has_cloud_cover(coll)

            def _search() -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]

                search_kwargs: dict[str, object] = {
                    "collections": [coll],
                    "bbox": bbox,
                    "max_items": items_max,
                }
                if date_range:
                    search_kwargs["datetime"] = date_range

                # Only apply cloud cover filter for optical collections
                if has_cloud:
                    search_kwargs["query"] = {STACProperty.CLOUD_COVER: {"lt": cloud_max}}

                search = client.search(**search_kwargs)
                items = list(search.items())

                # Sort by cloud cover ascending (optical) or datetime (non-optical)
                if has_cloud:
                    items.sort(
                        key=lambda x: x.properties.get(STACProperty.CLOUD_COVER, 100)
                    )
                else:
                    items.sort(
                        key=lambda x: x.properties.get(STACProperty.DATETIME, "")
                    )

                return items

            items = await asyncio.to_thread(_search)

            scenes: list[SceneInfo] = []
            for item in items:
                # Convert pystac item to typed STACItem and cache
                stac_item = STACItem.model_validate(item.to_dict())
                manager.cache_scene(item.id, stac_item, catalog_name)  # type: ignore[union-attr]

                thumbnail = None
                if THUMBNAIL_KEY in item.assets:
                    thumbnail = item.assets[THUMBNAIL_KEY].href

                scenes.append(
                    SceneInfo(
                        scene_id=item.id,
                        collection=coll,
                        datetime=stac_item.properties.datetime,
                        bbox=stac_item.bbox if stac_item.bbox else bbox,
                        cloud_cover=stac_item.properties.cloud_cover,
                        thumbnail_url=thumbnail,
                        asset_count=len(stac_item.assets),
                    )
                )

            # Build hints
            hints: list[str] = []

            if not has_cloud:
                hints.append(
                    f"Cloud cover filter skipped for '{coll}' (non-optical collection)."
                )

            if not scenes:
                msg = ErrorMessages.NO_RESULTS

                filters_applied = [f"bbox={bbox}"]
                if date_range:
                    filters_applied.append(f"date_range={date_range}")
                if has_cloud:
                    filters_applied.append(f"max_cloud_cover={cloud_max}%")
                hints.append(f"Filters applied: {', '.join(filters_applied)}")

                if has_cloud and cloud_max < 50:
                    hints.append(
                        f"Try increasing max_cloud_cover (currently {cloud_max}%). "
                        "Values of 30-50 often yield more results."
                    )

                alt_catalogs = COLLECTION_CATALOGS.get(coll, [])
                other_catalogs = [c for c in alt_catalogs if c != catalog_name]
                if other_catalogs:
                    hints.append(
                        f"Collection '{coll}' is also available in: "
                        f"{', '.join(other_catalogs)}. Try searching a different catalog."
                    )
            else:
                msg = SuccessMessages.SEARCH_COMPLETE.format(len(scenes))

            return format_response(
                SearchResponse(
                    catalog=catalog_name,
                    collection=coll,
                    bbox=bbox,
                    date_range=date_range,
                    max_cloud_cover=cloud_max if has_cloud else None,
                    scene_count=len(scenes),
                    scenes=scenes,
                    hints=hints,
                    message=msg,
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"STAC search failed: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_describe_scene(
        scene_id: str,
        output_mode: str = "json",
    ) -> str:
        """
        Get detailed information about a specific scene.

        Shows all available assets/bands, properties, CRS, and download URLs.
        The scene must have been returned by a previous stac_search call.

        Args:
            scene_id: Scene identifier from a search result (use scene_id from stac_search)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with full scene details including all assets, CRS, and properties

        Tips for LLMs:
            - Call this after stac_search to see available bands before downloading
            - The assets list shows every downloadable band and its resolution
            - Use the band keys (e.g., red, nir, scl) in stac_download_bands
            - Check cloud_cover to decide if the scene is usable

        Example:
            detail = await stac_describe_scene(
                scene_id="S2B_MSIL2A_20240715T105629_N0510_R094_T31UCR_20240715T143301"
            )
        """
        try:
            item = manager.get_cached_scene(scene_id)  # type: ignore[union-attr]
            if not item:
                return format_response(
                    ErrorResponse(error=ErrorMessages.SCENE_NOT_FOUND.format(scene_id)),
                    output_mode,
                )

            assets: list[SceneAsset] = []
            for key, asset in item.assets.items():
                # Skip non-data assets
                if key in METADATA_ASSET_KEYS:
                    continue

                resolution = None
                if asset.gsd is not None:
                    resolution = asset.gsd
                elif asset.eo_bands:
                    first_band = asset.eo_bands[0]
                    if STACProperty.GSD in first_band:
                        resolution = first_band[STACProperty.GSD]

                assets.append(
                    SceneAsset(
                        key=key,
                        href=asset.href,
                        media_type=asset.media_type,
                        resolution_m=resolution,
                    )
                )

            # Build properties dict for the response (extra fields from model)
            props_dict = item.properties.model_dump(by_alias=True, exclude_none=True)

            return format_response(
                SceneDetailResponse(
                    scene_id=scene_id,
                    collection=item.collection,
                    datetime=item.properties.datetime,
                    bbox=item.bbox,
                    cloud_cover=item.properties.cloud_cover,
                    crs=item.crs_string,
                    assets=assets,
                    properties=props_dict,
                    message=f"Scene {scene_id}: {len(assets)} data asset(s)",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to describe scene: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_preview(
        scene_id: str,
        output_mode: str = "json",
    ) -> str:
        """
        Get a preview/thumbnail URL for a scene.

        Returns the URL of the scene's thumbnail or rendered preview image.
        Much faster than downloading full bands — useful for quick browsing.

        The scene must have been returned by a previous stac_search call.

        Args:
            scene_id: Scene identifier from a search result (use scene_id from stac_search)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with preview_url for the scene's thumbnail

        Tips for LLMs:
            - Use for quick visual checks before committing to full band downloads
            - The preview URL is a remote image that can be displayed directly
            - Not all scenes have thumbnails — check for errors in the response

        Example:
            preview = await stac_preview(scene_id="S2B_...")
        """
        try:
            item = manager.get_cached_scene(scene_id)  # type: ignore[union-attr]
            if not item:
                return format_response(
                    ErrorResponse(error=ErrorMessages.SCENE_NOT_FOUND.format(scene_id)),
                    output_mode,
                )

            # Search for preview assets in preference order
            for key in PREVIEW_ASSET_KEYS:
                if key in item.assets:
                    asset = item.assets[key]
                    return format_response(
                        PreviewResponse(
                            scene_id=scene_id,
                            preview_url=asset.href,
                            asset_key=key,
                            media_type=asset.media_type,
                            message=f"Preview available via '{key}' asset",
                        ),
                        output_mode,
                    )

            return format_response(
                ErrorResponse(
                    error=f"No preview available for scene '{scene_id}'. "
                    f"Looked for asset keys: {', '.join(PREVIEW_ASSET_KEYS)}"
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to get preview: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_describe_collection(
        collection_id: str,
        catalog: str | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        Get detailed information about a STAC collection.

        Returns band wavelengths, recommended composites, supported spectral
        indices, cloud masking info, and LLM-friendly usage guidance.

        For known collections (Sentinel-2, Landsat, Sentinel-1, DEM), provides
        rich metadata including band names needed for download tools.
        Unknown collections still return live STAC metadata.

        Args:
            collection_id: Collection identifier.
                Options: sentinel-2-l2a, sentinel-2-c1-l2a, landsat-c2-l2,
                         sentinel-1-grd, cop-dem-glo-30
            catalog: Catalog name (default: earth_search).
                Options: earth_search, planetary_computer, usgs
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with band details, composites, spectral indices, and guidance

        Tips for LLMs:
            - Call this to discover band names before using stac_download_bands
            - The composites field lists pre-defined band combinations
              (e.g., true_color = [red, green, blue])
            - The spectral_indices field shows which indices this collection supports
            - The llm_guidance field contains domain-specific usage advice
            - Check cloud_mask_band — if None, the collection is non-optical
              (SAR radar or DEM) and cloud_mask=True will fail

        Example:
            detail = await stac_describe_collection(
                collection_id="sentinel-2-l2a"
            )
        """
        try:
            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG

            def _get_collection() -> object:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                return client.get_collection(collection_id)

            coll = await asyncio.to_thread(_get_collection)

            # Extract live metadata
            title = getattr(coll, "title", None)
            description = getattr(coll, "description", None)

            spatial = None
            temporal = None
            extent = getattr(coll, "extent", None)
            if extent:
                sp = getattr(extent, "spatial", None)
                if sp and hasattr(sp, "bboxes") and sp.bboxes:
                    spatial = list(sp.bboxes[0])
                tp = getattr(extent, "temporal", None)
                if tp and hasattr(tp, "intervals") and tp.intervals:
                    interval = tp.intervals[0]
                    temporal = [
                        interval[0].isoformat() if interval[0] else None,
                        interval[1].isoformat() if interval[1] else None,
                    ]

            # Merge with static intelligence
            intel = COLLECTION_INTELLIGENCE.get(collection_id, {})

            bands: list[BandDetail] = []
            for band_name, band_info in intel.get("bands", {}).items():
                bands.append(
                    BandDetail(
                        name=band_name,
                        wavelength_nm=band_info["wavelength_nm"],
                        resolution_m=band_info["resolution_m"],
                    )
                )

            composites: list[CompositeRecipe] = []
            for comp_name, comp_info in intel.get("composites", {}).items():
                composites.append(
                    CompositeRecipe(
                        name=comp_name,
                        bands=comp_info["bands"],
                        description=comp_info["description"],
                    )
                )

            # Detect supported spectral indices
            band_names = set(intel.get("bands", {}).keys())
            # Also add "nir" if "nir08" present (Landsat NIR → NDVI compatible)
            if "nir08" in band_names and "nir" not in band_names:
                # Don't add nir — Landsat uses nir08 for different index formulas
                pass
            supported_indices = []
            for index_name, required in INDEX_BANDS.items():
                if all(b in band_names for b in required):
                    supported_indices.append(index_name)

            return format_response(
                CollectionDetailResponse(
                    collection_id=collection_id,
                    catalog=catalog_name,
                    title=title,
                    description=description,
                    spatial_extent=spatial,
                    temporal_extent=temporal,
                    platform=intel.get("platform"),
                    instrument=intel.get("instrument"),
                    bands=bands,
                    composites=composites,
                    spectral_indices=supported_indices,
                    cloud_mask_band=intel.get("cloud_mask_band"),
                    llm_guidance=intel.get("llm_guidance"),
                    message=f"Collection '{collection_id}' with {len(bands)} bands",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to describe collection: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.CATALOG_ERROR.format(str(e))),
                output_mode,
            )

    @mcp.tool  # type: ignore[union-attr]
    async def stac_get_conformance(
        catalog: str | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        Check which STAC API features a catalog supports.

        Reads the catalog's conformance URIs and matches them against
        known STAC API conformance classes to determine feature support
        (core, item_search, filter, sort, fields, query, collections).

        Args:
            catalog: Catalog name (default: earth_search).
                Options: earth_search, planetary_computer, usgs
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with feature support flags and raw conformance URIs

        Tips for LLMs:
            - Rarely needed — most workflows don't require conformance checking
            - Useful for debugging when a catalog doesn't support expected features
            - Check for "query" support if advanced filtering is needed

        Example:
            conformance = await stac_get_conformance(catalog="earth_search")
        """
        try:
            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG

            def _get_conformance() -> list[str]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                return list(getattr(client, "conformance", None) or [])

            raw_uris = await asyncio.to_thread(_get_conformance)
            uri_set = set(raw_uris)

            if not raw_uris:
                return format_response(
                    ConformanceResponse(
                        catalog=catalog_name,
                        conformance_available=False,
                        features=[],
                        raw_uris=[],
                        message=f"Catalog '{catalog_name}' does not expose conformance information",
                    ),
                    output_mode,
                )

            features: list[ConformanceFeature] = []
            for feature_name, known_uris in CONFORMANCE_CLASSES.items():
                matching = [uri for uri in known_uris if uri in uri_set]
                features.append(
                    ConformanceFeature(
                        name=feature_name,
                        supported=len(matching) > 0,
                        matching_uris=matching,
                    )
                )

            supported_count = sum(1 for f in features if f.supported)

            return format_response(
                ConformanceResponse(
                    catalog=catalog_name,
                    conformance_available=True,
                    features=features,
                    raw_uris=raw_uris,
                    message=f"{supported_count}/{len(features)} features supported",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to get conformance: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.CATALOG_ERROR.format(str(e))),
                output_mode,
            )

    # ─── Analysis Tools ─────────────────────────────────────────────────────

    def _bbox_overlap_percent(bbox_a: list[float], bbox_b: list[float]) -> float:
        """Compute overlap percentage between two bboxes (intersection / union * 100)."""
        w = max(0, min(bbox_a[2], bbox_b[2]) - max(bbox_a[0], bbox_b[0]))
        h = max(0, min(bbox_a[3], bbox_b[3]) - max(bbox_a[1], bbox_b[1]))
        intersection = w * h
        if intersection == 0:
            return 0.0
        area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
        area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])
        union = area_a + area_b - intersection
        if union <= 0:
            return 0.0
        return (intersection / union) * 100

    @mcp.tool  # type: ignore[union-attr]
    async def stac_find_pairs(
        bbox: list[float],
        before_range: str,
        after_range: str,
        collection: str | None = None,
        max_cloud_cover: int | None = None,
        catalog: str | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        Find before/after scene pairs for change detection.

        Searches two date ranges and matches scenes by spatial overlap,
        useful for detecting changes between time periods (e.g., flood
        damage, urban growth, deforestation, seasonal vegetation change).

        Args:
            bbox: Bounding box [west, south, east, north] in EPSG:4326
            before_range: Before date range "YYYY-MM-DD/YYYY-MM-DD"
            after_range: After date range "YYYY-MM-DD/YYYY-MM-DD"
            collection: STAC collection (default: sentinel-2-l2a).
                Options: sentinel-2-l2a, sentinel-2-c1-l2a, landsat-c2-l2,
                         sentinel-1-grd, cop-dem-glo-30
            max_cloud_cover: Maximum cloud cover percentage 0-100 (default: 20).
                Ignored for non-optical collections (sentinel-1-grd, cop-dem-glo-30).
            catalog: Catalog name (default: earth_search).
                Options: earth_search, planetary_computer, usgs
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with matched scene pairs sorted by overlap percentage

        Tips for LLMs:
            - Best for change detection workflows: find pairs, then download
              the same bands for before/after scenes and compare
            - For flood mapping: use sentinel-1-grd (SAR sees through clouds)
              with before_range = dry season, after_range = flood event
            - For vegetation change: use sentinel-2-l2a, then compute NDVI
              for each scene in the pair
            - Higher overlap_percent means better spatial coverage for comparison
            - Follow up with stac_download_bands or stac_compute_index on each
              scene in the pair

        Example:
            pairs = await stac_find_pairs(
                bbox=[0.8, 51.8, 1.0, 51.95],
                before_range="2024-01-01/2024-03-31",
                after_range="2024-07-01/2024-09-30"
            )
        """
        try:
            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG
            coll = collection or DEFAULT_COLLECTION
            cloud_max = max_cloud_cover if max_cloud_cover is not None else MAX_CLOUD_COVER
            has_cloud = collection_has_cloud_cover(coll)

            def _search_range(date_range: str) -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]
                search_kwargs: dict[str, object] = {
                    "collections": [coll],
                    "bbox": bbox,
                    "datetime": date_range,
                    "max_items": MAX_ITEMS,
                }
                if has_cloud:
                    search_kwargs["query"] = {
                        STACProperty.CLOUD_COVER: {"lt": cloud_max},
                    }
                search = client.search(**search_kwargs)
                return list(search.items())

            before_items, after_items = await asyncio.gather(
                asyncio.to_thread(_search_range, before_range),
                asyncio.to_thread(_search_range, after_range),
            )

            # Cache all found items
            for item in before_items + after_items:
                stac_item = STACItem.model_validate(item.to_dict())
                manager.cache_scene(item.id, stac_item, catalog_name)  # type: ignore[union-attr]

            # Build pairs with overlap
            pairs: list[ScenePair] = []
            for b_item in before_items:
                b_bbox = list(b_item.bbox) if b_item.bbox else bbox
                b_dt = b_item.properties.get("datetime", "")
                for a_item in after_items:
                    a_bbox = list(a_item.bbox) if a_item.bbox else bbox
                    a_dt = a_item.properties.get("datetime", "")
                    overlap = _bbox_overlap_percent(b_bbox, a_bbox)
                    if overlap > 0:
                        pairs.append(
                            ScenePair(
                                before_scene_id=b_item.id,
                                before_datetime=b_dt,
                                after_scene_id=a_item.id,
                                after_datetime=a_dt,
                                overlap_percent=round(overlap, 2),
                            )
                        )

            pairs.sort(key=lambda p: p.overlap_percent, reverse=True)

            return format_response(
                FindPairsResponse(
                    bbox=bbox,
                    collection=coll,
                    before_range=before_range,
                    after_range=after_range,
                    pair_count=len(pairs),
                    pairs=pairs,
                    message=f"Found {len(pairs)} pair(s) from {len(before_items)} before "
                    f"and {len(after_items)} after scene(s)",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to find pairs: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_coverage_check(
        bbox: list[float],
        scene_ids: list[str],
        output_mode: str = "json",
    ) -> str:
        """
        Check if cached scenes fully cover a requested bounding box.

        Rasterizes the target bbox into a grid and checks which cells
        are covered by the provided scenes. Useful for planning mosaics
        to ensure gap-free coverage.

        Args:
            bbox: Target bounding box [west, south, east, north] in EPSG:4326
            scene_ids: Scene identifiers (must be cached from prior stac_search calls)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with coverage percentage and uncovered areas

        Tips for LLMs:
            - Call this before stac_mosaic to verify scenes fully cover your
              area of interest
            - If coverage is less than 100%, search for more scenes or
              widen the date range to find additional tiles
            - Scenes must have been found by a prior stac_search call

        Example:
            check = await stac_coverage_check(
                bbox=[0.8, 51.8, 1.0, 51.95],
                scene_ids=["S2B_...", "S2A_..."]
            )
        """
        try:
            if len(bbox) != 4:
                return format_response(
                    ErrorResponse(error=ErrorMessages.INVALID_BBOX),
                    output_mode,
                )

            west, south, east, north = bbox
            grid_w, grid_h = 100, 100
            grid = np.zeros((grid_h, grid_w), dtype=bool)

            valid_ids: list[str] = []
            for sid in scene_ids:
                item = manager.get_cached_scene(sid)  # type: ignore[union-attr]
                if not item:
                    continue
                valid_ids.append(sid)

                s_bbox = item.bbox if item.bbox else []
                if len(s_bbox) != 4:
                    continue

                # Map scene bbox to grid coords (row 0 = north, row N = south)
                col_start = max(0, int((s_bbox[0] - west) / (east - west) * grid_w))
                col_end = min(grid_w, int((s_bbox[2] - west) / (east - west) * grid_w))
                row_start = max(0, int((north - s_bbox[3]) / (north - south) * grid_h))
                row_end = min(grid_h, int((north - s_bbox[1]) / (north - south) * grid_h))

                if col_start < col_end and row_start < row_end:
                    grid[row_start:row_end, col_start:col_end] = True

            covered = int(np.sum(grid))
            total = grid_w * grid_h
            coverage_pct = round((covered / total) * 100, 2) if total > 0 else 0.0
            fully = coverage_pct >= 100.0

            # Identify uncovered areas as bboxes (simplified: up to 4 quadrants)
            uncovered_areas: list[list[float]] = []
            if not fully:
                # Check quadrants for uncovered regions
                mid_col = grid_w // 2
                mid_row = grid_h // 2
                mid_lon = (west + east) / 2
                mid_lat = (south + north) / 2
                quadrants = [
                    (0, mid_row, 0, mid_col, [west, mid_lat, mid_lon, north]),
                    (0, mid_row, mid_col, grid_w, [mid_lon, mid_lat, east, north]),
                    (mid_row, grid_h, 0, mid_col, [west, south, mid_lon, mid_lat]),
                    (mid_row, grid_h, mid_col, grid_w, [mid_lon, south, east, mid_lat]),
                ]
                for r0, r1, c0, c1, q_bbox in quadrants:
                    sub = grid[r0:r1, c0:c1]
                    if not np.all(sub):
                        uncovered_areas.append(q_bbox)

            return format_response(
                CoverageCheckResponse(
                    bbox=bbox,
                    scene_count=len(valid_ids),
                    fully_covered=fully,
                    coverage_percent=coverage_pct,
                    uncovered_areas=uncovered_areas,
                    scene_ids=valid_ids,
                    message=f"{coverage_pct:.1f}% coverage from {len(valid_ids)} scene(s)",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Coverage check failed: {e}")
            return format_response(ErrorResponse(error=str(e)), output_mode)

    @mcp.tool  # type: ignore[union-attr]
    async def stac_queryables(
        catalog: str | None = None,
        collection: str | None = None,
        output_mode: str = "json",
    ) -> str:
        """
        Fetch queryable properties from a STAC API.

        Returns the properties that can be used in search queries,
        including their types and allowed values. Useful for understanding
        what filtering options are available.

        Args:
            catalog: Catalog name (default: earth_search).
                Options: earth_search, planetary_computer, usgs
            collection: Optional collection to scope queryables
                (e.g., "sentinel-2-l2a" for collection-specific properties)
            output_mode: Response format - "json" (default) or "text"

        Returns:
            JSON with queryable property names, types, and descriptions

        Tips for LLMs:
            - Rarely needed — stac_search handles common filters automatically
            - Useful when debugging why searches return unexpected results
            - Different catalogs support different queryable properties

        Example:
            queryables = await stac_queryables(
                catalog="earth_search",
                collection="sentinel-2-l2a"
            )
        """
        try:
            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG

            if collection:
                url = f"{catalog_url}/collections/{collection}/queryables"
            else:
                url = f"{catalog_url}/queryables"

            def _fetch_queryables() -> dict:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                    return json.loads(resp.read().decode())

            data = await asyncio.to_thread(_fetch_queryables)

            properties = data.get("properties", {})
            queryables: list[QueryableProperty] = []
            for name, schema in properties.items():
                q_type = schema.get("type", "unknown")
                if isinstance(q_type, list):
                    q_type = ", ".join(str(t) for t in q_type)
                queryables.append(
                    QueryableProperty(
                        name=name,
                        type=q_type,
                        description=schema.get("description", ""),
                        enum_values=[str(v) for v in schema.get("enum", [])],
                    )
                )

            return format_response(
                QueryablesResponse(
                    catalog=catalog_name,
                    collection=collection,
                    queryable_count=len(queryables),
                    queryables=queryables,
                    message=f"{len(queryables)} queryable propert(ies) available",
                ),
                output_mode,
            )

        except Exception as e:
            logger.error(f"Failed to fetch queryables: {e}")
            return format_response(
                ErrorResponse(error=ErrorMessages.CATALOG_ERROR.format(str(e))),
                output_mode,
            )
