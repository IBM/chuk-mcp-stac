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
        assert len(result["catalogs"]) == 2
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
