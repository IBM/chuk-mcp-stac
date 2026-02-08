"""Tests for chuk_mcp_stac.constants."""

from chuk_mcp_stac.constants import (
    BAND_ALIASES,
    CLIENT_CACHE_TTL,
    COLLECTION_CATALOGS,
    COLLECTION_INTELLIGENCE,
    CONFORMANCE_CLASSES,
    DEFAULT_CATALOG,
    DEFAULT_COLLECTION,
    DEFAULT_COMPOSITE_NAME,
    DEM_BANDS,
    INDEX_BANDS,
    LANDSAT_BANDS,
    MAX_BAND_WORKERS,
    MAX_CLOUD_COVER,
    MAX_ITEMS,
    METADATA_ASSET_KEYS,
    PENDING_SCHEME,
    PREVIEW_ASSET_KEYS,
    RASTER_CACHE_MAX_BYTES,
    RASTER_CACHE_MAX_ITEM,
    RETRY_ATTEMPTS,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
    RGB_BANDS,
    RGB_COMPOSITE_TYPE,
    SCL_BAND_NAME,
    SCL_COLLECTIONS,
    SCL_GOOD_VALUES,
    SENTINEL1_BANDS,
    SENTINEL2_BANDS,
    THUMBNAIL_KEY,
    ArtifactType,
    EnvVar,
    ErrorMessages,
    MimeType,
    SatelliteCollection,
    ServerConfig,
    SessionProvider,
    STACEndpoints,
    STACProperty,
    StorageProvider,
    SuccessMessages,
    collection_has_cloud_cover,
    resolve_band_name,
)


class TestSTACEndpoints:
    def test_all_has_all_catalogs(self):
        assert "earth_search" in STACEndpoints.ALL
        assert "planetary_computer" in STACEndpoints.ALL
        assert "usgs" in STACEndpoints.ALL

    def test_urls_start_with_https(self):
        for url in STACEndpoints.ALL.values():
            assert url.startswith("https://")

    def test_class_attributes_match_dict(self):
        assert STACEndpoints.ALL["earth_search"] == STACEndpoints.EARTH_SEARCH
        assert STACEndpoints.ALL["planetary_computer"] == STACEndpoints.PLANETARY_COMPUTER
        assert STACEndpoints.ALL["usgs"] == STACEndpoints.USGS

    def test_usgs_url(self):
        assert "landsatlook.usgs.gov" in STACEndpoints.USGS


class TestSatelliteCollection:
    def test_all_has_five_collections(self):
        assert len(SatelliteCollection.ALL) == 5

    def test_sentinel_2_l2a_value(self):
        assert SatelliteCollection.SENTINEL_2_L2A == "sentinel-2-l2a"

    def test_sentinel_2_c1_l2a_value(self):
        assert SatelliteCollection.SENTINEL_2_C1_L2A == "sentinel-2-c1-l2a"

    def test_landsat_value(self):
        assert SatelliteCollection.LANDSAT_C2_L2 == "landsat-c2-l2"

    def test_sentinel_1_grd_value(self):
        assert SatelliteCollection.SENTINEL_1_GRD == "sentinel-1-grd"

    def test_cop_dem_glo_30_value(self):
        assert SatelliteCollection.COP_DEM_GLO_30 == "cop-dem-glo-30"


class TestBandMappings:
    def test_sentinel2_bands_has_expected_keys(self):
        expected = {"coastal", "blue", "green", "red", "nir", "swir16", "swir22", "scl"}
        assert expected.issubset(set(SENTINEL2_BANDS.keys()))

    def test_index_bands_ndvi(self):
        assert INDEX_BANDS["ndvi"] == ["red", "nir"]

    def test_index_bands_ndwi(self):
        assert INDEX_BANDS["ndwi"] == ["green", "nir"]

    def test_index_bands_all_have_lists(self):
        for name, bands in INDEX_BANDS.items():
            assert isinstance(bands, list), f"{name} should map to a list"
            assert len(bands) >= 2, f"{name} should require at least 2 bands"


class TestDefaults:
    def test_max_cloud_cover(self):
        assert MAX_CLOUD_COVER == 20

    def test_max_items(self):
        assert MAX_ITEMS == 10

    def test_default_catalog(self):
        assert DEFAULT_CATALOG == "earth_search"

    def test_default_collection(self):
        assert DEFAULT_COLLECTION == "sentinel-2-l2a"

    def test_rgb_bands(self):
        assert RGB_BANDS == ["red", "green", "blue"]


class TestMetadataAssetKeys:
    def test_is_frozenset(self):
        assert isinstance(METADATA_ASSET_KEYS, frozenset)

    def test_contains_expected_keys(self):
        assert "thumbnail" in METADATA_ASSET_KEYS
        assert "info" in METADATA_ASSET_KEYS
        assert "metadata" in METADATA_ASSET_KEYS
        assert "tilejson" in METADATA_ASSET_KEYS


class TestMessages:
    def test_error_format_strings(self):
        assert "test_band" in ErrorMessages.BAND_NOT_FOUND.format("test_band")
        assert "test_scene" in ErrorMessages.SCENE_NOT_FOUND.format("test_scene")
        assert "oops" in ErrorMessages.DOWNLOAD_FAILED.format("oops")
        assert "oops" in ErrorMessages.CATALOG_ERROR.format("oops")

    def test_success_format_strings(self):
        assert "5" in SuccessMessages.SEARCH_COMPLETE.format(5)
        assert "3" in SuccessMessages.DOWNLOAD_COMPLETE.format(3)
        assert "RGB" in SuccessMessages.COMPOSITE_COMPLETE.format("RGB", 3)

    def test_invalid_bbox_values_named_format(self):
        msg = ErrorMessages.INVALID_BBOX_VALUES.format(west=-10, east=10, south=-5, north=5)
        assert "-10" in msg
        assert "10" in msg
        assert "west" in msg.lower()


class TestServerConfig:
    def test_name(self):
        assert ServerConfig.NAME == "chuk-mcp-stac"

    def test_version(self):
        assert ServerConfig.VERSION == "0.1.0"


class TestSTACProperty:
    def test_cloud_cover(self):
        assert STACProperty.CLOUD_COVER == "eo:cloud_cover"

    def test_datetime(self):
        assert STACProperty.DATETIME == "datetime"


class TestArtifactType:
    def test_satellite_raster(self):
        assert ArtifactType.SATELLITE_RASTER == "satellite_raster"

    def test_is_str_enum(self):
        assert isinstance(ArtifactType.SATELLITE_RASTER, str)


class TestStorageProvider:
    def test_memory(self):
        assert StorageProvider.MEMORY == "memory"

    def test_s3(self):
        assert StorageProvider.S3 == "s3"

    def test_filesystem(self):
        assert StorageProvider.FILESYSTEM == "filesystem"

    def test_is_str_enum(self):
        assert isinstance(StorageProvider.MEMORY, str)


class TestSessionProvider:
    def test_memory(self):
        assert SessionProvider.MEMORY == "memory"

    def test_redis(self):
        assert SessionProvider.REDIS == "redis"

    def test_is_str_enum(self):
        assert isinstance(SessionProvider.MEMORY, str)


class TestEnvVar:
    def test_artifacts_provider(self):
        assert EnvVar.ARTIFACTS_PROVIDER == "CHUK_ARTIFACTS_PROVIDER"

    def test_bucket_name(self):
        assert EnvVar.BUCKET_NAME == "BUCKET_NAME"

    def test_mcp_stdio(self):
        assert EnvVar.MCP_STDIO == "MCP_STDIO"

    def test_aws_keys(self):
        assert EnvVar.AWS_ACCESS_KEY_ID == "AWS_ACCESS_KEY_ID"
        assert EnvVar.AWS_SECRET_ACCESS_KEY == "AWS_SECRET_ACCESS_KEY"


class TestMimeType:
    def test_geotiff(self):
        assert MimeType.GEOTIFF == "image/tiff"

    def test_png(self):
        assert MimeType.PNG == "image/png"


class TestLandsatBands:
    def test_has_expected_keys(self):
        expected = {"coastal", "blue", "green", "red", "nir08", "swir16", "swir22"}
        assert expected.issubset(set(LANDSAT_BANDS.keys()))

    def test_has_thermal_bands(self):
        assert "lwir11" in LANDSAT_BANDS
        assert "lwir12" in LANDSAT_BANDS

    def test_has_qa_bands(self):
        assert "qa_pixel" in LANDSAT_BANDS
        assert "qa_radsat" in LANDSAT_BANDS

    def test_has_panchromatic(self):
        assert "pan" in LANDSAT_BANDS

    def test_nir_is_nir08(self):
        """Landsat uses nir08 not nir — verify no 'nir' key exists."""
        assert "nir08" in LANDSAT_BANDS
        assert "nir" not in LANDSAT_BANDS


class TestRetryAndParallelConstants:
    def test_retry_attempts(self):
        assert RETRY_ATTEMPTS == 3

    def test_retry_wait_bounds(self):
        assert RETRY_MIN_WAIT == 1
        assert RETRY_MAX_WAIT == 10
        assert RETRY_MIN_WAIT < RETRY_MAX_WAIT

    def test_max_band_workers(self):
        assert MAX_BAND_WORKERS == 4

    def test_client_cache_ttl(self):
        assert CLIENT_CACHE_TTL == 300


class TestNewConstants:
    def test_thumbnail_key(self):
        assert THUMBNAIL_KEY == "thumbnail"
        assert THUMBNAIL_KEY in METADATA_ASSET_KEYS

    def test_pending_scheme(self):
        assert PENDING_SCHEME == "pending://"

    def test_rgb_composite_type(self):
        assert RGB_COMPOSITE_TYPE == "rgb"

    def test_default_composite_name(self):
        assert DEFAULT_COMPOSITE_NAME == "custom"


class TestPreviewAssetKeys:
    def test_is_tuple(self):
        assert isinstance(PREVIEW_ASSET_KEYS, tuple)

    def test_contains_expected_keys(self):
        assert "rendered_preview" in PREVIEW_ASSET_KEYS
        assert "thumbnail" in PREVIEW_ASSET_KEYS

    def test_rendered_preview_preferred(self):
        """rendered_preview should come before thumbnail."""
        assert PREVIEW_ASSET_KEYS.index("rendered_preview") < PREVIEW_ASSET_KEYS.index("thumbnail")


class TestSCLConstants:
    def test_scl_band_name(self):
        assert SCL_BAND_NAME == "scl"

    def test_scl_good_values_is_frozenset(self):
        assert isinstance(SCL_GOOD_VALUES, frozenset)

    def test_scl_good_values_contains_vegetation(self):
        assert 4 in SCL_GOOD_VALUES  # vegetation

    def test_scl_good_values_contains_bare_soil(self):
        assert 5 in SCL_GOOD_VALUES

    def test_scl_good_values_contains_water(self):
        assert 6 in SCL_GOOD_VALUES

    def test_scl_good_values_excludes_clouds(self):
        assert 8 not in SCL_GOOD_VALUES  # cloud_med
        assert 9 not in SCL_GOOD_VALUES  # cloud_high
        assert 10 not in SCL_GOOD_VALUES  # thin_cirrus

    def test_scl_collections_is_frozenset(self):
        assert isinstance(SCL_COLLECTIONS, frozenset)

    def test_scl_collections_contains_sentinel2(self):
        assert SatelliteCollection.SENTINEL_2_L2A in SCL_COLLECTIONS
        assert SatelliteCollection.SENTINEL_2_C1_L2A in SCL_COLLECTIONS

    def test_scl_collections_excludes_landsat(self):
        assert SatelliteCollection.LANDSAT_C2_L2 not in SCL_COLLECTIONS


class TestIndexCompleteMessage:
    def test_index_complete_format(self):
        msg = SuccessMessages.INDEX_COMPLETE.format("NDVI")
        assert "NDVI" in msg


class TestBandAliases:
    def test_sentinel2_b04_resolves_to_red(self):
        assert resolve_band_name("B04") == "red"

    def test_sentinel2_b08_resolves_to_nir(self):
        assert resolve_band_name("B08") == "nir"

    def test_sentinel2_b8a_resolves_to_nir08(self):
        assert resolve_band_name("B8A") == "nir08"

    def test_landsat_sr_b4_resolves_to_red(self):
        assert resolve_band_name("SR_B4") == "red"

    def test_landsat_sr_b5_resolves_to_nir08(self):
        assert resolve_band_name("SR_B5") == "nir08"

    def test_common_name_passes_through(self):
        assert resolve_band_name("red") == "red"
        assert resolve_band_name("nir") == "nir"
        assert resolve_band_name("swir16") == "swir16"

    def test_unknown_name_passes_through(self):
        assert resolve_band_name("custom_band") == "custom_band"

    def test_all_sentinel2_aliases(self):
        """All Sentinel-2 hardware names should resolve to valid common names."""
        s2_aliases = {k: v for k, v in BAND_ALIASES.items() if k.startswith("B")}
        for alias, common in s2_aliases.items():
            assert common in SENTINEL2_BANDS, f"{alias} -> {common} not in SENTINEL2_BANDS"

    def test_all_landsat_aliases(self):
        """All Landsat hardware names should resolve to valid common names."""
        ls_aliases = {k: v for k, v in BAND_ALIASES.items() if k.startswith("SR_")}
        for alias, common in ls_aliases.items():
            assert common in LANDSAT_BANDS, f"{alias} -> {common} not in LANDSAT_BANDS"

    def test_band_aliases_is_dict(self):
        assert isinstance(BAND_ALIASES, dict)
        assert len(BAND_ALIASES) > 0


class TestCollectionIntelligence:
    def test_has_known_collections(self):
        assert "sentinel-2-l2a" in COLLECTION_INTELLIGENCE
        assert "sentinel-2-c1-l2a" in COLLECTION_INTELLIGENCE
        assert "landsat-c2-l2" in COLLECTION_INTELLIGENCE
        assert "sentinel-1-grd" in COLLECTION_INTELLIGENCE
        assert "cop-dem-glo-30" in COLLECTION_INTELLIGENCE

    def test_sentinel2_bands_match(self):
        """All band names in intelligence should exist in SENTINEL2_BANDS."""
        intel_bands = COLLECTION_INTELLIGENCE["sentinel-2-l2a"]["bands"]
        for band_name in intel_bands:
            assert band_name in SENTINEL2_BANDS, f"{band_name} not in SENTINEL2_BANDS"

    def test_landsat_bands_match(self):
        """All band names in intelligence should exist in LANDSAT_BANDS."""
        intel_bands = COLLECTION_INTELLIGENCE["landsat-c2-l2"]["bands"]
        for band_name in intel_bands:
            assert band_name in LANDSAT_BANDS, f"{band_name} not in LANDSAT_BANDS"

    def test_has_required_fields(self):
        for coll_id, intel in COLLECTION_INTELLIGENCE.items():
            assert "platform" in intel, f"{coll_id} missing platform"
            assert "instrument" in intel, f"{coll_id} missing instrument"
            assert "bands" in intel, f"{coll_id} missing bands"
            assert "composites" in intel, f"{coll_id} missing composites"
            assert "llm_guidance" in intel, f"{coll_id} missing llm_guidance"


class TestConformanceClasses:
    def test_has_core_features(self):
        assert "core" in CONFORMANCE_CLASSES
        assert "item_search" in CONFORMANCE_CLASSES
        assert "collections" in CONFORMANCE_CLASSES

    def test_all_values_are_lists(self):
        for feature, uris in CONFORMANCE_CLASSES.items():
            assert isinstance(uris, list), f"{feature} should be a list"
            assert len(uris) > 0, f"{feature} should have at least one URI"


class TestSentinel1Bands:
    def test_has_polarisations(self):
        assert "vv" in SENTINEL1_BANDS
        assert "vh" in SENTINEL1_BANDS

    def test_has_two_bands(self):
        assert len(SENTINEL1_BANDS) == 2

    def test_intelligence_bands_match(self):
        intel_bands = COLLECTION_INTELLIGENCE["sentinel-1-grd"]["bands"]
        for band_name in intel_bands:
            assert band_name in SENTINEL1_BANDS, f"{band_name} not in SENTINEL1_BANDS"

    def test_intelligence_no_cloud_mask(self):
        assert COLLECTION_INTELLIGENCE["sentinel-1-grd"]["cloud_mask_band"] is None

    def test_intelligence_platform(self):
        assert COLLECTION_INTELLIGENCE["sentinel-1-grd"]["platform"] == "Sentinel-1"


class TestDEMBands:
    def test_has_data_band(self):
        assert "data" in DEM_BANDS

    def test_has_one_band(self):
        assert len(DEM_BANDS) == 1

    def test_intelligence_bands_match(self):
        intel_bands = COLLECTION_INTELLIGENCE["cop-dem-glo-30"]["bands"]
        for band_name in intel_bands:
            assert band_name in DEM_BANDS, f"{band_name} not in DEM_BANDS"

    def test_intelligence_no_cloud_mask(self):
        assert COLLECTION_INTELLIGENCE["cop-dem-glo-30"]["cloud_mask_band"] is None

    def test_intelligence_platform(self):
        assert COLLECTION_INTELLIGENCE["cop-dem-glo-30"]["platform"] == "TanDEM-X"

    def test_intelligence_resolution(self):
        assert COLLECTION_INTELLIGENCE["cop-dem-glo-30"]["bands"]["data"]["resolution_m"] == 30


class TestRasterCacheConstants:
    def test_max_bytes(self):
        assert RASTER_CACHE_MAX_BYTES == 100 * 1024 * 1024

    def test_max_item(self):
        assert RASTER_CACHE_MAX_ITEM == 10 * 1024 * 1024

    def test_item_smaller_than_total(self):
        assert RASTER_CACHE_MAX_ITEM < RASTER_CACHE_MAX_BYTES


class TestCollectionHasCloudCover:
    def test_sentinel_2_l2a_has_cloud_cover(self):
        assert collection_has_cloud_cover("sentinel-2-l2a") is True

    def test_sentinel_2_c1_l2a_has_cloud_cover(self):
        assert collection_has_cloud_cover("sentinel-2-c1-l2a") is True

    def test_landsat_has_cloud_cover(self):
        assert collection_has_cloud_cover("landsat-c2-l2") is True

    def test_sentinel_1_grd_no_cloud_cover(self):
        assert collection_has_cloud_cover("sentinel-1-grd") is False

    def test_cop_dem_glo_30_no_cloud_cover(self):
        assert collection_has_cloud_cover("cop-dem-glo-30") is False

    def test_unknown_collection_defaults_to_true(self):
        assert collection_has_cloud_cover("my-custom-collection") is True


class TestCollectionCatalogs:
    def test_all_known_collections_present(self):
        for coll in SatelliteCollection.ALL:
            assert coll in COLLECTION_CATALOGS, f"{coll} missing from COLLECTION_CATALOGS"

    def test_sentinel_2_in_multiple_catalogs(self):
        cats = COLLECTION_CATALOGS["sentinel-2-l2a"]
        assert "earth_search" in cats
        assert "planetary_computer" in cats

    def test_sentinel_1_in_catalogs(self):
        cats = COLLECTION_CATALOGS["sentinel-1-grd"]
        assert len(cats) >= 1

    def test_all_catalogs_are_valid(self):
        for coll, cats in COLLECTION_CATALOGS.items():
            for cat in cats:
                assert cat in STACEndpoints.ALL, f"Unknown catalog '{cat}' for {coll}"
