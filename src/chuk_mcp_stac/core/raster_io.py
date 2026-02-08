"""
Synchronous raster I/O for reading Cloud-Optimised GeoTIFFs.

All functions in this module are sync (they use rasterio, which is sync).
Callers should wrap them in asyncio.to_thread() for async contexts.
"""

import io
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict, Field
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.errors import WindowError
from rasterio.windows import Window, from_bounds
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..constants import MAX_BAND_WORKERS, RETRY_ATTEMPTS, RETRY_MAX_WAIT, RETRY_MIN_WAIT
from ..models.stac import STACAsset

_RETRY_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)


class RasterReadResult(BaseModel):
    """Result of reading bands from COGs."""

    model_config = ConfigDict(frozen=True)

    data: bytes
    crs: str
    shape: list[int] = Field(default_factory=list)
    dtype: str = ""


class ArrayReadResult(BaseModel):
    """Result of reading bands as raw numpy arrays (not packaged as GeoTIFF)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    arrays: list  # list[np.ndarray], one per band
    crs: str
    transform: list[float]  # Affine transform as 6 floats [a, b, c, d, e, f]
    shape: tuple[int, int]  # (height, width) of each band array
    dtype: str


# ─── Low-Level Helpers ─────────────────────────────────────────────────────────


def _reproject_bbox(bbox_4326: list[float], dst_crs: object) -> list[float]:
    """Reproject a [west, south, east, north] bbox from EPSG:4326 to dst_crs."""
    transformer = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
    west, south = transformer.transform(bbox_4326[0], bbox_4326[1])
    east, north = transformer.transform(bbox_4326[2], bbox_4326[3])
    return [west, south, east, north]


@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
    reraise=True,
)
def _read_one_band(
    href: str,
    bbox_4326: list[float] | None,
    target_shape: tuple[int, int] | None,
    resampling: Resampling = Resampling.bilinear,
    fallback_crs: str | None = None,
    fallback_transform: list[float] | None = None,
) -> tuple[np.ndarray, str, object]:
    """
    Read a single band from a COG with retry on transient network errors.

    Args:
        href: URL of the COG asset
        bbox_4326: Optional crop bbox in EPSG:4326
        target_shape: If set, resample to this (height, width)
        resampling: Resampling method (default bilinear; use nearest for classification)
        fallback_crs: CRS to use when the COG has no embedded CRS (e.g., from STAC proj:code)
        fallback_transform: Affine transform [a,b,c,d,e,f] to use when the COG has an
            identity transform (e.g., from STAC proj:transform)

    Returns:
        Tuple of (band_array, crs_string, transform)
    """
    with rasterio.open(href) as src:
        # Use embedded CRS/transform, falling back to STAC metadata
        if src.crs:
            crs_str = str(src.crs)
            geo_transform = src.transform
        elif fallback_crs and fallback_transform:
            crs_str = fallback_crs
            geo_transform = Affine(*fallback_transform)
        else:
            crs_str = str(src.crs)
            geo_transform = src.transform

        if bbox_4326 and len(bbox_4326) == 4:
            if crs_str and crs_str not in ("None", "EPSG:4326"):
                native_bbox = _reproject_bbox(bbox_4326, crs_str)
            else:
                native_bbox = bbox_4326

            window = from_bounds(
                native_bbox[0],
                native_bbox[1],
                native_bbox[2],
                native_bbox[3],
                geo_transform,
            )
            # Clip window to the raster's valid extent so we don't
            # read outside the dataset when the bbox is larger than the scene
            try:
                window = window.intersection(Window(0, 0, src.width, src.height))
            except WindowError:
                raise ValueError(
                    "Requested bbox does not overlap with this scene's extent"
                )

            if window.width < 1 or window.height < 1:
                raise ValueError(
                    "Requested bbox does not overlap with this scene's extent"
                )

            if target_shape is None:
                data = src.read(1, window=window)
            else:
                data = src.read(
                    1,
                    window=window,
                    out_shape=target_shape,
                    resampling=resampling,
                )

            transform = rasterio.windows.transform(window, geo_transform)
        else:
            if target_shape is None:
                data = src.read(1)
            else:
                data = src.read(
                    1,
                    out_shape=target_shape,
                    resampling=resampling,
                )

            transform = geo_transform

    return data, crs_str, transform


# ─── Array-Level Read ──────────────────────────────────────────────────────────


def read_bands_as_arrays(
    assets: dict[str, STACAsset],
    band_names: list[str],
    bbox_4326: list[float] | None = None,
    classification_bands: frozenset[str] | None = None,
    fallback_crs: str | None = None,
    fallback_transform: list[float] | None = None,
) -> ArrayReadResult:
    """
    Read bands from COG assets and return raw numpy arrays + geo metadata.

    Same pipeline as read_bands_from_cogs but returns arrays instead of
    packaging into a GeoTIFF. Used by compute_spectral_index and cloud
    masking operations that need direct array access.

    Args:
        assets: STAC item assets (band_key -> STACAsset)
        band_names: Band asset keys to read
        bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]
        classification_bands: Band names that should use nearest-neighbor
            resampling instead of bilinear (e.g., SCL classification band)
        fallback_crs: CRS from STAC metadata, used when COG has no embedded CRS
        fallback_transform: Affine transform from STAC metadata [a,b,c,d,e,f]

    Returns:
        ArrayReadResult with raw arrays, CRS, transform, shape, and dtype
    """
    classification = classification_bands or frozenset()

    env_opts: dict[str, object] = {"GDAL_HTTP_TIMEOUT": 30}
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        env_opts["AWS_REQUEST_PAYER"] = "requester"
    else:
        env_opts["AWS_NO_SIGN_REQUEST"] = "YES"
    env = rasterio.Env(**env_opts)

    with env:
        # Read first band to establish CRS/transform/target shape
        first_name = band_names[0]
        first_resampling = (
            Resampling.nearest if first_name in classification else Resampling.bilinear
        )
        first_href = assets[first_name].href
        first_data, crs_str, out_transform = _read_one_band(
            first_href, bbox_4326, None, resampling=first_resampling,
            fallback_crs=fallback_crs, fallback_transform=fallback_transform,
        )
        target_shape = first_data.shape

        band_arrays = [first_data]

        # Read remaining bands in parallel
        remaining = band_names[1:]
        if remaining:
            workers = min(len(remaining), MAX_BAND_WORKERS)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(
                        _read_one_band,
                        assets[band].href,
                        bbox_4326,
                        target_shape,
                        Resampling.nearest if band in classification else Resampling.bilinear,
                        fallback_crs,
                        fallback_transform,
                    )
                    for band in remaining
                ]
                for future in futures:
                    data, _, _ = future.result()
                    band_arrays.append(data)

    transform_list = [
        out_transform.a,
        out_transform.b,
        out_transform.c,
        out_transform.d,
        out_transform.e,
        out_transform.f,
    ]

    return ArrayReadResult(
        arrays=band_arrays,
        crs=crs_str or "",
        transform=transform_list,
        shape=target_shape,
        dtype=str(first_data.dtype),
    )


# ─── GeoTIFF Packaging ────────────────────────────────────────────────────────


def arrays_to_geotiff(
    band_arrays: list[np.ndarray],
    crs: str,
    transform: list[float],
    dtype: str = "float32",
    nodata: float | None = None,
) -> bytes:
    """
    Package numpy arrays into in-memory GeoTIFF bytes.

    Args:
        band_arrays: List of 2D numpy arrays (one per band)
        crs: CRS string (e.g., "EPSG:32631")
        transform: Affine transform as 6 floats [a, b, c, d, e, f]
        dtype: Output data type
        nodata: NoData value for the GeoTIFF

    Returns:
        GeoTIFF bytes
    """
    stack = np.stack(band_arrays, axis=0).astype(dtype)
    affine = Affine(*transform)

    buf = io.BytesIO()
    write_kwargs: dict[str, object] = {
        "driver": "GTiff",
        "height": stack.shape[1],
        "width": stack.shape[2],
        "count": stack.shape[0],
        "dtype": dtype,
        "crs": crs,
        "transform": affine,
    }
    if nodata is not None:
        write_kwargs["nodata"] = nodata

    with rasterio.open(buf, "w", **write_kwargs) as dst:
        for i in range(stack.shape[0]):
            dst.write(stack[i], i + 1)

    return buf.getvalue()


def read_bands_from_cogs(
    assets: dict[str, STACAsset],
    band_names: list[str],
    bbox_4326: list[float] | None = None,
    fallback_crs: str | None = None,
    fallback_transform: list[float] | None = None,
) -> RasterReadResult:
    """
    Read bands from COG assets and write an in-memory GeoTIFF.

    The bbox is expected in EPSG:4326. If the raster is in a different
    CRS (e.g., UTM), the bbox is reprojected before windowing.

    Bands with different native resolutions (e.g., 10m vs 20m) are
    resampled to match the first band's pixel grid using bilinear
    interpolation.

    The first band is read to establish CRS, transform, and target shape.
    Remaining bands are read in parallel using a ThreadPoolExecutor.

    Args:
        assets: STAC item assets (band_key -> STACAsset)
        band_names: Band asset keys to read
        bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]
        fallback_crs: CRS from STAC metadata, used when COG has no embedded CRS
        fallback_transform: Affine transform from STAC metadata [a,b,c,d,e,f]

    Returns:
        RasterReadResult with GeoTIFF bytes, CRS, shape, and dtype
    """
    arr_result = read_bands_as_arrays(
        assets, band_names, bbox_4326,
        fallback_crs=fallback_crs, fallback_transform=fallback_transform,
    )
    stack = np.stack(arr_result.arrays, axis=0)
    geotiff_bytes = arrays_to_geotiff(
        arr_result.arrays, arr_result.crs, arr_result.transform, arr_result.dtype
    )

    return RasterReadResult(
        data=geotiff_bytes,
        crs=arr_result.crs,
        shape=list(stack.shape),
        dtype=arr_result.dtype,
    )


# ─── Raster Merging ───────────────────────────────────────────────────────────


def merge_rasters(rasters: list[RasterReadResult]) -> RasterReadResult:
    """
    Merge multiple rasters into a single raster using rasterio.merge.

    Later rasters fill nodata areas from earlier ones. All rasters must
    have the same band count and compatible CRS.

    Args:
        rasters: List of RasterReadResult objects to merge

    Returns:
        Merged RasterReadResult with combined spatial extent

    Raises:
        ValueError: If rasters list is empty
    """
    if not rasters:
        raise ValueError("No rasters to merge")
    if len(rasters) == 1:
        return rasters[0]

    mem_files: list[MemoryFile] = []
    datasets = []
    try:
        for r in rasters:
            memfile = MemoryFile(r.data)
            mem_files.append(memfile)
            datasets.append(memfile.open())

        mosaic_array, mosaic_transform = merge(datasets)
        crs_str = str(datasets[0].crs)

        buf = io.BytesIO()
        with rasterio.open(
            buf,
            "w",
            driver="GTiff",
            height=mosaic_array.shape[1],
            width=mosaic_array.shape[2],
            count=mosaic_array.shape[0],
            dtype=mosaic_array.dtype,
            crs=crs_str,
            transform=mosaic_transform,
        ) as dst:
            for i in range(mosaic_array.shape[0]):
                dst.write(mosaic_array[i], i + 1)

        return RasterReadResult(
            data=buf.getvalue(),
            crs=crs_str,
            shape=list(mosaic_array.shape),
            dtype=str(mosaic_array.dtype),
        )
    finally:
        for ds in datasets:
            ds.close()
        for mf in mem_files:
            mf.close()


# ─── Temporal Compositing ─────────────────────────────────────────────────────

COMPOSITE_METHODS: dict[str, Callable] = {
    "median": lambda a, axis: np.nanmedian(a, axis=axis),
    "mean": lambda a, axis: np.nanmean(a, axis=axis),
    "max": lambda a, axis: np.nanmax(a, axis=axis),
    "min": lambda a, axis: np.nanmin(a, axis=axis),
}


def temporal_composite_arrays(
    scene_arrays: list[list[np.ndarray]],
    method: str = "median",
) -> list[np.ndarray]:
    """
    Combine arrays from multiple scenes per-band using a statistical method.

    Args:
        scene_arrays: List of per-scene band arrays.
            scene_arrays[scene_idx][band_idx] is a 2D numpy array.
            All scenes must have the same number of bands and same shapes.
        method: Compositing method - "median", "mean", "max", or "min"

    Returns:
        List of composited 2D arrays (one per band)

    Raises:
        ValueError: If method is unknown or no scenes provided
    """
    if method not in COMPOSITE_METHODS:
        raise ValueError(
            f"Unknown composite method '{method}'. Available: {list(COMPOSITE_METHODS.keys())}"
        )
    if not scene_arrays:
        raise ValueError("No scene arrays to composite")

    func = COMPOSITE_METHODS[method]
    n_bands = len(scene_arrays[0])

    # Use first scene's shape as reference; resample others to match
    ref_shape = scene_arrays[0][0].shape
    for scene in scene_arrays[1:]:
        for band_idx in range(n_bands):
            if scene[band_idx].shape != ref_shape:
                scene[band_idx] = _resize_array(scene[band_idx], ref_shape)

    result: list[np.ndarray] = []

    for band_idx in range(n_bands):
        # Stack this band across all scenes: shape (n_scenes, H, W)
        stacked = np.stack(
            [scene[band_idx].astype(np.float32) for scene in scene_arrays],
            axis=0,
        )
        # Replace 0 with NaN for cleaner compositing (0 = nodata from cloud mask)
        stacked[stacked == 0] = np.nan
        composited = func(stacked, axis=0)
        result.append(composited)

    return result


# ─── Quality-Weighted Merge ──────────────────────────────────────────────────


def quality_weighted_merge(
    scene_data: list[tuple[list[np.ndarray], np.ndarray]],
) -> list[np.ndarray]:
    """
    Merge multiple scenes, preferring pixels with best quality (lowest cloud).

    For each pixel, selects the value from the scene with the lowest SCL
    cloud/shadow score. SCL values 4-7 (vegetation, soil, water) are best;
    higher values indicate cloud/shadow.

    Args:
        scene_data: List of (band_arrays, scl_array) per scene.
            band_arrays is list[np.ndarray], scl_array is np.ndarray.
            All must have same shapes.

    Returns:
        List of merged 2D arrays (one per band)

    Raises:
        ValueError: If no scene data provided
    """
    if not scene_data:
        raise ValueError("No scene data to merge")
    if len(scene_data) == 1:
        return scene_data[0][0]

    n_bands = len(scene_data[0][0])
    shape = scene_data[0][0][0].shape

    # Stack SCL arrays to find best quality per pixel
    scl_stack = np.stack([scl for _, scl in scene_data], axis=0).astype(np.float32)
    # Quality score: distance from 4 (vegetation) — lower is better
    quality = np.abs(scl_stack - 4.0)
    best_idx = np.argmin(quality, axis=0)  # shape (H, W)

    result: list[np.ndarray] = []
    for band_idx in range(n_bands):
        band_stack = np.stack(
            [bands[band_idx] for bands, _ in scene_data],
            axis=0,
        )
        # Gather pixels from best scene
        out = np.zeros(shape, dtype=band_stack.dtype)
        for s in range(len(scene_data)):
            mask = best_idx == s
            out[mask] = band_stack[s][mask]
        result.append(out)

    return result


# ─── Spectral Index Computation ───────────────────────────────────────────────


def _resize_array(arr: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
    """Resize a 2D array to target shape using nearest-neighbour interpolation."""
    src_h, src_w = arr.shape
    tgt_h, tgt_w = target_shape
    row_idx = (np.arange(tgt_h) * src_h / tgt_h).astype(int).clip(0, src_h - 1)
    col_idx = (np.arange(tgt_w) * src_w / tgt_w).astype(int).clip(0, src_w - 1)
    return arr[np.ix_(row_idx, col_idx)]


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Division with NaN where denominator is zero."""
    result = np.full_like(numerator, np.nan, dtype=np.float32)
    valid = denominator != 0
    result[valid] = numerator[valid].astype(np.float32) / denominator[valid].astype(np.float32)
    return result


INDEX_FORMULAS: dict[str, Callable[[dict[str, np.ndarray]], np.ndarray]] = {
    "ndvi": lambda b: _safe_divide(b["nir"] - b["red"], b["nir"] + b["red"]),
    "ndwi": lambda b: _safe_divide(b["green"] - b["nir"], b["green"] + b["nir"]),
    "ndbi": lambda b: _safe_divide(b["swir16"] - b["nir"], b["swir16"] + b["nir"]),
    "evi": lambda b: (
        2.5
        * _safe_divide(
            b["nir"] - b["red"],
            b["nir"] + 6.0 * b["red"] - 7.5 * b["blue"] + 1.0,
        )
    ),
    "savi": lambda b: (
        _safe_divide(
            b["nir"] - b["red"],
            b["nir"] + b["red"] + 0.5,
        )
        * 1.5
    ),
    "bsi": lambda b: _safe_divide(
        (b["swir16"] + b["red"]) - (b["nir"] + b["blue"]),
        (b["swir16"] + b["red"]) + (b["nir"] + b["blue"]),
    ),
}


def compute_spectral_index(
    band_arrays: dict[str, np.ndarray],
    index_name: str,
) -> np.ndarray:
    """
    Compute a spectral index from band arrays.

    Args:
        band_arrays: Mapping of band_name -> 2D numpy array
        index_name: Index name (must be a key in INDEX_FORMULAS)

    Returns:
        2D float32 numpy array with index values

    Raises:
        ValueError: If index_name is unknown
    """
    formula = INDEX_FORMULAS.get(index_name)
    if formula is None:
        raise ValueError(
            f"Unknown spectral index '{index_name}'. Available: {list(INDEX_FORMULAS.keys())}"
        )
    return formula(band_arrays)


# ─── Cloud Masking ─────────────────────────────────────────────────────────────


def apply_cloud_mask(
    band_arrays: list[np.ndarray],
    scl_array: np.ndarray,
    good_values: frozenset[int] | set[int],
    nodata_value: float = 0,
) -> list[np.ndarray]:
    """
    Apply cloud mask to band arrays using the SCL (Scene Classification Layer).

    Pixels where the SCL value is NOT in good_values are set to nodata_value.

    Args:
        band_arrays: List of 2D numpy arrays (one per band)
        scl_array: 2D numpy array with SCL classification values
        good_values: Set of SCL values to keep (e.g., {4, 5, 6, 7, 11})
        nodata_value: Value to assign to masked (cloudy) pixels

    Returns:
        List of masked 2D numpy arrays (same length as input)
    """
    mask = np.isin(scl_array, list(good_values))

    masked_arrays = []
    for arr in band_arrays:
        masked = arr.copy()
        masked[~mask] = nodata_value
        masked_arrays.append(masked)

    return masked_arrays


def apply_cloud_mask_float(
    band_arrays: list[np.ndarray],
    scl_array: np.ndarray,
    good_values: frozenset[int] | set[int],
) -> list[np.ndarray]:
    """
    Apply cloud mask using NaN for masked pixels (for float32 index outputs).

    Converts arrays to float32 and sets masked pixels to NaN.
    """
    mask = np.isin(scl_array, list(good_values))

    masked_arrays = []
    for arr in band_arrays:
        masked = arr.astype(np.float32)
        masked[~mask] = np.nan
        masked_arrays.append(masked)

    return masked_arrays


# ─── PNG Conversion ────────────────────────────────────────────────────────────


def _percentile_stretch(arr: np.ndarray, low: float = 2, high: float = 98) -> np.ndarray:
    """
    Stretch each band from [p_low, p_high] percentile to [0, 255] uint8.

    Args:
        arr: Array of shape (bands, height, width)
        low: Low percentile (default 2)
        high: High percentile (default 98)

    Returns:
        uint8 array of same shape
    """
    result = np.zeros_like(arr, dtype=np.uint8)
    for i in range(arr.shape[0]):
        band = arr[i].astype(np.float64)
        p_low = np.percentile(band, low)
        p_high = np.percentile(band, high)
        if p_high <= p_low:
            result[i] = 0
        else:
            clipped = np.clip(band, p_low, p_high)
            scaled = (clipped - p_low) / (p_high - p_low) * 255.0
            result[i] = scaled.astype(np.uint8)
    return result


def estimate_band_size(
    assets: dict[str, STACAsset],
    band_names: list[str],
    bbox_4326: list[float] | None = None,
    fallback_crs: str | None = None,
    fallback_transform: list[float] | None = None,
) -> dict:
    """
    Estimate download size by reading COG headers only (no pixel data).

    Opens each band's COG to read the IFD (~1KB), gets dimensions and dtype,
    computes windowed dimensions if bbox is provided.

    Args:
        assets: STAC item assets (band_key -> STACAsset)
        band_names: Band asset keys to estimate
        bbox_4326: Optional crop bbox in EPSG:4326 [west, south, east, north]
        fallback_crs: CRS from STAC metadata, used when COG has no embedded CRS
        fallback_transform: Affine transform from STAC metadata [a,b,c,d,e,f]

    Returns:
        Dict with per_band details, total_pixels, estimated_bytes, estimated_mb, crs
    """
    env_opts: dict[str, object] = {"GDAL_HTTP_TIMEOUT": 30}
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        env_opts["AWS_REQUEST_PAYER"] = "requester"
    else:
        env_opts["AWS_NO_SIGN_REQUEST"] = "YES"

    per_band = []
    total_pixels = 0
    total_bytes = 0
    crs_str = ""

    with rasterio.Env(**env_opts):
        for band_name in band_names:
            href = assets[band_name].href
            with rasterio.open(href) as src:
                # Use embedded CRS/transform, falling back to STAC metadata
                if src.crs:
                    effective_crs = str(src.crs)
                    effective_transform = src.transform
                elif fallback_crs and fallback_transform:
                    effective_crs = fallback_crs
                    effective_transform = Affine(*fallback_transform)
                else:
                    effective_crs = str(src.crs)
                    effective_transform = src.transform

                if not crs_str:
                    crs_str = effective_crs

                dtype_str = str(src.dtypes[0])
                dtype_bytes = np.dtype(dtype_str).itemsize

                if bbox_4326 and len(bbox_4326) == 4:
                    if effective_crs and effective_crs not in ("None", "EPSG:4326"):
                        native_bbox = _reproject_bbox(bbox_4326, effective_crs)
                    else:
                        native_bbox = bbox_4326
                    window = from_bounds(
                        native_bbox[0],
                        native_bbox[1],
                        native_bbox[2],
                        native_bbox[3],
                        effective_transform,
                    )
                    # Clip window to the raster's valid extent
                    try:
                        window = window.intersection(
                            Window(0, 0, src.width, src.height)
                        )
                        height = max(int(round(window.height)), 0)
                        width = max(int(round(window.width)), 0)
                    except WindowError:
                        height = 0
                        width = 0
                else:
                    height = src.height
                    width = src.width

                pixels = height * width
                band_bytes = pixels * dtype_bytes
                total_pixels += pixels
                total_bytes += band_bytes

                per_band.append(
                    {
                        "band": band_name,
                        "width": width,
                        "height": height,
                        "dtype": dtype_str,
                        "bytes": band_bytes,
                    }
                )

    return {
        "per_band": per_band,
        "total_pixels": total_pixels,
        "estimated_bytes": total_bytes,
        "estimated_mb": round(total_bytes / (1024 * 1024), 2),
        "crs": crs_str,
    }


def geotiff_to_png(data: bytes) -> bytes:
    """
    Convert in-memory GeoTIFF bytes to a PNG image.

    Handles:
    - 3+ bands: RGB PNG from first 3 bands
    - 1 band: Grayscale PNG
    - 2 bands: Grayscale from first band

    Applies 2nd-98th percentile auto-stretch for uint8 conversion.

    Args:
        data: GeoTIFF bytes (from read_bands_from_cogs or merge_rasters)

    Returns:
        PNG image bytes
    """
    from PIL import Image

    with MemoryFile(data) as memfile:
        with memfile.open() as src:
            arr = src.read()

    # Determine which bands to use
    band_count = arr.shape[0]
    if band_count >= 3:
        rgb = arr[:3]
    else:
        rgb = arr[:1]

    # Apply per-band percentile stretch to uint8
    stretched = _percentile_stretch(rgb)

    # Create PIL image
    if stretched.shape[0] == 1:
        img = Image.fromarray(stretched[0], mode="L")
    else:
        img = Image.fromarray(np.transpose(stretched, (1, 2, 0)), mode="RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
