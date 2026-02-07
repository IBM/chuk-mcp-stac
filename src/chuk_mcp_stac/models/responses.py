"""
Response Models for chuk-mcp-stac tools.

All tool responses are Pydantic models for type safety and consistent API.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """Error response model for tool failures."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(..., description="Error message describing what went wrong")


class SuccessResponse(BaseModel):
    """Generic success response for simple operations."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., description="Success message")


class SceneAsset(BaseModel):
    """A single asset (band) within a STAC scene."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., description="Asset key in the STAC item")
    href: str = Field(..., description="URL to the asset (COG)")
    media_type: str | None = Field(None, description="MIME type of the asset")
    resolution_m: float | None = Field(None, description="Ground sample distance in meters")


class SceneInfo(BaseModel):
    """Summary of a STAC scene (item) from a search result."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Unique scene/item identifier")
    collection: str = Field(..., description="STAC collection name")
    datetime: str = Field(..., description="Acquisition date/time ISO 8601")
    bbox: list[float] = Field(..., description="Scene bounding box [west, south, east, north]")
    cloud_cover: float | None = Field(None, description="Cloud cover percentage", ge=0, le=100)
    thumbnail_url: str | None = Field(None, description="Thumbnail preview URL")
    asset_count: int = Field(..., description="Number of available assets/bands", ge=0)


class SearchResponse(BaseModel):
    """Response model for STAC scene search."""

    model_config = ConfigDict(extra="forbid")

    catalog: str = Field(..., description="STAC catalog searched")
    collection: str = Field(..., description="Collection searched")
    bbox: list[float] = Field(..., description="Search bounding box")
    date_range: str | None = Field(None, description="Date range searched")
    max_cloud_cover: int | None = Field(None, description="Cloud cover filter")
    scene_count: int = Field(..., description="Number of scenes found", ge=0)
    scenes: list[SceneInfo] = Field(..., description="Matching scenes")
    message: str = Field(..., description="Operation result message")


class SceneDetailResponse(BaseModel):
    """Response model for detailed scene description."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Scene identifier")
    collection: str = Field(..., description="Collection name")
    datetime: str = Field(..., description="Acquisition date/time")
    bbox: list[float] = Field(..., description="Scene bounding box")
    cloud_cover: float | None = Field(None, description="Cloud cover percentage")
    crs: str | None = Field(None, description="Coordinate reference system")
    assets: list[SceneAsset] = Field(..., description="Available assets/bands")
    properties: dict[str, Any] = Field(default_factory=dict, description="Full STAC properties")
    message: str = Field(..., description="Operation result message")


class BandDownloadResponse(BaseModel):
    """Response model for band download."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Source scene identifier")
    bands: list[str] = Field(..., description="Band names downloaded")
    artifact_ref: str = Field(..., description="Artifact store reference for the downloaded data")
    bbox: list[float] = Field(..., description="Data bounding box")
    crs: str = Field(..., description="CRS of the downloaded data")
    shape: list[int] = Field(..., description="Array shape [bands, height, width]")
    dtype: str = Field(..., description="Data type of the array")
    message: str = Field(..., description="Operation result message")


class CompositeResponse(BaseModel):
    """Response model for RGB/composite creation."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Source scene identifier")
    composite_type: str = Field(..., description="Composite type (rgb, false_color, etc.)")
    bands: list[str] = Field(..., description="Bands used in composite")
    artifact_ref: str = Field(..., description="Artifact store reference")
    bbox: list[float] = Field(..., description="Data bounding box")
    crs: str = Field(..., description="CRS of the composite")
    shape: list[int] = Field(..., description="Array shape [bands, height, width]")
    message: str = Field(..., description="Operation result message")


class MosaicResponse(BaseModel):
    """Response model for scene mosaic."""

    model_config = ConfigDict(extra="forbid")

    scene_ids: list[str] = Field(..., description="Source scene identifiers")
    bands: list[str] = Field(..., description="Bands included in mosaic")
    artifact_ref: str = Field(..., description="Artifact store reference")
    bbox: list[float] = Field(..., description="Mosaic bounding box")
    crs: str = Field(..., description="CRS of the mosaic")
    shape: list[int] = Field(..., description="Array shape [bands, height, width]")
    message: str = Field(..., description="Operation result message")


class TimeSeriesEntry(BaseModel):
    """A single time series data point."""

    model_config = ConfigDict(extra="forbid")

    datetime: str = Field(..., description="Acquisition date/time")
    scene_id: str = Field(..., description="Scene identifier")
    artifact_ref: str = Field(..., description="Artifact store reference for this date")
    cloud_cover: float | None = Field(None, description="Cloud cover percentage")


class TimeSeriesResponse(BaseModel):
    """Response model for time series extraction."""

    model_config = ConfigDict(extra="forbid")

    bbox: list[float] = Field(..., description="Area of interest bounding box")
    collection: str = Field(..., description="Collection used")
    bands: list[str] = Field(..., description="Bands extracted")
    date_count: int = Field(..., description="Number of dates in series", ge=0)
    entries: list[TimeSeriesEntry] = Field(..., description="Time series entries")
    message: str = Field(..., description="Operation result message")


class CollectionInfo(BaseModel):
    """Information about a STAC collection."""

    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(..., description="Collection identifier")
    title: str | None = Field(None, description="Human-readable title")
    description: str | None = Field(None, description="Collection description")
    spatial_extent: list[float] | None = Field(None, description="Spatial extent bbox")
    temporal_extent: list[str | None] | None = Field(
        None, description="Temporal extent [start, end]"
    )


class CollectionsResponse(BaseModel):
    """Response model for listing collections."""

    model_config = ConfigDict(extra="forbid")

    catalog: str = Field(..., description="STAC catalog queried")
    collection_count: int = Field(..., description="Number of collections", ge=0)
    collections: list[CollectionInfo] = Field(..., description="Available collections")
    message: str = Field(..., description="Operation result message")


class CatalogInfo(BaseModel):
    """Information about a known STAC catalog."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Catalog short name")
    url: str = Field(..., description="Catalog API endpoint URL")


class CatalogsResponse(BaseModel):
    """Response model for listing known catalogs."""

    model_config = ConfigDict(extra="forbid")

    catalogs: list[CatalogInfo] = Field(..., description="Known STAC catalogs")
    default: str = Field(..., description="Default catalog name")
    message: str = Field(..., description="Operation result message")


class SpectralIndexInfo(BaseModel):
    """Band requirements for a spectral index."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Index name (e.g., ndvi)")
    required_bands: list[str] = Field(..., description="Bands needed to compute this index")


class CapabilitiesResponse(BaseModel):
    """Response model for server capabilities listing."""

    model_config = ConfigDict(extra="forbid")

    server: str = Field(..., description="Server name")
    version: str = Field(..., description="Server version")
    catalogs: list[CatalogInfo] = Field(..., description="Known STAC catalogs")
    default_catalog: str = Field(..., description="Default catalog name")
    known_collections: list[str] = Field(..., description="Known satellite collections")
    spectral_indices: list[SpectralIndexInfo] = Field(
        ..., description="Spectral indices with required bands"
    )
    tool_count: int = Field(..., description="Number of available tools", ge=0)
    band_mappings: dict[str, list[str]] = Field(
        default_factory=dict, description="Band names by satellite platform"
    )


class StatusResponse(BaseModel):
    """Response model for server status queries."""

    model_config = ConfigDict(extra="forbid")

    server: str = Field(default="chuk-mcp-stac", description="Server name")
    version: str = Field(default="0.1.0", description="Server version")
    storage_provider: str = Field(..., description="Active storage provider (memory/filesystem/s3)")
    default_catalog: str = Field(..., description="Default STAC catalog")
    artifact_store_available: bool = Field(
        default=False, description="Whether artifact store is available"
    )
