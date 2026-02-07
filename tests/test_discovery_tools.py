"""Tests for chuk_mcp_stac.tools.discovery.api."""

import json
from unittest.mock import patch

import pytest

from chuk_mcp_stac.core.catalog_manager import CatalogManager
from chuk_mcp_stac.tools.discovery.api import register_discovery_tools

from .conftest import MockMCPServer


@pytest.fixture
def discovery_tools():
    """Register discovery tools on a mock MCP and return (mcp, manager)."""
    mcp = MockMCPServer()
    manager = CatalogManager()
    register_discovery_tools(mcp, manager)
    return mcp, manager


class TestStacStatus:
    async def test_returns_status(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with patch("chuk_mcp_stac.tools.discovery.api.has_artifact_store", return_value=False):
            result = json.loads(await fn())

        assert result["server"] == "chuk-mcp-stac"
        assert result["version"] == "0.1.0"
        assert result["storage_provider"] == "memory"
        assert result["default_catalog"] == "earth_search"
        assert result["artifact_store_available"] is False

    async def test_with_artifact_store(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with patch("chuk_mcp_stac.tools.discovery.api.has_artifact_store", return_value=True):
            result = json.loads(await fn())

        assert result["artifact_store_available"] is True

    async def test_with_custom_provider(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with (
            patch("chuk_mcp_stac.tools.discovery.api.has_artifact_store", return_value=True),
            patch.dict("os.environ", {"CHUK_ARTIFACTS_PROVIDER": "s3"}),
        ):
            result = json.loads(await fn())

        assert result["storage_provider"] == "s3"


class TestStacCapabilities:
    async def test_returns_capabilities(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        assert result["server"] == "chuk-mcp-stac"
        assert result["version"] == "0.1.0"
        assert result["default_catalog"] == "earth_search"
        # Dynamic count: only discovery tools registered in this fixture
        assert result["tool_count"] == len(mcp.get_tools())

    async def test_has_all_catalogs(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        catalog_names = [c["name"] for c in result["catalogs"]]
        assert "earth_search" in catalog_names
        assert "planetary_computer" in catalog_names

    async def test_has_known_collections(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        assert "sentinel-2-l2a" in result["known_collections"]
        assert "sentinel-1-grd" in result["known_collections"]
        assert "cop-dem-glo-30" in result["known_collections"]
        assert len(result["known_collections"]) == 5

    async def test_has_spectral_indices(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        index_names = [i["name"] for i in result["spectral_indices"]]
        assert "ndvi" in index_names
        assert "ndwi" in index_names
        # Each index should have required_bands
        for idx in result["spectral_indices"]:
            assert len(idx["required_bands"]) >= 2


class TestStacCapabilitiesBandMappings:
    async def test_has_band_mappings(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        assert "band_mappings" in result
        assert "sentinel-2" in result["band_mappings"]
        assert "landsat" in result["band_mappings"]
        assert "sentinel-1" in result["band_mappings"]
        assert "dem" in result["band_mappings"]

    async def test_sentinel_bands_present(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        s2_bands = result["band_mappings"]["sentinel-2"]
        assert "red" in s2_bands
        assert "nir" in s2_bands

    async def test_landsat_bands_present(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        ls_bands = result["band_mappings"]["landsat"]
        assert "red" in ls_bands
        assert "nir08" in ls_bands
        assert "lwir11" in ls_bands

    async def test_sentinel1_bands_present(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        s1_bands = result["band_mappings"]["sentinel-1"]
        assert "vv" in s1_bands
        assert "vh" in s1_bands

    async def test_dem_bands_present(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = json.loads(await fn())

        dem_bands = result["band_mappings"]["dem"]
        assert "data" in dem_bands


class TestStacStatusError:
    async def test_exception_returns_error(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with patch(
            "chuk_mcp_stac.tools.discovery.api.has_artifact_store",
            side_effect=Exception("connection failed"),
        ):
            result = json.loads(await fn())

        assert "error" in result
        assert "connection failed" in result["error"]


# ---------------------------------------------------------------------------
# Feature 5: output_mode tests for discovery tools
# ---------------------------------------------------------------------------


class TestOutputModeDiscovery:
    async def test_status_text(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with patch("chuk_mcp_stac.tools.discovery.api.has_artifact_store", return_value=False):
            result = await fn(output_mode="text")

        assert "chuk-mcp-stac v0.1.0" in result
        assert "Storage: memory" in result
        assert not result.startswith("{")

    async def test_status_json_default(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with patch("chuk_mcp_stac.tools.discovery.api.has_artifact_store", return_value=False):
            result = await fn()

        parsed = json.loads(result)
        assert parsed["server"] == "chuk-mcp-stac"

    async def test_capabilities_text(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_capabilities")
        result = await fn(output_mode="text")

        assert "chuk-mcp-stac v0.1.0" in result
        assert "Tools:" in result
        assert not result.startswith("{")

    async def test_status_error_text(self, discovery_tools):
        mcp, _ = discovery_tools
        fn = mcp.get_tool("stac_status")

        with patch(
            "chuk_mcp_stac.tools.discovery.api.has_artifact_store",
            side_effect=Exception("boom"),
        ):
            result = await fn(output_mode="text")

        assert result.startswith("Error:")
