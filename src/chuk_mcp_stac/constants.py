"""
Constants and configuration for chuk-mcp-stac.

All magic strings live here as enums or module-level constants.
"""

from enum import Enum
from typing import Literal

# ─── Server Configuration ──────────────────────────────────────────────────────


class ServerConfig(str, Enum):
    NAME = "chuk-mcp-stac"
    VERSION = "0.1.0"
    DESCRIPTION = "Satellite Imagery Discovery & Retrieval"


# ─── Storage / Session Providers ───────────────────────────────────────────────


class StorageProvider(str, Enum):
    MEMORY = "memory"
    S3 = "s3"
    FILESYSTEM = "filesystem"


class SessionProvider(str, Enum):
    MEMORY = "memory"
    REDIS = "redis"


# ─── Environment Variable Names ───────────────────────────────────────────────


class EnvVar:
    """Environment variable names used throughout the application."""

    ARTIFACTS_PROVIDER = "CHUK_ARTIFACTS_PROVIDER"
    BUCKET_NAME = "BUCKET_NAME"
    REDIS_URL = "REDIS_URL"
    ARTIFACTS_PATH = "CHUK_ARTIFACTS_PATH"
    AWS_ACCESS_KEY_ID = "AWS_ACCESS_KEY_ID"
    AWS_SECRET_ACCESS_KEY = "AWS_SECRET_ACCESS_KEY"
    AWS_ENDPOINT_URL_S3 = "AWS_ENDPOINT_URL_S3"
    MCP_STDIO = "MCP_STDIO"


# ─── STAC Catalogs ──────────────────────────────────────────────────────────────


class STACEndpoints:
    """Well-known STAC catalog endpoints."""

    EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
    PLANETARY_COMPUTER = "https://planetarycomputer.microsoft.com/api/stac/v1"

    ALL: dict[str, str] = {
        "earth_search": EARTH_SEARCH,
        "planetary_computer": PLANETARY_COMPUTER,
    }


# ─── Collections ────────────────────────────────────────────────────────────────


class SatelliteCollection:
    """Well-known satellite imagery collections."""

    SENTINEL_2_L2A = "sentinel-2-l2a"
    SENTINEL_2_C1_L2A = "sentinel-2-c1-l2a"
    LANDSAT_C2_L2 = "landsat-c2-l2"

    ALL: list[str] = [SENTINEL_2_L2A, SENTINEL_2_C1_L2A, LANDSAT_C2_L2]


# ─── Band Mappings ──────────────────────────────────────────────────────────────


# Sentinel-2 band name -> STAC asset key mapping
SENTINEL2_BANDS: dict[str, str] = {
    "coastal": "coastal",
    "blue": "blue",
    "green": "green",
    "red": "red",
    "rededge1": "rededge1",
    "rededge2": "rededge2",
    "rededge3": "rededge3",
    "nir": "nir",
    "nir08": "nir08",
    "nir09": "nir09",
    "swir16": "swir16",
    "swir22": "swir22",
    "scl": "scl",
}

# Landsat Collection 2 Level-2 band name -> STAC asset key mapping
# Note: Landsat NIR is "nir08", not "nir" as in Sentinel-2
LANDSAT_BANDS: dict[str, str] = {
    "coastal": "coastal",  # Band 1 - 30m (OLI)
    "blue": "blue",  # Band 2 - 30m
    "green": "green",  # Band 3 - 30m
    "red": "red",  # Band 4 - 30m
    "nir08": "nir08",  # Band 5 - 30m
    "swir16": "swir16",  # Band 6 - 30m
    "swir22": "swir22",  # Band 7 - 30m
    "pan": "pan",  # Band 8 - 15m (panchromatic)
    "cirrus": "cirrus",  # Band 9 - 30m
    "lwir11": "lwir11",  # Band 10 - 100m (thermal)
    "lwir12": "lwir12",  # Band 11 - 100m (thermal)
    "qa_pixel": "qa_pixel",  # QA band
    "qa_radsat": "qa_radsat",  # Radiometric saturation QA
}

# Common spectral index band requirements
INDEX_BANDS: dict[str, list[str]] = {
    "ndvi": ["red", "nir"],
    "ndwi": ["green", "nir"],
    "ndbi": ["swir16", "nir"],
    "evi": ["blue", "red", "nir"],
    "savi": ["red", "nir"],
    "bsi": ["blue", "red", "nir", "swir16"],
}


# ─── Defaults ───────────────────────────────────────────────────────────────────


MAX_CLOUD_COVER: int = 20
MAX_ITEMS: int = 10
DEFAULT_CATALOG: str = "earth_search"
DEFAULT_COLLECTION: str = SatelliteCollection.SENTINEL_2_L2A

# RGB band defaults for true-color composites
RGB_BANDS: list[str] = ["red", "green", "blue"]

# Retry configuration for transient network failures
RETRY_ATTEMPTS: int = 3
RETRY_MIN_WAIT: int = 1  # seconds
RETRY_MAX_WAIT: int = 10  # seconds

# Maximum threads for parallel band reads within a scene
MAX_BAND_WORKERS: int = 4

# TTL for cached STAC client connections (seconds)
CLIENT_CACHE_TTL: int = 300


# ─── Type Literals ──────────────────────────────────────────────────────────────


CatalogName = Literal["earth_search", "planetary_computer"]
CompositeMethod = Literal["median", "mean", "min", "max", "latest"]
DownloadFormat = Literal["geotiff", "png"]


# ─── STAC Asset / Property Constants ─────────────────────────────────────────


# Asset keys that are metadata, not data bands — skipped in describe_scene
METADATA_ASSET_KEYS = frozenset({"thumbnail", "info", "metadata", "tilejson"})

THUMBNAIL_KEY = "thumbnail"


# ─── MIME Types ──────────────────────────────────────────────────────────────


class MimeType:
    """MIME type constants for artifact storage."""

    GEOTIFF = "image/tiff"


# ─── Artifact Types ──────────────────────────────────────────────────────────


class ArtifactType(str, Enum):
    """Type identifiers for artifacts stored in chuk-artifacts."""

    SATELLITE_RASTER = "satellite_raster"


# ─── Artifact Reference Schemes ──────────────────────────────────────────────


PENDING_SCHEME = "pending://"


# ─── Composite Constants ────────────────────────────────────────────────────


RGB_COMPOSITE_TYPE = "rgb"
DEFAULT_COMPOSITE_NAME = "custom"


# ─── STAC Property Keys ─────────────────────────────────────────────────────


class STACProperty:
    """Well-known STAC property keys to avoid magic strings."""

    CLOUD_COVER = "eo:cloud_cover"
    DATETIME = "datetime"
    PROJ_EPSG = "proj:epsg"
    PROJ_CODE = "proj:code"
    GSD = "gsd"
    EO_BANDS = "eo:bands"


# ─── Messages ───────────────────────────────────────────────────────────────


class ErrorMessages:
    NO_RESULTS = "No scenes found matching search criteria"
    INVALID_BBOX = "Invalid bounding box: must be [west, south, east, north]"
    INVALID_BBOX_VALUES = (
        "Invalid bounding box values: west ({west}) must be < east ({east}), "
        "south ({south}) must be < north ({north}), "
        "longitude must be -180..180, latitude must be -90..90"
    )
    INVALID_DATE = "Invalid date range format. Use YYYY-MM-DD/YYYY-MM-DD"
    BAND_NOT_FOUND = "Band '{}' not found in scene assets"
    DOWNLOAD_FAILED = "Failed to download band data: {}"
    CATALOG_ERROR = "Failed to connect to STAC catalog: {}"
    SCENE_NOT_FOUND = "Scene '{}' not found"
    NO_CATALOG = "No catalog specified and no default set"


class SuccessMessages:
    SEARCH_COMPLETE = "Found {} scene(s) matching criteria"
    DOWNLOAD_COMPLETE = "Downloaded {} band(s) and stored as artifact"
    COMPOSITE_COMPLETE = "Created {} composite from {} band(s)"
    MOSAIC_COMPLETE = "Created mosaic from {} scene(s)"
    TIME_SERIES = "Extracted time series: {} dates"
