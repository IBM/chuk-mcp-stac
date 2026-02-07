"""Tests for spectral index computation and array utilities in raster_io."""

import io

import numpy as np
import pytest
import rasterio

from chuk_mcp_stac.core.raster_io import (
    _safe_divide,
    arrays_to_geotiff,
    compute_spectral_index,
)


class TestSafeDivide:
    def test_normal_values(self):
        num = np.array([2.0, 4.0], dtype=np.float32)
        den = np.array([4.0, 2.0], dtype=np.float32)
        result = _safe_divide(num, den)
        np.testing.assert_array_almost_equal(result, [0.5, 2.0])

    def test_zero_denominator_gives_nan(self):
        num = np.array([1.0, 2.0], dtype=np.float32)
        den = np.array([0.0, 2.0], dtype=np.float32)
        result = _safe_divide(num, den)
        assert np.isnan(result[0])
        assert result[1] == pytest.approx(1.0)

    def test_both_zero(self):
        num = np.array([0.0], dtype=np.float32)
        den = np.array([0.0], dtype=np.float32)
        result = _safe_divide(num, den)
        assert np.isnan(result[0])

    def test_returns_float32(self):
        num = np.array([1, 2], dtype=np.uint16)
        den = np.array([2, 4], dtype=np.uint16)
        result = _safe_divide(num, den)
        assert result.dtype == np.float32


class TestComputeSpectralIndex:
    def test_ndvi(self):
        bands = {
            "red": np.array([[100, 200]], dtype=np.float32),
            "nir": np.array([[300, 400]], dtype=np.float32),
        }
        result = compute_spectral_index(bands, "ndvi")
        expected_0 = (300 - 100) / (300 + 100)
        expected_1 = (400 - 200) / (400 + 200)
        assert result[0, 0] == pytest.approx(expected_0)
        assert result[0, 1] == pytest.approx(expected_1)

    def test_ndwi(self):
        bands = {
            "green": np.array([[100]], dtype=np.float32),
            "nir": np.array([[200]], dtype=np.float32),
        }
        result = compute_spectral_index(bands, "ndwi")
        assert result[0, 0] == pytest.approx((100 - 200) / (100 + 200))

    def test_ndbi(self):
        bands = {
            "swir16": np.array([[250]], dtype=np.float32),
            "nir": np.array([[200]], dtype=np.float32),
        }
        result = compute_spectral_index(bands, "ndbi")
        assert result[0, 0] == pytest.approx((250 - 200) / (250 + 200))

    def test_evi(self):
        bands = {
            "blue": np.array([[50]], dtype=np.float32),
            "red": np.array([[100]], dtype=np.float32),
            "nir": np.array([[300]], dtype=np.float32),
        }
        result = compute_spectral_index(bands, "evi")
        expected = 2.5 * (300 - 100) / (300 + 6 * 100 - 7.5 * 50 + 1)
        assert result[0, 0] == pytest.approx(expected, rel=1e-5)

    def test_savi(self):
        bands = {
            "red": np.array([[100]], dtype=np.float32),
            "nir": np.array([[300]], dtype=np.float32),
        }
        result = compute_spectral_index(bands, "savi")
        expected = ((300 - 100) / (300 + 100 + 0.5)) * 1.5
        assert result[0, 0] == pytest.approx(expected, rel=1e-5)

    def test_bsi(self):
        bands = {
            "blue": np.array([[50]], dtype=np.float32),
            "red": np.array([[100]], dtype=np.float32),
            "nir": np.array([[300]], dtype=np.float32),
            "swir16": np.array([[250]], dtype=np.float32),
        }
        result = compute_spectral_index(bands, "bsi")
        expected = ((250 + 100) - (300 + 50)) / ((250 + 100) + (300 + 50))
        assert result[0, 0] == pytest.approx(expected, rel=1e-5)

    def test_unknown_index_raises(self):
        with pytest.raises(ValueError, match="Unknown spectral index"):
            compute_spectral_index({}, "fake_index")

    def test_all_zeros_gives_nan(self):
        bands = {
            "red": np.zeros((3, 3), dtype=np.float32),
            "nir": np.zeros((3, 3), dtype=np.float32),
        }
        result = compute_spectral_index(bands, "ndvi")
        assert np.all(np.isnan(result))

    def test_ndvi_value_range(self):
        """NDVI should be in [-1, 1] for non-NaN values."""
        rng = np.random.default_rng(42)
        bands = {
            "red": rng.integers(1, 10000, size=(20, 20)).astype(np.float32),
            "nir": rng.integers(1, 10000, size=(20, 20)).astype(np.float32),
        }
        result = compute_spectral_index(bands, "ndvi")
        valid = result[~np.isnan(result)]
        assert valid.min() >= -1.0
        assert valid.max() <= 1.0


class TestArraysToGeotiff:
    def test_single_band_float32(self):
        arr = np.random.rand(10, 10).astype(np.float32)
        transform = [10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0]
        data = arrays_to_geotiff([arr], "EPSG:32631", transform)

        with rasterio.open(io.BytesIO(data)) as src:
            assert src.count == 1
            assert src.dtypes[0] == "float32"
            read_back = src.read(1)
            np.testing.assert_array_almost_equal(read_back, arr)

    def test_multi_band(self):
        arrs = [np.random.rand(10, 10).astype(np.float32) for _ in range(3)]
        transform = [10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0]
        data = arrays_to_geotiff(arrs, "EPSG:32631", transform)

        with rasterio.open(io.BytesIO(data)) as src:
            assert src.count == 3

    def test_with_nodata(self):
        arr = np.full((5, 5), np.nan, dtype=np.float32)
        transform = [10.0, 0.0, 500000.0, 0.0, -10.0, 5700050.0]
        data = arrays_to_geotiff([arr], "EPSG:32631", transform, nodata=float("nan"))

        with rasterio.open(io.BytesIO(data)) as src:
            assert src.nodata is not None

    def test_preserves_crs(self):
        arr = np.zeros((5, 5), dtype=np.float32)
        transform = [10.0, 0.0, 500000.0, 0.0, -10.0, 5700050.0]
        data = arrays_to_geotiff([arr], "EPSG:4326", transform)

        with rasterio.open(io.BytesIO(data)) as src:
            assert "4326" in str(src.crs)

    def test_uint16_dtype(self):
        arr = np.full((5, 5), 1000, dtype=np.uint16)
        transform = [10.0, 0.0, 500000.0, 0.0, -10.0, 5700050.0]
        data = arrays_to_geotiff([arr], "EPSG:32631", transform, dtype="uint16")

        with rasterio.open(io.BytesIO(data)) as src:
            assert src.dtypes[0] == "uint16"
