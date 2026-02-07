"""
Pydantic Models for chuk-mcp-stac.

All data structures are Pydantic models for type safety and validation.
"""

from .responses import (
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
    StatusResponse,
    SuccessResponse,
    TimeSeriesEntry,
    TimeSeriesResponse,
)
from .stac import STACAsset, STACItem, STACProperties

__all__ = [
    # STAC data models
    "STACAsset",
    "STACProperties",
    "STACItem",
    # Response models
    "ErrorResponse",
    "SuccessResponse",
    "SceneInfo",
    "SceneAsset",
    "SearchResponse",
    "SceneDetailResponse",
    "BandDownloadResponse",
    "CompositeResponse",
    "MosaicResponse",
    "TimeSeriesEntry",
    "TimeSeriesResponse",
    "CollectionInfo",
    "CollectionsResponse",
    "CatalogInfo",
    "CatalogsResponse",
    "SpectralIndexInfo",
    "CapabilitiesResponse",
    "StatusResponse",
]
