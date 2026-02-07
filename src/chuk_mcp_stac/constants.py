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
    USGS = "https://landsatlook.usgs.gov/stac-server"

    ALL: dict[str, str] = {
        "earth_search": EARTH_SEARCH,
        "planetary_computer": PLANETARY_COMPUTER,
        "usgs": USGS,
    }


# ─── Collections ────────────────────────────────────────────────────────────────


class SatelliteCollection:
    """Well-known satellite imagery collections."""

    SENTINEL_2_L2A = "sentinel-2-l2a"
    SENTINEL_2_C1_L2A = "sentinel-2-c1-l2a"
    LANDSAT_C2_L2 = "landsat-c2-l2"
    SENTINEL_1_GRD = "sentinel-1-grd"
    COP_DEM_GLO_30 = "cop-dem-glo-30"

    ALL: list[str] = [
        SENTINEL_2_L2A,
        SENTINEL_2_C1_L2A,
        LANDSAT_C2_L2,
        SENTINEL_1_GRD,
        COP_DEM_GLO_30,
    ]


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

# Sentinel-1 GRD SAR band name -> STAC asset key mapping
SENTINEL1_BANDS: dict[str, str] = {
    "vv": "vv",  # Co-polarisation
    "vh": "vh",  # Cross-polarisation
}

# Copernicus DEM GLO-30 band name -> STAC asset key mapping
DEM_BANDS: dict[str, str] = {
    "data": "data",  # Elevation values in metres
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

# Hardware band name → common name aliases
# Allows users to pass e.g. "B04" or "SR_B4" instead of "red"
BAND_ALIASES: dict[str, str] = {
    # Sentinel-2 MSI hardware designations
    "B01": "coastal",
    "B02": "blue",
    "B03": "green",
    "B04": "red",
    "B05": "rededge1",
    "B06": "rededge2",
    "B07": "rededge3",
    "B08": "nir",
    "B8A": "nir08",
    "B09": "nir09",
    "B11": "swir16",
    "B12": "swir22",
    # Landsat Collection 2 Surface Reflectance designations
    "SR_B1": "coastal",
    "SR_B2": "blue",
    "SR_B3": "green",
    "SR_B4": "red",
    "SR_B5": "nir08",
    "SR_B6": "swir16",
    "SR_B7": "swir22",
}


def resolve_band_name(name: str) -> str:
    """Resolve a hardware band alias to its common name, or return as-is."""
    return BAND_ALIASES.get(name, name)


# ─── Collection Intelligence ─────────────────────────────────────────────────
# Static metadata keyed by collection ID, merged with live STAC data at runtime.

COLLECTION_INTELLIGENCE: dict[str, dict] = {
    "sentinel-2-l2a": {
        "platform": "Sentinel-2",
        "instrument": "MSI",
        "bands": {
            "coastal": {"wavelength_nm": 443, "resolution_m": 60},
            "blue": {"wavelength_nm": 490, "resolution_m": 10},
            "green": {"wavelength_nm": 560, "resolution_m": 10},
            "red": {"wavelength_nm": 665, "resolution_m": 10},
            "rededge1": {"wavelength_nm": 705, "resolution_m": 20},
            "rededge2": {"wavelength_nm": 740, "resolution_m": 20},
            "rededge3": {"wavelength_nm": 783, "resolution_m": 20},
            "nir": {"wavelength_nm": 842, "resolution_m": 10},
            "nir08": {"wavelength_nm": 865, "resolution_m": 20},
            "nir09": {"wavelength_nm": 945, "resolution_m": 60},
            "swir16": {"wavelength_nm": 1610, "resolution_m": 20},
            "swir22": {"wavelength_nm": 2190, "resolution_m": 20},
        },
        "composites": {
            "true_color": {"bands": ["red", "green", "blue"], "description": "Natural colour RGB"},
            "false_color_ir": {
                "bands": ["nir", "red", "green"],
                "description": "Vegetation in red",
            },
            "agriculture": {"bands": ["swir16", "nir", "blue"], "description": "Crop health"},
            "urban": {"bands": ["swir22", "swir16", "red"], "description": "Urban areas"},
        },
        "cloud_mask_band": "scl",
        "llm_guidance": (
            "Sentinel-2 L2A provides surface reflectance at 10-60m resolution. "
            "Use 'red', 'green', 'blue' for RGB. NIR band is 'nir' (10m). "
            "Cloud masking via SCL band. Best for vegetation, water, and land cover analysis."
        ),
    },
    "sentinel-2-c1-l2a": {
        "platform": "Sentinel-2",
        "instrument": "MSI",
        "bands": {
            "coastal": {"wavelength_nm": 443, "resolution_m": 60},
            "blue": {"wavelength_nm": 490, "resolution_m": 10},
            "green": {"wavelength_nm": 560, "resolution_m": 10},
            "red": {"wavelength_nm": 665, "resolution_m": 10},
            "rededge1": {"wavelength_nm": 705, "resolution_m": 20},
            "rededge2": {"wavelength_nm": 740, "resolution_m": 20},
            "rededge3": {"wavelength_nm": 783, "resolution_m": 20},
            "nir": {"wavelength_nm": 842, "resolution_m": 10},
            "nir08": {"wavelength_nm": 865, "resolution_m": 20},
            "nir09": {"wavelength_nm": 945, "resolution_m": 60},
            "swir16": {"wavelength_nm": 1610, "resolution_m": 20},
            "swir22": {"wavelength_nm": 2190, "resolution_m": 20},
        },
        "composites": {
            "true_color": {"bands": ["red", "green", "blue"], "description": "Natural colour RGB"},
            "false_color_ir": {
                "bands": ["nir", "red", "green"],
                "description": "Vegetation in red",
            },
        },
        "cloud_mask_band": "scl",
        "llm_guidance": (
            "Sentinel-2 Collection 1 L2A (harmonized). Same bands as sentinel-2-l2a "
            "but with improved radiometric consistency across the archive."
        ),
    },
    "landsat-c2-l2": {
        "platform": "Landsat 8/9",
        "instrument": "OLI/TIRS",
        "bands": {
            "coastal": {"wavelength_nm": 443, "resolution_m": 30},
            "blue": {"wavelength_nm": 482, "resolution_m": 30},
            "green": {"wavelength_nm": 562, "resolution_m": 30},
            "red": {"wavelength_nm": 655, "resolution_m": 30},
            "nir08": {"wavelength_nm": 865, "resolution_m": 30},
            "swir16": {"wavelength_nm": 1609, "resolution_m": 30},
            "swir22": {"wavelength_nm": 2201, "resolution_m": 30},
            "lwir11": {"wavelength_nm": 10895, "resolution_m": 100},
        },
        "composites": {
            "true_color": {"bands": ["red", "green", "blue"], "description": "Natural colour RGB"},
            "false_color_ir": {
                "bands": ["nir08", "red", "green"],
                "description": "Vegetation in red",
            },
        },
        "cloud_mask_band": "qa_pixel",
        "llm_guidance": (
            "Landsat Collection 2 Level-2 at 30m resolution. NIR band is 'nir08' (not 'nir'). "
            "Includes thermal bands (lwir11, lwir12). Use qa_pixel for cloud masking. "
            "30+ year archive for change detection."
        ),
    },
    "sentinel-1-grd": {
        "platform": "Sentinel-1",
        "instrument": "C-SAR",
        "bands": {
            "vv": {"wavelength_nm": 56000, "resolution_m": 10},
            "vh": {"wavelength_nm": 56000, "resolution_m": 10},
        },
        "composites": {},
        "cloud_mask_band": None,
        "llm_guidance": (
            "Sentinel-1 GRD provides C-band SAR backscatter at 10m resolution. "
            "Polarisations: VV (co-pol) and VH (cross-pol). Not affected by clouds. "
            "Use for flood mapping, ship detection, and structural monitoring. "
            "No cloud masking needed. No spectral indices available."
        ),
    },
    "cop-dem-glo-30": {
        "platform": "TanDEM-X",
        "instrument": "X-SAR",
        "bands": {
            "data": {"wavelength_nm": 0, "resolution_m": 30},
        },
        "composites": {},
        "cloud_mask_band": None,
        "llm_guidance": (
            "Copernicus GLO-30 DEM provides global elevation data at 30m resolution. "
            "Single 'data' band contains elevation values in metres. "
            "Use for terrain analysis, slope, aspect, and hydrological modelling. "
            "No temporal dimension, no cloud cover, no spectral indices."
        ),
    },
}

# ─── Conformance Classes ─────────────────────────────────────────────────────
# Maps feature names to known conformance URI patterns for STAC API parsing.

CONFORMANCE_CLASSES: dict[str, list[str]] = {
    "core": [
        "https://api.stacspec.org/v1.0.0/core",
        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    ],
    "item_search": [
        "https://api.stacspec.org/v1.0.0/item-search",
        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    ],
    "filter": [
        "https://api.stacspec.org/v1.0.0/item-search#filter",
        "http://www.opengis.net/spec/cql2/1.0/conf/cql2-text",
        "http://www.opengis.net/spec/cql2/1.0/conf/cql2-json",
    ],
    "sort": [
        "https://api.stacspec.org/v1.0.0/item-search#sort",
    ],
    "fields": [
        "https://api.stacspec.org/v1.0.0/item-search#fields",
    ],
    "query": [
        "https://api.stacspec.org/v1.0.0/item-search#query",
    ],
    "collections": [
        "https://api.stacspec.org/v1.0.0/collections",
        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    ],
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

# In-memory raster cache limits
RASTER_CACHE_MAX_BYTES: int = 100 * 1024 * 1024  # 100 MB total
RASTER_CACHE_MAX_ITEM: int = 10 * 1024 * 1024  # 10 MB per item


# ─── Type Literals ──────────────────────────────────────────────────────────────


CatalogName = Literal["earth_search", "planetary_computer", "usgs"]
CompositeMethod = Literal["median", "mean", "min", "max", "latest"]
DownloadFormat = Literal["geotiff", "png"]


# ─── STAC Asset / Property Constants ─────────────────────────────────────────


# Asset keys that are metadata, not data bands — skipped in describe_scene
METADATA_ASSET_KEYS = frozenset({"thumbnail", "info", "metadata", "tilejson"})

THUMBNAIL_KEY = "thumbnail"

# Asset keys checked for scene preview/thumbnail URLs (ordered by preference)
PREVIEW_ASSET_KEYS: tuple[str, ...] = ("rendered_preview", "thumbnail")


# ─── MIME Types ──────────────────────────────────────────────────────────────


class MimeType:
    """MIME type constants for artifact storage."""

    GEOTIFF = "image/tiff"
    PNG = "image/png"


# ─── Artifact Types ──────────────────────────────────────────────────────────


class ArtifactType(str, Enum):
    """Type identifiers for artifacts stored in chuk-artifacts."""

    SATELLITE_RASTER = "satellite_raster"


# ─── Artifact Reference Schemes ──────────────────────────────────────────────


PENDING_SCHEME = "pending://"


# ─── Composite Constants ────────────────────────────────────────────────────


RGB_COMPOSITE_TYPE = "rgb"
DEFAULT_COMPOSITE_NAME = "custom"


# ─── Cloud Masking ─────────────────────────────────────────────────────────


# Sentinel-2 Scene Classification Layer (SCL) band name
SCL_BAND_NAME: str = "scl"

# SCL values considered "good" (not cloud/shadow/saturated)
# 4=vegetation, 5=bare_soil, 6=water, 7=cloud_low_prob, 11=snow
SCL_GOOD_VALUES: frozenset[int] = frozenset({4, 5, 6, 7, 11})

# Collections that support SCL-based cloud masking
SCL_COLLECTIONS: frozenset[str] = frozenset(
    {SatelliteCollection.SENTINEL_2_L2A, SatelliteCollection.SENTINEL_2_C1_L2A}
)


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
    INDEX_COMPLETE = "Computed {} index"
