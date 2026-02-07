"""Tests for chuk_mcp_stac.models — STAC data models + response models."""

import json

import pytest
from pydantic import ValidationError

from chuk_mcp_stac.models import (
    BandDetail,
    BandDownloadResponse,
    BandSizeDetail,
    CapabilitiesResponse,
    CatalogInfo,
    CatalogsResponse,
    CollectionDetailResponse,
    CollectionInfo,
    CollectionsResponse,
    CompositeRecipe,
    CompositeResponse,
    ConformanceFeature,
    ConformanceResponse,
    CoverageCheckResponse,
    ErrorResponse,
    FindPairsResponse,
    IndexResponse,
    MosaicResponse,
    PreviewResponse,
    QueryableProperty,
    QueryablesResponse,
    SceneAsset,
    SceneDetailResponse,
    SceneInfo,
    ScenePair,
    SearchResponse,
    SizeEstimateResponse,
    SpectralIndexInfo,
    STACAsset,
    STACItem,
    STACProperties,
    StatusResponse,
    SuccessResponse,
    TemporalCompositeResponse,
    TimeSeriesEntry,
    TimeSeriesResponse,
    format_response,
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


class TestPreviewResponse:
    def test_valid(self):
        r = PreviewResponse(
            scene_id="S2B_001",
            preview_url="https://example.com/thumb.png",
            asset_key="thumbnail",
            media_type="image/png",
            message="ok",
        )
        assert r.preview_url == "https://example.com/thumb.png"
        assert r.asset_key == "thumbnail"

    def test_media_type_optional(self):
        r = PreviewResponse(
            scene_id="S2B_001",
            preview_url="https://example.com/thumb.png",
            asset_key="thumbnail",
            message="ok",
        )
        assert r.media_type is None

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            PreviewResponse(
                scene_id="S2B_001",
                preview_url="https://example.com/thumb.png",
                asset_key="thumbnail",
                message="ok",
                extra="bad",
            )


class TestIndexResponse:
    def test_valid(self):
        r = IndexResponse(
            scene_id="S2B_001",
            index_name="ndvi",
            required_bands=["red", "nir"],
            value_range=[-0.2, 0.85],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 100, 100],
            message="Computed NDVI index",
        )
        assert r.index_name == "ndvi"
        assert r.value_range == [-0.2, 0.85]

    def test_output_format_default(self):
        r = IndexResponse(
            scene_id="S2B_001",
            index_name="ndvi",
            required_bands=["red", "nir"],
            value_range=[0.0, 1.0],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 100, 100],
            message="ok",
        )
        assert r.output_format == "geotiff"

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            IndexResponse(
                scene_id="S2B_001",
                index_name="ndvi",
                required_bands=["red", "nir"],
                value_range=[0.0, 1.0],
                artifact_ref="art://123",
                bbox=[0, 0, 1, 1],
                crs="EPSG:32631",
                shape=[1, 100, 100],
                message="ok",
                extra="bad",
            )


class TestOutputFormatDefaults:
    def test_band_download_default(self):
        r = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red"],
            artifact_ref="art://1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            message="ok",
        )
        assert r.output_format == "geotiff"

    def test_composite_default(self):
        r = CompositeResponse(
            scene_id="S2B_001",
            composite_type="rgb",
            bands=["red", "green", "blue"],
            artifact_ref="art://1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[3, 10, 10],
            message="ok",
        )
        assert r.output_format == "geotiff"

    def test_mosaic_default(self):
        r = MosaicResponse(
            scene_ids=["a"],
            bands=["red"],
            artifact_ref="art://1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            message="ok",
        )
        assert r.output_format == "geotiff"

    def test_band_download_png(self):
        r = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red"],
            artifact_ref="art://1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            output_format="png",
            message="ok",
        )
        assert r.output_format == "png"


class TestPreviewRefField:
    """Verify preview_ref is an optional field on all download response models."""

    def test_band_download_preview_ref_default_none(self):
        r = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red"],
            artifact_ref="art://1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            message="ok",
        )
        assert r.preview_ref is None

    def test_band_download_preview_ref_set(self):
        r = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red"],
            artifact_ref="art://1",
            preview_ref="art://preview-1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            dtype="uint16",
            message="ok",
        )
        assert r.preview_ref == "art://preview-1"

    def test_composite_preview_ref(self):
        r = CompositeResponse(
            scene_id="S2B_001",
            composite_type="rgb",
            bands=["red", "green", "blue"],
            artifact_ref="art://1",
            preview_ref="art://p1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[3, 10, 10],
            message="ok",
        )
        assert r.preview_ref == "art://p1"

    def test_mosaic_preview_ref(self):
        r = MosaicResponse(
            scene_ids=["a"],
            bands=["red"],
            artifact_ref="art://1",
            preview_ref="art://p1",
            bbox=[],
            crs="",
            shape=[],
            message="ok",
        )
        assert r.preview_ref == "art://p1"

    def test_index_preview_ref(self):
        r = IndexResponse(
            scene_id="S2B_001",
            index_name="ndvi",
            required_bands=["red", "nir"],
            value_range=[0.0, 1.0],
            artifact_ref="art://1",
            preview_ref="art://p1",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 10, 10],
            message="ok",
        )
        assert r.preview_ref == "art://p1"

    def test_time_series_entry_preview_ref(self):
        e = TimeSeriesEntry(
            datetime="2024-01-01T00:00:00Z",
            scene_id="S2B_001",
            artifact_ref="art://1",
            preview_ref="art://p1",
        )
        assert e.preview_ref == "art://p1"


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


class TestBandSizeDetail:
    def test_valid(self):
        d = BandSizeDetail(band="red", width=100, height=100, dtype="uint16", bytes=20000)
        assert d.band == "red"
        assert d.bytes == 20000

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            BandSizeDetail(
                band="red", width=100, height=100, dtype="uint16", bytes=20000, extra="bad"
            )


class TestBandDetail:
    def test_valid(self):
        d = BandDetail(name="red", wavelength_nm=665, resolution_m=10)
        assert d.name == "red"
        assert d.wavelength_nm == 665


class TestCompositeRecipe:
    def test_valid(self):
        r = CompositeRecipe(
            name="true_color",
            bands=["red", "green", "blue"],
            description="Natural colour",
        )
        assert r.name == "true_color"
        assert len(r.bands) == 3


class TestCollectionDetailResponse:
    def test_valid_with_intelligence(self):
        r = CollectionDetailResponse(
            collection_id="sentinel-2-l2a",
            catalog="earth_search",
            title="Sentinel-2 L2A",
            platform="Sentinel-2",
            instrument="MSI",
            bands=[BandDetail(name="red", wavelength_nm=665, resolution_m=10)],
            composites=[CompositeRecipe(name="rgb", bands=["r", "g", "b"], description="RGB")],
            spectral_indices=["ndvi"],
            cloud_mask_band="scl",
            llm_guidance="Use nir for vegetation",
            message="ok",
        )
        assert r.platform == "Sentinel-2"
        assert len(r.bands) == 1

    def test_valid_empty_intelligence(self):
        r = CollectionDetailResponse(
            collection_id="unknown",
            catalog="earth_search",
            message="ok",
        )
        assert r.bands == []
        assert r.composites == []
        assert r.platform is None


class TestConformanceFeature:
    def test_valid(self):
        f = ConformanceFeature(name="core", supported=True, matching_uris=["https://example.com"])
        assert f.supported is True


class TestConformanceResponse:
    def test_valid(self):
        r = ConformanceResponse(
            catalog="earth_search",
            conformance_available=True,
            features=[ConformanceFeature(name="core", supported=True)],
            raw_uris=["https://api.stacspec.org/v1.0.0/core"],
            message="ok",
        )
        assert r.conformance_available is True
        assert len(r.features) == 1


class TestSizeEstimateResponse:
    def test_valid(self):
        r = SizeEstimateResponse(
            scene_id="S2B_001",
            band_count=2,
            per_band=[
                BandSizeDetail(band="red", width=100, height=100, dtype="uint16", bytes=20000),
            ],
            total_pixels=10000,
            estimated_bytes=20000,
            estimated_mb=0.02,
            crs="EPSG:32631",
            message="Estimated 0.02 MB",
        )
        assert r.band_count == 2
        assert r.warnings == []
        assert r.bbox == []

    def test_with_warnings(self):
        r = SizeEstimateResponse(
            scene_id="S2B_001",
            band_count=1,
            per_band=[],
            total_pixels=100000000,
            estimated_bytes=600000000,
            estimated_mb=572.0,
            crs="EPSG:32631",
            warnings=["Large download"],
            message="Estimated 572.0 MB",
        )
        assert len(r.warnings) == 1


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


# ---------------------------------------------------------------------------
# Feature 5: to_text() methods and format_response utility
# ---------------------------------------------------------------------------


class TestFormatResponse:
    def test_json_mode_returns_json(self):
        model = ErrorResponse(error="boom")
        result = format_response(model, "json")
        parsed = json.loads(result)
        assert parsed["error"] == "boom"

    def test_text_mode_returns_text(self):
        model = ErrorResponse(error="boom")
        result = format_response(model, "text")
        assert result == "Error: boom"
        # Should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result)

    def test_default_mode_is_json(self):
        model = ErrorResponse(error="boom")
        result = format_response(model)
        parsed = json.loads(result)
        assert parsed["error"] == "boom"

    def test_unknown_mode_falls_back_to_json(self):
        model = ErrorResponse(error="boom")
        result = format_response(model, "xml")
        parsed = json.loads(result)
        assert parsed["error"] == "boom"


class TestErrorResponseToText:
    def test_simple_error(self):
        assert ErrorResponse(error="not found").to_text() == "Error: not found"


class TestSuccessResponseToText:
    def test_simple_message(self):
        from chuk_mcp_stac.models import SuccessResponse

        assert SuccessResponse(message="done").to_text() == "done"


class TestSearchResponseToText:
    def test_with_scenes(self):
        resp = SearchResponse(
            catalog="earth_search",
            collection="sentinel-2-l2a",
            bbox=[0.8, 51.8, 1.0, 51.95],
            scene_count=2,
            scenes=[
                SceneInfo(
                    scene_id="S2B_001",
                    collection="sentinel-2-l2a",
                    datetime="2024-07-15",
                    bbox=[0.8, 51.8, 1.0, 51.95],
                    cloud_cover=3.2,
                    asset_count=10,
                ),
                SceneInfo(
                    scene_id="S2B_002",
                    collection="sentinel-2-l2a",
                    datetime="2024-07-18",
                    bbox=[0.8, 51.8, 1.0, 51.95],
                    cloud_cover=None,
                    asset_count=10,
                ),
            ],
            message="Found 2 scene(s)",
        )
        text = resp.to_text()
        assert "Found 2 scene(s)" in text
        assert "S2B_001" in text
        assert "3.2% cloud" in text
        assert "S2B_002" in text

    def test_empty_search(self):
        resp = SearchResponse(
            catalog="earth_search",
            collection="sentinel-2-l2a",
            bbox=[0, 0, 1, 1],
            scene_count=0,
            scenes=[],
            message="No results",
        )
        assert "Found 0 scene(s)" in resp.to_text()


class TestSceneDetailResponseToText:
    def test_with_assets(self):
        resp = SceneDetailResponse(
            scene_id="S2B_001",
            collection="sentinel-2-l2a",
            datetime="2024-07-15",
            bbox=[0, 0, 1, 1],
            cloud_cover=5.0,
            crs="EPSG:32631",
            assets=[
                SceneAsset(key="red", href="https://example.com/red.tif", resolution_m=10.0),
                SceneAsset(key="nir", href="https://example.com/nir.tif"),
            ],
            message="Scene S2B_001",
        )
        text = resp.to_text()
        assert "Scene S2B_001" in text
        assert "EPSG:32631" in text
        assert "red (10.0m)" in text
        assert "nir" in text


class TestPreviewResponseToText:
    def test_preview(self):
        resp = PreviewResponse(
            scene_id="S2B_001",
            preview_url="https://example.com/thumb.png",
            asset_key="thumbnail",
            message="ok",
        )
        text = resp.to_text()
        assert "S2B_001" in text
        assert "https://example.com/thumb.png" in text


class TestBandDownloadResponseToText:
    def test_with_preview(self):
        resp = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red", "nir"],
            artifact_ref="art://123",
            preview_ref="art://prev",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[2, 100, 100],
            dtype="uint16",
            message="done",
        )
        text = resp.to_text()
        assert "Downloaded 2 band(s)" in text
        assert "art://123" in text
        assert "2x100x100" in text
        assert "Preview: art://prev" in text

    def test_without_preview(self):
        resp = BandDownloadResponse(
            scene_id="S2B_001",
            bands=["red"],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 100, 100],
            dtype="uint16",
            message="done",
        )
        assert "Preview" not in resp.to_text()


class TestCompositeResponseToText:
    def test_composite(self):
        resp = CompositeResponse(
            scene_id="S2B_001",
            composite_type="rgb",
            bands=["red", "green", "blue"],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[3, 100, 100],
            message="done",
        )
        text = resp.to_text()
        assert "rgb composite" in text
        assert "red, green, blue" in text


class TestMosaicResponseToText:
    def test_mosaic(self):
        resp = MosaicResponse(
            scene_ids=["S2B_001", "S2B_002"],
            bands=["red"],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 200, 200],
            message="done",
        )
        text = resp.to_text()
        assert "Mosaic of 2 scene(s)" in text
        assert "method: last" in text


class TestIndexResponseToText:
    def test_index(self):
        resp = IndexResponse(
            scene_id="S2B_001",
            index_name="ndvi",
            required_bands=["red", "nir"],
            value_range=[-0.2, 0.85],
            artifact_ref="art://123",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[1, 100, 100],
            message="done",
        )
        text = resp.to_text()
        assert "NDVI" in text
        assert "-0.2000" in text
        assert "0.8500" in text


class TestTimeSeriesResponseToText:
    def test_time_series(self):
        resp = TimeSeriesResponse(
            bbox=[0, 0, 1, 1],
            collection="sentinel-2-l2a",
            bands=["red", "nir"],
            date_count=2,
            entries=[
                TimeSeriesEntry(
                    datetime="2024-07-15",
                    scene_id="S2B_001",
                    artifact_ref="art://1",
                    cloud_cover=5.0,
                ),
                TimeSeriesEntry(
                    datetime="2024-07-20",
                    scene_id="S2B_002",
                    artifact_ref="art://2",
                ),
            ],
            message="done",
        )
        text = resp.to_text()
        assert "2 date(s)" in text
        assert "5.0% cloud" in text
        assert "S2B_002" in text


class TestCollectionsResponseToText:
    def test_collections(self):
        resp = CollectionsResponse(
            catalog="earth_search",
            collection_count=2,
            collections=[
                CollectionInfo(collection_id="sentinel-2-l2a", title="Sentinel-2"),
                CollectionInfo(collection_id="landsat-c2-l2"),
            ],
            message="ok",
        )
        text = resp.to_text()
        assert "2 collection(s)" in text
        assert "sentinel-2-l2a: Sentinel-2" in text
        assert "landsat-c2-l2" in text


class TestCatalogsResponseToText:
    def test_catalogs(self):
        resp = CatalogsResponse(
            catalogs=[
                CatalogInfo(name="earth_search", url="https://earth-search.aws.element84.com/v1"),
            ],
            default="earth_search",
            message="ok",
        )
        text = resp.to_text()
        assert "1 catalog(s)" in text
        assert "earth_search" in text


class TestCapabilitiesResponseToText:
    def test_capabilities(self):
        resp = CapabilitiesResponse(
            server="chuk-mcp-stac",
            version="0.1.0",
            catalogs=[CatalogInfo(name="earth_search", url="https://example.com")],
            default_catalog="earth_search",
            known_collections=["sentinel-2-l2a"],
            spectral_indices=[SpectralIndexInfo(name="ndvi", required_bands=["red", "nir"])],
            tool_count=16,
        )
        text = resp.to_text()
        assert "chuk-mcp-stac v0.1.0" in text
        assert "Tools: 16" in text
        assert "ndvi" in text


class TestStatusResponseToText:
    def test_status(self):
        resp = StatusResponse(
            storage_provider="memory",
            default_catalog="earth_search",
            artifact_store_available=True,
        )
        text = resp.to_text()
        assert "chuk-mcp-stac v0.1.0" in text
        assert "Storage: memory" in text
        assert "Artifact store: available" in text

    def test_status_not_available(self):
        resp = StatusResponse(
            storage_provider="s3",
            default_catalog="earth_search",
            artifact_store_available=False,
        )
        assert "not available" in resp.to_text()


class TestSizeEstimateResponseToText:
    def test_size_estimate(self):
        resp = SizeEstimateResponse(
            scene_id="S2B_001",
            band_count=2,
            per_band=[
                BandSizeDetail(band="red", width=512, height=512, dtype="uint16", bytes=524288),
                BandSizeDetail(band="nir", width=512, height=512, dtype="uint16", bytes=524288),
            ],
            total_pixels=524288,
            estimated_bytes=1048576,
            estimated_mb=1.0,
            crs="EPSG:32631",
            warnings=["Large download"],
            message="ok",
        )
        text = resp.to_text()
        assert "1.0 MB" in text
        assert "red: 512x512" in text
        assert "WARNING: Large download" in text


class TestCollectionDetailResponseToText:
    def test_with_bands_and_composites(self):
        resp = CollectionDetailResponse(
            collection_id="sentinel-2-l2a",
            catalog="earth_search",
            title="Sentinel-2 L2A",
            platform="Sentinel-2",
            bands=[BandDetail(name="red", wavelength_nm=665, resolution_m=10)],
            composites=[
                CompositeRecipe(
                    name="true_color", bands=["red", "green", "blue"], description="Natural color"
                )
            ],
            spectral_indices=["ndvi", "ndwi"],
            llm_guidance="Use for vegetation analysis",
            message="ok",
        )
        text = resp.to_text()
        assert "sentinel-2-l2a" in text
        assert "Sentinel-2" in text
        assert "red: 665nm" in text
        assert "true_color" in text
        assert "ndvi, ndwi" in text
        assert "Use for vegetation analysis" in text


class TestConformanceResponseToText:
    def test_with_features(self):
        resp = ConformanceResponse(
            catalog="earth_search",
            conformance_available=True,
            features=[
                ConformanceFeature(name="core", supported=True, matching_uris=["http://x"]),
                ConformanceFeature(name="filter", supported=False),
            ],
            raw_uris=["http://x"],
            message="1/2 features",
        )
        text = resp.to_text()
        assert "1/2 features" in text
        assert "Supported: core" in text
        assert "Not supported: filter" in text

    def test_no_conformance(self):
        resp = ConformanceResponse(
            catalog="test",
            conformance_available=False,
            message="no conformance",
        )
        assert "does not expose conformance" in resp.to_text()


# ---------------------------------------------------------------------------
# Batch D: New response models
# ---------------------------------------------------------------------------


class TestScenePair:
    def test_valid(self):
        p = ScenePair(
            before_scene_id="B1",
            before_datetime="2024-01-01",
            after_scene_id="A1",
            after_datetime="2024-07-01",
            overlap_percent=95.5,
        )
        assert p.overlap_percent == 95.5

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            ScenePair(
                before_scene_id="B1",
                before_datetime="2024-01-01",
                after_scene_id="A1",
                after_datetime="2024-07-01",
                overlap_percent=50.0,
                extra="bad",
            )

    def test_overlap_validation(self):
        with pytest.raises(ValidationError):
            ScenePair(
                before_scene_id="B1",
                before_datetime="2024-01-01",
                after_scene_id="A1",
                after_datetime="2024-07-01",
                overlap_percent=150.0,
            )


class TestFindPairsResponse:
    def test_valid(self):
        r = FindPairsResponse(
            bbox=[0, 0, 1, 1],
            collection="sentinel-2-l2a",
            before_range="2024-01-01/2024-03-31",
            after_range="2024-07-01/2024-09-30",
            pair_count=0,
            pairs=[],
            message="ok",
        )
        assert r.pair_count == 0

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            FindPairsResponse(
                bbox=[0, 0, 1, 1],
                collection="x",
                before_range="x",
                after_range="x",
                pair_count=0,
                pairs=[],
                message="ok",
                extra="bad",
            )

    def test_to_text(self):
        r = FindPairsResponse(
            bbox=[0, 0, 1, 1],
            collection="sentinel-2-l2a",
            before_range="2024-01-01/2024-03-31",
            after_range="2024-07-01/2024-09-30",
            pair_count=1,
            pairs=[
                ScenePair(
                    before_scene_id="B1",
                    before_datetime="2024-01-15",
                    after_scene_id="A1",
                    after_datetime="2024-07-15",
                    overlap_percent=98.5,
                )
            ],
            message="Found 1 pair",
        )
        text = r.to_text()
        assert "1 scene pair(s)" in text
        assert "B1 -> A1" in text
        assert "98.5% overlap" in text


class TestCoverageCheckResponse:
    def test_valid_fully_covered(self):
        r = CoverageCheckResponse(
            bbox=[0, 0, 1, 1],
            scene_count=2,
            fully_covered=True,
            coverage_percent=100.0,
            scene_ids=["s1", "s2"],
            message="ok",
        )
        assert r.fully_covered is True
        assert r.uncovered_areas == []

    def test_valid_partial(self):
        r = CoverageCheckResponse(
            bbox=[0, 0, 1, 1],
            scene_count=1,
            fully_covered=False,
            coverage_percent=60.0,
            uncovered_areas=[[0.5, 0, 1, 0.5]],
            scene_ids=["s1"],
            message="ok",
        )
        assert len(r.uncovered_areas) == 1

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            CoverageCheckResponse(
                bbox=[0, 0, 1, 1],
                scene_count=0,
                fully_covered=False,
                coverage_percent=0.0,
                scene_ids=[],
                message="ok",
                extra="bad",
            )

    def test_to_text_covered(self):
        r = CoverageCheckResponse(
            bbox=[0, 0, 1, 1],
            scene_count=1,
            fully_covered=True,
            coverage_percent=100.0,
            scene_ids=["s1"],
            message="ok",
        )
        text = r.to_text()
        assert "fully covered" in text

    def test_to_text_partial(self):
        r = CoverageCheckResponse(
            bbox=[0, 0, 1, 1],
            scene_count=1,
            fully_covered=False,
            coverage_percent=50.0,
            uncovered_areas=[[0.5, 0, 1, 1]],
            scene_ids=["s1"],
            message="ok",
        )
        text = r.to_text()
        assert "50.0% covered" in text
        assert "Uncovered areas: 1" in text


class TestQueryableProperty:
    def test_valid(self):
        q = QueryableProperty(
            name="eo:cloud_cover",
            type="number",
            description="Cloud cover percentage",
        )
        assert q.name == "eo:cloud_cover"
        assert q.enum_values == []

    def test_with_enum(self):
        q = QueryableProperty(
            name="platform",
            type="string",
            enum_values=["sentinel-2a", "sentinel-2b"],
        )
        assert len(q.enum_values) == 2


class TestQueryablesResponse:
    def test_valid(self):
        r = QueryablesResponse(
            catalog="earth_search",
            queryable_count=1,
            queryables=[QueryableProperty(name="cloud", type="number")],
            message="ok",
        )
        assert r.queryable_count == 1
        assert r.collection is None

    def test_with_collection(self):
        r = QueryablesResponse(
            catalog="earth_search",
            collection="sentinel-2-l2a",
            queryable_count=0,
            queryables=[],
            message="ok",
        )
        assert r.collection == "sentinel-2-l2a"

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            QueryablesResponse(
                catalog="x",
                queryable_count=0,
                queryables=[],
                message="ok",
                extra="bad",
            )

    def test_to_text(self):
        r = QueryablesResponse(
            catalog="earth_search",
            collection="sentinel-2-l2a",
            queryable_count=2,
            queryables=[
                QueryableProperty(name="cloud", type="number", description="Cloud cover"),
                QueryableProperty(name="platform", type="string"),
            ],
            message="ok",
        )
        text = r.to_text()
        assert "2 queryable" in text
        assert "sentinel-2-l2a" in text
        assert "cloud (number)" in text

    def test_to_text_no_collection(self):
        r = QueryablesResponse(
            catalog="earth_search",
            queryable_count=0,
            queryables=[],
            message="ok",
        )
        text = r.to_text()
        assert "earth_search" in text


class TestTemporalCompositeResponse:
    def test_valid(self):
        r = TemporalCompositeResponse(
            scene_ids=["s1", "s2"],
            bands=["red", "nir"],
            method="median",
            artifact_ref="art://composite",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[2, 100, 100],
            date_range="2024-01-01/2024-12-31",
            message="ok",
        )
        assert r.method == "median"
        assert r.date_range == "2024-01-01/2024-12-31"

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            TemporalCompositeResponse(
                scene_ids=[],
                bands=[],
                method="median",
                artifact_ref="x",
                bbox=[],
                crs="x",
                shape=[],
                date_range="x",
                message="ok",
                extra="bad",
            )

    def test_to_text(self):
        r = TemporalCompositeResponse(
            scene_ids=["s1", "s2"],
            bands=["red", "nir"],
            method="median",
            artifact_ref="art://composite",
            bbox=[0, 0, 1, 1],
            crs="EPSG:32631",
            shape=[2, 100, 100],
            date_range="2024-06-01/2024-08-31",
            message="ok",
        )
        text = r.to_text()
        assert "median composite" in text
        assert "2 scene(s)" in text
        assert "2024-06-01/2024-08-31" in text

    def test_mosaic_method_field(self):
        r = MosaicResponse(
            scene_ids=["a"],
            bands=["red"],
            artifact_ref="art://1",
            bbox=[],
            crs="",
            shape=[],
            method="quality",
            message="ok",
        )
        assert r.method == "quality"
        assert "method: quality" in r.to_text()
