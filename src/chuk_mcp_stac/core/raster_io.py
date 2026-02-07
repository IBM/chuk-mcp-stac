"""
Synchronous raster I/O for reading Cloud-Optimised GeoTIFFs.

All functions in this module are sync (they use rasterio, which is sync).
Callers should wrap them in asyncio.to_thread() for async contexts.
"""

import io
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict, Field
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.windows import from_bounds
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
) -> tuple[np.ndarray, str, object]:
    """
    Read a single band from a COG with retry on transient network errors.

    Args:
        href: URL of the COG asset
        bbox_4326: Optional crop bbox in EPSG:4326
        target_shape: If set, resample to this (height, width)

    Returns:
        Tuple of (band_array, crs_string, transform)
    """
    with rasterio.open(href) as src:
        crs_str = str(src.crs)

        if bbox_4326 and len(bbox_4326) == 4:
            if src.crs and crs_str != "EPSG:4326":
                native_bbox = _reproject_bbox(bbox_4326, src.crs)
            else:
                native_bbox = bbox_4326

            window = from_bounds(
                native_bbox[0],
                native_bbox[1],
                native_bbox[2],
                native_bbox[3],
                src.transform,
            )

            if target_shape is None:
                data = src.read(1, window=window)
            else:
                data = src.read(
                    1,
                    window=window,
                    out_shape=target_shape,
                    resampling=Resampling.bilinear,
                )

            transform = src.window_transform(window)
        else:
            if target_shape is None:
                data = src.read(1)
            else:
                data = src.read(
                    1,
                    out_shape=target_shape,
                    resampling=Resampling.bilinear,
                )

            transform = src.transform

    return data, crs_str, transform


def read_bands_from_cogs(
    assets: dict[str, STACAsset],
    band_names: list[str],
    bbox_4326: list[float] | None = None,
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

    Returns:
        RasterReadResult with GeoTIFF bytes, CRS, shape, and dtype
    """
    # When AWS credentials are available, use signed requests with requester-pays
    # (needed for Landsat requester-pays buckets). Otherwise fall back to
    # anonymous access (sufficient for public Sentinel-2 COGs).
    env_opts: dict[str, object] = {"GDAL_HTTP_TIMEOUT": 30}
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        env_opts["AWS_REQUEST_PAYER"] = "requester"
    else:
        env_opts["AWS_NO_SIGN_REQUEST"] = "YES"
    env = rasterio.Env(**env_opts)

    with env:
        # Read first band to establish CRS/transform/target shape
        first_href = assets[band_names[0]].href
        first_data, crs_str, out_transform = _read_one_band(first_href, bbox_4326, None)
        target_shape = first_data.shape

        band_arrays = [first_data]

        # Read remaining bands in parallel
        remaining = band_names[1:]
        if remaining:
            workers = min(len(remaining), MAX_BAND_WORKERS)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_read_one_band, assets[band].href, bbox_4326, target_shape)
                    for band in remaining
                ]
                for future in futures:
                    data, _, _ = future.result()
                    band_arrays.append(data)

    stack = np.stack(band_arrays, axis=0)

    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=stack.shape[1],
        width=stack.shape[2],
        count=stack.shape[0],
        dtype=stack.dtype,
        crs=crs_str,
        transform=out_transform,
    ) as dst:
        for i in range(stack.shape[0]):
            dst.write(stack[i], i + 1)

    return RasterReadResult(
        data=buf.getvalue(),
        crs=crs_str or "",
        shape=list(stack.shape),
        dtype=str(stack.dtype),
    )


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
