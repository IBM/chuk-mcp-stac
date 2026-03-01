"""Tests for STAC map visualisation tools: stac_map and stac_pairs_map."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from chuk_mcp_stac.tools.map.api import (
    _bbox_to_polygon,
    _center_and_zoom,
    _scene_to_feature,
    _zoom_from_extent,
    register_map_tools,
)
from tests.conftest import SAMPLE_BBOX, SAMPLE_SCENE_ID, MockMCPServer, make_stac_item

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BEFORE_ID = "S2B_BEFORE_20240101"
AFTER_ID = "S2B_AFTER_20240701"


def _make_manager(*items: tuple[str, Any]) -> MagicMock:
    """Build a mock CatalogManager with pre-cached scenes."""
    cache: dict[str, Any] = dict(items)
    m = MagicMock()
    m.get_cached_scene.side_effect = lambda sid: cache.get(sid)
    return m


def _sc(result: dict[str, Any]) -> dict[str, Any]:
    """Extract structuredContent from a wrapper result dict."""
    return result["structuredContent"]


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_bbox_to_polygon_coordinates(self) -> None:
        poly = _bbox_to_polygon([0.0, 51.0, 1.0, 52.0])
        assert poly["type"] == "Polygon"
        coords = poly["coordinates"][0]
        assert len(coords) == 5  # closed ring
        assert coords[0] == [0.0, 51.0]
        assert coords[-1] == [0.0, 51.0]

    def test_zoom_from_extent_small(self) -> None:
        assert _zoom_from_extent(0.1, 0.1) >= 10

    def test_zoom_from_extent_large(self) -> None:
        assert _zoom_from_extent(20.0, 20.0) <= 7

    def test_zoom_clamped(self) -> None:
        assert _zoom_from_extent(0.0, 0.0) >= 5
        assert _zoom_from_extent(1000.0, 1000.0) >= 5

    def test_scene_to_feature_valid(self) -> None:
        item = make_stac_item(cloud_cover=15.5)
        feat = _scene_to_feature(SAMPLE_SCENE_ID, item)
        assert feat is not None
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Polygon"
        assert feat["properties"]["scene_id"] == SAMPLE_SCENE_ID
        assert feat["properties"]["cloud_cover_pct"] == 15.5

    def test_scene_to_feature_no_cloud(self) -> None:
        item = make_stac_item(cloud_cover=None)
        feat = _scene_to_feature(SAMPLE_SCENE_ID, item)
        assert feat is not None
        assert "cloud_cover_pct" not in feat["properties"]

    def test_scene_to_feature_with_thumbnail(self) -> None:
        item = make_stac_item(extra_assets={"thumbnail": {"href": "https://example.com/thumb.png"}})
        feat = _scene_to_feature(SAMPLE_SCENE_ID, item)
        assert feat is not None
        assert feat["properties"]["thumbnail_url"] == "https://example.com/thumb.png"

    def test_scene_to_feature_no_bbox(self) -> None:
        item = make_stac_item()
        item.bbox = []
        assert _scene_to_feature(SAMPLE_SCENE_ID, item) is None

    def test_center_and_zoom_single(self) -> None:
        bboxes = [[0.85, 51.85, 0.95, 51.93]]
        clat, clon, zoom = _center_and_zoom(bboxes)
        assert abs(clat - 51.89) < 0.01
        assert abs(clon - 0.90) < 0.01
        assert 5 <= zoom <= 14

    def test_center_and_zoom_multiple(self) -> None:
        bboxes = [[-5.0, 50.0, 5.0, 60.0], [10.0, 45.0, 20.0, 55.0]]
        clat, clon, zoom = _center_and_zoom(bboxes)
        assert 5 <= zoom <= 14


# ---------------------------------------------------------------------------
# stac_map tests
# ---------------------------------------------------------------------------


class TestStacMap:
    @pytest.fixture
    def mock_mcp(self) -> MockMCPServer:
        return MockMCPServer()

    @pytest.fixture
    def manager_one(self) -> MagicMock:
        return _make_manager((SAMPLE_SCENE_ID, make_stac_item()))

    @pytest.fixture
    def manager_two_collections(self) -> MagicMock:
        s2 = make_stac_item(scene_id=SAMPLE_SCENE_ID, collection="sentinel-2-l2a")
        ls = make_stac_item(scene_id="LC09_L2SP_20240701", collection="landsat-c2-l2")
        return _make_manager((SAMPLE_SCENE_ID, s2), ("LC09_L2SP_20240701", ls))

    def test_registration(self, mock_mcp: MockMCPServer) -> None:
        register_map_tools(mock_mcp, _make_manager())
        assert "stac_map" in mock_mcp._tools
        assert "stac_pairs_map" in mock_mcp._tools

    @pytest.mark.asyncio
    async def test_structuredcontent_present(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        assert isinstance(result, dict)
        assert "structuredContent" in result
        assert "content" in result
        assert _sc(result)["type"] == "map"

    @pytest.mark.asyncio
    async def test_empty_scene_ids_returns_empty_layers(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids="")
        assert _sc(result)["layers"] == []

    @pytest.mark.asyncio
    async def test_unknown_scene_returns_empty(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids="not_a_real_id")
        assert _sc(result)["layers"] == []

    @pytest.mark.asyncio
    async def test_single_scene_produces_one_layer(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        layers = _sc(result)["layers"]
        assert len(layers) == 1
        assert layers[0]["id"] == "scenes_sentinel_2_l2a"

    @pytest.mark.asyncio
    async def test_two_collections_produce_two_layers(
        self, mock_mcp: MockMCPServer, manager_two_collections: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_two_collections)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=f"{SAMPLE_SCENE_ID},LC09_L2SP_20240701")
        layers = _sc(result)["layers"]
        assert len(layers) == 2
        ids = {la["id"] for la in layers}
        assert "scenes_sentinel_2_l2a" in ids
        assert "scenes_landsat_c2_l2" in ids

    @pytest.mark.asyncio
    async def test_center_computed_from_scenes(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        center = _sc(result)["center"]
        expected_lat = (SAMPLE_BBOX[1] + SAMPLE_BBOX[3]) / 2
        expected_lon = (SAMPLE_BBOX[0] + SAMPLE_BBOX[2]) / 2
        assert abs(center["lat"] - expected_lat) < 0.01
        assert abs(center["lon"] - expected_lon) < 0.01

    @pytest.mark.asyncio
    async def test_invalid_basemap_defaults_to_osm(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID, basemap="invalid")
        assert _sc(result)["basemap"] == "osm"

    @pytest.mark.asyncio
    async def test_satellite_basemap_accepted(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID, basemap="satellite")
        assert _sc(result)["basemap"] == "satellite"

    @pytest.mark.asyncio
    async def test_layer_label_includes_count(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        assert "(1)" in _sc(result)["layers"][0]["label"]

    @pytest.mark.asyncio
    async def test_features_are_polygons(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        layer = _sc(result)["layers"][0]
        assert layer["features"]["features"][0]["geometry"]["type"] == "Polygon"

    @pytest.mark.asyncio
    async def test_popup_contains_cloud_cover(
        self, mock_mcp: MockMCPServer, manager_one: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        props = _sc(result)["layers"][0]["features"]["features"][0]["properties"]
        assert "cloud_cover_pct" in props

    @pytest.mark.asyncio
    async def test_zoom_within_range(self, mock_mcp: MockMCPServer, manager_one: MagicMock) -> None:
        register_map_tools(mock_mcp, manager_one)
        fn = mock_mcp.get_tool("stac_map")
        result = await fn(scene_ids=SAMPLE_SCENE_ID)
        zoom = _sc(result)["zoom"]
        assert 5 <= zoom <= 14


# ---------------------------------------------------------------------------
# stac_pairs_map tests
# ---------------------------------------------------------------------------


class TestStacPairsMap:
    @pytest.fixture
    def mock_mcp(self) -> MockMCPServer:
        return MockMCPServer()

    @pytest.fixture
    def manager_pairs(self) -> MagicMock:
        before = make_stac_item(scene_id=BEFORE_ID, cloud_cover=8.0)
        after = make_stac_item(scene_id=AFTER_ID, cloud_cover=3.0)
        return _make_manager((BEFORE_ID, before), (AFTER_ID, after))

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids="", after_scene_ids="")
        assert _sc(result)["layers"] == []

    @pytest.mark.asyncio
    async def test_two_layers_produced(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        layers = _sc(result)["layers"]
        assert len(layers) == 2
        ids = {la["id"] for la in layers}
        assert "before" in ids
        assert "after" in ids

    @pytest.mark.asyncio
    async def test_before_layer_label(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        before_layer = next(la for la in _sc(result)["layers"] if la["id"] == "before")
        assert "Before" in before_layer["label"]

    @pytest.mark.asyncio
    async def test_default_basemap_satellite(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        assert _sc(result)["basemap"] == "satellite"

    @pytest.mark.asyncio
    async def test_only_before_produces_one_layer(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids="")
        layers = _sc(result)["layers"]
        assert len(layers) == 1
        assert layers[0]["id"] == "before"

    @pytest.mark.asyncio
    async def test_features_are_polygons(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        for layer in _sc(result)["layers"]:
            geom_type = layer["features"]["features"][0]["geometry"]["type"]
            assert geom_type == "Polygon"

    @pytest.mark.asyncio
    async def test_center_from_both_layers(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        center = _sc(result)["center"]
        assert SAMPLE_BBOX[1] <= center["lat"] <= SAMPLE_BBOX[3]
        assert SAMPLE_BBOX[0] <= center["lon"] <= SAMPLE_BBOX[2]

    @pytest.mark.asyncio
    async def test_controls_present(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        assert "controls" in _sc(result)
        assert _sc(result)["controls"]["layers"] is True

    @pytest.mark.asyncio
    async def test_structuredcontent_type_is_map(
        self, mock_mcp: MockMCPServer, manager_pairs: MagicMock
    ) -> None:
        register_map_tools(mock_mcp, manager_pairs)
        fn = mock_mcp.get_tool("stac_pairs_map")
        result = await fn(before_scene_ids=BEFORE_ID, after_scene_ids=AFTER_ID)
        assert _sc(result)["type"] == "map"
