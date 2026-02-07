"""Shared fixtures for chuk-mcp-stac tests."""

import os
import tempfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds as transform_from_bounds

from chuk_mcp_stac.core.catalog_manager import CatalogManager
from chuk_mcp_stac.models.stac import STACAsset, STACItem, STACProperties

# ---------------------------------------------------------------------------
# Mock MCP server — collects registered tools without a real MCP runtime
# ---------------------------------------------------------------------------


class MockMCPServer:
    """Minimal MCP server mock that captures tools registered via @mcp.tool."""

    def __init__(self) -> None:
        self._tools: dict[str, object] = {}

    def tool(self, fn: object) -> object:
        """Decorator that registers the function and returns it unchanged."""
        self._tools[fn.__name__] = fn  # type: ignore[union-attr]
        return fn

    def get_tool(self, name: str) -> object:
        return self._tools[name]

    def get_tools(self) -> list[object]:
        return list(self._tools.values())


@pytest.fixture
def mock_mcp() -> MockMCPServer:
    return MockMCPServer()


# ---------------------------------------------------------------------------
# CatalogManager fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def catalog_manager() -> CatalogManager:
    """Fresh CatalogManager with no cached scenes."""
    return CatalogManager()


SAMPLE_SCENE_ID = "S2B_MSIL2A_20240715T105629_N0510_R094_T31UCR_20240715T143301"
SAMPLE_BBOX = [0.85, 51.85, 0.95, 51.93]


def make_stac_item(
    scene_id: str = SAMPLE_SCENE_ID,
    cloud_cover: float = 5.2,
    bands: list[str] | None = None,
    extra_assets: dict[str, dict[str, str]] | None = None,
    proj_epsg: int | None = 32631,
) -> STACItem:
    """Build a minimal STACItem that matches what tools expect."""
    if bands is None:
        bands = ["red", "green", "blue", "nir", "swir16"]

    assets: dict[str, STACAsset] = {}
    for b in bands:
        assets[b] = STACAsset(
            href=f"https://example.com/cogs/{scene_id}/{b}.tif",
            media_type="image/tiff; application=geotiff; profile=cloud-optimized",
        )

    if extra_assets:
        for key, data in extra_assets.items():
            assets[key] = STACAsset(**data)

    properties = STACProperties(
        datetime="2024-07-15T10:56:29Z",
        cloud_cover=cloud_cover,
        proj_epsg=proj_epsg,
    )

    return STACItem(
        id=scene_id,
        collection="sentinel-2-l2a",
        bbox=list(SAMPLE_BBOX),
        properties=properties,
        assets=assets,
    )


@pytest.fixture
def sample_stac_item() -> STACItem:
    return make_stac_item()


@pytest.fixture
def sample_stac_item_with_metadata() -> STACItem:
    """Item that includes non-data assets (thumbnail, info, metadata)."""
    return make_stac_item(
        extra_assets={
            "thumbnail": {
                "href": "https://example.com/thumb.png",
                "type": "image/png",
            },
            "info": {
                "href": "https://example.com/info.json",
                "type": "application/json",
            },
            "metadata": {
                "href": "https://example.com/metadata.xml",
                "type": "application/xml",
            },
            "tilejson": {
                "href": "https://example.com/tiles.json",
                "type": "application/json",
            },
        }
    )


@pytest.fixture
def manager_with_scene(
    catalog_manager: CatalogManager, sample_stac_item: STACItem
) -> CatalogManager:
    """CatalogManager with one scene pre-cached."""
    catalog_manager.cache_scene(SAMPLE_SCENE_ID, sample_stac_item, "earth_search")
    return catalog_manager


# ---------------------------------------------------------------------------
# Temporary GeoTIFF helpers for raster I/O tests
# ---------------------------------------------------------------------------


def create_temp_geotiff(
    tmp_dir: str,
    name: str = "test.tif",
    width: int = 10,
    height: int = 10,
    crs: str = "EPSG:32631",
    bounds: tuple[float, ...] = (500000, 5700000, 500100, 5700100),
    dtype: str = "uint16",
    fill_value: int = 1000,
) -> str:
    """Create a temporary single-band GeoTIFF file and return its path."""
    path = os.path.join(tmp_dir, name)
    transform = transform_from_bounds(*bounds, width, height)
    data = np.full((height, width), fill_value, dtype=dtype)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    return path


@pytest.fixture
def temp_geotiff_dir():
    """Provide a temporary directory for GeoTIFF test files."""
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp
