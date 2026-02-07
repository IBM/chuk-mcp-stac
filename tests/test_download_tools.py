"""Tests for chuk_mcp_stac.tools.download.api."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuk_mcp_stac.core.catalog_manager import BandDownloadResult, CatalogManager
from chuk_mcp_stac.tools.download.api import register_download_tools

from .conftest import SAMPLE_BBOX, SAMPLE_SCENE_ID, MockMCPServer, make_stac_item


@pytest.fixture
def download_tools():
    """Register download tools on a mock MCP and return (mcp, manager)."""
    mcp = MockMCPServer()
    manager = CatalogManager()
    # Pre-cache a scene
    manager.cache_scene(SAMPLE_SCENE_ID, make_stac_item(), "earth_search")
    register_download_tools(mcp, manager)
    return mcp, manager


def _mock_download_result(preview_ref="art://preview-123"):
    return BandDownloadResult(
        artifact_ref="art://test-123",
        crs="EPSG:32631",
        shape=[3, 100, 100],
        dtype="uint16",
        preview_ref=preview_ref,
    )


class TestStacDownloadBands:
    async def test_happy_path(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red", "nir"]))

        assert result["artifact_ref"] == "art://test-123"
        assert result["bands"] == ["red", "nir"]
        assert result["crs"] == "EPSG:32631"

    async def test_value_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager,
            "download_bands",
            new_callable=AsyncMock,
            side_effect=ValueError("scene not found"),
        ):
            result = json.loads(await fn(scene_id="bad", bands=["red"]))

        assert "error" in result
        assert "not found" in result["error"]

    async def test_runtime_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, side_effect=RuntimeError("no store")
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"]))

        assert "error" in result
        assert "no store" in result["error"]

    async def test_unexpected_exception(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, side_effect=IOError("disk error")
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"]))

        assert "error" in result

    async def test_with_bbox(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"], bbox=SAMPLE_BBOX))

        assert result["bbox"] == SAMPLE_BBOX


class TestStacDownloadRgb:
    async def test_happy_path(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_rgb")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ) as mock_dl:
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert result["composite_type"] == "rgb"
        assert result["bands"] == ["red", "green", "blue"]
        # Verify it called download_bands with RGB bands
        mock_dl.assert_called_once_with(
            SAMPLE_SCENE_ID,
            ["red", "green", "blue"],
            None,
            output_format="geotiff",
            cloud_mask=False,
        )

    async def test_value_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_rgb")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, side_effect=ValueError("bad")
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert "error" in result


class TestStacDownloadComposite:
    async def test_custom_name(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_composite")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = json.loads(
                await fn(
                    scene_id=SAMPLE_SCENE_ID,
                    bands=["nir", "red", "green"],
                    composite_name="false_color_ir",
                )
            )

        assert result["composite_type"] == "false_color_ir"
        assert result["bands"] == ["nir", "red", "green"]

    async def test_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_composite")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, side_effect=RuntimeError("fail")
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"]))

        assert "error" in result


class TestStacMosaic:
    async def test_scene_not_found(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_mosaic")

        with patch.object(
            manager,
            "download_mosaic",
            new_callable=AsyncMock,
            side_effect=ValueError("Scene 'nonexistent' not found"),
        ):
            result = json.loads(await fn(scene_ids=["nonexistent"], bands=["red"]))

        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_happy_path(self, download_tools):
        mcp, manager = download_tools
        manager.cache_scene("S2B_002", make_stac_item(scene_id="S2B_002"), "earth_search")

        fn = mcp.get_tool("stac_mosaic")

        with patch.object(
            manager,
            "download_mosaic",
            new_callable=AsyncMock,
            return_value=_mock_download_result(),
        ):
            result = json.loads(
                await fn(
                    scene_ids=[SAMPLE_SCENE_ID, "S2B_002"],
                    bands=["red", "green"],
                )
            )

        assert result["artifact_ref"] == "art://test-123"
        assert result["scene_ids"] == [SAMPLE_SCENE_ID, "S2B_002"]
        assert "pending" not in result["artifact_ref"]

    async def test_value_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_mosaic")

        with patch.object(
            manager,
            "download_mosaic",
            new_callable=AsyncMock,
            side_effect=ValueError("band not found"),
        ):
            result = json.loads(await fn(scene_ids=[SAMPLE_SCENE_ID], bands=["bad"]))

        assert "error" in result

    async def test_runtime_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_mosaic")

        with patch.object(
            manager,
            "download_mosaic",
            new_callable=AsyncMock,
            side_effect=RuntimeError("no store"),
        ):
            result = json.loads(await fn(scene_ids=[SAMPLE_SCENE_ID], bands=["red"]))

        assert "error" in result
        assert "no store" in result["error"]


class TestStacComputeIndex:
    async def test_happy_path(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_compute_index")

        from chuk_mcp_stac.core.catalog_manager import IndexComputeResult

        mock_result = IndexComputeResult(
            artifact_ref="art://ndvi-123",
            crs="EPSG:32631",
            shape=[1, 100, 100],
            value_range=[-0.2, 0.85],
        )

        with patch.object(
            manager, "compute_index", new_callable=AsyncMock, return_value=mock_result
        ) as mock_ci:
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, index_name="ndvi"))

        assert result["index_name"] == "ndvi"
        assert result["artifact_ref"] == "art://ndvi-123"
        assert result["value_range"] == [-0.2, 0.85]
        assert result["required_bands"] == ["red", "nir"]
        assert result["output_format"] == "geotiff"
        mock_ci.assert_called_once_with(
            SAMPLE_SCENE_ID,
            "ndvi",
            None,
            cloud_mask=False,
            output_format="geotiff",
        )

    async def test_with_cloud_mask(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_compute_index")

        from chuk_mcp_stac.core.catalog_manager import IndexComputeResult

        mock_result = IndexComputeResult(
            artifact_ref="art://ndvi-masked",
            crs="EPSG:32631",
            shape=[1, 100, 100],
            value_range=[0.0, 0.9],
        )

        with patch.object(
            manager, "compute_index", new_callable=AsyncMock, return_value=mock_result
        ):
            result = json.loads(
                await fn(
                    scene_id=SAMPLE_SCENE_ID,
                    index_name="ndvi",
                    cloud_mask=True,
                )
            )

        assert result["artifact_ref"] == "art://ndvi-masked"

    async def test_with_png_format(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_compute_index")

        from chuk_mcp_stac.core.catalog_manager import IndexComputeResult

        mock_result = IndexComputeResult(
            artifact_ref="art://ndvi-png",
            crs="EPSG:32631",
            shape=[1, 100, 100],
            value_range=[-0.1, 0.8],
        )

        with patch.object(
            manager, "compute_index", new_callable=AsyncMock, return_value=mock_result
        ):
            result = json.loads(
                await fn(
                    scene_id=SAMPLE_SCENE_ID,
                    index_name="ndvi",
                    output_format="png",
                )
            )

        assert result["output_format"] == "png"

    async def test_unknown_index(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_compute_index")

        with patch.object(
            manager,
            "compute_index",
            new_callable=AsyncMock,
            side_effect=ValueError("Unknown index 'fake'"),
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, index_name="fake"))

        assert "error" in result

    async def test_scene_not_found(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_compute_index")

        with patch.object(
            manager,
            "compute_index",
            new_callable=AsyncMock,
            side_effect=ValueError("Scene 'bad' not found"),
        ):
            result = json.loads(await fn(scene_id="bad", index_name="ndvi"))

        assert "error" in result


class TestPreviewRefPassthrough:
    """Verify preview_ref flows from CatalogManager through to JSON responses."""

    async def test_download_bands_preview_ref(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"]))

        assert result["preview_ref"] == "art://preview-123"

    async def test_rgb_preview_ref(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_rgb")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert result["preview_ref"] == "art://preview-123"

    async def test_mosaic_preview_ref(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_mosaic")

        with patch.object(
            manager, "download_mosaic", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = json.loads(await fn(scene_ids=[SAMPLE_SCENE_ID], bands=["red"]))

        assert result["preview_ref"] == "art://preview-123"

    async def test_compute_index_preview_ref(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_compute_index")

        from chuk_mcp_stac.core.catalog_manager import IndexComputeResult

        mock_result = IndexComputeResult(
            artifact_ref="art://ndvi-123",
            crs="EPSG:32631",
            shape=[1, 100, 100],
            value_range=[-0.2, 0.85],
            preview_ref="art://ndvi-preview",
        )

        with patch.object(
            manager, "compute_index", new_callable=AsyncMock, return_value=mock_result
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, index_name="ndvi"))

        assert result["preview_ref"] == "art://ndvi-preview"

    async def test_preview_ref_null_for_png(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager,
            "download_bands",
            new_callable=AsyncMock,
            return_value=_mock_download_result(preview_ref=None),
        ):
            result = json.loads(
                await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"], output_format="png")
            )

        assert result["preview_ref"] is None


class TestOutputFormatPassthrough:
    async def test_download_bands_png(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ) as mock_dl:
            result = json.loads(
                await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"], output_format="png")
            )

        assert result["output_format"] == "png"
        mock_dl.assert_called_once_with(
            SAMPLE_SCENE_ID,
            ["red"],
            None,
            output_format="png",
            cloud_mask=False,
        )

    async def test_composite_cloud_mask(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_composite")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ) as mock_dl:
            json.loads(
                await fn(
                    scene_id=SAMPLE_SCENE_ID,
                    bands=["nir", "red", "green"],
                    cloud_mask=True,
                )
            )

        mock_dl.assert_called_once_with(
            SAMPLE_SCENE_ID,
            ["nir", "red", "green"],
            None,
            output_format="geotiff",
            cloud_mask=True,
        )

    async def test_mosaic_output_format(self, download_tools):
        mcp, manager = download_tools
        manager.cache_scene("S2B_002", make_stac_item(scene_id="S2B_002"), "earth_search")
        fn = mcp.get_tool("stac_mosaic")

        with patch.object(
            manager,
            "download_mosaic",
            new_callable=AsyncMock,
            return_value=_mock_download_result(),
        ) as mock_dl:
            result = json.loads(
                await fn(
                    scene_ids=[SAMPLE_SCENE_ID],
                    bands=["red"],
                    output_format="png",
                )
            )

        assert result["output_format"] == "png"
        mock_dl.assert_called_once_with(
            [SAMPLE_SCENE_ID],
            ["red"],
            None,
            output_format="png",
            cloud_mask=False,
            method="last",
        )


class TestStacEstimateSize:
    async def test_happy_path(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_estimate_size")

        mock_result = {
            "per_band": [
                {"band": "red", "width": 100, "height": 100, "dtype": "uint16", "bytes": 20000},
                {"band": "nir", "width": 100, "height": 100, "dtype": "uint16", "bytes": 20000},
            ],
            "total_pixels": 20000,
            "estimated_bytes": 40000,
            "estimated_mb": 0.04,
            "crs": "EPSG:32631",
            "warnings": [],
        }

        with patch.object(
            manager, "estimate_size", new_callable=AsyncMock, return_value=mock_result
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red", "nir"]))

        assert result["band_count"] == 2
        assert result["estimated_mb"] == 0.04
        assert len(result["per_band"]) == 2
        assert result["per_band"][0]["band"] == "red"

    async def test_with_bbox(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_estimate_size")

        mock_result = {
            "per_band": [
                {"band": "red", "width": 50, "height": 50, "dtype": "uint16", "bytes": 5000}
            ],
            "total_pixels": 2500,
            "estimated_bytes": 5000,
            "estimated_mb": 0.005,
            "crs": "EPSG:32631",
            "warnings": [],
        }

        with patch.object(
            manager, "estimate_size", new_callable=AsyncMock, return_value=mock_result
        ):
            result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"], bbox=SAMPLE_BBOX))

        assert result["bbox"] == SAMPLE_BBOX

    async def test_scene_not_found(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_estimate_size")

        with patch.object(
            manager,
            "estimate_size",
            new_callable=AsyncMock,
            side_effect=ValueError("Scene 'bad' not found"),
        ):
            result = json.loads(await fn(scene_id="bad", bands=["red"]))

        assert "error" in result


class TestStacTimeSeries:
    async def test_invalid_bbox(self, download_tools):
        mcp, _ = download_tools
        fn = mcp.get_tool("stac_time_series")
        result = json.loads(
            await fn(bbox=[0, 0], bands=["red"], date_range="2024-01-01/2024-12-31")
        )
        assert "error" in result

    async def test_happy_path(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_time_series")

        mock_item_1 = MagicMock()
        mock_item_1.id = "S2B_TS_001"
        mock_item_1.properties = {"datetime": "2024-01-15T00:00:00Z", "eo:cloud_cover": 3.0}
        mock_item_1.to_dict.return_value = {
            "id": "S2B_TS_001",
            "collection": "sentinel-2-l2a",
            "bbox": list(SAMPLE_BBOX),
            "properties": {
                "datetime": "2024-01-15T00:00:00Z",
                "eo:cloud_cover": 3.0,
                "proj:epsg": 32631,
            },
            "assets": {
                "red": {"href": "https://example.com/red.tif"},
                "nir": {"href": "https://example.com/nir.tif"},
            },
        }

        mock_item_2 = MagicMock()
        mock_item_2.id = "S2B_TS_002"
        mock_item_2.properties = {"datetime": "2024-02-15T00:00:00Z", "eo:cloud_cover": 8.0}
        mock_item_2.to_dict.return_value = {
            "id": "S2B_TS_002",
            "collection": "sentinel-2-l2a",
            "bbox": list(SAMPLE_BBOX),
            "properties": {
                "datetime": "2024-02-15T00:00:00Z",
                "eo:cloud_cover": 8.0,
                "proj:epsg": 32631,
            },
            "assets": {
                "red": {"href": "https://example.com/red.tif"},
                "nir": {"href": "https://example.com/nir.tif"},
            },
        }

        mock_search = MagicMock()
        mock_search.items.return_value = [mock_item_1, mock_item_2]
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with (
            patch.object(manager, "get_stac_client", return_value=mock_client),
            patch.object(
                manager,
                "download_bands",
                new_callable=AsyncMock,
                return_value=_mock_download_result(),
            ),
        ):
            result = json.loads(
                await fn(
                    bbox=SAMPLE_BBOX,
                    bands=["red", "nir"],
                    date_range="2024-01-01/2024-12-31",
                )
            )

        assert result["date_count"] == 2
        assert len(result["entries"]) == 2
        assert result["entries"][0]["scene_id"] == "S2B_TS_001"
        assert result["entries"][0]["artifact_ref"] == "art://test-123"
        assert "pending" not in result["entries"][0]["artifact_ref"]
        # Scenes should be cached
        assert manager.get_cached_scene("S2B_TS_001") is not None

    async def test_download_error(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_time_series")

        mock_item = MagicMock()
        mock_item.id = "S2B_TS_ERR"
        mock_item.properties = {"datetime": "2024-01-15T00:00:00Z", "eo:cloud_cover": 3.0}
        mock_item.to_dict.return_value = {
            "id": "S2B_TS_ERR",
            "collection": "sentinel-2-l2a",
            "bbox": list(SAMPLE_BBOX),
            "properties": {
                "datetime": "2024-01-15T00:00:00Z",
                "eo:cloud_cover": 3.0,
                "proj:epsg": 32631,
            },
            "assets": {"red": {"href": "https://example.com/red.tif"}},
        }

        mock_search = MagicMock()
        mock_search.items.return_value = [mock_item]
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with (
            patch.object(manager, "get_stac_client", return_value=mock_client),
            patch.object(
                manager,
                "download_bands",
                new_callable=AsyncMock,
                side_effect=RuntimeError("no store"),
            ),
        ):
            result = json.loads(
                await fn(
                    bbox=SAMPLE_BBOX,
                    bands=["red"],
                    date_range="2024-01-01/2024-12-31",
                )
            )

        assert "error" in result

    async def test_max_items_parameter(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_time_series")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            await fn(
                bbox=SAMPLE_BBOX,
                bands=["red"],
                date_range="2024-01-01/2024-12-31",
                max_items=25,
            )

        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["max_items"] == 25


# ---------------------------------------------------------------------------
# Feature 5: output_mode tests for download tools
# ---------------------------------------------------------------------------


class TestOutputModeDownload:
    async def test_download_bands_text(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = await fn(scene_id=SAMPLE_SCENE_ID, bands=["red", "nir"], output_mode="text")

        assert "Downloaded 2 band(s)" in result
        assert "art://test-123" in result
        assert not result.startswith("{")

    async def test_download_bands_json_default(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, return_value=_mock_download_result()
        ):
            result = await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"])

        parsed = json.loads(result)
        assert "artifact_ref" in parsed

    async def test_download_bands_error_text(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_download_bands")

        with patch.object(
            manager, "download_bands", new_callable=AsyncMock, side_effect=ValueError("bad")
        ):
            result = await fn(scene_id="x", bands=["red"], output_mode="text")

        assert result.startswith("Error:")

    async def test_estimate_size_text(self, download_tools):
        mcp, manager = download_tools
        fn = mcp.get_tool("stac_estimate_size")

        mock_result = {
            "per_band": [
                {"band": "red", "width": 100, "height": 100, "dtype": "uint16", "bytes": 20000}
            ],
            "total_pixels": 10000,
            "estimated_bytes": 20000,
            "estimated_mb": 0.02,
            "crs": "EPSG:32631",
        }
        with patch.object(
            manager, "estimate_size", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await fn(scene_id=SAMPLE_SCENE_ID, bands=["red"], output_mode="text")

        assert "Estimated" in result
        assert "MB" in result
        assert not result.startswith("{")
