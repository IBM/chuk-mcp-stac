"""Tests for cloud masking functions in raster_io."""

import numpy as np

from chuk_mcp_stac.constants import SCL_GOOD_VALUES
from chuk_mcp_stac.core.raster_io import apply_cloud_mask, apply_cloud_mask_float


class TestApplyCloudMask:
    def test_masks_cloud_pixels(self):
        band = np.full((3, 3), 1000, dtype=np.uint16)
        scl = np.array(
            [
                [4, 9, 5],  # veg, cloud_high, bare_soil
                [8, 4, 6],  # cloud_med, veg, water
                [3, 11, 1],  # shadow, snow, saturated
            ],
            dtype=np.uint8,
        )

        result = apply_cloud_mask([band], scl, SCL_GOOD_VALUES)

        assert result[0][0, 0] == 1000  # SCL=4 (veg) — kept
        assert result[0][0, 1] == 0  # SCL=9 (cloud_high) — masked
        assert result[0][0, 2] == 1000  # SCL=5 (bare_soil) — kept
        assert result[0][1, 0] == 0  # SCL=8 (cloud_med) — masked
        assert result[0][1, 1] == 1000  # SCL=4 (veg) — kept
        assert result[0][1, 2] == 1000  # SCL=6 (water) — kept
        assert result[0][2, 0] == 0  # SCL=3 (shadow) — masked
        assert result[0][2, 1] == 1000  # SCL=11 (snow) — kept
        assert result[0][2, 2] == 0  # SCL=1 (saturated) — masked

    def test_preserves_good_pixels(self):
        band = np.arange(9, dtype=np.uint16).reshape(3, 3)
        scl = np.full((3, 3), 4, dtype=np.uint8)  # all vegetation
        result = apply_cloud_mask([band], scl, SCL_GOOD_VALUES)
        np.testing.assert_array_equal(result[0], band)

    def test_masks_all_bad(self):
        band = np.full((3, 3), 500, dtype=np.uint16)
        scl = np.full((3, 3), 9, dtype=np.uint8)  # all cloud
        result = apply_cloud_mask([band], scl, SCL_GOOD_VALUES)
        assert np.all(result[0] == 0)

    def test_multiple_bands(self):
        band1 = np.full((2, 2), 100, dtype=np.uint16)
        band2 = np.full((2, 2), 200, dtype=np.uint16)
        scl = np.array([[4, 9], [9, 5]], dtype=np.uint8)

        result = apply_cloud_mask([band1, band2], scl, SCL_GOOD_VALUES)

        assert len(result) == 2
        assert result[0][0, 0] == 100  # kept
        assert result[0][0, 1] == 0  # masked
        assert result[1][0, 0] == 200  # kept
        assert result[1][0, 1] == 0  # masked

    def test_does_not_modify_original(self):
        band = np.full((3, 3), 1000, dtype=np.uint16)
        scl = np.full((3, 3), 9, dtype=np.uint8)  # all cloud
        original_copy = band.copy()
        apply_cloud_mask([band], scl, SCL_GOOD_VALUES)
        np.testing.assert_array_equal(band, original_copy)

    def test_custom_nodata_value(self):
        band = np.full((2, 2), 100, dtype=np.uint16)
        scl = np.array([[4, 9], [9, 4]], dtype=np.uint8)
        result = apply_cloud_mask([band], scl, SCL_GOOD_VALUES, nodata_value=999)
        assert result[0][0, 1] == 999

    def test_cloud_low_prob_kept(self):
        """SCL=7 (cloud_low_prob) is in SCL_GOOD_VALUES."""
        band = np.full((1, 1), 42, dtype=np.uint16)
        scl = np.array([[7]], dtype=np.uint8)
        result = apply_cloud_mask([band], scl, SCL_GOOD_VALUES)
        assert result[0][0, 0] == 42


class TestApplyCloudMaskFloat:
    def test_uses_nan_for_masked(self):
        band = np.full((2, 2), 1000.0, dtype=np.float32)
        scl = np.array([[4, 9], [8, 5]], dtype=np.uint8)

        result = apply_cloud_mask_float([band], scl, SCL_GOOD_VALUES)

        assert result[0][0, 0] == 1000.0
        assert np.isnan(result[0][0, 1])
        assert np.isnan(result[0][1, 0])
        assert result[0][1, 1] == 1000.0

    def test_converts_to_float32(self):
        band = np.full((2, 2), 100, dtype=np.uint16)
        scl = np.full((2, 2), 4, dtype=np.uint8)
        result = apply_cloud_mask_float([band], scl, SCL_GOOD_VALUES)
        assert result[0].dtype == np.float32

    def test_multiple_bands(self):
        band1 = np.full((2, 2), 100, dtype=np.uint16)
        band2 = np.full((2, 2), 200, dtype=np.uint16)
        scl = np.array([[4, 9], [9, 5]], dtype=np.uint8)

        result = apply_cloud_mask_float([band1, band2], scl, SCL_GOOD_VALUES)

        assert len(result) == 2
        assert result[0][0, 0] == 100.0
        assert np.isnan(result[0][0, 1])
        assert result[1][0, 0] == 200.0
        assert np.isnan(result[1][0, 1])

    def test_all_nan_when_all_cloud(self):
        band = np.full((3, 3), 500, dtype=np.float32)
        scl = np.full((3, 3), 9, dtype=np.uint8)
        result = apply_cloud_mask_float([band], scl, SCL_GOOD_VALUES)
        assert np.all(np.isnan(result[0]))
