"""
Catalog Manager for chuk-mcp-stac.

Manages STAC catalog connections, search state, and artifact storage
for downloaded band data.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..constants import (
    CLIENT_CACHE_TTL,
    DEFAULT_CATALOG,
    RETRY_ATTEMPTS,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
    ArtifactType,
    ErrorMessages,
    MimeType,
    STACEndpoints,
)
from ..models.stac import STACItem

# Maximum number of scenes to keep in the cache before evicting oldest entries
_MAX_SCENE_CACHE = 200

logger = logging.getLogger(__name__)

_RETRY_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)


class BandDownloadResult(BaseModel):
    """Result of downloading bands and storing them as an artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_ref: str
    crs: str
    shape: list[int] = Field(default_factory=list)
    dtype: str = ""


class CatalogManager:
    """
    Manages STAC catalog connections and search results.

    Keeps track of the current catalog, caches search results for
    follow-up operations (describe, download), and handles artifact
    storage for downloaded data.

    The download_bands() method is the primary API for tools — it
    reads COGs, stores the result in chuk-artifacts, and returns
    an artifact reference. Tools never handle raw bytes.
    """

    def __init__(self, default_catalog: str = DEFAULT_CATALOG) -> None:
        self._default_catalog = default_catalog
        # LRU cache of recent search results: scene_id -> STACItem
        self._scene_cache: dict[str, STACItem] = {}
        # Track which catalog each cached scene came from
        self._scene_catalogs: dict[str, str] = {}
        # TTL-based STAC client cache: url -> (client, created_at)
        self._client_cache: dict[str, tuple[Any, float]] = {}
        self._client_lock = threading.Lock()
        logger.info(f"CatalogManager initialized (default catalog: {default_catalog})")

    def _get_store(self) -> Any:
        """Get the artifact store from context."""
        try:
            from chuk_mcp_server import get_artifact_store, has_artifact_store

            if has_artifact_store():
                return get_artifact_store()
        except ImportError:
            pass
        return None

    def get_catalog_url(self, catalog_name: str | None = None) -> str:
        """
        Resolve a catalog name to its API URL.

        Args:
            catalog_name: Catalog short name (e.g., "earth_search") or
                         a full STAC API URL (https://...). Uses default if None.

        Returns:
            Catalog API URL

        Raises:
            ValueError: If catalog name is not recognized
        """
        name = catalog_name or self._default_catalog
        # Accept full URLs directly
        if name.startswith(("http://", "https://")):
            return name
        url = STACEndpoints.ALL.get(name)
        if not url:
            raise ValueError(
                f"Unknown catalog '{name}'. Known catalogs: {list(STACEndpoints.ALL.keys())}. "
                "Or pass a full STAC API URL (https://...)."
            )
        return url

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
        retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
        reraise=True,
    )
    def get_stac_client(self, catalog_url: str) -> Any:
        """
        Get or create a cached STAC client for the given URL.

        Uses a TTL-based cache with thread-safe access. Retries on
        transient network errors (ConnectionError, TimeoutError, OSError).

        Args:
            catalog_url: STAC API URL

        Returns:
            pystac_client.Client instance
        """
        from pystac_client import Client

        now = time.monotonic()
        with self._client_lock:
            cached = self._client_cache.get(catalog_url)
            if cached is not None:
                client, created_at = cached
                if now - created_at < CLIENT_CACHE_TTL:
                    return client
        # Open outside the lock to avoid blocking other threads
        client = Client.open(catalog_url)
        with self._client_lock:
            self._client_cache[catalog_url] = (client, now)
        return client

    def cache_scene(self, scene_id: str, item: STACItem, catalog: str) -> None:
        """Cache a STAC item for later describe/download operations."""
        # Move to end if already present (LRU touch) — delete + re-insert
        if scene_id in self._scene_cache:
            del self._scene_cache[scene_id]
        self._scene_cache[scene_id] = item
        self._scene_catalogs[scene_id] = catalog
        # Evict oldest entries if over limit
        while len(self._scene_cache) > _MAX_SCENE_CACHE:
            evicted_id = next(iter(self._scene_cache))
            del self._scene_cache[evicted_id]
            self._scene_catalogs.pop(evicted_id, None)

    def get_cached_scene(self, scene_id: str) -> STACItem | None:
        """Get a cached STAC item by scene ID."""
        item = self._scene_cache.get(scene_id)
        if item is not None:
            # LRU touch — move to end via delete + re-insert
            del self._scene_cache[scene_id]
            self._scene_cache[scene_id] = item
        return item

    def get_scene_catalog(self, scene_id: str) -> str | None:
        """Get the catalog a cached scene came from."""
        return self._scene_catalogs.get(scene_id)

    # ─── Download Pipeline ──────────────────────────────────────────────────

    async def download_bands(
        self,
        scene_id: str,
        band_names: list[str],
        bbox_4326: list[float] | None = None,
    ) -> BandDownloadResult:
        """
        Download bands from a cached scene and store as an artifact.

        This is the primary download API. It:
        1. Looks up the scene in the cache
        2. Validates that all requested bands exist
        3. Reads band COGs via HTTP (in a thread)
        4. Stores the GeoTIFF in chuk-artifacts
        5. Returns an artifact reference

        Tools call this method — they never handle raw bytes.

        Args:
            scene_id: Scene identifier (must be cached from a prior search)
            band_names: Band asset keys to download
            bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]

        Returns:
            BandDownloadResult with artifact_ref, crs, shape, dtype

        Raises:
            ValueError: If scene not found or band not available
            RuntimeError: If no artifact store is available
        """
        item = self.get_cached_scene(scene_id)
        if not item:
            raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(scene_id))

        for band in band_names:
            if band not in item.assets:
                raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))

        # Check store availability before expensive COG read
        store = self._get_store()
        if not store:
            raise RuntimeError(
                "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER "
                "to persist downloaded raster data."
            )

        # Read COGs in a thread (rasterio is sync)
        from .raster_io import read_bands_from_cogs

        result = await asyncio.to_thread(read_bands_from_cogs, item.assets, band_names, bbox_4326)

        # Store in artifact store
        artifact_ref = await self._store_raster(
            store=store,
            data=result.data,
            scene_id=scene_id,
            bands=band_names,
            bbox=bbox_4326 or [],
            crs=result.crs,
            shape=result.shape,
            dtype=result.dtype,
        )

        return BandDownloadResult(
            artifact_ref=artifact_ref,
            crs=result.crs,
            shape=result.shape,
            dtype=result.dtype,
        )

    async def download_mosaic(
        self,
        scene_ids: list[str],
        band_names: list[str],
        bbox_4326: list[float] | None = None,
    ) -> BandDownloadResult:
        """
        Download bands from multiple scenes and merge into a single mosaic.

        Reads bands from each scene individually (without storing intermediates),
        merges them using rasterio.merge, and stores only the final result.

        Args:
            scene_ids: Scene identifiers (must be cached from prior searches)
            band_names: Band asset keys to download
            bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]

        Returns:
            BandDownloadResult with artifact_ref, crs, shape, dtype

        Raises:
            ValueError: If any scene not found or band not available
            RuntimeError: If no artifact store is available
        """
        for sid in scene_ids:
            item = self.get_cached_scene(sid)
            if not item:
                raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(sid))
            for band in band_names:
                if band not in item.assets:
                    raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))

        store = self._get_store()
        if not store:
            raise RuntimeError(
                "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER "
                "to persist downloaded raster data."
            )

        from .raster_io import merge_rasters, read_bands_from_cogs

        raster_results = []
        for sid in scene_ids:
            item = self.get_cached_scene(sid)
            result = await asyncio.to_thread(
                read_bands_from_cogs,
                item.assets,
                band_names,
                bbox_4326,  # type: ignore[union-attr]
            )
            raster_results.append(result)

        merged = await asyncio.to_thread(merge_rasters, raster_results)

        mosaic_id = "_".join(scene_ids)
        artifact_ref = await self._store_raster(
            store=store,
            data=merged.data,
            scene_id=f"mosaic:{mosaic_id}",
            bands=band_names,
            bbox=bbox_4326 or [],
            crs=merged.crs,
            shape=merged.shape,
            dtype=merged.dtype,
        )

        return BandDownloadResult(
            artifact_ref=artifact_ref,
            crs=merged.crs,
            shape=merged.shape,
            dtype=merged.dtype,
        )

    # ─── Artifact Storage ───────────────────────────────────────────────────

    async def _store_raster(
        self,
        store: Any,
        data: bytes,
        scene_id: str,
        bands: list[str],
        bbox: list[float],
        crs: str,
        shape: list[int],
        dtype: str,
    ) -> str:
        """
        Store downloaded raster data in the artifact store.

        Returns:
            Artifact reference string

        Raises:
            RuntimeError: If the store operation fails
        """
        try:
            artifact_id = await store.store(  # type: ignore[union-attr]
                data=data,
                mime=MimeType.GEOTIFF,
                summary=f"stac:{scene_id}:{'_'.join(bands)}",
                meta={
                    "type": ArtifactType.SATELLITE_RASTER,
                    "scene_id": scene_id,
                    "bands": bands,
                    "bbox": bbox,
                    "crs": crs,
                    "shape": shape,
                    "dtype": dtype,
                },
            )
            logger.info(f"Stored raster for {scene_id} bands={bands} -> {artifact_id}")
            return artifact_id
        except Exception as e:
            raise RuntimeError(f"Failed to store raster in artifact store: {e}") from e
