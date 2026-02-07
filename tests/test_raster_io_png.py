"""Tests for PNG conversion in raster_io."""

import io

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds as transform_from_bounds

from chuk_mcp_stac.core.raster_io import _percentile_stretch, geotiff_to_png


def _make_geotiff_bytes(
    bands: int,
    height: int = 20,
    width: int = 20,
    dtype: str = "uint16",
    fill: int = 1000,
) -> bytes:
    """Create in-memory GeoTIFF bytes for testing."""
    arr = np.full((bands, height, width), fill, dtype=dtype)
    for b in range(bands):
        arr[b, :, :] += b * 100
        arr[b, 0, 0] = 0
        arr[b, -1, -1] = 10000

    buf = io.BytesIO()
    transform = transform_from_bounds(0, 0, 1, 1, width, height)
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=bands,
        dtype=dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        for i in range(bands):
            dst.write(arr[i], i + 1)
    return buf.getvalue()


class TestPercentileStretch:
    def test_basic_stretch(self):
        arr = np.array([[[0, 50, 100, 150, 200]]], dtype=np.uint16)
        result = _percentile_stretch(arr)
        assert result.dtype == np.uint8
        assert result.shape == arr.shape

    def test_flat_band_returns_zeros(self):
        arr = np.full((1, 10, 10), 42, dtype=np.uint16)
        result = _percentile_stretch(arr)
        assert np.all(result == 0)

    def test_multi_band(self):
        arr = np.random.randint(0, 10000, (3, 10, 10), dtype=np.uint16)
        result = _percentile_stretch(arr)
        assert result.shape == (3, 10, 10)
        assert result.dtype == np.uint8

    def test_output_range(self):
        arr = np.linspace(0, 10000, 100, dtype=np.uint16).reshape(1, 10, 10)
        result = _percentile_stretch(arr)
        assert result.min() >= 0
        assert result.max() <= 255


class TestGeotiffToPng:
    def test_3band_rgb(self):
        data = _make_geotiff_bytes(3)
        png_bytes = geotiff_to_png(data)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.mode == "RGB"
        assert img.size == (20, 20)

    def test_1band_grayscale(self):
        data = _make_geotiff_bytes(1)
        png_bytes = geotiff_to_png(data)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.mode == "L"

    def test_4band_uses_first_3(self):
        data = _make_geotiff_bytes(4)
        png_bytes = geotiff_to_png(data)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.mode == "RGB"

    def test_2band_grayscale_fallback(self):
        data = _make_geotiff_bytes(2)
        png_bytes = geotiff_to_png(data)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.mode == "L"

    def test_output_is_valid_png(self):
        data = _make_geotiff_bytes(3)
        png_bytes = geotiff_to_png(data)
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_roundtrip_preserves_size(self):
        data = _make_geotiff_bytes(3, height=50, width=30)
        png_bytes = geotiff_to_png(data)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.size == (30, 50)
