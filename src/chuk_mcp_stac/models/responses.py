"""
Response Models for chuk-mcp-stac tools.

All tool responses are Pydantic models for type safety and consistent API.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def format_response(model: BaseModel, output_mode: str = "json") -> str:
    """Format a response model as JSON or human-readable text.

    Args:
        model: Pydantic response model instance
        output_mode: "json" (default) or "text"

    Returns:
        Formatted string
    """
    if output_mode == "text" and hasattr(model, "to_text"):
        return model.to_text()
    return model.model_dump_json()


class ErrorResponse(BaseModel):
    """Error response model for tool failures."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(..., description="Error message describing what went wrong")

    def to_text(self) -> str:
        return f"Error: {self.error}"


class SuccessResponse(BaseModel):
    """Generic success response for simple operations."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., description="Success message")

    def to_text(self) -> str:
        return self.message


class SceneAsset(BaseModel):
    """A single asset (band) within a STAC scene."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., description="Asset key in the STAC item (e.g., red, nir, vv)")
    href: str = Field(..., description="URL to the asset (Cloud-Optimised GeoTIFF)")
    media_type: str | None = Field(None, description="MIME type of the asset (usually image/tiff)")
    resolution_m: float | None = Field(
        None,
        description="Ground sample distance in metres. "
        "Sentinel-2: 10m (RGB/NIR), 20m (SWIR/RedEdge), 60m (atmospheric). "
        "Landsat: 30m. Sentinel-1: 10m",
    )


class SceneInfo(BaseModel):
    """Summary of a STAC scene (item) from a search result."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Unique scene/item identifier")
    collection: str = Field(..., description="STAC collection name")
    datetime: str = Field(..., description="Acquisition date/time ISO 8601")
    bbox: list[float] = Field(..., description="Scene bounding box [west, south, east, north]")
    cloud_cover: float | None = Field(
        None,
        description="Cloud cover percentage (0-100). "
        "<5%=clear, 5-20%=mostly clear, 20-50%=partly cloudy, >50%=cloudy. "
        "None for non-optical collections (sentinel-1-grd, cop-dem-glo-30)",
        ge=0,
        le=100,
    )
    thumbnail_url: str | None = Field(None, description="Thumbnail preview URL if available")
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
    hints: list[str] = Field(
        default_factory=list,
        description="Actionable hints when results are empty or limited",
    )
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        lines = [f"Found {self.scene_count} scene(s) in {self.collection} ({self.catalog})"]
        for s in self.scenes:
            cloud = f" ({s.cloud_cover:.1f}% cloud)" if s.cloud_cover is not None else ""
            lines.append(f"  - {s.scene_id} [{s.datetime}]{cloud}")
        for hint in self.hints:
            lines.append(f"Hint: {hint}")
        return "\n".join(lines)


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

    def to_text(self) -> str:
        lines = [
            f"Scene {self.scene_id}",
            f"Collection: {self.collection}",
            f"Datetime: {self.datetime}",
        ]
        if self.cloud_cover is not None:
            lines.append(f"Cloud cover: {self.cloud_cover:.1f}%")
        if self.crs:
            lines.append(f"CRS: {self.crs}")
        lines.append(f"Assets ({len(self.assets)}):")
        for a in self.assets:
            res = f" ({a.resolution_m}m)" if a.resolution_m else ""
            lines.append(f"  - {a.key}{res}")
        return "\n".join(lines)


class PreviewResponse(BaseModel):
    """Response model for scene preview/thumbnail."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Scene identifier")
    preview_url: str = Field(..., description="URL to the preview/thumbnail image")
    asset_key: str = Field(
        ..., description="STAC asset key used (e.g., thumbnail, rendered_preview)"
    )
    media_type: str | None = Field(None, description="MIME type of the preview image")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        return f"Preview for {self.scene_id}\nURL: {self.preview_url}\nAsset: {self.asset_key}"


class BandDownloadResponse(BaseModel):
    """Response model for band download."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Source scene identifier")
    bands: list[str] = Field(..., description="Band names downloaded (e.g., ['red', 'nir'])")
    artifact_ref: str = Field(
        ...,
        description="Artifact store reference for the downloaded data. "
        "Use this to retrieve the raster from the artifact store",
    )
    preview_ref: str | None = Field(
        None,
        description="Auto-generated 8-bit PNG preview with 2nd-98th percentile stretch. "
        "Created automatically when output_format is geotiff",
    )
    bbox: list[float] = Field(
        ..., description="Data bounding box [west, south, east, north] in EPSG:4326"
    )
    crs: str = Field(..., description="CRS of the downloaded data (e.g., EPSG:32631)")
    shape: list[int] = Field(..., description="Array shape [bands, height, width] in pixels")
    dtype: str = Field(
        ...,
        description="Data type of the array. "
        "uint16 = 16-bit unsigned (surface reflectance), float32 = 32-bit float (indices)",
    )
    output_format: str = Field(default="geotiff", description="Output format: geotiff or png")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        shape_str = "x".join(str(s) for s in self.shape)
        lines = [
            f"Downloaded {len(self.bands)} band(s) for {self.scene_id}",
            f"Artifact: {self.artifact_ref}",
            f"Shape: {shape_str} ({self.crs})",
        ]
        if self.preview_ref:
            lines.append(f"Preview: {self.preview_ref}")
        return "\n".join(lines)


class CompositeResponse(BaseModel):
    """Response model for RGB/composite creation."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Source scene identifier")
    composite_type: str = Field(..., description="Composite type (e.g., rgb, false_color_ir)")
    bands: list[str] = Field(
        ..., description="Bands used in composite (order determines RGB mapping)"
    )
    artifact_ref: str = Field(..., description="Artifact store reference for the composite raster")
    preview_ref: str | None = Field(
        None,
        description="Auto-generated 8-bit PNG preview with 2nd-98th percentile stretch",
    )
    bbox: list[float] = Field(..., description="Data bounding box")
    crs: str = Field(..., description="CRS of the composite")
    shape: list[int] = Field(..., description="Array shape [bands, height, width]")
    output_format: str = Field(default="geotiff", description="Output format: geotiff or png")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        shape_str = "x".join(str(s) for s in self.shape)
        lines = [
            f"{self.composite_type} composite for {self.scene_id}",
            f"Bands: {', '.join(self.bands)}",
            f"Artifact: {self.artifact_ref}",
            f"Shape: {shape_str} ({self.crs})",
        ]
        if self.preview_ref:
            lines.append(f"Preview: {self.preview_ref}")
        return "\n".join(lines)


class MosaicResponse(BaseModel):
    """Response model for scene mosaic."""

    model_config = ConfigDict(extra="forbid")

    scene_ids: list[str] = Field(..., description="Source scene identifiers used in mosaic")
    bands: list[str] = Field(..., description="Bands included in mosaic")
    artifact_ref: str = Field(..., description="Artifact store reference for the mosaic raster")
    preview_ref: str | None = Field(
        None, description="Auto-generated 8-bit PNG preview with 2nd-98th percentile stretch"
    )
    bbox: list[float] = Field(..., description="Mosaic bounding box [west, south, east, north]")
    crs: str = Field(..., description="CRS of the mosaic (e.g., EPSG:32631)")
    shape: list[int] = Field(..., description="Array shape [bands, height, width] in pixels")
    output_format: str = Field(default="geotiff", description="Output format: geotiff or png")
    method: str = Field(
        default="last",
        description="Merge method used. "
        "'last' = later scenes overwrite earlier gaps; "
        "'quality' = SCL-based best-pixel selection (Sentinel-2 only)",
    )
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        shape_str = "x".join(str(s) for s in self.shape)
        lines = [
            f"Mosaic of {len(self.scene_ids)} scene(s) (method: {self.method})",
            f"Bands: {', '.join(self.bands)}",
            f"Artifact: {self.artifact_ref}",
            f"Shape: {shape_str} ({self.crs})",
        ]
        if self.preview_ref:
            lines.append(f"Preview: {self.preview_ref}")
        return "\n".join(lines)


class IndexResponse(BaseModel):
    """Response model for spectral index computation."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Source scene identifier")
    index_name: str = Field(..., description="Spectral index name (e.g., ndvi, ndwi, ndbi)")
    required_bands: list[str] = Field(
        ..., description="Bands used for computation (e.g., ['red', 'nir'])"
    )
    value_range: list[float] = Field(
        ...,
        description="[min, max] of computed index values (excluding NaN). "
        "Typical: NDVI -1 to 1 (>0.6=dense vegetation, 0.2-0.6=moderate, <0.2=bare/water). "
        "NDWI -1 to 1 (>0=water, <0=land). "
        "NDBI -1 to 1 (>0=built-up, <0=natural)",
    )
    artifact_ref: str = Field(
        ..., description="Artifact store reference for the single-band float32 index raster"
    )
    preview_ref: str | None = Field(
        None, description="Auto-generated 8-bit PNG preview with 2nd-98th percentile stretch"
    )
    bbox: list[float] = Field(..., description="Data bounding box")
    crs: str = Field(..., description="CRS of the output raster")
    shape: list[int] = Field(..., description="Array shape [1, height, width]")
    output_format: str = Field(default="geotiff", description="Output format: geotiff or png")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        shape_str = "x".join(str(s) for s in self.shape)
        lines = [
            f"Computed {self.index_name.upper()} for {self.scene_id}",
            f"Range: [{self.value_range[0]:.4f}, {self.value_range[1]:.4f}]",
            f"Artifact: {self.artifact_ref}",
            f"Shape: {shape_str} ({self.crs})",
        ]
        if self.preview_ref:
            lines.append(f"Preview: {self.preview_ref}")
        return "\n".join(lines)


class TimeSeriesEntry(BaseModel):
    """A single time series data point."""

    model_config = ConfigDict(extra="forbid")

    datetime: str = Field(..., description="Acquisition date/time")
    scene_id: str = Field(..., description="Scene identifier")
    artifact_ref: str = Field(..., description="Artifact store reference for this date")
    preview_ref: str | None = Field(
        None, description="PNG preview artifact (auto-generated for GeoTIFF)"
    )
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

    def to_text(self) -> str:
        lines = [
            f"Time series: {self.date_count} date(s) from {self.collection}",
            f"Bands: {', '.join(self.bands)}",
        ]
        for e in self.entries:
            cloud = f" ({e.cloud_cover:.1f}% cloud)" if e.cloud_cover is not None else ""
            lines.append(f"  - {e.datetime} {e.scene_id}{cloud}")
        return "\n".join(lines)


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

    def to_text(self) -> str:
        lines = [f"{self.collection_count} collection(s) in {self.catalog}"]
        for c in self.collections:
            title = f": {c.title}" if c.title else ""
            lines.append(f"  - {c.collection_id}{title}")
        return "\n".join(lines)


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

    def to_text(self) -> str:
        lines = [f"{len(self.catalogs)} catalog(s) available (default: {self.default})"]
        for c in self.catalogs:
            lines.append(f"  - {c.name}: {c.url}")
        return "\n".join(lines)


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

    def to_text(self) -> str:
        lines = [
            f"{self.server} v{self.version}",
            f"Tools: {self.tool_count}",
            f"Catalogs: {', '.join(c.name for c in self.catalogs)}",
            f"Collections: {', '.join(self.known_collections)}",
            f"Indices: {', '.join(i.name for i in self.spectral_indices)}",
        ]
        return "\n".join(lines)


class BandSizeDetail(BaseModel):
    """Size estimate for a single band."""

    model_config = ConfigDict(extra="forbid")

    band: str = Field(..., description="Band name (e.g., red, nir)")
    width: int = Field(..., description="Pixel width of the band")
    height: int = Field(..., description="Pixel height of the band")
    dtype: str = Field(
        ...,
        description="Data type. uint16 = 16-bit unsigned (reflectance), "
        "float32 = 32-bit float (indices, DEM elevation)",
    )
    bytes: int = Field(..., description="Estimated size in bytes (uncompressed)")


class SizeEstimateResponse(BaseModel):
    """Response model for download size estimation."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., description="Scene identifier")
    band_count: int = Field(..., description="Number of bands estimated")
    per_band: list[BandSizeDetail] = Field(..., description="Per-band size details")
    total_pixels: int = Field(..., description="Total pixels across all bands")
    estimated_bytes: int = Field(..., description="Estimated total bytes")
    estimated_mb: float = Field(
        ...,
        description="Estimated total megabytes. "
        ">500 MB is large — consider using a smaller bbox. "
        ">1000 MB is very large",
    )
    crs: str = Field(..., description="Coordinate reference system")
    bbox: list[float] = Field(default_factory=list, description="Crop bbox if provided")
    warnings: list[str] = Field(default_factory=list, description="Warnings for large downloads")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        lines = [f"Estimated {self.estimated_mb:.1f} MB for {self.band_count} band(s)"]
        for b in self.per_band:
            lines.append(f"  - {b.band}: {b.width}x{b.height} {b.dtype}")
        for w in self.warnings:
            lines.append(f"WARNING: {w}")
        return "\n".join(lines)


class BandDetail(BaseModel):
    """Band wavelength and resolution detail for collection intelligence."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Band common name")
    wavelength_nm: int = Field(..., description="Central wavelength in nanometers")
    resolution_m: int = Field(..., description="Ground sample distance in meters")


class CompositeRecipe(BaseModel):
    """Named band combination recipe."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Composite name (e.g., true_color)")
    bands: list[str] = Field(..., description="Band names for the composite")
    description: str = Field(..., description="What this composite shows")


class CollectionDetailResponse(BaseModel):
    """Response model for detailed collection description."""

    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(..., description="Collection identifier")
    catalog: str = Field(..., description="STAC catalog queried")
    title: str | None = Field(None, description="Human-readable title")
    description: str | None = Field(None, description="Collection description")
    spatial_extent: list[float] | None = Field(None, description="Spatial extent bbox")
    temporal_extent: list[str | None] | None = Field(
        None, description="Temporal extent [start, end]"
    )
    platform: str | None = Field(None, description="Satellite platform")
    instrument: str | None = Field(None, description="Instrument name")
    bands: list[BandDetail] = Field(
        default_factory=list, description="Band details with wavelengths"
    )
    composites: list[CompositeRecipe] = Field(
        default_factory=list, description="Named composite recipes"
    )
    spectral_indices: list[str] = Field(
        default_factory=list, description="Supported spectral indices"
    )
    cloud_mask_band: str | None = Field(None, description="Band name for cloud masking")
    llm_guidance: str | None = Field(None, description="LLM-friendly usage guidance")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        lines = [f"Collection '{self.collection_id}' ({self.catalog})"]
        if self.title:
            lines.append(f"Title: {self.title}")
        if self.platform:
            lines.append(f"Platform: {self.platform}")
        if self.bands:
            lines.append(f"Bands ({len(self.bands)}):")
            for b in self.bands:
                lines.append(f"  - {b.name}: {b.wavelength_nm}nm, {b.resolution_m}m")
        if self.composites:
            lines.append("Composites:")
            for c in self.composites:
                lines.append(f"  - {c.name}: {', '.join(c.bands)}")
        if self.spectral_indices:
            lines.append(f"Indices: {', '.join(self.spectral_indices)}")
        if self.llm_guidance:
            lines.append(f"Guidance: {self.llm_guidance}")
        return "\n".join(lines)


class ConformanceFeature(BaseModel):
    """A STAC API conformance feature with support status."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Feature name (e.g., core, item_search)")
    supported: bool = Field(..., description="Whether this feature is supported")
    matching_uris: list[str] = Field(default_factory=list, description="Matching conformance URIs")


class ConformanceResponse(BaseModel):
    """Response model for STAC API conformance checking."""

    model_config = ConfigDict(extra="forbid")

    catalog: str = Field(..., description="STAC catalog queried")
    conformance_available: bool = Field(..., description="Whether the catalog exposes conformance")
    features: list[ConformanceFeature] = Field(
        default_factory=list, description="Feature support flags"
    )
    raw_uris: list[str] = Field(default_factory=list, description="Raw conformance URIs")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        if not self.conformance_available:
            return f"Catalog '{self.catalog}' does not expose conformance information"
        supported = [f.name for f in self.features if f.supported]
        unsupported = [f.name for f in self.features if not f.supported]
        lines = [f"Conformance for {self.catalog}: {len(supported)}/{len(self.features)} features"]
        if supported:
            lines.append(f"Supported: {', '.join(supported)}")
        if unsupported:
            lines.append(f"Not supported: {', '.join(unsupported)}")
        return "\n".join(lines)


class TemporalCompositeResponse(BaseModel):
    """Response model for temporal composite."""

    model_config = ConfigDict(extra="forbid")

    scene_ids: list[str] = Field(..., description="Source scene identifiers combined")
    bands: list[str] = Field(..., description="Bands composited")
    method: str = Field(
        ...,
        description="Compositing method used. "
        "'median' = robust cloud-free composite (recommended); "
        "'mean' = average of all scenes; "
        "'max'/'min' = extreme values (useful for peak NDVI or minimum temperature)",
    )
    artifact_ref: str = Field(..., description="Artifact store reference for the composite raster")
    preview_ref: str | None = Field(
        None, description="Auto-generated 8-bit PNG preview with 2nd-98th percentile stretch"
    )
    bbox: list[float] = Field(..., description="Composite bounding box")
    crs: str = Field(..., description="CRS of the composite")
    shape: list[int] = Field(..., description="Array shape [bands, height, width]")
    date_range: str = Field(..., description="Date range of composited scenes")
    output_format: str = Field(default="geotiff", description="Output format: geotiff or png")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        shape_str = "x".join(str(s) for s in self.shape)
        lines = [
            f"Temporal {self.method} composite of {len(self.scene_ids)} scene(s)",
            f"Bands: {', '.join(self.bands)}",
            f"Date range: {self.date_range}",
            f"Artifact: {self.artifact_ref}",
            f"Shape: {shape_str} ({self.crs})",
        ]
        if self.preview_ref:
            lines.append(f"Preview: {self.preview_ref}")
        return "\n".join(lines)


class ScenePair(BaseModel):
    """A before/after scene pair for change detection."""

    model_config = ConfigDict(extra="forbid")

    before_scene_id: str = Field(..., description="Before scene identifier")
    before_datetime: str = Field(..., description="Before acquisition datetime")
    after_scene_id: str = Field(..., description="After scene identifier")
    after_datetime: str = Field(..., description="After acquisition datetime")
    overlap_percent: float = Field(..., description="Bbox overlap percentage", ge=0, le=100)


class FindPairsResponse(BaseModel):
    """Response model for finding before/after scene pairs."""

    model_config = ConfigDict(extra="forbid")

    bbox: list[float] = Field(..., description="Search bounding box")
    collection: str = Field(..., description="Collection searched")
    before_range: str = Field(..., description="Before date range")
    after_range: str = Field(..., description="After date range")
    pair_count: int = Field(..., description="Number of pairs found", ge=0)
    pairs: list[ScenePair] = Field(..., description="Scene pairs sorted by overlap")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        lines = [f"Found {self.pair_count} scene pair(s) for change detection"]
        for p in self.pairs:
            lines.append(
                f"  - {p.before_scene_id} -> {p.after_scene_id} ({p.overlap_percent:.1f}% overlap)"
            )
        return "\n".join(lines)


class CoverageCheckResponse(BaseModel):
    """Response model for coverage checking."""

    model_config = ConfigDict(extra="forbid")

    bbox: list[float] = Field(..., description="Target bounding box")
    scene_count: int = Field(..., description="Number of scenes checked", ge=0)
    fully_covered: bool = Field(..., description="Whether the bbox is fully covered")
    coverage_percent: float = Field(..., description="Coverage percentage", ge=0, le=100)
    uncovered_areas: list[list[float]] = Field(
        default_factory=list, description="Uncovered sub-regions as bboxes"
    )
    scene_ids: list[str] = Field(..., description="Scene IDs checked")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        status = "fully covered" if self.fully_covered else f"{self.coverage_percent:.1f}% covered"
        lines = [
            f"Coverage check: {status}",
            f"Scenes: {', '.join(self.scene_ids)}",
        ]
        if self.uncovered_areas:
            lines.append(f"Uncovered areas: {len(self.uncovered_areas)}")
        return "\n".join(lines)


class QueryableProperty(BaseModel):
    """A single queryable property from a STAC API."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Property name")
    type: str = Field(..., description="JSON Schema type")
    description: str = Field(default="", description="Property description")
    enum_values: list[str] = Field(default_factory=list, description="Allowed values if enum")


class QueryablesResponse(BaseModel):
    """Response model for queryable properties."""

    model_config = ConfigDict(extra="forbid")

    catalog: str = Field(..., description="STAC catalog queried")
    collection: str | None = Field(None, description="Collection if scoped")
    queryable_count: int = Field(..., description="Number of queryable properties", ge=0)
    queryables: list[QueryableProperty] = Field(..., description="Queryable properties")
    message: str = Field(..., description="Operation result message")

    def to_text(self) -> str:
        scope = f" ({self.collection})" if self.collection else ""
        lines = [f"{self.queryable_count} queryable propert(ies) in {self.catalog}{scope}"]
        for q in self.queryables:
            desc = f" - {q.description}" if q.description else ""
            lines.append(f"  - {q.name} ({q.type}){desc}")
        return "\n".join(lines)


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

    def to_text(self) -> str:
        store_status = "available" if self.artifact_store_available else "not available"
        return (
            f"{self.server} v{self.version}\n"
            f"Storage: {self.storage_provider}\n"
            f"Default catalog: {self.default_catalog}\n"
            f"Artifact store: {store_status}"
        )


class ArtifactResponse(BaseModel):
    """Response for artifact retrieval with file path and metadata."""

    model_config = ConfigDict(extra="forbid")

    artifact_ref: str = Field(..., description="Artifact identifier")
    file_path: str = Field(..., description="Local file path where artifact was saved")
    mime: str = Field(..., description="MIME type (image/png or image/tiff)")
    size_bytes: int = Field(..., description="File size in bytes")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Artifact metadata")
    message: str = Field(default="", description="Human-readable status message")

    def to_text(self) -> str:
        mb = self.size_bytes / (1024 * 1024)
        return (
            f"Artifact: {self.artifact_ref}\n"
            f"Saved to: {self.file_path}\n"
            f"Type: {self.mime} ({mb:.2f} MB)\n"
            f"{self.message}"
        )
