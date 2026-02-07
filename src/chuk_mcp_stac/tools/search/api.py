"""
MCP tools for searching STAC catalogs.

Provides scene search, describe, and catalog/collection listing.
"""

import asyncio
import logging

from ...constants import (
    DEFAULT_CATALOG,
    DEFAULT_COLLECTION,
    MAX_CLOUD_COVER,
    MAX_ITEMS,
    METADATA_ASSET_KEYS,
    THUMBNAIL_KEY,
    ErrorMessages,
    STACEndpoints,
    STACProperty,
    SuccessMessages,
)
from ...models import (
    CatalogInfo,
    CatalogsResponse,
    CollectionInfo,
    CollectionsResponse,
    ErrorResponse,
    SceneAsset,
    SceneDetailResponse,
    SceneInfo,
    SearchResponse,
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
    async def stac_list_catalogs() -> str:
        """
        List all known STAC catalogs.

        Returns pre-configured catalog endpoints that can be searched.

        Returns:
            JSON with catalog names and URLs

        Example:
            catalogs = await stac_list_catalogs()
        """
        catalogs = [CatalogInfo(name=name, url=url) for name, url in STACEndpoints.ALL.items()]
        return CatalogsResponse(
            catalogs=catalogs,
            default=DEFAULT_CATALOG,
            message=f"{len(catalogs)} catalog(s) available",
        ).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_list_collections(
        catalog: str | None = None,
    ) -> str:
        """
        List available collections in a STAC catalog.

        Args:
            catalog: Catalog name (default: earth_search)
                Options: earth_search, planetary_computer

        Returns:
            JSON list of collections with metadata

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

            return CollectionsResponse(
                catalog=catalog_name,
                collection_count=len(collections),
                collections=collections,
                message=f"{len(collections)} collection(s) in {catalog_name}",
            ).model_dump_json()

        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return ErrorResponse(error=ErrorMessages.CATALOG_ERROR.format(str(e))).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_search(
        bbox: list[float],
        collection: str | None = None,
        date_range: str | None = None,
        max_cloud_cover: int | None = None,
        max_items: int | None = None,
        catalog: str | None = None,
    ) -> str:
        """
        Search for satellite scenes matching spatial and temporal criteria.

        This is the primary entry point for finding satellite imagery.
        Results are cached for follow-up describe/download operations.

        Args:
            bbox: Bounding box [west, south, east, north] in EPSG:4326
            collection: STAC collection (default: sentinel-2-l2a)
                Options: sentinel-2-l2a, sentinel-2-c1-l2a, landsat-c2-l2
            date_range: Date range as "YYYY-MM-DD/YYYY-MM-DD" (optional)
            max_cloud_cover: Maximum cloud cover percentage 0-100 (default: 20)
            max_items: Maximum results to return (default: 10)
            catalog: Catalog name (default: earth_search)

        Returns:
            JSON with matching scenes sorted by cloud cover

        Example:
            results = await stac_search(
                bbox=[0.8, 51.8, 1.0, 51.95],
                date_range="2024-06-01/2024-08-31",
                max_cloud_cover=10
            )
        """
        try:
            if len(bbox) != 4:
                return ErrorResponse(error=ErrorMessages.INVALID_BBOX).model_dump_json()

            west, south, east, north = bbox
            if (
                west >= east
                or south >= north
                or not (-180 <= west <= 180)
                or not (-180 <= east <= 180)
                or not (-90 <= south <= 90)
                or not (-90 <= north <= 90)
            ):
                return ErrorResponse(
                    error=ErrorMessages.INVALID_BBOX_VALUES.format(
                        west=west, east=east, south=south, north=north
                    )
                ).model_dump_json()

            catalog_url = manager.get_catalog_url(catalog)  # type: ignore[union-attr]
            catalog_name = catalog or DEFAULT_CATALOG
            coll = collection or DEFAULT_COLLECTION
            cloud_max = max_cloud_cover if max_cloud_cover is not None else MAX_CLOUD_COVER
            items_max = max_items if max_items is not None else MAX_ITEMS

            def _search() -> list[object]:
                client = manager.get_stac_client(catalog_url)  # type: ignore[union-attr]

                search_kwargs: dict[str, object] = {
                    "collections": [coll],
                    "bbox": bbox,
                    "max_items": items_max,
                }
                if date_range:
                    search_kwargs["datetime"] = date_range

                # Apply cloud cover filter via query
                search_kwargs["query"] = {STACProperty.CLOUD_COVER: {"lt": cloud_max}}

                search = client.search(**search_kwargs)
                items = list(search.items())

                # Sort by cloud cover ascending
                items.sort(key=lambda x: x.properties.get(STACProperty.CLOUD_COVER, 100))

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

            if not scenes:
                msg = ErrorMessages.NO_RESULTS
            else:
                msg = SuccessMessages.SEARCH_COMPLETE.format(len(scenes))

            return SearchResponse(
                catalog=catalog_name,
                collection=coll,
                bbox=bbox,
                date_range=date_range,
                max_cloud_cover=cloud_max,
                scene_count=len(scenes),
                scenes=scenes,
                message=msg,
            ).model_dump_json()

        except Exception as e:
            logger.error(f"STAC search failed: {e}")
            return ErrorResponse(error=str(e)).model_dump_json()

    @mcp.tool  # type: ignore[union-attr]
    async def stac_describe_scene(scene_id: str) -> str:
        """
        Get detailed information about a specific scene.

        Shows all available assets/bands, properties, and download URLs.
        The scene must have been returned by a previous stac_search call.

        Args:
            scene_id: Scene identifier from a search result

        Returns:
            JSON with full scene details including all assets

        Example:
            detail = await stac_describe_scene(
                scene_id="S2B_MSIL2A_20240715T105629_N0510_R094_T31UCR_20240715T143301"
            )
        """
        try:
            item = manager.get_cached_scene(scene_id)  # type: ignore[union-attr]
            if not item:
                return ErrorResponse(
                    error=ErrorMessages.SCENE_NOT_FOUND.format(scene_id)
                ).model_dump_json()

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

            return SceneDetailResponse(
                scene_id=scene_id,
                collection=item.collection,
                datetime=item.properties.datetime,
                bbox=item.bbox,
                cloud_cover=item.properties.cloud_cover,
                crs=item.crs_string,
                assets=assets,
                properties=props_dict,
                message=f"Scene {scene_id}: {len(assets)} data asset(s)",
            ).model_dump_json()

        except Exception as e:
            logger.error(f"Failed to describe scene: {e}")
            return ErrorResponse(error=str(e)).model_dump_json()
