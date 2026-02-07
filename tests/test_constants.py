"""Tests for chuk_mcp_stac.constants."""

from chuk_mcp_stac.constants import (
    CLIENT_CACHE_TTL,
    DEFAULT_CATALOG,
    DEFAULT_COLLECTION,
    DEFAULT_COMPOSITE_NAME,
    INDEX_BANDS,
    LANDSAT_BANDS,
    MAX_BAND_WORKERS,
    MAX_CLOUD_COVER,
    MAX_ITEMS,
    METADATA_ASSET_KEYS,
    PENDING_SCHEME,
    RETRY_ATTEMPTS,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
    RGB_BANDS,
    RGB_COMPOSITE_TYPE,
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
)


class TestSTACEndpoints:
    def test_all_has_both_catalogs(self):
        assert "earth_search" in STACEndpoints.ALL
        assert "planetary_computer" in STACEndpoints.ALL

    def test_urls_start_with_https(self):
        for url in STACEndpoints.ALL.values():
            assert url.startswith("https://")

    def test_class_attributes_match_dict(self):
        assert STACEndpoints.ALL["earth_search"] == STACEndpoints.EARTH_SEARCH
        assert STACEndpoints.ALL["planetary_computer"] == STACEndpoints.PLANETARY_COMPUTER


class TestSatelliteCollection:
    def test_all_has_three_collections(self):
        assert len(SatelliteCollection.ALL) == 3

    def test_sentinel_2_l2a_value(self):
        assert SatelliteCollection.SENTINEL_2_L2A == "sentinel-2-l2a"

    def test_sentinel_2_c1_l2a_value(self):
        assert SatelliteCollection.SENTINEL_2_C1_L2A == "sentinel-2-c1-l2a"

    def test_landsat_value(self):
        assert SatelliteCollection.LANDSAT_C2_L2 == "landsat-c2-l2"


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
