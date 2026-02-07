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

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from collections.abc import Callable

from ..constants import (
    CLIENT_CACHE_TTL,
    COLLECTION_INTELLIGENCE,
    DEFAULT_CATALOG,
    INDEX_BANDS,
    RASTER_CACHE_MAX_BYTES,
    RASTER_CACHE_MAX_ITEM,
    RETRY_ATTEMPTS,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
    SCL_BAND_NAME,
    SCL_GOOD_VALUES,
    ArtifactType,
    ErrorMessages,
    MimeType,
    STACEndpoints,
    resolve_band_name,
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
    preview_ref: str | None = None


class IndexComputeResult(BaseModel):
    """Result of computing a spectral index."""

    model_config = ConfigDict(frozen=True)

    artifact_ref: str
    crs: str
    shape: list[int] = Field(default_factory=list)
    value_range: list[float] = Field(default_factory=list)
    preview_ref: str | None = None


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

    def __init__(
        self,
        default_catalog: str = DEFAULT_CATALOG,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        self._default_catalog = default_catalog
        # LRU cache of recent search results: scene_id -> STACItem
        self._scene_cache: dict[str, STACItem] = {}
        # Track which catalog each cached scene came from
        self._scene_catalogs: dict[str, str] = {}
        # TTL-based STAC client cache: url -> (client, created_at)
        self._client_cache: dict[str, tuple[Any, float]] = {}
        self._client_lock = threading.Lock()
        # In-memory raster cache: key -> {data, crs, shape, dtype}
        self._raster_cache: dict[str, dict[str, Any]] = {}
        self._raster_cache_sizes: dict[str, int] = {}
        self._raster_cache_total: int = 0
        # Optional progress callback
        self._progress_callback = progress_callback
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
        # Auto-detect Planetary Computer and apply signing modifier
        modifier = None
        if "planetarycomputer.microsoft.com" in catalog_url:
            try:
                import planetary_computer  # type: ignore[import-not-found]

                modifier = planetary_computer.sign_inplace
                logger.info("Planetary Computer signing enabled")
            except ImportError:
                logger.warning(
                    "planetary-computer package not installed. "
                    "Install with: pip install 'chuk-mcp-stac[pc]'"
                )
        # Open outside the lock to avoid blocking other threads
        client = Client.open(catalog_url, modifier=modifier)
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

    def _enrichment_kwargs(self, item: STACItem, band_names: list[str]) -> dict[str, Any]:
        """Extract enriched metadata kwargs for _store_raster from a STACItem."""
        intel = COLLECTION_INTELLIGENCE.get(item.collection, {})
        band_wl: dict[str, int] = {}
        for b in band_names:
            info = intel.get("bands", {}).get(b)
            if info and info.get("wavelength_nm"):
                band_wl[b] = info["wavelength_nm"]
        return {
            "collection": item.collection,
            "datetime_str": item.properties.datetime,
            "band_wavelengths": band_wl or None,
            "sun_elevation": item.properties.sun_elevation,
            "sun_azimuth": item.properties.sun_azimuth,
            "view_off_nadir": item.properties.view_off_nadir,
        }

    # ─── Raster Cache ────────────────────────────────────────────────────────

    @staticmethod
    def _raster_cache_key(
        scene_id: str,
        band_names: list[str],
        bbox: list[float] | None,
        cloud_mask: bool = False,
    ) -> str:
        """Build a deterministic cache key for raster data."""
        sorted_bands = ",".join(sorted(band_names))
        bbox_str = ",".join(f"{v:.6f}" for v in bbox) if bbox else ""
        return f"{scene_id}:{sorted_bands}:{bbox_str}:{cloud_mask}"

    def _raster_cache_get(self, key: str) -> dict[str, Any] | None:
        """Get cached raster data with LRU touch, or None if not cached."""
        entry = self._raster_cache.get(key)
        if entry is not None:
            # LRU touch — move to end
            del self._raster_cache[key]
            self._raster_cache[key] = entry
            size = self._raster_cache_sizes.pop(key)
            self._raster_cache_sizes[key] = size
        return entry

    def _raster_cache_put(
        self, key: str, data: bytes, crs: str, shape: list[int], dtype: str
    ) -> None:
        """Store raster data in cache with LRU eviction."""
        size = len(data)
        if size > RASTER_CACHE_MAX_ITEM:
            return  # Single item too large for cache
        # Evict oldest entries until we have room
        while self._raster_cache_total + size > RASTER_CACHE_MAX_BYTES and self._raster_cache:
            evict_key = next(iter(self._raster_cache))
            evict_size = self._raster_cache_sizes.pop(evict_key)
            del self._raster_cache[evict_key]
            self._raster_cache_total -= evict_size
        self._raster_cache[key] = {"data": data, "crs": crs, "shape": shape, "dtype": dtype}
        self._raster_cache_sizes[key] = size
        self._raster_cache_total += size

    # ─── Progress Reporting ──────────────────────────────────────────────────

    def _report_progress(self, stage: str, current: int, total: int) -> None:
        """Report progress to the callback, if one is registered."""
        if self._progress_callback is not None:
            try:
                self._progress_callback(stage, current, total)
            except Exception:
                pass  # Never let callback errors break the pipeline

    # ─── Download Pipeline ──────────────────────────────────────────────────

    async def download_bands(
        self,
        scene_id: str,
        band_names: list[str],
        bbox_4326: list[float] | None = None,
        output_format: str = "geotiff",
        cloud_mask: bool = False,
    ) -> BandDownloadResult:
        """
        Download bands from a cached scene and store as an artifact.

        This is the primary download API. It:
        1. Looks up the scene in the cache
        2. Validates that all requested bands exist
        3. Reads band COGs via HTTP (in a thread)
        4. Optionally applies SCL-based cloud masking
        5. Optionally converts to PNG
        6. Stores the result in chuk-artifacts
        7. Returns an artifact reference

        Tools call this method — they never handle raw bytes.

        Args:
            scene_id: Scene identifier (must be cached from a prior search)
            band_names: Band asset keys to download
            bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]
            output_format: Output format - "geotiff" (default) or "png"
            cloud_mask: If True, apply SCL-based cloud masking (Sentinel-2 only)

        Returns:
            BandDownloadResult with artifact_ref, crs, shape, dtype

        Raises:
            ValueError: If scene not found or band not available
            RuntimeError: If no artifact store is available
        """
        band_names = [resolve_band_name(b) for b in band_names]

        item = self.get_cached_scene(scene_id)
        if not item:
            raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(scene_id))

        for band in band_names:
            if band not in item.assets:
                raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))

        if cloud_mask and SCL_BAND_NAME not in item.assets:
            raise ValueError(
                f"Cloud masking requires '{SCL_BAND_NAME}' band, "
                f"which is not available in scene '{scene_id}'. "
                "Cloud masking is only supported for Sentinel-2 L2A scenes."
            )

        # Check store availability before expensive COG read
        store = self._get_store()
        if not store:
            raise RuntimeError(
                "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER "
                "to persist downloaded raster data."
            )

        # Check in-memory raster cache
        cache_key = self._raster_cache_key(scene_id, band_names, bbox_4326, cloud_mask)
        cached = self._raster_cache_get(cache_key)
        if cached is not None:
            geotiff_bytes = cached["data"]
            crs = cached["crs"]
            shape = cached["shape"]
            dtype = cached["dtype"]
        elif cloud_mask:
            from .raster_io import apply_cloud_mask, arrays_to_geotiff, read_bands_as_arrays

            self._report_progress("reading_bands", 1, 1)
            all_bands = list(band_names) + [SCL_BAND_NAME]
            arr_result = await asyncio.to_thread(
                read_bands_as_arrays,
                item.assets,
                all_bands,
                bbox_4326,
                frozenset({SCL_BAND_NAME}),
            )

            data_arrays = arr_result.arrays[:-1]
            scl_array = arr_result.arrays[-1]
            masked_arrays = apply_cloud_mask(data_arrays, scl_array, SCL_GOOD_VALUES)

            stack = np.stack(masked_arrays, axis=0)
            geotiff_bytes = await asyncio.to_thread(
                arrays_to_geotiff,
                masked_arrays,
                arr_result.crs,
                arr_result.transform,
                arr_result.dtype,
                0,
            )
            crs = arr_result.crs
            shape = list(stack.shape)
            dtype = arr_result.dtype
            self._raster_cache_put(cache_key, geotiff_bytes, crs, shape, dtype)
        else:
            from .raster_io import read_bands_from_cogs

            self._report_progress("reading_bands", 1, 1)
            result = await asyncio.to_thread(
                read_bands_from_cogs, item.assets, band_names, bbox_4326
            )
            geotiff_bytes = result.data
            crs = result.crs
            shape = result.shape
            dtype = result.dtype
            self._raster_cache_put(cache_key, geotiff_bytes, crs, shape, dtype)

        # Determine output format and mime type
        if output_format == "png":
            from .raster_io import geotiff_to_png

            store_data = await asyncio.to_thread(geotiff_to_png, geotiff_bytes)
            store_mime = MimeType.PNG
        else:
            store_data = geotiff_bytes
            store_mime = MimeType.GEOTIFF

        # Store in artifact store
        artifact_ref, preview_ref = await self._store_raster(
            store=store,
            data=store_data,
            scene_id=scene_id,
            bands=band_names,
            bbox=bbox_4326 or [],
            crs=crs,
            shape=shape,
            dtype=dtype,
            mime=store_mime,
            geotiff_data=geotiff_bytes if store_mime == MimeType.GEOTIFF else None,
            **self._enrichment_kwargs(item, band_names),
        )

        return BandDownloadResult(
            artifact_ref=artifact_ref,
            crs=crs,
            shape=shape,
            dtype=dtype,
            preview_ref=preview_ref,
        )

    async def download_mosaic(
        self,
        scene_ids: list[str],
        band_names: list[str],
        bbox_4326: list[float] | None = None,
        output_format: str = "geotiff",
        cloud_mask: bool = False,
        method: str = "last",
    ) -> BandDownloadResult:
        """
        Download bands from multiple scenes and merge into a single mosaic.

        Reads bands from each scene individually (without storing intermediates),
        merges them using rasterio.merge, and stores only the final result.

        Args:
            scene_ids: Scene identifiers (must be cached from prior searches)
            band_names: Band asset keys to download
            bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]
            output_format: Output format - "geotiff" (default) or "png"
            cloud_mask: If True, apply SCL-based cloud masking per scene before merge

        Returns:
            BandDownloadResult with artifact_ref, crs, shape, dtype

        Raises:
            ValueError: If any scene not found or band not available
            RuntimeError: If no artifact store is available
        """
        band_names = [resolve_band_name(b) for b in band_names]

        for sid in scene_ids:
            item = self.get_cached_scene(sid)
            if not item:
                raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(sid))
            for band in band_names:
                if band not in item.assets:
                    raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))
            if cloud_mask and SCL_BAND_NAME not in item.assets:
                raise ValueError(f"Cloud masking requires '{SCL_BAND_NAME}' band in scene '{sid}'.")

        store = self._get_store()
        if not store:
            raise RuntimeError(
                "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER "
                "to persist downloaded raster data."
            )

        from .raster_io import RasterReadResult, merge_rasters

        n_scenes = len(scene_ids)
        if cloud_mask:
            from .raster_io import apply_cloud_mask, arrays_to_geotiff, read_bands_as_arrays

            raster_results = []
            for i, sid in enumerate(scene_ids):
                self._report_progress("reading_scene", i + 1, n_scenes)
                item = self.get_cached_scene(sid)
                all_bands = list(band_names) + [SCL_BAND_NAME]
                arr_result = await asyncio.to_thread(
                    read_bands_as_arrays,
                    item.assets,  # type: ignore[union-attr]
                    all_bands,
                    bbox_4326,
                    frozenset({SCL_BAND_NAME}),
                )

                data_arrays = arr_result.arrays[:-1]
                scl_array = arr_result.arrays[-1]
                masked_arrays = apply_cloud_mask(data_arrays, scl_array, SCL_GOOD_VALUES)

                geotiff_bytes = arrays_to_geotiff(
                    masked_arrays,
                    arr_result.crs,
                    arr_result.transform,
                    arr_result.dtype,
                    0,
                )
                stack = np.stack(masked_arrays, axis=0)
                raster_results.append(
                    RasterReadResult(
                        data=geotiff_bytes,
                        crs=arr_result.crs,
                        shape=list(stack.shape),
                        dtype=arr_result.dtype,
                    )
                )
        else:
            from .raster_io import read_bands_from_cogs

            raster_results = []
            for i, sid in enumerate(scene_ids):
                self._report_progress("reading_scene", i + 1, n_scenes)
                item = self.get_cached_scene(sid)
                result = await asyncio.to_thread(
                    read_bands_from_cogs,
                    item.assets,  # type: ignore[union-attr]
                    band_names,
                    bbox_4326,
                )
                raster_results.append(result)

        if method == "quality":
            # Quality-weighted merge: read SCL alongside bands, pick best pixel
            from .raster_io import arrays_to_geotiff, quality_weighted_merge, read_bands_as_arrays

            scene_data: list[tuple[list[np.ndarray], np.ndarray]] = []
            first_arr_result = None
            for i, sid in enumerate(scene_ids):
                self._report_progress("reading_scene", i + 1, n_scenes)
                item = self.get_cached_scene(sid)
                all_bands = list(band_names) + [SCL_BAND_NAME]
                arr_result = await asyncio.to_thread(
                    read_bands_as_arrays,
                    item.assets,  # type: ignore[union-attr]
                    all_bands,
                    bbox_4326,
                    frozenset({SCL_BAND_NAME}),
                )
                if first_arr_result is None:
                    first_arr_result = arr_result
                data_arrays = arr_result.arrays[: len(band_names)]
                scl_array = arr_result.arrays[-1]
                scene_data.append((data_arrays, scl_array))

            self._report_progress("merging", 1, 1)
            merged_arrays = await asyncio.to_thread(quality_weighted_merge, scene_data)
            geotiff_bytes = await asyncio.to_thread(
                arrays_to_geotiff,
                merged_arrays,
                first_arr_result.crs,  # type: ignore[union-attr]
                first_arr_result.transform,  # type: ignore[union-attr]
                first_arr_result.dtype,  # type: ignore[union-attr]
                0,
            )
            stack = np.stack(merged_arrays, axis=0)
            merged = RasterReadResult(
                data=geotiff_bytes,
                crs=first_arr_result.crs,  # type: ignore[union-attr]
                shape=list(stack.shape),
                dtype=first_arr_result.dtype,  # type: ignore[union-attr]
            )
        else:
            self._report_progress("merging", 1, 1)
            merged = await asyncio.to_thread(merge_rasters, raster_results)

        # Determine output format and mime type
        if output_format == "png":
            from .raster_io import geotiff_to_png

            store_data = await asyncio.to_thread(geotiff_to_png, merged.data)
            store_mime = MimeType.PNG
        else:
            store_data = merged.data
            store_mime = MimeType.GEOTIFF

        mosaic_id = "_".join(scene_ids)
        # Use first scene's metadata for enrichment
        first_item = self.get_cached_scene(scene_ids[0])
        enrich = self._enrichment_kwargs(first_item, band_names) if first_item else {}
        artifact_ref, preview_ref = await self._store_raster(
            store=store,
            data=store_data,
            scene_id=f"mosaic:{mosaic_id}",
            bands=band_names,
            bbox=bbox_4326 or [],
            crs=merged.crs,
            shape=merged.shape,
            dtype=merged.dtype,
            mime=store_mime,
            geotiff_data=merged.data if store_mime == MimeType.GEOTIFF else None,
            **enrich,
        )

        return BandDownloadResult(
            artifact_ref=artifact_ref,
            crs=merged.crs,
            shape=merged.shape,
            dtype=merged.dtype,
            preview_ref=preview_ref,
        )

    # ─── Temporal Compositing ────────────────────────────────────────────────

    async def temporal_composite(
        self,
        scene_ids: list[str],
        band_names: list[str],
        method: str = "median",
        bbox_4326: list[float] | None = None,
        cloud_mask: bool = False,
        output_format: str = "geotiff",
    ) -> BandDownloadResult:
        """
        Composite multiple scenes into a single raster via temporal statistics.

        Reads bands from each scene, stacks them, and applies a per-pixel
        statistical method (median, mean, max, min) along the time axis.

        Args:
            scene_ids: Scene identifiers (must be cached)
            band_names: Band asset keys to composite
            method: Statistical method (median, mean, max, min)
            bbox_4326: Optional crop bbox in EPSG:4326
            cloud_mask: Apply SCL cloud masking per scene before compositing
            output_format: Output format - "geotiff" (default) or "png"

        Returns:
            BandDownloadResult with artifact_ref for the composite

        Raises:
            ValueError: If scene not found, band not available, or method unknown
            RuntimeError: If no artifact store available
        """
        band_names = [resolve_band_name(b) for b in band_names]

        for sid in scene_ids:
            item = self.get_cached_scene(sid)
            if not item:
                raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(sid))
            for band in band_names:
                if band not in item.assets:
                    raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))
            if cloud_mask and SCL_BAND_NAME not in item.assets:
                raise ValueError(f"Cloud masking requires '{SCL_BAND_NAME}' band in scene '{sid}'.")

        store = self._get_store()
        if not store:
            raise RuntimeError(
                "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER "
                "to persist downloaded raster data."
            )

        from .raster_io import (
            arrays_to_geotiff,
            read_bands_as_arrays,
            temporal_composite_arrays,
        )

        # Read bands from each scene as arrays
        scene_arrays: list[list[np.ndarray]] = []
        first_result = None
        n_scenes = len(scene_ids)

        for i, sid in enumerate(scene_ids):
            self._report_progress("reading_scene", i + 1, n_scenes)
            item = self.get_cached_scene(sid)
            if cloud_mask:
                from .raster_io import apply_cloud_mask_float

                all_bands = list(band_names) + [SCL_BAND_NAME]
                arr_result = await asyncio.to_thread(
                    read_bands_as_arrays,
                    item.assets,  # type: ignore[union-attr]
                    all_bands,
                    bbox_4326,
                    frozenset({SCL_BAND_NAME}),
                )
                data_arrays = apply_cloud_mask_float(
                    arr_result.arrays[: len(band_names)],
                    arr_result.arrays[-1],
                    SCL_GOOD_VALUES,
                )
            else:
                arr_result = await asyncio.to_thread(
                    read_bands_as_arrays,
                    item.assets,  # type: ignore[union-attr]
                    band_names,
                    bbox_4326,
                )
                data_arrays = arr_result.arrays

            if first_result is None:
                first_result = arr_result
            scene_arrays.append(data_arrays)

        # Composite along time axis
        self._report_progress("compositing", 1, 1)
        composited = await asyncio.to_thread(temporal_composite_arrays, scene_arrays, method)

        # Package as GeoTIFF
        geotiff_bytes = await asyncio.to_thread(
            arrays_to_geotiff,
            composited,
            first_result.crs,  # type: ignore[union-attr]
            first_result.transform,  # type: ignore[union-attr]
            "float32",
            float("nan"),
        )

        stack = np.stack(composited, axis=0)
        shape = list(stack.shape)

        if output_format == "png":
            from .raster_io import geotiff_to_png

            store_data = await asyncio.to_thread(geotiff_to_png, geotiff_bytes)
            store_mime = MimeType.PNG
        else:
            store_data = geotiff_bytes
            store_mime = MimeType.GEOTIFF

        composite_id = f"composite:{'_'.join(scene_ids)}"
        first_item = self.get_cached_scene(scene_ids[0])
        enrich = self._enrichment_kwargs(first_item, band_names) if first_item else {}
        artifact_ref, preview_ref = await self._store_raster(
            store=store,
            data=store_data,
            scene_id=composite_id,
            bands=band_names,
            bbox=bbox_4326 or [],
            crs=first_result.crs,  # type: ignore[union-attr]
            shape=shape,
            dtype="float32",
            mime=store_mime,
            geotiff_data=geotiff_bytes if store_mime == MimeType.GEOTIFF else None,
            **enrich,
        )

        return BandDownloadResult(
            artifact_ref=artifact_ref,
            crs=first_result.crs,  # type: ignore[union-attr]
            shape=shape,
            dtype="float32",
            preview_ref=preview_ref,
        )

    # ─── Index Computation ──────────────────────────────────────────────────

    async def compute_index(
        self,
        scene_id: str,
        index_name: str,
        bbox_4326: list[float] | None = None,
        cloud_mask: bool = False,
        output_format: str = "geotiff",
    ) -> IndexComputeResult:
        """
        Compute a spectral index for a scene and store as an artifact.

        Steps:
        1. Look up required bands from INDEX_BANDS
        2. Read bands as raw arrays
        3. Optionally apply SCL cloud mask
        4. Compute index formula
        5. Package as single-band float32 GeoTIFF
        6. Optionally convert to PNG
        7. Store in artifact store

        Args:
            scene_id: Scene identifier (must be cached)
            index_name: Spectral index name (ndvi, ndwi, ndbi, evi, savi, bsi)
            bbox_4326: Optional crop bbox in EPSG:4326
            cloud_mask: If True, apply SCL-based cloud masking
            output_format: Output format - "geotiff" (default) or "png"

        Returns:
            IndexComputeResult with artifact_ref, crs, shape, value_range

        Raises:
            ValueError: If scene not found, index unknown, or band not available
            RuntimeError: If no artifact store is available
        """
        if index_name not in INDEX_BANDS:
            raise ValueError(f"Unknown index '{index_name}'. Available: {list(INDEX_BANDS.keys())}")

        item = self.get_cached_scene(scene_id)
        if not item:
            raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(scene_id))

        required_bands = INDEX_BANDS[index_name]
        for band in required_bands:
            if band not in item.assets:
                raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))

        if cloud_mask and SCL_BAND_NAME not in item.assets:
            raise ValueError(
                f"Cloud masking requires '{SCL_BAND_NAME}' band in scene '{scene_id}'."
            )

        store = self._get_store()
        if not store:
            raise RuntimeError(
                "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER "
                "to persist downloaded raster data."
            )

        from .raster_io import arrays_to_geotiff, compute_spectral_index, read_bands_as_arrays

        # Build band list — add SCL if cloud masking
        read_bands = list(required_bands)
        classification_bands: frozenset[str] | None = None
        if cloud_mask:
            read_bands.append(SCL_BAND_NAME)
            classification_bands = frozenset({SCL_BAND_NAME})

        arr_result = await asyncio.to_thread(
            read_bands_as_arrays, item.assets, read_bands, bbox_4326, classification_bands
        )

        if cloud_mask:
            from .raster_io import apply_cloud_mask_float

            data_arrays = arr_result.arrays[: len(required_bands)]
            scl_array = arr_result.arrays[-1]
            data_arrays = apply_cloud_mask_float(data_arrays, scl_array, SCL_GOOD_VALUES)
        else:
            data_arrays = arr_result.arrays

        # Build band_name -> array mapping
        band_dict = dict(zip(required_bands, data_arrays))

        # Compute index
        index_array = await asyncio.to_thread(compute_spectral_index, band_dict, index_name)

        # Compute value range (excluding NaN)
        valid_mask = ~np.isnan(index_array)
        if np.any(valid_mask):
            value_range = [float(np.nanmin(index_array)), float(np.nanmax(index_array))]
        else:
            value_range = [0.0, 0.0]

        # Package as GeoTIFF (single band, float32, NaN nodata)
        geotiff_bytes = await asyncio.to_thread(
            arrays_to_geotiff,
            [index_array],
            arr_result.crs,
            arr_result.transform,
            "float32",
            float("nan"),
        )

        # Determine output format and mime type
        if output_format == "png":
            from .raster_io import geotiff_to_png

            store_data = await asyncio.to_thread(geotiff_to_png, geotiff_bytes)
            store_mime = MimeType.PNG
        else:
            store_data = geotiff_bytes
            store_mime = MimeType.GEOTIFF

        index_shape = [1, index_array.shape[0], index_array.shape[1]]

        # Store artifact
        artifact_ref, preview_ref = await self._store_raster(
            store=store,
            data=store_data,
            scene_id=scene_id,
            bands=required_bands,
            bbox=bbox_4326 or [],
            crs=arr_result.crs,
            shape=index_shape,
            dtype="float32",
            mime=store_mime,
            geotiff_data=geotiff_bytes if store_mime == MimeType.GEOTIFF else None,
            **self._enrichment_kwargs(item, required_bands),
        )

        return IndexComputeResult(
            artifact_ref=artifact_ref,
            crs=arr_result.crs,
            shape=index_shape,
            value_range=value_range,
            preview_ref=preview_ref,
        )

    # ─── Size Estimation ─────────────────────────────────────────────────────

    async def estimate_size(
        self,
        scene_id: str,
        band_names: list[str],
        bbox_4326: list[float] | None = None,
    ) -> dict:
        """
        Estimate download size for a scene's bands without reading pixel data.

        Args:
            scene_id: Scene identifier (must be cached)
            band_names: Band names to estimate
            bbox_4326: Optional crop bbox in EPSG:4326

        Returns:
            Dict with per_band, total_pixels, estimated_bytes, estimated_mb,
            crs, warnings

        Raises:
            ValueError: If scene not found or band not available
        """
        band_names = [resolve_band_name(b) for b in band_names]

        item = self.get_cached_scene(scene_id)
        if not item:
            raise ValueError(ErrorMessages.SCENE_NOT_FOUND.format(scene_id))

        for band in band_names:
            if band not in item.assets:
                raise ValueError(ErrorMessages.BAND_NOT_FOUND.format(band))

        from .raster_io import estimate_band_size

        result = await asyncio.to_thread(estimate_band_size, item.assets, band_names, bbox_4326)

        # Add warnings for large downloads
        warnings: list[str] = []
        mb = result["estimated_mb"]
        if mb >= 1024:
            warnings.append(f"Very large download (~{mb:.0f} MB). Consider using a smaller bbox.")
        elif mb >= 500:
            warnings.append(f"Large download (~{mb:.0f} MB). Consider cropping with a bbox.")
        result["warnings"] = warnings

        return result

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
        mime: str = MimeType.GEOTIFF,
        geotiff_data: bytes | None = None,
        *,
        collection: str = "",
        datetime_str: str = "",
        band_wavelengths: dict[str, int] | None = None,
        sun_elevation: float | None = None,
        sun_azimuth: float | None = None,
        view_off_nadir: float | None = None,
    ) -> tuple[str, str | None]:
        """
        Store downloaded raster data in the artifact store.

        When the main artifact is a GeoTIFF, automatically generates and
        stores a PNG preview alongside it. Preview failure is non-fatal.

        Args:
            geotiff_data: Original GeoTIFF bytes for preview generation.
                         Pass this when mime is GEOTIFF. When mime is PNG,
                         the main artifact IS the preview so no separate
                         preview is generated.

        Returns:
            Tuple of (artifact_ref, preview_ref). preview_ref is None
            when mime is PNG or preview generation fails.

        Raises:
            RuntimeError: If the main store operation fails
        """
        try:
            meta: dict[str, Any] = {
                "type": ArtifactType.SATELLITE_RASTER,
                "schema_version": "1.0",
                "scene_id": scene_id,
                "bands": bands,
                "bbox": bbox,
                "crs": crs,
                "shape": shape,
                "dtype": dtype,
            }
            if collection:
                meta["collection"] = collection
            if datetime_str:
                meta["datetime"] = datetime_str
            if band_wavelengths:
                meta["band_wavelengths"] = band_wavelengths
            if sun_elevation is not None:
                meta["sun_elevation"] = sun_elevation
            if sun_azimuth is not None:
                meta["sun_azimuth"] = sun_azimuth
            if view_off_nadir is not None:
                meta["view_off_nadir"] = view_off_nadir
            artifact_id = await store.store(  # type: ignore[union-attr]
                data=data,
                mime=mime,
                summary=f"stac:{scene_id}:{'_'.join(bands)}",
                meta=meta,
            )
            logger.info(f"Stored raster for {scene_id} bands={bands} -> {artifact_id}")
        except Exception as e:
            raise RuntimeError(f"Failed to store raster in artifact store: {e}") from e

        # Generate PNG preview for GeoTIFF artifacts
        preview_ref: str | None = None
        if mime == MimeType.GEOTIFF and geotiff_data is not None:
            try:
                from .raster_io import geotiff_to_png

                png_data = await asyncio.to_thread(geotiff_to_png, geotiff_data)
                preview_ref = await store.store(  # type: ignore[union-attr]
                    data=png_data,
                    mime=MimeType.PNG,
                    summary=f"stac:{scene_id}:{'_'.join(bands)}:preview",
                    meta={
                        "type": ArtifactType.SATELLITE_RASTER,
                        "scene_id": scene_id,
                        "bands": bands,
                        "preview_of": artifact_id,
                    },
                )
                logger.info(f"Stored preview for {scene_id} -> {preview_ref}")
            except Exception:
                logger.warning(f"Preview generation failed for {scene_id}", exc_info=True)

        return artifact_id, preview_ref
