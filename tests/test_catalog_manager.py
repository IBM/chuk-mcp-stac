"""Tests for chuk_mcp_stac.core.catalog_manager."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from chuk_mcp_stac.core.catalog_manager import (
    _MAX_SCENE_CACHE,
    BandDownloadResult,
    CatalogManager,
    IndexComputeResult,
)
from chuk_mcp_stac.core.raster_io import RasterReadResult
from chuk_mcp_stac.models.stac import STACItem

from .conftest import SAMPLE_BBOX, SAMPLE_SCENE_ID, make_stac_item


class TestGetCatalogUrl:
    def test_default_catalog(self, catalog_manager):
        url = catalog_manager.get_catalog_url()
        assert "earth-search" in url

    def test_explicit_earth_search(self, catalog_manager):
        url = catalog_manager.get_catalog_url("earth_search")
        assert "earth-search" in url

    def test_explicit_planetary_computer(self, catalog_manager):
        url = catalog_manager.get_catalog_url("planetary_computer")
        assert "planetarycomputer" in url

    def test_unknown_raises(self, catalog_manager):
        with pytest.raises(ValueError, match="Unknown catalog"):
            catalog_manager.get_catalog_url("nonexistent")


class TestSceneCache:
    def test_cache_and_retrieve(self, catalog_manager):
        item = make_stac_item()
        catalog_manager.cache_scene("scene1", item, "earth_search")
        assert catalog_manager.get_cached_scene("scene1") == item

    def test_get_uncached_returns_none(self, catalog_manager):
        assert catalog_manager.get_cached_scene("nonexistent") is None

    def test_get_scene_catalog(self, catalog_manager):
        item = make_stac_item()
        catalog_manager.cache_scene("scene1", item, "planetary_computer")
        assert catalog_manager.get_scene_catalog("scene1") == "planetary_computer"

    def test_get_scene_catalog_missing(self, catalog_manager):
        assert catalog_manager.get_scene_catalog("nonexistent") is None

    def test_lru_eviction(self, catalog_manager):
        # Fill cache to max + 1
        for i in range(_MAX_SCENE_CACHE + 1):
            item = STACItem(id=f"scene_{i}")
            catalog_manager.cache_scene(f"scene_{i}", item, "es")

        # First scene should have been evicted
        assert catalog_manager.get_cached_scene("scene_0") is None
        # Last scene should still be there
        assert catalog_manager.get_cached_scene(f"scene_{_MAX_SCENE_CACHE}") is not None

    def test_lru_touch_prevents_eviction(self, catalog_manager):
        # Cache scene_0
        catalog_manager.cache_scene("scene_0", STACItem(id="scene_0"), "es")

        # Fill up to max - 1 more (total = MAX)
        for i in range(1, _MAX_SCENE_CACHE):
            catalog_manager.cache_scene(f"scene_{i}", STACItem(id=f"scene_{i}"), "es")

        # Touch scene_0 (moves to end)
        catalog_manager.get_cached_scene("scene_0")

        # Add one more to trigger eviction — scene_1 (oldest untouched) should go
        catalog_manager.cache_scene("scene_new", STACItem(id="scene_new"), "es")

        assert catalog_manager.get_cached_scene("scene_0") is not None
        assert catalog_manager.get_cached_scene("scene_1") is None

    def test_recaching_same_scene_moves_to_end(self, catalog_manager):
        item1 = make_stac_item(scene_id="s1")
        item2 = make_stac_item(scene_id="s2")
        catalog_manager.cache_scene("s1", item1, "es")
        catalog_manager.cache_scene("s2", item2, "es")
        # Re-cache s1 with updated value
        item1_new = make_stac_item(scene_id="s1", cloud_cover=99.0)
        catalog_manager.cache_scene("s1", item1_new, "es")
        result = catalog_manager.get_cached_scene("s1")
        assert result is not None
        assert result.properties.cloud_cover == 99.0


class TestSignPcAssets:
    def test_noop_for_earth_search(self, catalog_manager):
        """Non-PC catalogs should not modify asset hrefs."""
        item = make_stac_item()
        catalog_manager.cache_scene("s1", item, "earth_search")
        original_href = item.assets["red"].href
        catalog_manager._sign_pc_assets("s1", item)
        assert item.assets["red"].href == original_href

    def test_signs_azure_urls(self, catalog_manager):
        """PC catalog should sign Azure Blob Storage URLs."""
        item = make_stac_item()
        for asset in item.assets.values():
            asset.href = f"https://sentinel1euwest.blob.core.windows.net/s1-grd/{asset.href}"
        catalog_manager.cache_scene("s1", item, "planetary_computer")

        with patch("planetary_computer.sign_url", side_effect=lambda url: url + "?sig=SIGNED"):
            catalog_manager._sign_pc_assets("s1", item)

        for asset in item.assets.values():
            assert asset.href.endswith("?sig=SIGNED")

    def test_skips_non_azure_urls(self, catalog_manager):
        """PC signing should skip non-Azure URLs (e.g., S3 hrefs)."""
        item = make_stac_item()
        catalog_manager.cache_scene("s1", item, "planetary_computer")
        original_hrefs = {k: a.href for k, a in item.assets.items()}

        with patch("planetary_computer.sign_url") as mock_sign:
            catalog_manager._sign_pc_assets("s1", item)
            mock_sign.assert_not_called()

        for k, asset in item.assets.items():
            assert asset.href == original_hrefs[k]

    def test_no_crash_without_package(self, catalog_manager):
        """Should not crash if planetary-computer is not installed."""
        item = make_stac_item()
        for asset in item.assets.values():
            asset.href = "https://sentinel1euwest.blob.core.windows.net/s1-grd/test.tif"
        catalog_manager.cache_scene("s1", item, "planetary_computer")

        with patch.dict("sys.modules", {"planetary_computer": None}):
            catalog_manager._sign_pc_assets("s1", item)


class TestDownloadBands:
    async def test_scene_not_found(self, catalog_manager):
        with pytest.raises(ValueError, match="not found"):
            await catalog_manager.download_bands("nonexistent", ["red"])

    async def test_band_not_found(self, manager_with_scene):
        with pytest.raises(ValueError, match="Band.*not found"):
            await manager_with_scene.download_bands(SAMPLE_SCENE_ID, ["nonexistent_band"])

    async def test_no_artifact_store(self, manager_with_scene):
        mock_result = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store", return_value=None
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_result),
        ):
            with pytest.raises(RuntimeError, match="No artifact store"):
                await manager_with_scene.download_bands(SAMPLE_SCENE_ID, ["red"])

    async def test_happy_path(self, manager_with_scene):
        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[2, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(side_effect=["art://test-ref-123", "art://preview-ref"])

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_result),
            patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"),
        ):
            result = await manager_with_scene.download_bands(
                SAMPLE_SCENE_ID, ["red", "nir"], SAMPLE_BBOX
            )

        assert isinstance(result, BandDownloadResult)
        assert result.artifact_ref == "art://test-ref-123"
        assert result.crs == "EPSG:32631"
        assert result.shape == [2, 10, 10]
        assert result.preview_ref == "art://preview-ref"


class TestBandAliasResolution:
    """Verify hardware band aliases are resolved before download."""

    async def test_download_bands_resolves_aliases(self, manager_with_scene):
        """B04 and B08 should be resolved to red and nir before asset lookup."""
        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[2, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://alias-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch(
                "chuk_mcp_stac.core.raster_io.read_bands_from_cogs",
                return_value=mock_result,
            ) as mock_read,
        ):
            result = await manager_with_scene.download_bands(SAMPLE_SCENE_ID, ["B04", "B08"])

        assert isinstance(result, BandDownloadResult)
        # read_bands_from_cogs should have received resolved names
        call_args = mock_read.call_args
        assert call_args[0][1] == ["red", "nir"]

    async def test_download_mosaic_resolves_aliases(self, manager_with_scene):
        """B04 should be resolved to red in mosaic downloads."""
        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        mock_merged = RasterReadResult(
            data=b"merged", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://mosaic-alias")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch(
                "chuk_mcp_stac.core.raster_io.read_bands_from_cogs",
                return_value=mock_result,
            ) as mock_read,
            patch(
                "chuk_mcp_stac.core.raster_io.merge_rasters",
                return_value=mock_merged,
            ),
        ):
            result = await manager_with_scene.download_mosaic([SAMPLE_SCENE_ID], ["B04"])

        assert isinstance(result, BandDownloadResult)
        # read_bands_from_cogs should have received resolved name
        call_args = mock_read.call_args
        assert call_args[0][1] == ["red"]


class TestStoreRaster:
    async def test_store_failure_raises_runtime_error(self, catalog_manager):
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(side_effect=Exception("storage exploded"))

        with pytest.raises(RuntimeError, match="storage exploded"):
            await catalog_manager._store_raster(
                store=mock_store,
                data=b"data",
                scene_id="s1",
                bands=["red"],
                bbox=[],
                crs="EPSG:32631",
                shape=[1, 10, 10],
                dtype="uint16",
            )

    async def test_geotiff_generates_preview(self, catalog_manager):
        """GeoTIFF storage should auto-generate a PNG preview."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(side_effect=["art://main-ref", "art://preview-ref"])

        with patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"):
            artifact_ref, preview_ref = await catalog_manager._store_raster(
                store=mock_store,
                data=b"geotiff_data",
                scene_id="s1",
                bands=["red"],
                bbox=[],
                crs="EPSG:32631",
                shape=[1, 10, 10],
                dtype="uint16",
                mime="image/tiff",
                geotiff_data=b"geotiff_data",
            )

        assert artifact_ref == "art://main-ref"
        assert preview_ref == "art://preview-ref"
        assert mock_store.store.call_count == 2
        # Second call should be PNG preview
        preview_call = mock_store.store.call_args_list[1]
        assert preview_call[1]["mime"] == "image/png"
        assert "preview" in preview_call[1]["summary"]

    async def test_png_no_preview(self, catalog_manager):
        """PNG storage should NOT generate a separate preview."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://png-ref")

        artifact_ref, preview_ref = await catalog_manager._store_raster(
            store=mock_store,
            data=b"png_data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
        )

        assert artifact_ref == "art://png-ref"
        assert preview_ref is None
        assert mock_store.store.call_count == 1

    async def test_preview_failure_nonfatal(self, catalog_manager):
        """Preview generation failure should not break the main store."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(side_effect=["art://main-ref", Exception("preview failed")])

        with patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"):
            artifact_ref, preview_ref = await catalog_manager._store_raster(
                store=mock_store,
                data=b"geotiff_data",
                scene_id="s1",
                bands=["red"],
                bbox=[],
                crs="EPSG:32631",
                shape=[1, 10, 10],
                dtype="uint16",
                mime="image/tiff",
                geotiff_data=b"geotiff_data",
            )

        assert artifact_ref == "art://main-ref"
        assert preview_ref is None

    async def test_geotiff_without_geotiff_data_no_preview(self, catalog_manager):
        """GeoTIFF mime but no geotiff_data param should skip preview."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://main-ref")

        artifact_ref, preview_ref = await catalog_manager._store_raster(
            store=mock_store,
            data=b"geotiff_data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/tiff",
        )

        assert artifact_ref == "art://main-ref"
        assert preview_ref is None
        assert mock_store.store.call_count == 1


class TestEstimateSize:
    async def test_scene_not_found(self, catalog_manager):
        with pytest.raises(ValueError, match="not found"):
            await catalog_manager.estimate_size("nonexistent", ["red"])

    async def test_band_not_found(self, manager_with_scene):
        with pytest.raises(ValueError, match="Band.*not found"):
            await manager_with_scene.estimate_size(SAMPLE_SCENE_ID, ["nonexistent"])

    async def test_happy_path(self, manager_with_scene):
        mock_estimate = {
            "per_band": [
                {"band": "red", "width": 100, "height": 100, "dtype": "uint16", "bytes": 20000}
            ],
            "total_pixels": 10000,
            "estimated_bytes": 20000,
            "estimated_mb": 0.02,
            "crs": "EPSG:32631",
        }
        with patch("chuk_mcp_stac.core.raster_io.estimate_band_size", return_value=mock_estimate):
            result = await manager_with_scene.estimate_size(SAMPLE_SCENE_ID, ["red"])

        assert result["estimated_mb"] == 0.02
        assert result["warnings"] == []

    async def test_large_download_warning(self, manager_with_scene):
        mock_estimate = {
            "per_band": [
                {
                    "band": "red",
                    "width": 10000,
                    "height": 10000,
                    "dtype": "uint16",
                    "bytes": 200_000_000,
                }
            ],
            "total_pixels": 100_000_000,
            "estimated_bytes": 600_000_000,
            "estimated_mb": 572.0,
            "crs": "EPSG:32631",
        }
        with patch("chuk_mcp_stac.core.raster_io.estimate_band_size", return_value=mock_estimate):
            result = await manager_with_scene.estimate_size(SAMPLE_SCENE_ID, ["red"])

        assert len(result["warnings"]) == 1
        assert "Large download" in result["warnings"][0]

    async def test_very_large_download_warning(self, manager_with_scene):
        mock_estimate = {
            "per_band": [
                {
                    "band": "red",
                    "width": 20000,
                    "height": 20000,
                    "dtype": "uint16",
                    "bytes": 800_000_000,
                }
            ],
            "total_pixels": 400_000_000,
            "estimated_bytes": 1_500_000_000,
            "estimated_mb": 1430.0,
            "crs": "EPSG:32631",
        }
        with patch("chuk_mcp_stac.core.raster_io.estimate_band_size", return_value=mock_estimate):
            result = await manager_with_scene.estimate_size(SAMPLE_SCENE_ID, ["red"])

        assert len(result["warnings"]) == 1
        assert "Very large download" in result["warnings"][0]

    async def test_resolves_band_aliases(self, manager_with_scene):
        mock_estimate = {
            "per_band": [
                {"band": "red", "width": 10, "height": 10, "dtype": "uint16", "bytes": 200}
            ],
            "total_pixels": 100,
            "estimated_bytes": 200,
            "estimated_mb": 0.0,
            "crs": "EPSG:32631",
        }
        with patch(
            "chuk_mcp_stac.core.raster_io.estimate_band_size", return_value=mock_estimate
        ) as mock_est:
            await manager_with_scene.estimate_size(SAMPLE_SCENE_ID, ["B04"])

        # Should have resolved B04 to red before calling estimate_band_size
        call_args = mock_est.call_args
        assert call_args[0][1] == ["red"]


class TestGetStore:
    def test_returns_none_on_import_error(self, catalog_manager):
        with patch.dict("sys.modules", {"chuk_mcp_server": None}):
            result = catalog_manager._get_store()
            assert result is None


class TestDownloadMosaic:
    async def test_scene_not_found(self, catalog_manager):
        with pytest.raises(ValueError, match="not found"):
            await catalog_manager.download_mosaic(["nonexistent"], ["red"])

    async def test_band_not_found(self, manager_with_scene):
        with pytest.raises(ValueError, match="Band.*not found"):
            await manager_with_scene.download_mosaic([SAMPLE_SCENE_ID], ["nonexistent_band"])

    async def test_no_artifact_store(self, manager_with_scene):
        mock_raster = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=None,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_raster),
        ):
            with pytest.raises(RuntimeError, match="No artifact store"):
                await manager_with_scene.download_mosaic([SAMPLE_SCENE_ID], ["red"])

    async def test_happy_path(self, manager_with_scene):
        mock_raster = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        merged_raster = RasterReadResult(
            data=b"merged", crs="EPSG:32631", shape=[1, 20, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://mosaic-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_raster),
            patch("chuk_mcp_stac.core.raster_io.merge_rasters", return_value=merged_raster),
        ):
            result = await manager_with_scene.download_mosaic([SAMPLE_SCENE_ID], ["red"])

        assert isinstance(result, BandDownloadResult)
        assert result.artifact_ref == "art://mosaic-ref"
        assert result.shape == [1, 20, 10]


class TestBandDownloadResult:
    def test_frozen(self):
        r = BandDownloadResult(artifact_ref="art://1", crs="EPSG:32631")
        with pytest.raises(ValidationError):
            r.crs = "EPSG:4326"

    def test_defaults(self):
        r = BandDownloadResult(artifact_ref="art://1", crs="EPSG:32631")
        assert r.shape == []
        assert r.dtype == ""


class TestGetCatalogUrlGenericUrls:
    def test_https_url_passthrough(self, catalog_manager):
        url = "https://custom-stac.example.com/api/v1"
        assert catalog_manager.get_catalog_url(url) == url

    def test_http_url_passthrough(self, catalog_manager):
        url = "http://localhost:8080/stac"
        assert catalog_manager.get_catalog_url(url) == url

    def test_short_names_still_work(self, catalog_manager):
        url = catalog_manager.get_catalog_url("earth_search")
        assert "earth-search" in url


class TestIndexComputeResult:
    def test_frozen(self):
        r = IndexComputeResult(artifact_ref="art://1", crs="EPSG:32631")
        with pytest.raises(ValidationError):
            r.crs = "EPSG:4326"

    def test_defaults(self):
        r = IndexComputeResult(artifact_ref="art://1", crs="EPSG:32631")
        assert r.shape == []
        assert r.value_range == []


class TestComputeIndex:
    async def test_unknown_index(self, catalog_manager):
        with pytest.raises(ValueError, match="Unknown index"):
            await catalog_manager.compute_index("any", "fake_index")

    async def test_scene_not_found(self, manager_with_scene):
        with pytest.raises(ValueError, match="not found"):
            await manager_with_scene.compute_index("nonexistent", "ndvi")

    async def test_band_not_found(self, catalog_manager):
        """Scene exists but is missing required bands."""
        item = make_stac_item(bands=["green", "blue"])  # no red, no nir
        catalog_manager.cache_scene("no_bands", item, "es")
        with pytest.raises(ValueError, match="Band.*not found"):
            await catalog_manager.compute_index("no_bands", "ndvi")

    async def test_cloud_mask_requires_scl(self, catalog_manager):
        """cloud_mask=True should fail when scene has no SCL band."""
        item = make_stac_item(bands=["red", "nir"])  # no scl
        catalog_manager.cache_scene("no_scl", item, "es")
        with pytest.raises(ValueError, match="scl"):
            await catalog_manager.compute_index("no_scl", "ndvi", cloud_mask=True)

    async def test_no_artifact_store(self, manager_with_scene):
        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store", return_value=None
            ),
        ):
            with pytest.raises(RuntimeError, match="No artifact store"):
                await manager_with_scene.compute_index(SAMPLE_SCENE_ID, "ndvi")

    async def test_happy_path(self, manager_with_scene):
        import numpy as np

        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        mock_arr_result = ArrayReadResult(
            arrays=[
                np.array([[100, 200]], dtype=np.float32),  # red
                np.array([[300, 400]], dtype=np.float32),  # nir
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(1, 2),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ndvi-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch(
                "chuk_mcp_stac.core.raster_io.read_bands_as_arrays",
                return_value=mock_arr_result,
            ),
        ):
            result = await manager_with_scene.compute_index(SAMPLE_SCENE_ID, "ndvi")

        assert isinstance(result, IndexComputeResult)
        assert result.artifact_ref == "art://ndvi-ref"
        assert result.crs == "EPSG:32631"
        assert len(result.value_range) == 2
        assert result.value_range[0] <= result.value_range[1]


class TestDownloadBandsCloudMask:
    async def test_cloud_mask_requires_scl(self, catalog_manager):
        """cloud_mask=True should fail when scene has no SCL band."""
        item = make_stac_item(bands=["red", "green", "blue"])
        catalog_manager.cache_scene("no_scl", item, "es")
        with pytest.raises(ValueError, match="scl"):
            await catalog_manager.download_bands("no_scl", ["red"], cloud_mask=True)

    async def test_cloud_mask_happy_path(self, manager_with_scene):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        mock_arr = ArrayReadResult(
            arrays=[
                np.full((3, 3), 1000, dtype=np.uint16),  # red
                np.full((3, 3), 4, dtype=np.uint8),  # scl (all vegetation = good)
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(3, 3),
            dtype="uint16",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://masked-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.arrays_to_geotiff", return_value=b"fake_tiff"),
        ):
            result = await manager_with_scene.download_bands(
                SAMPLE_SCENE_ID, ["red"], cloud_mask=True
            )

        assert isinstance(result, BandDownloadResult)
        assert result.artifact_ref == "art://masked-ref"


class TestDownloadBandsPng:
    async def test_png_output_format(self, manager_with_scene):
        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://png-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_result),
            patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"),
        ):
            result = await manager_with_scene.download_bands(
                SAMPLE_SCENE_ID, ["red"], output_format="png"
            )

        assert result.artifact_ref == "art://png-ref"
        # Verify PNG mime type was used
        store_call = mock_store.store.call_args
        assert store_call[1]["mime"] == "image/png"


class TestDownloadMosaicCloudMask:
    async def test_mosaic_cloud_mask_happy_path(self, manager_with_scene):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        mock_arr = ArrayReadResult(
            arrays=[
                np.full((3, 3), 1000, dtype=np.uint16),  # red
                np.full((3, 3), 4, dtype=np.uint8),  # scl
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(3, 3),
            dtype="uint16",
        )

        merged_raster = RasterReadResult(
            data=b"merged", crs="EPSG:32631", shape=[1, 6, 3], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://mosaic-masked")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.arrays_to_geotiff", return_value=b"fake_tiff"),
            patch("chuk_mcp_stac.core.raster_io.merge_rasters", return_value=merged_raster),
        ):
            result = await manager_with_scene.download_mosaic(
                [SAMPLE_SCENE_ID], ["red"], cloud_mask=True
            )

        assert result.artifact_ref == "art://mosaic-masked"

    async def test_mosaic_cloud_mask_requires_scl(self, catalog_manager):
        item = make_stac_item(bands=["red", "green", "blue"])
        catalog_manager.cache_scene("no_scl", item, "es")
        with pytest.raises(ValueError, match="scl"):
            await catalog_manager.download_mosaic(["no_scl"], ["red"], cloud_mask=True)


class TestDownloadMosaicPng:
    async def test_mosaic_png_format(self, manager_with_scene):
        mock_raster = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        merged_raster = RasterReadResult(
            data=b"merged", crs="EPSG:32631", shape=[1, 20, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://mosaic-png")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_raster),
            patch("chuk_mcp_stac.core.raster_io.merge_rasters", return_value=merged_raster),
            patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"),
        ):
            result = await manager_with_scene.download_mosaic(
                [SAMPLE_SCENE_ID], ["red"], output_format="png"
            )

        assert result.artifact_ref == "art://mosaic-png"
        store_call = mock_store.store.call_args
        assert store_call[1]["mime"] == "image/png"


class TestComputeIndexPng:
    async def test_compute_index_png_format(self, manager_with_scene):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        mock_arr = ArrayReadResult(
            arrays=[
                np.array([[100, 200]], dtype=np.float32),
                np.array([[300, 400]], dtype=np.float32),
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(1, 2),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ndvi-png")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"),
        ):
            result = await manager_with_scene.compute_index(
                SAMPLE_SCENE_ID, "ndvi", output_format="png"
            )

        assert result.artifact_ref == "art://ndvi-png"
        store_call = mock_store.store.call_args
        assert store_call[1]["mime"] == "image/png"


class TestComputeIndexCloudMask:
    async def test_compute_index_with_cloud_mask(self, manager_with_scene):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        mock_arr = ArrayReadResult(
            arrays=[
                np.array([[100, 200]], dtype=np.float32),  # red
                np.array([[300, 400]], dtype=np.float32),  # nir
                np.array([[4, 9]], dtype=np.uint8),  # scl (4=good, 9=cloud)
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(1, 2),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ndvi-masked")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
        ):
            result = await manager_with_scene.compute_index(
                SAMPLE_SCENE_ID, "ndvi", cloud_mask=True
            )

        assert isinstance(result, IndexComputeResult)
        assert result.artifact_ref == "art://ndvi-masked"


class TestGetStacClient:
    def test_cache_hit(self, catalog_manager):
        """Second call should return cached client without calling Client.open again."""
        mock_client = MagicMock()
        with patch("pystac_client.Client.open", return_value=mock_client) as mock_open:
            c1 = catalog_manager.get_stac_client("https://example.com/stac")
            c2 = catalog_manager.get_stac_client("https://example.com/stac")

        assert c1 is c2
        assert mock_open.call_count == 1

    def test_different_urls_cached_independently(self, catalog_manager):
        """Different URLs should create separate cache entries."""
        mock_a = MagicMock()
        mock_b = MagicMock()
        with patch("pystac_client.Client.open", side_effect=[mock_a, mock_b]):
            ca = catalog_manager.get_stac_client("https://a.example.com")
            cb = catalog_manager.get_stac_client("https://b.example.com")

        assert ca is not cb

    def test_ttl_expiry(self, catalog_manager):
        """Expired cache entry should trigger a new Client.open call."""
        mock_old = MagicMock()
        mock_new = MagicMock()
        with patch("pystac_client.Client.open", side_effect=[mock_old, mock_new]):
            c1 = catalog_manager.get_stac_client("https://example.com")
            # Manually expire the cache entry
            url = "https://example.com"
            with catalog_manager._client_lock:
                _, _ = catalog_manager._client_cache[url]
                catalog_manager._client_cache[url] = (mock_old, time.monotonic() - 400)
            c2 = catalog_manager.get_stac_client("https://example.com")

        assert c1 is mock_old
        assert c2 is mock_new

    def test_retry_on_transient_error(self, catalog_manager):
        """Should retry on ConnectionError and succeed on second attempt."""
        mock_client = MagicMock()
        with patch(
            "pystac_client.Client.open",
            side_effect=[ConnectionError("refused"), mock_client],
        ):
            result = catalog_manager.get_stac_client("https://example.com")

        assert result is mock_client

    def test_retry_exhausted_raises(self, catalog_manager):
        """Should raise after all retry attempts are exhausted."""
        with patch(
            "pystac_client.Client.open",
            side_effect=ConnectionError("refused"),
        ):
            with pytest.raises(ConnectionError):
                catalog_manager.get_stac_client("https://example.com")


class TestEnrichmentKwargs:
    """Tests for _enrichment_kwargs helper."""

    def test_sentinel2_band_wavelengths(self, catalog_manager):
        """Known collection with band intel should return wavelengths."""
        item = make_stac_item(collection="sentinel-2-l2a")
        result = catalog_manager._enrichment_kwargs(item, ["red", "nir"])
        assert result["collection"] == "sentinel-2-l2a"
        assert result["datetime_str"] == "2024-07-15T10:56:29Z"
        assert result["band_wavelengths"] is not None
        assert "red" in result["band_wavelengths"]
        assert "nir" in result["band_wavelengths"]

    def test_unknown_collection_no_wavelengths(self, catalog_manager):
        """Unknown collection should return None for band_wavelengths."""
        item = make_stac_item(collection="unknown-collection")
        result = catalog_manager._enrichment_kwargs(item, ["red"])
        assert result["collection"] == "unknown-collection"
        assert result["band_wavelengths"] is None

    def test_geometry_fields_populated(self, catalog_manager):
        """Items with geometry fields should pass them through."""
        item = make_stac_item(
            sun_elevation=45.2,
            sun_azimuth=120.5,
            view_off_nadir=3.1,
        )
        result = catalog_manager._enrichment_kwargs(item, ["red"])
        assert result["sun_elevation"] == 45.2
        assert result["sun_azimuth"] == 120.5
        assert result["view_off_nadir"] == 3.1

    def test_geometry_fields_none_when_absent(self, catalog_manager):
        """Items without geometry fields should return None."""
        item = make_stac_item()
        result = catalog_manager._enrichment_kwargs(item, ["red"])
        assert result["sun_elevation"] is None
        assert result["sun_azimuth"] is None
        assert result["view_off_nadir"] is None


class TestStoreRasterMetadata:
    """Tests for enriched metadata in _store_raster."""

    async def test_schema_version_in_metadata(self, catalog_manager):
        """Metadata should include schema_version '1.0'."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
        )

        call_kwargs = mock_store.store.call_args[1]
        assert call_kwargs["meta"]["schema_version"] == "1.0"

    async def test_collection_in_metadata(self, catalog_manager):
        """Collection should appear in metadata when provided."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
            collection="sentinel-2-l2a",
        )

        meta = mock_store.store.call_args[1]["meta"]
        assert meta["collection"] == "sentinel-2-l2a"

    async def test_collection_omitted_when_empty(self, catalog_manager):
        """Empty collection should not appear in metadata."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
        )

        meta = mock_store.store.call_args[1]["meta"]
        assert "collection" not in meta

    async def test_datetime_in_metadata(self, catalog_manager):
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
            datetime_str="2024-07-15T10:56:29Z",
        )

        meta = mock_store.store.call_args[1]["meta"]
        assert meta["datetime"] == "2024-07-15T10:56:29Z"

    async def test_band_wavelengths_in_metadata(self, catalog_manager):
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
            band_wavelengths={"red": 665},
        )

        meta = mock_store.store.call_args[1]["meta"]
        assert meta["band_wavelengths"] == {"red": 665}

    async def test_sun_elevation_in_metadata(self, catalog_manager):
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
            sun_elevation=45.2,
            sun_azimuth=120.5,
            view_off_nadir=3.1,
        )

        meta = mock_store.store.call_args[1]["meta"]
        assert meta["sun_elevation"] == 45.2
        assert meta["sun_azimuth"] == 120.5
        assert meta["view_off_nadir"] == 3.1

    async def test_none_geometry_omitted(self, catalog_manager):
        """None geometry values should not appear in metadata."""
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        await catalog_manager._store_raster(
            store=mock_store,
            data=b"data",
            scene_id="s1",
            bands=["red"],
            bbox=[],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            mime="image/png",
        )

        meta = mock_store.store.call_args[1]["meta"]
        assert "sun_elevation" not in meta
        assert "sun_azimuth" not in meta
        assert "view_off_nadir" not in meta


class TestDownloadBandsEnrichment:
    """Verify download_bands passes enrichment kwargs to _store_raster."""

    async def test_metadata_includes_collection_and_datetime(self, catalog_manager):
        item = make_stac_item(
            collection="sentinel-2-l2a",
            sun_elevation=50.0,
        )
        catalog_manager.cache_scene("enrich1", item, "es")

        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(side_effect=["art://main", "art://preview"])

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_result),
            patch("chuk_mcp_stac.core.raster_io.geotiff_to_png", return_value=b"fake_png"),
        ):
            await catalog_manager.download_bands("enrich1", ["red"])

        meta = mock_store.store.call_args_list[0][1]["meta"]
        assert meta["schema_version"] == "1.0"
        assert meta["collection"] == "sentinel-2-l2a"
        assert meta["datetime"] == "2024-07-15T10:56:29Z"
        assert meta["sun_elevation"] == 50.0


class TestDownloadMosaicEnrichment:
    """Verify download_mosaic passes enrichment kwargs from first scene."""

    async def test_mosaic_metadata_from_first_scene(self, catalog_manager):
        item1 = make_stac_item(scene_id="m1", collection="sentinel-2-l2a", sun_elevation=48.0)
        item2 = make_stac_item(scene_id="m2", collection="sentinel-2-l2a", sun_elevation=52.0)
        catalog_manager.cache_scene("m1", item1, "es")
        catalog_manager.cache_scene("m2", item2, "es")

        mock_raster = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        merged = RasterReadResult(
            data=b"merged", crs="EPSG:32631", shape=[1, 20, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://mosaic")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_raster),
            patch("chuk_mcp_stac.core.raster_io.merge_rasters", return_value=merged),
        ):
            await catalog_manager.download_mosaic(["m1", "m2"], ["red"])

        meta = mock_store.store.call_args_list[0][1]["meta"]
        assert meta["schema_version"] == "1.0"
        assert meta["collection"] == "sentinel-2-l2a"
        # Should use first scene's sun_elevation
        assert meta["sun_elevation"] == 48.0


class TestComputeIndexEnrichment:
    """Verify compute_index passes enrichment kwargs to _store_raster."""

    async def test_index_metadata_includes_enrichment(self, catalog_manager):
        item = make_stac_item(
            scene_id="idx1",
            collection="sentinel-2-l2a",
            sun_elevation=55.0,
        )
        catalog_manager.cache_scene("idx1", item, "es")

        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        mock_arr = ArrayReadResult(
            arrays=[
                np.array([[100, 200]], dtype=np.float32),
                np.array([[300, 400]], dtype=np.float32),
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(1, 2),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ndvi")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
        ):
            await catalog_manager.compute_index("idx1", "ndvi")

        meta = mock_store.store.call_args_list[0][1]["meta"]
        assert meta["schema_version"] == "1.0"
        assert meta["collection"] == "sentinel-2-l2a"
        assert meta["sun_elevation"] == 55.0
        assert meta["datetime"] == "2024-07-15T10:56:29Z"


class TestPlanetaryComputerAuth:
    def test_pc_url_applies_modifier(self, catalog_manager):
        """PC URL with package installed should pass modifier to Client.open."""
        mock_client = MagicMock()
        mock_sign = MagicMock()
        mock_pc_module = MagicMock()
        mock_pc_module.sign_inplace = mock_sign

        with (
            patch("pystac_client.Client.open", return_value=mock_client) as mock_open,
            patch.dict("sys.modules", {"planetary_computer": mock_pc_module}),
        ):
            result = catalog_manager.get_stac_client(
                "https://planetarycomputer.microsoft.com/api/stac/v1"
            )

        assert result is mock_client
        mock_open.assert_called_once_with(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=mock_sign,
        )

    def test_pc_url_without_package_logs_warning(self, catalog_manager):
        """PC URL without package should log warning and open without modifier."""
        mock_client = MagicMock()

        with (
            patch("pystac_client.Client.open", return_value=mock_client) as mock_open,
            patch.dict("sys.modules", {"planetary_computer": None}),
        ):
            result = catalog_manager.get_stac_client(
                "https://planetarycomputer.microsoft.com/api/stac/v1"
            )

        assert result is mock_client
        mock_open.assert_called_once_with(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=None,
        )

    def test_non_pc_url_no_modifier(self, catalog_manager):
        """Non-PC URL should not attempt to import planetary_computer."""
        mock_client = MagicMock()

        with patch("pystac_client.Client.open", return_value=mock_client) as mock_open:
            result = catalog_manager.get_stac_client("https://earth-search.aws.element84.com/v1")

        assert result is mock_client
        mock_open.assert_called_once_with(
            "https://earth-search.aws.element84.com/v1",
            modifier=None,
        )


class TestRasterCache:
    """Tests for in-memory raster cache."""

    def test_cache_key_deterministic(self, catalog_manager):
        """Same inputs should produce the same cache key."""
        k1 = catalog_manager._raster_cache_key("s1", ["red", "nir"], [0.0, 1.0, 2.0, 3.0])
        k2 = catalog_manager._raster_cache_key("s1", ["red", "nir"], [0.0, 1.0, 2.0, 3.0])
        assert k1 == k2

    def test_cache_key_sorted_bands(self, catalog_manager):
        """Band order should not affect cache key."""
        k1 = catalog_manager._raster_cache_key("s1", ["nir", "red"], None)
        k2 = catalog_manager._raster_cache_key("s1", ["red", "nir"], None)
        assert k1 == k2

    def test_cache_key_cloud_mask_differs(self, catalog_manager):
        """Different cloud_mask values should produce different keys."""
        k1 = catalog_manager._raster_cache_key("s1", ["red"], None, False)
        k2 = catalog_manager._raster_cache_key("s1", ["red"], None, True)
        assert k1 != k2

    def test_cache_miss_returns_none(self, catalog_manager):
        assert catalog_manager._raster_cache_get("nonexistent") is None

    def test_cache_put_and_get(self, catalog_manager):
        catalog_manager._raster_cache_put("k1", b"data", "EPSG:32631", [1, 10, 10], "uint16")
        entry = catalog_manager._raster_cache_get("k1")
        assert entry is not None
        assert entry["data"] == b"data"
        assert entry["crs"] == "EPSG:32631"
        assert entry["shape"] == [1, 10, 10]
        assert entry["dtype"] == "uint16"
        assert catalog_manager._raster_cache_total == 4  # len(b"data")

    def test_oversized_item_skipped(self, catalog_manager):
        """Items exceeding RASTER_CACHE_MAX_ITEM should not be cached."""
        with patch("chuk_mcp_stac.core.catalog_manager.RASTER_CACHE_MAX_ITEM", 10):
            catalog_manager._raster_cache_put("big", b"x" * 11, "EPSG:32631", [1, 10, 10], "uint16")
        assert catalog_manager._raster_cache_get("big") is None
        assert catalog_manager._raster_cache_total == 0

    def test_eviction_on_capacity(self, catalog_manager):
        """Oldest entries should be evicted when total exceeds max bytes."""
        with (
            patch("chuk_mcp_stac.core.catalog_manager.RASTER_CACHE_MAX_BYTES", 100),
            patch("chuk_mcp_stac.core.catalog_manager.RASTER_CACHE_MAX_ITEM", 60),
        ):
            catalog_manager._raster_cache_put("a", b"x" * 50, "EPSG:32631", [1], "uint16")
            catalog_manager._raster_cache_put("b", b"y" * 50, "EPSG:32631", [1], "uint16")
            # This should evict "a" to make room
            catalog_manager._raster_cache_put("c", b"z" * 50, "EPSG:32631", [1], "uint16")

        assert catalog_manager._raster_cache_get("a") is None
        assert catalog_manager._raster_cache_get("b") is not None
        assert catalog_manager._raster_cache_get("c") is not None

    def test_lru_touch_on_get(self, catalog_manager):
        """Accessed entries should survive eviction over untouched ones."""
        with (
            patch("chuk_mcp_stac.core.catalog_manager.RASTER_CACHE_MAX_BYTES", 80),
            patch("chuk_mcp_stac.core.catalog_manager.RASTER_CACHE_MAX_ITEM", 40),
        ):
            catalog_manager._raster_cache_put("a", b"x" * 30, "EPSG:32631", [1], "uint16")
            catalog_manager._raster_cache_put("b", b"y" * 30, "EPSG:32631", [1], "uint16")

            # Touch "a" — should move it to end
            catalog_manager._raster_cache_get("a")

            # Add "c" — should evict "b" (oldest untouched), since 60 + 30 > 80
            catalog_manager._raster_cache_put("c", b"z" * 30, "EPSG:32631", [1], "uint16")

        assert catalog_manager._raster_cache_get("a") is not None
        assert catalog_manager._raster_cache_get("b") is None
        assert catalog_manager._raster_cache_get("c") is not None

    async def test_download_bands_cache_hit(self, manager_with_scene):
        """Second download with same params should use cached raster data."""
        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch(
                "chuk_mcp_stac.core.raster_io.read_bands_from_cogs",
                return_value=mock_result,
            ) as mock_read,
        ):
            # First call — cache miss, reads COGs
            await manager_with_scene.download_bands(SAMPLE_SCENE_ID, ["red"])
            assert mock_read.call_count == 1

            # Second call — cache hit, should NOT read COGs again
            await manager_with_scene.download_bands(SAMPLE_SCENE_ID, ["red"])
            assert mock_read.call_count == 1  # Still 1


class TestProgressCallback:
    """Tests for progress callback reporting."""

    async def test_callback_invoked_during_download(self, catalog_manager):
        """Progress callback should be called during download_bands."""
        callback = MagicMock()
        catalog_manager._progress_callback = callback

        item = make_stac_item()
        catalog_manager.cache_scene("p1", item, "es")

        mock_result = RasterReadResult(
            data=b"fake_tiff", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_result),
        ):
            await catalog_manager.download_bands("p1", ["red"])

        callback.assert_called_with("reading_bands", 1, 1)

    async def test_callback_invoked_during_mosaic(self, catalog_manager):
        """Progress callback should report per-scene and merging stages."""
        callback = MagicMock()
        catalog_manager._progress_callback = callback

        item1 = make_stac_item(scene_id="m1")
        item2 = make_stac_item(scene_id="m2")
        catalog_manager.cache_scene("m1", item1, "es")
        catalog_manager.cache_scene("m2", item2, "es")

        mock_raster = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 10, 10], dtype="uint16"
        )
        merged = RasterReadResult(
            data=b"merged", crs="EPSG:32631", shape=[1, 20, 10], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_raster),
            patch("chuk_mcp_stac.core.raster_io.merge_rasters", return_value=merged),
        ):
            await catalog_manager.download_mosaic(["m1", "m2"], ["red"])

        # Should have scene progress + merging progress
        calls = [c.args for c in callback.call_args_list]
        assert ("reading_scene", 1, 2) in calls
        assert ("reading_scene", 2, 2) in calls
        assert ("merging", 1, 1) in calls

    def test_no_callback_no_error(self, catalog_manager):
        """_report_progress with no callback should not raise."""
        catalog_manager._report_progress("reading_bands", 1, 1)

    def test_callback_exception_suppressed(self, catalog_manager):
        """Callback exceptions should be silently suppressed."""

        def bad_callback(stage, current, total):
            raise RuntimeError("boom")

        catalog_manager._progress_callback = bad_callback
        # Should not raise
        catalog_manager._report_progress("reading_bands", 1, 1)

    def test_callback_receives_correct_args(self):
        """Callback should receive (stage, current, total) args."""
        callback = MagicMock()
        mgr = CatalogManager(progress_callback=callback)
        mgr._report_progress("compositing", 3, 5)
        callback.assert_called_once_with("compositing", 3, 5)


class TestTemporalComposite:
    """Tests for the temporal_composite method."""

    async def test_scene_not_found(self, catalog_manager):
        with pytest.raises(ValueError, match="not found"):
            await catalog_manager.temporal_composite(["nonexistent"], ["red"])

    async def test_band_not_found(self, manager_with_scene):
        with pytest.raises(ValueError, match="Band.*not found"):
            await manager_with_scene.temporal_composite([SAMPLE_SCENE_ID], ["nonexistent_band"])

    async def test_no_artifact_store(self, manager_with_scene):
        with patch(
            "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="No artifact store"):
                await manager_with_scene.temporal_composite([SAMPLE_SCENE_ID], ["red"])

    async def test_happy_path(self, catalog_manager):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        item1 = make_stac_item(scene_id="t1")
        item2 = make_stac_item(scene_id="t2")
        catalog_manager.cache_scene("t1", item1, "es")
        catalog_manager.cache_scene("t2", item2, "es")

        mock_arr = ArrayReadResult(
            arrays=[np.full((3, 3), 1000, dtype=np.float32)],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(3, 3),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://composite-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.arrays_to_geotiff", return_value=b"fake_tiff"),
        ):
            result = await catalog_manager.temporal_composite(["t1", "t2"], ["red"])

        assert isinstance(result, BandDownloadResult)
        assert result.artifact_ref == "art://composite-ref"

    async def test_cloud_mask_path(self, catalog_manager):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        item = make_stac_item(scene_id="tc1")
        catalog_manager.cache_scene("tc1", item, "es")

        mock_arr = ArrayReadResult(
            arrays=[
                np.full((3, 3), 1000, dtype=np.float32),  # red
                np.full((3, 3), 4, dtype=np.uint8),  # scl
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(3, 3),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://composite-masked")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.arrays_to_geotiff", return_value=b"fake_tiff"),
        ):
            result = await catalog_manager.temporal_composite(["tc1"], ["red"], cloud_mask=True)

        assert result.artifact_ref == "art://composite-masked"

    async def test_cloud_mask_requires_scl(self, catalog_manager):
        item = make_stac_item(bands=["red", "green", "blue"])
        catalog_manager.cache_scene("no_scl", item, "es")
        with pytest.raises(ValueError, match="scl"):
            await catalog_manager.temporal_composite(["no_scl"], ["red"], cloud_mask=True)

    async def test_progress_callback(self, catalog_manager):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult

        callback = MagicMock()
        catalog_manager._progress_callback = callback

        item = make_stac_item(scene_id="tp1")
        catalog_manager.cache_scene("tp1", item, "es")

        mock_arr = ArrayReadResult(
            arrays=[np.full((3, 3), 1000, dtype=np.float32)],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(3, 3),
            dtype="float32",
        )

        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.arrays_to_geotiff", return_value=b"fake_tiff"),
        ):
            await catalog_manager.temporal_composite(["tp1"], ["red"])

        calls = [c.args for c in callback.call_args_list]
        assert ("reading_scene", 1, 1) in calls
        assert ("compositing", 1, 1) in calls


class TestDownloadMosaicQuality:
    """Tests for quality-weighted mosaic method."""

    async def test_quality_merge(self, catalog_manager):
        from chuk_mcp_stac.core.raster_io import ArrayReadResult, RasterReadResult

        item1 = make_stac_item(scene_id="q1")
        item2 = make_stac_item(scene_id="q2")
        catalog_manager.cache_scene("q1", item1, "es")
        catalog_manager.cache_scene("q2", item2, "es")

        mock_arr = ArrayReadResult(
            arrays=[
                np.full((3, 3), 1000, dtype=np.uint16),  # red
                np.full((3, 3), 4, dtype=np.uint8),  # scl
            ],
            crs="EPSG:32631",
            transform=[10.0, 0.0, 500000.0, 0.0, -10.0, 5700100.0],
            shape=(3, 3),
            dtype="uint16",
        )

        mock_raster = RasterReadResult(
            data=b"fake", crs="EPSG:32631", shape=[1, 3, 3], dtype="uint16"
        )
        mock_store = AsyncMock()
        mock_store.store = AsyncMock(return_value="art://quality-ref")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_raster),
            patch("chuk_mcp_stac.core.raster_io.read_bands_as_arrays", return_value=mock_arr),
            patch("chuk_mcp_stac.core.raster_io.arrays_to_geotiff", return_value=b"fake_tiff"),
        ):
            result = await catalog_manager.download_mosaic(["q1", "q2"], ["red"], method="quality")

        assert isinstance(result, BandDownloadResult)
        assert result.artifact_ref == "art://quality-ref"
