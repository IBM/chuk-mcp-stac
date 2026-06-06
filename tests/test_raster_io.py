"""Tests for chuk_mcp_stac.core.raster_io."""

import io
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError

from chuk_mcp_stac.core.raster_io import (
    RasterReadResult,
    _read_one_band,
    _reproject_bbox,
    estimate_band_size,
    merge_rasters,
    quality_weighted_merge,
    read_bands_from_cogs,
    temporal_composite_arrays,
)
from chuk_mcp_stac.models.stac import STACAsset

from .conftest import create_temp_geotiff


class TestReprojectBbox:
    def test_4326_to_utm(self):
        """Reprojecting from EPSG:4326 to UTM should produce meter-scale coords."""
        bbox = [0.85, 51.85, 0.95, 51.93]
        result = _reproject_bbox(bbox, "EPSG:32631")
        west, south, east, north = result

        # UTM zone 31N coords should be in the hundreds of thousands
        assert west > 100_000
        assert east > west
        assert north > south

    def test_4326_to_4326(self):
        """Reprojecting 4326 to 4326 should be ~identity."""
        bbox = [10.0, 50.0, 11.0, 51.0]
        result = _reproject_bbox(bbox, "EPSG:4326")
        assert abs(result[0] - 10.0) < 0.001
        assert abs(result[1] - 50.0) < 0.001
        assert abs(result[2] - 11.0) < 0.001
        assert abs(result[3] - 51.0) < 0.001


class TestReadBandsFromCogs:
    def test_single_band_no_bbox(self, temp_geotiff_dir):
        """Read a single band without bbox windowing."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        assets = {"red": STACAsset(href=path)}

        result = read_bands_from_cogs(assets, ["red"])

        assert isinstance(result, RasterReadResult)
        assert result.crs == "EPSG:32631"
        assert result.shape == [1, 10, 10]
        assert result.dtype == "uint16"
        assert len(result.data) > 0

        # Verify it's a valid GeoTIFF by reading it back
        with rasterio.open(io.BytesIO(result.data)) as src:
            data = src.read(1)
            assert data.shape == (10, 10)
            assert np.all(data == 42)

    def test_multi_band_no_bbox(self, temp_geotiff_dir):
        """Read multiple bands, all same resolution."""
        path_r = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=100)
        path_g = create_temp_geotiff(temp_geotiff_dir, "green.tif", fill_value=200)
        path_b = create_temp_geotiff(temp_geotiff_dir, "blue.tif", fill_value=300)

        assets = {
            "red": STACAsset(href=path_r),
            "green": STACAsset(href=path_g),
            "blue": STACAsset(href=path_b),
        }

        result = read_bands_from_cogs(assets, ["red", "green", "blue"])
        assert result.shape == [3, 10, 10]

        with rasterio.open(io.BytesIO(result.data)) as src:
            assert src.count == 3
            assert np.all(src.read(1) == 100)
            assert np.all(src.read(2) == 200)
            assert np.all(src.read(3) == 300)

    def test_with_bbox_utm(self, temp_geotiff_dir):
        """Read with a bbox that crops the raster (UTM CRS, bbox in 4326)."""
        from pyproj import Transformer

        # Create a raster in UTM zone 31N
        utm_bounds = (400000, 5700000, 600000, 5800000)
        path = create_temp_geotiff(
            temp_geotiff_dir,
            "red.tif",
            width=200,
            height=200,
            bounds=utm_bounds,
            fill_value=55,
        )
        assets = {"red": STACAsset(href=path)}

        # Convert the center ~25% of the raster bounds to EPSG:4326
        t = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
        w, s = t.transform(450000, 5725000)
        e, n = t.transform(550000, 5775000)
        bbox_4326 = [w, s, e, n]

        result = read_bands_from_cogs(assets, ["red"], bbox_4326)

        assert result.shape[0] == 1
        assert result.shape[1] > 0
        assert result.shape[2] > 0

    def test_resolution_mismatch_resampling(self, temp_geotiff_dir):
        """Bands with different resolutions should be resampled to match first band."""
        bounds = (500000, 5700000, 500100, 5700100)

        # Band 1: 10m (high res) -> 10x10 pixels
        path_hr = create_temp_geotiff(
            temp_geotiff_dir,
            "red.tif",
            width=10,
            height=10,
            bounds=bounds,
            fill_value=100,
        )
        # Band 2: 20m (low res) -> 5x5 pixels
        path_lr = create_temp_geotiff(
            temp_geotiff_dir,
            "swir.tif",
            width=5,
            height=5,
            bounds=bounds,
            fill_value=200,
        )

        assets = {
            "red": STACAsset(href=path_hr),
            "swir": STACAsset(href=path_lr),
        }

        result = read_bands_from_cogs(assets, ["red", "swir"])

        # Both bands should have the same shape (10x10, matching first band)
        assert result.shape == [2, 10, 10]

        with rasterio.open(io.BytesIO(result.data)) as src:
            band1 = src.read(1)
            band2 = src.read(2)
            assert band1.shape == (10, 10)
            assert band2.shape == (10, 10)

    def test_missing_band_key_raises(self, temp_geotiff_dir):
        """Requesting a band not in assets should raise KeyError."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif")
        assets = {"red": STACAsset(href=path)}
        with pytest.raises(KeyError):
            read_bands_from_cogs(assets, ["nonexistent"])

    def test_corrupt_file_raises(self, temp_geotiff_dir):
        """A corrupt GeoTIFF should raise a rasterio error."""
        import os

        corrupt_path = os.path.join(temp_geotiff_dir, "corrupt.tif")
        with open(corrupt_path, "wb") as f:
            f.write(b"not a geotiff")
        assets = {"red": STACAsset(href=corrupt_path)}
        with pytest.raises(Exception):
            read_bands_from_cogs(assets, ["red"])

    def test_empty_band_list(self, temp_geotiff_dir):
        """Empty band list should raise due to empty array stack."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif")
        assets = {"red": STACAsset(href=path)}
        with pytest.raises(Exception):
            read_bands_from_cogs(assets, [])

    def test_epsg_4326_source_crs(self, temp_geotiff_dir):
        """When source CRS is EPSG:4326, no reprojection of bbox needed."""
        path = create_temp_geotiff(
            temp_geotiff_dir,
            "red.tif",
            width=10,
            height=10,
            crs="EPSG:4326",
            bounds=(0.0, 51.0, 1.0, 52.0),
            fill_value=77,
        )
        assets = {"red": STACAsset(href=path)}

        bbox_4326 = [0.2, 51.2, 0.8, 51.8]
        result = read_bands_from_cogs(assets, ["red"], bbox_4326)

        assert result.crs == "EPSG:4326"
        assert result.shape[0] == 1
        assert result.shape[1] > 0


class TestMergeRasters:
    def test_merge_two_adjacent_rasters(self, temp_geotiff_dir):
        """Merge two side-by-side rasters into one wider raster."""
        path1 = create_temp_geotiff(
            temp_geotiff_dir,
            "left.tif",
            bounds=(500000, 5700000, 500050, 5700100),
            fill_value=100,
        )
        path2 = create_temp_geotiff(
            temp_geotiff_dir,
            "right.tif",
            bounds=(500050, 5700000, 500100, 5700100),
            fill_value=200,
        )

        r1 = read_bands_from_cogs({"red": STACAsset(href=path1)}, ["red"])
        r2 = read_bands_from_cogs({"red": STACAsset(href=path2)}, ["red"])

        merged = merge_rasters([r1, r2])

        assert merged.crs == "EPSG:32631"
        assert merged.shape[0] == 1  # 1 band
        # Merged should be wider than either input
        assert merged.shape[2] >= 20

        # Verify it's a valid GeoTIFF
        with rasterio.open(io.BytesIO(merged.data)) as src:
            assert src.count == 1

    def test_single_raster_passthrough(self, temp_geotiff_dir):
        """Merging a single raster should return it unchanged."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        r = read_bands_from_cogs({"red": STACAsset(href=path)}, ["red"])
        merged = merge_rasters([r])
        assert merged.data == r.data

    def test_empty_list_raises(self):
        """Merging an empty list should raise ValueError."""
        with pytest.raises(ValueError, match="No rasters"):
            merge_rasters([])


class TestReadOneBand:
    def test_single_band_no_bbox(self, temp_geotiff_dir):
        """_read_one_band should read a single band and return crs + transform."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        data, crs, transform = _read_one_band(path, None, None)
        assert data.shape == (10, 10)
        assert crs == "EPSG:32631"
        assert transform is not None

    def test_with_target_shape(self, temp_geotiff_dir):
        """_read_one_band should resample to target_shape when provided."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        data, crs, transform = _read_one_band(path, None, (5, 5))
        assert data.shape == (5, 5)

    def test_retry_on_connection_error(self, temp_geotiff_dir):
        """_read_one_band should retry on ConnectionError."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        original_open = rasterio.open
        call_count = 0

        def flaky_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient failure")
            return original_open(*args, **kwargs)

        with patch("chuk_mcp_stac.core.raster_io.rasterio.open", side_effect=flaky_open):
            data, crs, _ = _read_one_band(path, None, None)

        assert data.shape == (10, 10)
        assert call_count == 2

    def test_retry_exhausted_raises(self, temp_geotiff_dir):
        """_read_one_band should raise after retry exhaustion."""
        with patch(
            "chuk_mcp_stac.core.raster_io.rasterio.open",
            side_effect=ConnectionError("refused"),
        ):
            with pytest.raises(ConnectionError):
                _read_one_band("https://example.com/fake.tif", None, None)


class TestParallelBandReads:
    def test_single_band_skips_pool(self, temp_geotiff_dir):
        """A single band should not use ThreadPoolExecutor."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        assets = {"red": STACAsset(href=path)}

        with patch("chuk_mcp_stac.core.raster_io.ThreadPoolExecutor") as mock_pool:
            result = read_bands_from_cogs(assets, ["red"])

        mock_pool.assert_not_called()
        assert result.shape == [1, 10, 10]

    def test_multi_band_uses_pool(self, temp_geotiff_dir):
        """Multiple bands should use ThreadPoolExecutor for parallel reads."""
        path_r = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=100)
        path_g = create_temp_geotiff(temp_geotiff_dir, "green.tif", fill_value=200)
        path_b = create_temp_geotiff(temp_geotiff_dir, "blue.tif", fill_value=300)

        assets = {
            "red": STACAsset(href=path_r),
            "green": STACAsset(href=path_g),
            "blue": STACAsset(href=path_b),
        }

        result = read_bands_from_cogs(assets, ["red", "green", "blue"])
        assert result.shape == [3, 10, 10]

        # Verify band order preserved
        with rasterio.open(io.BytesIO(result.data)) as src:
            assert np.all(src.read(1) == 100)
            assert np.all(src.read(2) == 200)
            assert np.all(src.read(3) == 300)


class TestEstimateBandSize:
    def test_single_band_no_bbox(self, temp_geotiff_dir):
        """Estimate a single band without bbox cropping."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", width=100, height=100)
        assets = {"red": STACAsset(href=path)}

        result = estimate_band_size(assets, ["red"])

        assert len(result["per_band"]) == 1
        assert result["per_band"][0]["band"] == "red"
        assert result["per_band"][0]["width"] == 100
        assert result["per_band"][0]["height"] == 100
        assert result["per_band"][0]["dtype"] == "uint16"
        assert result["total_pixels"] == 10000
        assert result["estimated_bytes"] == 20000  # 10000 pixels * 2 bytes
        assert result["estimated_mb"] == pytest.approx(20000 / (1024 * 1024), abs=0.01)
        assert "EPSG:32631" in result["crs"]

    def test_multi_band_no_bbox(self, temp_geotiff_dir):
        """Estimate multiple bands."""
        path_r = create_temp_geotiff(temp_geotiff_dir, "red.tif", width=50, height=50)
        path_g = create_temp_geotiff(temp_geotiff_dir, "green.tif", width=50, height=50)
        assets = {"red": STACAsset(href=path_r), "green": STACAsset(href=path_g)}

        result = estimate_band_size(assets, ["red", "green"])

        assert len(result["per_band"]) == 2
        assert result["total_pixels"] == 5000  # 2500 * 2

    def test_with_bbox_reduces_size(self, temp_geotiff_dir):
        """Using a bbox should reduce the estimated dimensions."""
        path = create_temp_geotiff(
            temp_geotiff_dir,
            "red.tif",
            width=100,
            height=100,
            crs="EPSG:32631",
            bounds=(500000, 5700000, 500100, 5700100),
        )
        assets = {"red": STACAsset(href=path)}

        # Full size
        full = estimate_band_size(assets, ["red"])
        # Cropped — bbox covers roughly half the extent
        bbox_4326_half = [0.849, 51.849, 0.8504, 51.8495]
        # This will crop to a window, so should be smaller
        cropped = estimate_band_size(assets, ["red"], bbox_4326_half)

        assert cropped["total_pixels"] <= full["total_pixels"]


class TestRasterReadResult:
    def test_frozen(self):
        r = RasterReadResult(data=b"x", crs="EPSG:4326")
        with pytest.raises(ValidationError):
            r.crs = "EPSG:32631"

    def test_defaults(self):
        r = RasterReadResult(data=b"x", crs="EPSG:4326")
        assert r.shape == []
        assert r.dtype == ""


class TestTemporalCompositeArrays:
    def test_median_two_scenes(self):
        a1 = [np.array([[10, 20]], dtype=np.float32)]
        a2 = [np.array([[30, 40]], dtype=np.float32)]
        result = temporal_composite_arrays([a1, a2], "median")
        assert len(result) == 1
        assert result[0].shape == (1, 2)
        # median of [10,30]=20, [20,40]=30
        np.testing.assert_allclose(result[0], [[20, 30]])

    def test_mean_method(self):
        a1 = [np.array([[10, 20]], dtype=np.float32)]
        a2 = [np.array([[30, 40]], dtype=np.float32)]
        result = temporal_composite_arrays([a1, a2], "mean")
        np.testing.assert_allclose(result[0], [[20, 30]])

    def test_max_method(self):
        a1 = [np.array([[10, 40]], dtype=np.float32)]
        a2 = [np.array([[30, 20]], dtype=np.float32)]
        result = temporal_composite_arrays([a1, a2], "max")
        np.testing.assert_allclose(result[0], [[30, 40]])

    def test_min_method(self):
        a1 = [np.array([[10, 40]], dtype=np.float32)]
        a2 = [np.array([[30, 20]], dtype=np.float32)]
        result = temporal_composite_arrays([a1, a2], "min")
        np.testing.assert_allclose(result[0], [[10, 20]])

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown composite method"):
            temporal_composite_arrays([[np.zeros((2, 2))]], "invalid")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No scene arrays"):
            temporal_composite_arrays([], "median")

    def test_multi_band(self):
        a1 = [np.array([[1, 2]], dtype=np.float32), np.array([[10, 20]], dtype=np.float32)]
        a2 = [np.array([[3, 4]], dtype=np.float32), np.array([[30, 40]], dtype=np.float32)]
        result = temporal_composite_arrays([a1, a2], "mean")
        assert len(result) == 2
        np.testing.assert_allclose(result[0], [[2, 3]])
        np.testing.assert_allclose(result[1], [[20, 30]])


class TestQualityWeightedMerge:
    def test_prefers_vegetation(self):
        """Pixel from scene with SCL=4 (vegetation) should be preferred."""
        bands1 = [np.array([[100]], dtype=np.uint16)]
        scl1 = np.array([[4]], dtype=np.uint8)  # vegetation - best
        bands2 = [np.array([[200]], dtype=np.uint16)]
        scl2 = np.array([[9]], dtype=np.uint8)  # cloud

        result = quality_weighted_merge([(bands1, scl1), (bands2, scl2)])
        assert result[0][0, 0] == 100

    def test_single_scene_passthrough(self):
        bands = [np.array([[50, 60]], dtype=np.uint16)]
        scl = np.array([[4, 4]], dtype=np.uint8)
        result = quality_weighted_merge([(bands, scl)])
        np.testing.assert_array_equal(result[0], [[50, 60]])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No scene data"):
            quality_weighted_merge([])

    def test_multi_band(self):
        bands1 = [
            np.array([[100]], dtype=np.uint16),
            np.array([[10]], dtype=np.uint16),
        ]
        scl1 = np.array([[4]], dtype=np.uint8)
        bands2 = [
            np.array([[200]], dtype=np.uint16),
            np.array([[20]], dtype=np.uint16),
        ]
        scl2 = np.array([[9]], dtype=np.uint8)

        result = quality_weighted_merge([(bands1, scl1), (bands2, scl2)])
        assert len(result) == 2
        assert result[0][0, 0] == 100
        assert result[1][0, 0] == 10


def _create_no_crs_geotiff(
    tmp_dir: str,
    name: str = "vv.tif",
    width: int = 100,
    height: int = 100,
    fill_value: int = 500,
) -> str:
    """Create a GeoTIFF with no CRS and identity transform (simulates S1 GRD)."""
    import os

    path = os.path.join(tmp_dir, name)
    data = np.full((height, width), fill_value, dtype="uint16")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="uint16",
    ) as dst:
        dst.write(data, 1)
    return path


class TestFallbackCrsTransform:
    """Test fallback CRS/transform for COGs without embedded georeferencing."""

    def test_read_one_band_no_crs_no_fallback_no_bbox(self, temp_geotiff_dir):
        """Without bbox, reading works even without CRS."""
        path = _create_no_crs_geotiff(temp_geotiff_dir)
        data, crs, transform = _read_one_band(path, None, None)
        assert data.shape == (100, 100)

    def test_read_one_band_no_crs_with_fallback_and_bbox(self, temp_geotiff_dir):
        """With fallback CRS/transform, bbox windowing works on no-CRS COGs."""
        path = _create_no_crs_geotiff(temp_geotiff_dir, width=100, height=100)

        # Fallback: EPSG:4326, pixel=0.01 degrees, origin at (-2.0, 53.0)
        fb_crs = "EPSG:4326"
        fb_transform = [0.01, 0.0, -2.0, 0.0, -0.01, 53.0]

        # Bbox covering the middle area: -1.5 to -1.0 E, 52.5 to 52.8 N
        bbox = [-1.5, 52.5, -1.0, 52.8]

        data, crs, transform = _read_one_band(
            path,
            bbox,
            None,
            fallback_crs=fb_crs,
            fallback_transform=fb_transform,
        )
        assert crs == "EPSG:4326"
        # Window should be smaller than full raster
        assert data.shape[0] < 100
        assert data.shape[1] < 100
        assert data.shape[0] > 0
        assert data.shape[1] > 0

    def test_read_one_band_no_crs_bbox_no_overlap_raises(self, temp_geotiff_dir):
        """Non-overlapping bbox with fallback should raise ValueError."""
        path = _create_no_crs_geotiff(temp_geotiff_dir, width=100, height=100)

        fb_crs = "EPSG:4326"
        fb_transform = [0.01, 0.0, -2.0, 0.0, -0.01, 53.0]

        # Bbox completely outside the raster extent
        bbox = [10.0, 40.0, 11.0, 41.0]

        with pytest.raises(ValueError, match="does not overlap"):
            _read_one_band(
                path,
                bbox,
                None,
                fallback_crs=fb_crs,
                fallback_transform=fb_transform,
            )

    def test_read_bands_from_cogs_with_fallback(self, temp_geotiff_dir):
        """read_bands_from_cogs passes fallback through to _read_one_band."""
        path = _create_no_crs_geotiff(temp_geotiff_dir, name="vv.tif")
        assets = {"vv": STACAsset(href=path)}

        fb_crs = "EPSG:4326"
        fb_transform = [0.01, 0.0, -2.0, 0.0, -0.01, 53.0]
        bbox = [-1.5, 52.5, -1.0, 52.8]

        result = read_bands_from_cogs(
            assets,
            ["vv"],
            bbox,
            fallback_crs=fb_crs,
            fallback_transform=fb_transform,
        )
        assert result.crs == "EPSG:4326"
        assert len(result.data) > 0

    def test_estimate_band_size_with_fallback(self, temp_geotiff_dir):
        """estimate_band_size uses fallback for windowing."""
        path = _create_no_crs_geotiff(temp_geotiff_dir, name="vv.tif")
        assets = {"vv": STACAsset(href=path)}

        fb_crs = "EPSG:4326"
        fb_transform = [0.01, 0.0, -2.0, 0.0, -0.01, 53.0]
        bbox = [-1.5, 52.5, -1.0, 52.8]

        result = estimate_band_size(
            assets,
            ["vv"],
            bbox,
            fallback_crs=fb_crs,
            fallback_transform=fb_transform,
        )
        # Should succeed and report a smaller area than full raster
        assert result["total_pixels"] > 0
        assert result["total_pixels"] < 100 * 100

    def test_fallback_not_used_when_crs_present(self, temp_geotiff_dir):
        """When COG has embedded CRS, fallback is ignored."""
        path = create_temp_geotiff(temp_geotiff_dir, "red.tif", fill_value=42)
        assets = {"red": STACAsset(href=path)}

        # Pass bogus fallback — should be ignored
        result = read_bands_from_cogs(
            assets,
            ["red"],
            fallback_crs="EPSG:4326",
            fallback_transform=[0.01, 0.0, 0.0, 0.0, -0.01, 90.0],
        )
        # CRS should be from the GeoTIFF, not the fallback
        assert result.crs == "EPSG:32631"
