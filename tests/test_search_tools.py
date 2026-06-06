"""Tests for chuk_mcp_stac.tools.search.api."""

import json
from unittest.mock import MagicMock, patch

import pytest

from chuk_mcp_stac.core.catalog_manager import CatalogManager
from chuk_mcp_stac.tools.search.api import register_search_tools

from .conftest import SAMPLE_BBOX, SAMPLE_SCENE_ID, MockMCPServer, make_stac_item


@pytest.fixture
def search_tools():
    """Register search tools on a mock MCP and return (mcp, manager)."""
    mcp = MockMCPServer()
    manager = CatalogManager()
    register_search_tools(mcp, manager)
    return mcp, manager


def _make_mock_stac_item(scene_id="S2B_001", cloud_cover=5.0):
    """Create a mock pystac Item (not a model — has .id, .properties, .assets, .bbox, .to_dict())."""
    item = MagicMock()
    item.id = scene_id
    item.bbox = SAMPLE_BBOX
    item.properties = {
        "datetime": "2024-07-15T10:56:29Z",
        "eo:cloud_cover": cloud_cover,
    }
    item.assets = {
        "red": MagicMock(href="https://example.com/red.tif"),
        "green": MagicMock(href="https://example.com/green.tif"),
        "blue": MagicMock(href="https://example.com/blue.tif"),
        "thumbnail": MagicMock(href="https://example.com/thumb.png"),
    }
    # to_dict() returns a raw dict that STACItem.model_validate can parse
    item.to_dict.return_value = {
        "id": scene_id,
        "collection": "sentinel-2-l2a",
        "bbox": list(SAMPLE_BBOX),
        "properties": {
            "datetime": "2024-07-15T10:56:29Z",
            "eo:cloud_cover": cloud_cover,
            "proj:epsg": 32631,
        },
        "assets": {
            "red": {"href": "https://example.com/red.tif", "type": "image/tiff"},
            "green": {"href": "https://example.com/green.tif", "type": "image/tiff"},
            "blue": {"href": "https://example.com/blue.tif", "type": "image/tiff"},
            "thumbnail": {"href": "https://example.com/thumb.png", "type": "image/png"},
        },
    }
    return item


class TestStacListCatalogs:
    async def test_returns_catalogs(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_list_catalogs")
        result = json.loads(await fn())
        assert "catalogs" in result
        assert len(result["catalogs"]) == 3
        assert result["default"] == "earth_search"


class TestStacListCollections:
    async def test_happy_path(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_list_collections")

        mock_coll = MagicMock()
        mock_coll.id = "sentinel-2-l2a"
        mock_coll.title = "Sentinel-2 L2A"
        mock_coll.description = "Surface reflectance"
        mock_coll.extent = MagicMock()
        mock_coll.extent.spatial = MagicMock()
        mock_coll.extent.spatial.bboxes = [[-180, -90, 180, 90]]
        mock_coll.extent.temporal = MagicMock()
        mock_coll.extent.temporal.intervals = [[None, None]]

        mock_client = MagicMock()
        mock_client.get_collections.return_value = [mock_coll]

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn())

        assert result["collection_count"] == 1
        assert result["collections"][0]["collection_id"] == "sentinel-2-l2a"

    async def test_catalog_error(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_list_collections")

        with patch.object(manager, "get_stac_client", side_effect=Exception("connection refused")):
            result = json.loads(await fn())

        assert "error" in result
        assert "connection refused" in result["error"]


class TestStacSearch:
    async def test_invalid_bbox_length(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_search")
        result = json.loads(await fn(bbox=[0, 0, 1]))
        assert "error" in result
        assert "bounding box" in result["error"].lower()

    async def test_invalid_bbox_values_west_gt_east(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_search")
        result = json.loads(await fn(bbox=[10, 0, 5, 1]))
        assert "error" in result
        assert "west" in result["error"].lower() or "invalid" in result["error"].lower()

    async def test_invalid_bbox_out_of_range(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_search")
        result = json.loads(await fn(bbox=[-200, 0, 1, 1]))
        assert "error" in result

    async def test_happy_path(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_item = _make_mock_stac_item()
        mock_search = MagicMock()
        mock_search.items.return_value = [mock_item]
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX))

        assert result["scene_count"] == 1
        assert result["scenes"][0]["scene_id"] == "S2B_001"
        # Verify scene was cached
        assert manager.get_cached_scene("S2B_001") is not None

    async def test_no_results(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX))

        assert result["scene_count"] == 0
        assert "no scenes" in result["message"].lower()

    async def test_date_range_passed_to_client(self, search_tools):
        """date_range should be forwarded as the 'datetime' kwarg to pystac search."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX, date_range="2024-06-01/2024-08-31"))

        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["datetime"] == "2024-06-01/2024-08-31"
        assert result["date_range"] == "2024-06-01/2024-08-31"

    async def test_no_date_range_omits_datetime(self, search_tools):
        """Omitting date_range should not pass 'datetime' to pystac search."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX))

        call_kwargs = mock_client.search.call_args[1]
        assert "datetime" not in call_kwargs
        assert result["date_range"] is None

    async def test_max_items_zero(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            json.loads(await fn(bbox=SAMPLE_BBOX, max_items=0))

        # max_items=0 should be passed through, not treated as falsy default
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["max_items"] == 0


class TestStacSearchCloudFilter:
    """Tests for conditional cloud cover filter on non-optical collections."""

    def _make_s1_item(self, scene_id="S1_GRD_001"):
        item = MagicMock()
        item.id = scene_id
        item.bbox = SAMPLE_BBOX
        item.properties = {"datetime": "2024-07-15T10:56:29Z"}
        item.assets = {
            "vv": MagicMock(href="https://example.com/vv.tif"),
            "vh": MagicMock(href="https://example.com/vh.tif"),
        }
        item.to_dict.return_value = {
            "id": scene_id,
            "collection": "sentinel-1-grd",
            "bbox": list(SAMPLE_BBOX),
            "properties": {"datetime": "2024-07-15T10:56:29Z"},
            "assets": {
                "vv": {"href": "https://example.com/vv.tif", "type": "image/tiff"},
                "vh": {"href": "https://example.com/vh.tif", "type": "image/tiff"},
            },
        }
        return item

    async def test_sentinel1_no_cloud_filter(self, search_tools):
        """Sentinel-1 GRD search should NOT apply eo:cloud_cover filter."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = [self._make_s1_item()]
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX, collection="sentinel-1-grd"))

        call_kwargs = mock_client.search.call_args[1]
        assert "query" not in call_kwargs
        assert result["scene_count"] == 1
        assert result["max_cloud_cover"] is None

    async def test_cop_dem_no_cloud_filter(self, search_tools):
        """cop-dem-glo-30 search should NOT apply eo:cloud_cover filter."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX, collection="cop-dem-glo-30"))

        call_kwargs = mock_client.search.call_args[1]
        assert "query" not in call_kwargs
        assert result["max_cloud_cover"] is None

    async def test_optical_still_filters_cloud(self, search_tools):
        """Sentinel-2 search should still apply eo:cloud_cover filter."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(
                await fn(bbox=SAMPLE_BBOX, collection="sentinel-2-l2a", max_cloud_cover=30)
            )

        call_kwargs = mock_client.search.call_args[1]
        assert "query" in call_kwargs
        assert call_kwargs["query"]["eo:cloud_cover"]["lt"] == 30
        assert result["max_cloud_cover"] == 30

    async def test_sentinel1_hint_cloud_skipped(self, search_tools):
        """Sentinel-1 results should include a hint about skipped cloud filter."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = [self._make_s1_item()]
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX, collection="sentinel-1-grd"))

        assert any("cloud cover filter skipped" in h.lower() for h in result["hints"])


class TestStacSearchHints:
    """Tests for actionable hints on zero results."""

    async def test_zero_results_include_filters(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(
                await fn(
                    bbox=SAMPLE_BBOX,
                    date_range="2024-06-01/2024-08-31",
                    max_cloud_cover=10,
                )
            )

        assert result["scene_count"] == 0
        assert len(result["hints"]) > 0
        filters_hint = [h for h in result["hints"] if "Filters applied" in h]
        assert len(filters_hint) == 1
        assert "max_cloud_cover=10%" in filters_hint[0]
        assert "date_range=2024-06-01/2024-08-31" in filters_hint[0]

    async def test_zero_results_suggests_increase_cloud(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX, max_cloud_cover=5))

        assert any(
            "increasing max_cloud_cover" in h.lower() or "try increasing" in h.lower()
            for h in result["hints"]
        )

    async def test_zero_results_suggests_alt_catalogs(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(
                await fn(bbox=SAMPLE_BBOX, collection="sentinel-2-l2a", catalog="earth_search")
            )

        assert any("planetary_computer" in h for h in result["hints"])

    async def test_nonzero_results_no_filter_hints(self, search_tools):
        """Successful searches for optical collections should not include filter hints."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_item = _make_mock_stac_item()
        mock_search = MagicMock()
        mock_search.items.return_value = [mock_item]
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(bbox=SAMPLE_BBOX))

        assert result["scene_count"] == 1
        # Should have no hints for a successful optical search
        assert result["hints"] == []


class TestStacFindPairsCloudFilter:
    """Tests for conditional cloud cover filter in stac_find_pairs."""

    async def test_sentinel1_no_cloud_filter(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_find_pairs")

        mock_item = _make_mock_stac_item(scene_id="S1_B")
        mock_item.properties = {"datetime": "2024-01-15T10:00:00Z"}
        mock_item.to_dict.return_value["collection"] = "sentinel-1-grd"
        mock_item.to_dict.return_value["properties"] = {
            "datetime": "2024-01-15T10:00:00Z",
        }

        def _mock_search(**kwargs):
            mock_s = MagicMock()
            mock_s.items.return_value = [mock_item]
            return mock_s

        mock_client = MagicMock()
        mock_client.search.side_effect = _mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            await fn(
                bbox=SAMPLE_BBOX,
                before_range="2024-01-01/2024-03-31",
                after_range="2024-07-01/2024-09-30",
                collection="sentinel-1-grd",
            )

        for call in mock_client.search.call_args_list:
            assert "query" not in call[1]


class TestStacPreview:
    async def test_scene_not_found(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_preview")
        result = json.loads(await fn(scene_id="nonexistent"))
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_happy_path_thumbnail(self, search_tools):
        mcp, manager = search_tools
        item = make_stac_item(
            extra_assets={
                "thumbnail": {
                    "href": "https://example.com/thumb.png",
                    "type": "image/png",
                },
            }
        )
        manager.cache_scene(SAMPLE_SCENE_ID, item, "earth_search")

        fn = mcp.get_tool("stac_preview")
        result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert result["preview_url"] == "https://example.com/thumb.png"
        assert result["asset_key"] == "thumbnail"
        assert result["media_type"] == "image/png"

    async def test_prefers_rendered_preview(self, search_tools):
        mcp, manager = search_tools
        item = make_stac_item(
            extra_assets={
                "rendered_preview": {
                    "href": "https://example.com/rendered.png",
                    "type": "image/png",
                },
                "thumbnail": {
                    "href": "https://example.com/thumb.png",
                    "type": "image/png",
                },
            }
        )
        manager.cache_scene(SAMPLE_SCENE_ID, item, "earth_search")

        fn = mcp.get_tool("stac_preview")
        result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert result["asset_key"] == "rendered_preview"
        assert result["preview_url"] == "https://example.com/rendered.png"

    async def test_no_preview_available(self, search_tools):
        mcp, manager = search_tools
        # Item with no preview assets (only data bands)
        item = make_stac_item()
        manager.cache_scene(SAMPLE_SCENE_ID, item, "earth_search")

        fn = mcp.get_tool("stac_preview")
        result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert "error" in result
        assert "no preview" in result["error"].lower()


class TestStacDescribeScene:
    async def test_scene_not_found(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_describe_scene")
        result = json.loads(await fn(scene_id="nonexistent"))
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_happy_path(self, search_tools):
        mcp, manager = search_tools
        item = make_stac_item()
        manager.cache_scene(SAMPLE_SCENE_ID, item, "earth_search")

        fn = mcp.get_tool("stac_describe_scene")
        result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        assert result["scene_id"] == SAMPLE_SCENE_ID
        assert result["collection"] == "sentinel-2-l2a"
        # CRS should be formatted as EPSG:XXXX
        assert result["crs"] == "EPSG:32631"

    async def test_metadata_assets_filtered(self, search_tools, sample_stac_item_with_metadata):
        mcp, manager = search_tools
        manager.cache_scene(SAMPLE_SCENE_ID, sample_stac_item_with_metadata, "earth_search")

        fn = mcp.get_tool("stac_describe_scene")
        result = json.loads(await fn(scene_id=SAMPLE_SCENE_ID))

        asset_keys = [a["key"] for a in result["assets"]]
        # Metadata assets should be excluded
        assert "thumbnail" not in asset_keys
        assert "info" not in asset_keys
        assert "metadata" not in asset_keys
        assert "tilejson" not in asset_keys
        # Data assets should be present
        assert "red" in asset_keys

    async def test_crs_format_from_int(self, search_tools):
        """proj:epsg as int should be formatted to EPSG:XXXX string."""
        mcp, manager = search_tools
        item = make_stac_item(proj_epsg=32632)
        manager.cache_scene("test_crs", item, "earth_search")

        fn = mcp.get_tool("stac_describe_scene")
        result = json.loads(await fn(scene_id="test_crs"))
        assert result["crs"] == "EPSG:32632"

    async def test_crs_format_none(self, search_tools):
        """Missing CRS properties should result in null."""
        mcp, manager = search_tools
        item = make_stac_item(proj_epsg=None)
        manager.cache_scene("no_crs", item, "earth_search")

        fn = mcp.get_tool("stac_describe_scene")
        result = json.loads(await fn(scene_id="no_crs"))
        assert result["crs"] is None


class TestStacDescribeCollection:
    async def test_known_collection(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_describe_collection")

        mock_coll = MagicMock()
        mock_coll.title = "Sentinel-2 L2A"
        mock_coll.description = "Surface reflectance"
        mock_coll.extent = MagicMock()
        mock_coll.extent.spatial = MagicMock()
        mock_coll.extent.spatial.bboxes = [[-180, -90, 180, 90]]
        mock_coll.extent.temporal = MagicMock()
        mock_coll.extent.temporal.intervals = [[None, None]]

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_coll

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(collection_id="sentinel-2-l2a"))

        assert result["collection_id"] == "sentinel-2-l2a"
        assert result["platform"] == "Sentinel-2"
        assert len(result["bands"]) > 0
        assert len(result["composites"]) > 0
        assert result["cloud_mask_band"] == "scl"
        assert result["llm_guidance"] is not None

    async def test_unknown_collection(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_describe_collection")

        mock_coll = MagicMock()
        mock_coll.title = "Custom Collection"
        mock_coll.description = "Some custom data"
        mock_coll.extent = None

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_coll

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(collection_id="custom-unknown"))

        assert result["collection_id"] == "custom-unknown"
        assert result["bands"] == []
        assert result["composites"] == []
        assert result["platform"] is None

    async def test_spectral_indices_detected(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_describe_collection")

        mock_coll = MagicMock()
        mock_coll.title = "Sentinel-2"
        mock_coll.description = None
        mock_coll.extent = None

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_coll

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn(collection_id="sentinel-2-l2a"))

        # Sentinel-2 has nir, red, green, blue, swir16 → supports ndvi, ndwi, ndbi, evi, savi, bsi
        assert "ndvi" in result["spectral_indices"]
        assert "ndwi" in result["spectral_indices"]

    async def test_catalog_error(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_describe_collection")

        with patch.object(manager, "get_stac_client", side_effect=Exception("timeout")):
            result = json.loads(await fn(collection_id="sentinel-2-l2a"))

        assert "error" in result


class TestStacGetConformance:
    async def test_happy_path(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_get_conformance")

        mock_client = MagicMock()
        mock_client.conformance = [
            "https://api.stacspec.org/v1.0.0/core",
            "https://api.stacspec.org/v1.0.0/item-search",
            "https://api.stacspec.org/v1.0.0/item-search#filter",
        ]

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn())

        assert result["conformance_available"] is True
        features = {f["name"]: f["supported"] for f in result["features"]}
        assert features["core"] is True
        assert features["item_search"] is True
        assert features["filter"] is True
        assert len(result["raw_uris"]) == 3

    async def test_no_conformance(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_get_conformance")

        mock_client = MagicMock()
        mock_client.conformance = None

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn())

        assert result["conformance_available"] is False

    async def test_empty_conformance(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_get_conformance")

        mock_client = MagicMock()
        mock_client.conformance = []

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(await fn())

        assert result["conformance_available"] is False

    async def test_catalog_error(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_get_conformance")

        with patch.object(manager, "get_stac_client", side_effect=Exception("refused")):
            result = json.loads(await fn())

        assert "error" in result


# ---------------------------------------------------------------------------
# Feature 5: output_mode tests for search tools
# ---------------------------------------------------------------------------


class TestOutputModeSearch:
    async def test_list_catalogs_text(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_list_catalogs")
        result = await fn(output_mode="text")
        assert "catalog(s) available" in result
        # Should NOT be JSON
        assert not result.startswith("{")

    async def test_list_catalogs_json_default(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_list_catalogs")
        result = await fn()
        parsed = json.loads(result)
        assert "catalogs" in parsed

    async def test_search_text(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_search")

        mock_search = MagicMock()
        mock_search.items.return_value = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = await fn(bbox=SAMPLE_BBOX, output_mode="text")

        assert "Found 0 scene(s)" in result
        assert not result.startswith("{")

    async def test_search_error_text(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_search")
        result = await fn(bbox=[1, 2], output_mode="text")
        assert result.startswith("Error:")

    async def test_describe_collection_text(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_describe_collection")

        mock_coll = MagicMock()
        mock_coll.title = "Sentinel-2"
        mock_coll.description = "A collection"
        mock_coll.extent = None

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_coll

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = await fn(collection_id="sentinel-2-l2a", output_mode="text")

        assert "sentinel-2-l2a" in result
        assert not result.startswith("{")

    async def test_conformance_text(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_get_conformance")

        mock_client = MagicMock()
        mock_client.conformance = None

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = await fn(output_mode="text")

        assert "does not expose conformance" in result


# ---------------------------------------------------------------------------
# stac_find_pairs tests
# ---------------------------------------------------------------------------


class TestStacFindPairs:
    async def test_happy_path(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_find_pairs")

        before_item = _make_mock_stac_item(scene_id="BEFORE_1", cloud_cover=3.0)
        after_item = _make_mock_stac_item(scene_id="AFTER_1", cloud_cover=4.0)

        def _mock_search(**kwargs):
            dt = kwargs.get("datetime", "")
            mock_s = MagicMock()
            if "2024-01" in dt:
                mock_s.items.return_value = [before_item]
            else:
                mock_s.items.return_value = [after_item]
            return mock_s

        mock_client = MagicMock()
        mock_client.search.side_effect = _mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(
                await fn(
                    bbox=SAMPLE_BBOX,
                    before_range="2024-01-01/2024-03-31",
                    after_range="2024-07-01/2024-09-30",
                )
            )

        assert result["pair_count"] >= 1
        assert result["pairs"][0]["before_scene_id"] == "BEFORE_1"
        assert result["pairs"][0]["after_scene_id"] == "AFTER_1"
        assert result["pairs"][0]["overlap_percent"] > 0

    async def test_no_overlap(self, search_tools):
        """Scenes with non-overlapping bboxes produce no pairs."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_find_pairs")

        before_item = _make_mock_stac_item(scene_id="B1")
        before_item.bbox = [0, 0, 1, 1]
        before_item.to_dict.return_value["bbox"] = [0, 0, 1, 1]

        after_item = _make_mock_stac_item(scene_id="A1")
        after_item.bbox = [10, 10, 11, 11]
        after_item.to_dict.return_value["bbox"] = [10, 10, 11, 11]

        def _mock_search(**kwargs):
            dt = kwargs.get("datetime", "")
            mock_s = MagicMock()
            if "2024-01" in dt:
                mock_s.items.return_value = [before_item]
            else:
                mock_s.items.return_value = [after_item]
            return mock_s

        mock_client = MagicMock()
        mock_client.search.side_effect = _mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = json.loads(
                await fn(
                    bbox=SAMPLE_BBOX,
                    before_range="2024-01-01/2024-03-31",
                    after_range="2024-07-01/2024-09-30",
                )
            )

        assert result["pair_count"] == 0

    async def test_caches_scenes(self, search_tools):
        """All found scenes should be cached for later download."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_find_pairs")

        before_item = _make_mock_stac_item(scene_id="CACHED_B")
        after_item = _make_mock_stac_item(scene_id="CACHED_A")

        def _mock_search(**kwargs):
            dt = kwargs.get("datetime", "")
            mock_s = MagicMock()
            if "2024-01" in dt:
                mock_s.items.return_value = [before_item]
            else:
                mock_s.items.return_value = [after_item]
            return mock_s

        mock_client = MagicMock()
        mock_client.search.side_effect = _mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            await fn(
                bbox=SAMPLE_BBOX,
                before_range="2024-01-01/2024-03-31",
                after_range="2024-07-01/2024-09-30",
            )

        assert manager.get_cached_scene("CACHED_B") is not None
        assert manager.get_cached_scene("CACHED_A") is not None

    async def test_error_handling(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_find_pairs")

        with patch.object(manager, "get_stac_client", side_effect=Exception("network error")):
            result = json.loads(
                await fn(
                    bbox=SAMPLE_BBOX,
                    before_range="2024-01-01/2024-03-31",
                    after_range="2024-07-01/2024-09-30",
                )
            )

        assert "error" in result

    async def test_text_output(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_find_pairs")

        before_item = _make_mock_stac_item(scene_id="TB")
        after_item = _make_mock_stac_item(scene_id="TA")

        def _mock_search(**kwargs):
            dt = kwargs.get("datetime", "")
            mock_s = MagicMock()
            if "2024-01" in dt:
                mock_s.items.return_value = [before_item]
            else:
                mock_s.items.return_value = [after_item]
            return mock_s

        mock_client = MagicMock()
        mock_client.search.side_effect = _mock_search

        with patch.object(manager, "get_stac_client", return_value=mock_client):
            result = await fn(
                bbox=SAMPLE_BBOX,
                before_range="2024-01-01/2024-03-31",
                after_range="2024-07-01/2024-09-30",
                output_mode="text",
            )

        assert "scene pair(s)" in result
        assert not result.startswith("{")


# ---------------------------------------------------------------------------
# stac_coverage_check tests
# ---------------------------------------------------------------------------


class TestStacCoverageCheck:
    async def test_full_coverage(self, search_tools):
        """Scene bbox that fully contains target bbox → 100% coverage."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_coverage_check")

        # Scene bbox is larger than target
        item = make_stac_item(scene_id="big_scene")
        item = item.model_copy(update={"bbox": [0.0, 51.0, 2.0, 53.0]})
        manager.cache_scene("big_scene", item, "es")

        result = json.loads(
            await fn(
                bbox=[0.5, 51.5, 1.5, 52.5],
                scene_ids=["big_scene"],
            )
        )

        assert result["fully_covered"] is True
        assert result["coverage_percent"] == 100.0

    async def test_partial_coverage(self, search_tools):
        """Scene bbox that partially covers target → < 100%."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_coverage_check")

        # Scene only covers left half of target
        item = make_stac_item(scene_id="half_scene")
        item = item.model_copy(update={"bbox": [0.0, 51.0, 0.5, 53.0]})
        manager.cache_scene("half_scene", item, "es")

        result = json.loads(
            await fn(
                bbox=[0.0, 51.0, 1.0, 53.0],
                scene_ids=["half_scene"],
            )
        )

        assert result["fully_covered"] is False
        assert 0 < result["coverage_percent"] < 100

    async def test_no_coverage(self, search_tools):
        """Scene bbox that doesn't overlap target → 0%."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_coverage_check")

        item = make_stac_item(scene_id="far_scene")
        item = item.model_copy(update={"bbox": [10.0, 60.0, 11.0, 61.0]})
        manager.cache_scene("far_scene", item, "es")

        result = json.loads(
            await fn(
                bbox=[0.0, 51.0, 1.0, 52.0],
                scene_ids=["far_scene"],
            )
        )

        assert result["coverage_percent"] == 0.0
        assert result["fully_covered"] is False

    async def test_unknown_scene_skipped(self, search_tools):
        """Uncached scene IDs should be silently skipped."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_coverage_check")

        result = json.loads(
            await fn(
                bbox=SAMPLE_BBOX,
                scene_ids=["nonexistent"],
            )
        )

        assert result["scene_count"] == 0
        assert result["coverage_percent"] == 0.0

    async def test_invalid_bbox(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_coverage_check")
        result = json.loads(await fn(bbox=[1, 2], scene_ids=["x"]))
        assert "error" in result

    async def test_text_output(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_coverage_check")

        item = make_stac_item(scene_id="txt_scene")
        item = item.model_copy(update={"bbox": [0.0, 51.0, 2.0, 53.0]})
        manager.cache_scene("txt_scene", item, "es")

        result = await fn(
            bbox=[0.5, 51.5, 1.5, 52.5],
            scene_ids=["txt_scene"],
            output_mode="text",
        )

        assert "Coverage check" in result
        assert not result.startswith("{")


# ---------------------------------------------------------------------------
# stac_queryables tests
# ---------------------------------------------------------------------------


class TestStacQueryables:
    async def test_happy_path(self, search_tools):
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_queryables")

        mock_response = json.dumps(
            {
                "properties": {
                    "eo:cloud_cover": {
                        "type": "number",
                        "description": "Cloud cover percentage",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Satellite platform",
                        "enum": ["sentinel-2a", "sentinel-2b"],
                    },
                }
            }
        ).encode()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = mock_response
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = json.loads(await fn())

        assert result["queryable_count"] == 2
        names = [q["name"] for q in result["queryables"]]
        assert "eo:cloud_cover" in names
        assert "platform" in names

    async def test_with_collection(self, search_tools):
        """Collection-scoped queryables should build correct URL."""
        mcp, manager = search_tools
        fn = mcp.get_tool("stac_queryables")

        mock_response = json.dumps({"properties": {}}).encode()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = mock_response
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = json.loads(await fn(collection="sentinel-2-l2a"))

        assert result["collection"] == "sentinel-2-l2a"
        # Verify URL was constructed with collection
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "/collections/sentinel-2-l2a/queryables" in req.full_url

    async def test_enum_values(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_queryables")

        mock_response = json.dumps(
            {
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["s2a", "s2b"],
                    },
                }
            }
        ).encode()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = mock_response
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = json.loads(await fn())

        assert result["queryables"][0]["enum_values"] == ["s2a", "s2b"]

    async def test_error_handling(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_queryables")

        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = json.loads(await fn())

        assert "error" in result

    async def test_text_output(self, search_tools):
        mcp, _ = search_tools
        fn = mcp.get_tool("stac_queryables")

        mock_response = json.dumps(
            {
                "properties": {
                    "cloud": {"type": "number", "description": "Cloud cover"},
                }
            }
        ).encode()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = mock_response
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = await fn(output_mode="text")

        assert "queryable" in result
        assert not result.startswith("{")
