"""Tests for chuk_mcp_stac.models — STAC data models + response models."""

import json

import pytest
from pydantic import ValidationError

from chuk_mcp_stac.models import (
    BandDownloadResponse,
    CapabilitiesResponse,
    CatalogInfo,
    CatalogsResponse,
    CollectionInfo,
    CollectionsResponse,
    CompositeResponse,
    ErrorResponse,
    MosaicResponse,
    SceneAsset,
    SceneDetailResponse,
    SceneInfo,
    SearchResponse,
    SpectralIndexInfo,
    STACAsset,
    STACItem,
    STACProperties,
    StatusResponse,
    SuccessResponse,
    TimeSeriesEntry,
    TimeSeriesResponse,
)


class TestErrorResponse:
    def test_valid(self):
        r = ErrorResponse(error="something broke")
        assert r.error == "something broke"

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            ErrorResponse(error="x", extra_field="y")

    def test_json_roundtrip(self):
        r = ErrorResponse(error="test")
        data = json.loads(r.model_dump_json())
        assert data["error"] == "test"


class TestSuccessResponse:
    def test_valid(self):
        r = SuccessResponse(message="ok")
        assert r.message == "ok"

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            SuccessResponse(message="ok", extra="bad")


class TestSceneAsset:
    def test_valid_full(self):
        a = SceneAsset(
            key="red",
            href="https://example.com/red.tif",
            media_type="image/tiff",
            resolution_m=10.0,
        )
        assert a.key == "red"
        assert a.resolution_m == 10.0

    def test_optional_fields(self):
        a = SceneAsset(key="red", href="https://example.com/red.tif")
        assert a.media_type is None
        assert a.resolution_m is None


class TestSceneInfo:
    def test_valid(self):
        s = SceneInfo(
            scene_id="S2B_001",
            collection="sentinel-2-l2a",
            datetime="2024-07-15T10:56:29Z",
            bbox=[0.85, 51.85, 0.95, 51.93],
            cloud_cover=5.2,
            asset_count=13,
        )
        assert s.scene_id == "S2B_001"
        assert s.thumbnail_url is None

    def test_cloud_cover_validation(self):
        with pytest.raises(ValidationError):
            SceneInfo(
                scene_id="x",
                collection="x",
                datetime="x",
                bbox=[0, 0, 1, 1],
                cloud_cover=101,
                asset_count=1,
            )

    def test_cloud_cover_negative(self):
        with pytest.raises(ValidationError):
            SceneInfo(
                scene_id="x",
                collection="x",
                datetime="x",
                bbox=[0, 0, 1, 1],
                cloud_cover=-1,
                asset_count=1,
            )


class TestSearchResponse:
    def test_valid(self):
        r = SearchResponse(
            catalog="earth_search",
            collection="sentinel-2-l2a",
            bbox=[0, 0, 1, 1],
            scene_count=0,
            scenes=[],
            message="ok",
        )
        assert r.scene_count == 0

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            SearchResponse(
                catalog="x",
                collection="x",
                bbox=[0, 0, 1, 1],
                scene_count=0,
                scenes=[],
                message="ok",
                extra="bad",
            )


class TestSceneDetailResponse:
    def test_valid(self):
        r = SceneDetailResponse(
            scene_id="S2B_001",
            collection="sentinel-2-l2a",
            datetime="2024-07-15T10:56:29Z",
            bbox=[0.85, 51.85, 0.95, 51.93],
            assets=[],
            message="ok",
        )
        assert r.crs is None
        assert r.properties == {}


class TestBandDownloadResponse:
    def test_valid(self):
        r = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red", "nir"],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[2, 100, 100],
            dtype="uint16",
            message="ok",
        )
        assert r.artifact_ref == "art://123"


class TestCompositeResponse:
    def test_valid(self):
        r = CompositeResponse(
            scene_id="S2B_001",
            composite_type="rgb",
            bands=["red", "green", "blue"],
            artifact_ref="art://456",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[3, 100, 100],
            message="ok",
        )
        assert r.composite_type == "rgb"


class TestMosaicResponse:
    def test_valid(self):
        r = MosaicResponse(
            scene_ids=["a", "b"],
            bands=["red"],
            artifact_ref="pending://mosaic",
            bbox=[],
            crs="",
            shape=[],
            message="ok",
        )
        assert len(r.scene_ids) == 2


class TestTimeSeriesEntry:
    def test_valid(self):
        e = TimeSeriesEntry(
            datetime="2024-01-01T00:00:00Z",
            scene_id="S2B_001",
            artifact_ref="pending://ts",
        )
        assert e.cloud_cover is None


class TestTimeSeriesResponse:
    def test_valid(self):
        r = TimeSeriesResponse(
            bbox=[0, 0, 1, 1],
            collection="sentinel-2-l2a",
            bands=["red", "nir"],
            date_count=0,
            entries=[],
            message="ok",
        )
        assert r.date_count == 0


class TestCollectionInfo:
    def test_valid(self):
        c = CollectionInfo(collection_id="sentinel-2-l2a")
        assert c.title is None
        assert c.spatial_extent is None


class TestCollectionsResponse:
    def test_valid(self):
        r = CollectionsResponse(
            catalog="earth_search",
            collection_count=0,
            collections=[],
            message="ok",
        )
        assert r.collection_count == 0


class TestCatalogInfo:
    def test_valid(self):
        c = CatalogInfo(name="earth_search", url="https://example.com")
        assert c.name == "earth_search"


class TestCatalogsResponse:
    def test_valid(self):
        r = CatalogsResponse(
            catalogs=[CatalogInfo(name="es", url="https://example.com")],
            default="es",
            message="ok",
        )
        assert len(r.catalogs) == 1


class TestSpectralIndexInfo:
    def test_valid(self):
        s = SpectralIndexInfo(name="ndvi", required_bands=["red", "nir"])
        assert s.name == "ndvi"


class TestCapabilitiesResponse:
    def test_valid(self):
        r = CapabilitiesResponse(
            server="chuk-mcp-stac",
            version="0.1.0",
            catalogs=[],
            default_catalog="earth_search",
            known_collections=["sentinel-2-l2a"],
            spectral_indices=[],
            tool_count=11,
        )
        assert r.tool_count == 11


class TestStatusResponse:
    def test_valid(self):
        r = StatusResponse(
            storage_provider="memory",
            default_catalog="earth_search",
        )
        assert r.server == "chuk-mcp-stac"
        assert r.version == "0.1.0"
        assert r.artifact_store_available is False

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            StatusResponse(
                storage_provider="memory",
                default_catalog="earth_search",
                extra="bad",
            )


# ─── STAC Data Models ───────────────────────────────────────────────────────


class TestSTACAsset:
    def test_minimal(self):
        a = STACAsset(href="https://example.com/red.tif")
        assert a.href == "https://example.com/red.tif"
        assert a.media_type is None
        assert a.gsd is None

    def test_alias_type(self):
        """'type' alias should populate media_type."""
        raw = {"href": "https://example.com/red.tif", "type": "image/tiff"}
        a = STACAsset.model_validate(raw)
        assert a.media_type == "image/tiff"

    def test_alias_eo_bands(self):
        raw = {
            "href": "https://example.com/red.tif",
            "eo:bands": [{"name": "red", "common_name": "red"}],
        }
        a = STACAsset.model_validate(raw)
        assert a.eo_bands is not None
        assert a.eo_bands[0]["name"] == "red"

    def test_extra_fields_preserved(self):
        raw = {"href": "https://example.com/red.tif", "roles": ["data"]}
        a = STACAsset.model_validate(raw)
        # extra="allow" preserves unknown fields
        assert a.model_extra["roles"] == ["data"]

    def test_populate_by_name(self):
        """Can construct using Python field names directly."""
        a = STACAsset(href="https://example.com/red.tif", media_type="image/tiff")
        assert a.media_type == "image/tiff"


class TestSTACProperties:
    def test_defaults(self):
        p = STACProperties()
        assert p.datetime == ""
        assert p.cloud_cover is None
        assert p.proj_epsg is None

    def test_alias_cloud_cover(self):
        raw = {"eo:cloud_cover": 12.5, "datetime": "2024-01-01T00:00:00Z"}
        p = STACProperties.model_validate(raw)
        assert p.cloud_cover == 12.5
        assert p.datetime == "2024-01-01T00:00:00Z"

    def test_alias_proj_epsg(self):
        raw = {"proj:epsg": 32631}
        p = STACProperties.model_validate(raw)
        assert p.proj_epsg == 32631

    def test_alias_proj_code(self):
        raw = {"proj:code": "EPSG:32631"}
        p = STACProperties.model_validate(raw)
        assert p.proj_code == "EPSG:32631"

    def test_extra_fields_preserved(self):
        raw = {"datetime": "2024-01-01T00:00:00Z", "platform": "sentinel-2b"}
        p = STACProperties.model_validate(raw)
        assert p.model_extra["platform"] == "sentinel-2b"

    def test_populate_by_name(self):
        p = STACProperties(cloud_cover=5.0, proj_epsg=32631)
        assert p.cloud_cover == 5.0
        assert p.proj_epsg == 32631


class TestSTACItem:
    def test_minimal(self):
        item = STACItem(id="test-001")
        assert item.id == "test-001"
        assert item.collection == ""
        assert item.bbox == []
        assert item.assets == {}

    def test_full_construction(self):
        item = STACItem(
            id="S2B_001",
            collection="sentinel-2-l2a",
            bbox=[0.85, 51.85, 0.95, 51.93],
            properties=STACProperties(cloud_cover=5.2, proj_epsg=32631),
            assets={"red": STACAsset(href="https://example.com/red.tif")},
        )
        assert item.collection == "sentinel-2-l2a"
        assert item.properties.cloud_cover == 5.2
        assert item.assets["red"].href == "https://example.com/red.tif"

    def test_model_validate_from_stac_dict(self):
        """Simulate parsing a raw STAC item dict (from pystac item.to_dict())."""
        raw = {
            "id": "S2B_001",
            "collection": "sentinel-2-l2a",
            "bbox": [0.85, 51.85, 0.95, 51.93],
            "properties": {
                "datetime": "2024-07-15T10:56:29Z",
                "eo:cloud_cover": 5.2,
                "proj:epsg": 32631,
            },
            "assets": {
                "red": {"href": "https://example.com/red.tif", "type": "image/tiff"},
                "nir": {"href": "https://example.com/nir.tif", "type": "image/tiff"},
            },
        }
        item = STACItem.model_validate(raw)
        assert item.id == "S2B_001"
        assert item.properties.cloud_cover == 5.2
        assert item.properties.proj_epsg == 32631
        assert item.assets["red"].media_type == "image/tiff"
        assert len(item.assets) == 2

    def test_crs_string_from_epsg(self):
        item = STACItem(
            id="test",
            properties=STACProperties(proj_epsg=32631),
        )
        assert item.crs_string == "EPSG:32631"

    def test_crs_string_from_code(self):
        item = STACItem(
            id="test",
            properties=STACProperties(proj_code="EPSG:4326"),
        )
        assert item.crs_string == "EPSG:4326"

    def test_crs_string_none(self):
        item = STACItem(id="test")
        assert item.crs_string is None

    def test_crs_string_epsg_takes_precedence(self):
        item = STACItem(
            id="test",
            properties=STACProperties(proj_epsg=32631, proj_code="EPSG:4326"),
        )
        assert item.crs_string == "EPSG:32631"

    def test_extra_fields_preserved(self):
        raw = {
            "id": "test",
            "type": "Feature",
            "stac_version": "1.0.0",
        }
        item = STACItem.model_validate(raw)
        assert item.model_extra["type"] == "Feature"

    def test_json_roundtrip(self):
        item = STACItem(
            id="S2B_001",
            collection="sentinel-2-l2a",
            bbox=[0.85, 51.85, 0.95, 51.93],
            properties=STACProperties(cloud_cover=5.2, proj_epsg=32631),
            assets={"red": STACAsset(href="https://example.com/red.tif")},
        )
        data = json.loads(item.model_dump_json(by_alias=True))
        assert data["id"] == "S2B_001"
        restored = STACItem.model_validate(data)
        assert restored.properties.cloud_cover == 5.2
