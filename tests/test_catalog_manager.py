"""Tests for chuk_mcp_stac.core.catalog_manager."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from chuk_mcp_stac.core.catalog_manager import (
    _MAX_SCENE_CACHE,
    BandDownloadResult,
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
        mock_store.store = AsyncMock(return_value="art://test-ref-123")

        with (
            patch(
                "chuk_mcp_stac.core.catalog_manager.CatalogManager._get_store",
                return_value=mock_store,
            ),
            patch("chuk_mcp_stac.core.raster_io.read_bands_from_cogs", return_value=mock_result),
        ):
            result = await manager_with_scene.download_bands(
                SAMPLE_SCENE_ID, ["red", "nir"], SAMPLE_BBOX
            )

        assert isinstance(result, BandDownloadResult)
        assert result.artifact_ref == "art://test-ref-123"
        assert result.crs == "EPSG:32631"
        assert result.shape == [2, 10, 10]


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
