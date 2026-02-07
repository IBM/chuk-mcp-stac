# chuk-mcp-stac Specification

Version 0.1.0

## Overview

chuk-mcp-stac is an MCP (Model Context Protocol) server that provides satellite
imagery discovery and retrieval via STAC (SpatioTemporal Asset Catalog) APIs.

- **20 tools** for searching, downloading, and analysing satellite imagery
- **Dual output mode** — all tools return JSON (default) or human-readable text via `output_mode` parameter
- **Async-first** — tool entry points are async; sync I/O runs in thread pools
- **Pluggable storage** — raster data stored via chuk-artifacts (memory, filesystem, S3)

## Supported Catalogs

| Name | URL | Notes |
|------|-----|-------|
| `earth_search` (default) | `https://earth-search.aws.element84.com/v1` | Element 84 |
| `planetary_computer` | `https://planetarycomputer.microsoft.com/api/stac/v1` | Microsoft (auto-signs assets if `planetary-computer` package installed) |
| `usgs` | `https://landsatlook.usgs.gov/stac-server` | USGS Landsat Look |
| Custom URL | Any `https://...` URL | Passed directly |

The `catalog` parameter on search tools accepts either a short name or a full URL.

## Supported Collections

| Collection ID | Satellite | Notes |
|--------------|-----------|-------|
| `sentinel-2-l2a` (default) | Sentinel-2 | Surface reflectance, 10-60m |
| `sentinel-2-c1-l2a` | Sentinel-2 Collection 1 | Reprocessed archive |
| `landsat-c2-l2` | Landsat 8/9 | Collection 2 Level-2, 30m |
| `sentinel-1-grd` | Sentinel-1 | C-band SAR, 10m, VV/VH polarisation |
| `cop-dem-glo-30` | TanDEM-X | Copernicus DEM, 30m elevation |

## Band Naming

Tools accept **common spectral names** as the primary band vocabulary. Hardware
designations are resolved to common names automatically via `resolve_band_name()`.

### Common Names — Sentinel-2

| Common Name | Asset Key | Wavelength | Resolution |
|-------------|-----------|------------|------------|
| `coastal` | coastal | 443 nm | 60m |
| `blue` | blue | 490 nm | 10m |
| `green` | green | 560 nm | 10m |
| `red` | red | 665 nm | 10m |
| `rededge1` | rededge1 | 705 nm | 20m |
| `rededge2` | rededge2 | 740 nm | 20m |
| `rededge3` | rededge3 | 783 nm | 20m |
| `nir` | nir | 842 nm | 10m |
| `nir08` | nir08 | 865 nm | 20m |
| `nir09` | nir09 | 945 nm | 60m |
| `swir16` | swir16 | 1610 nm | 20m |
| `swir22` | swir22 | 2190 nm | 20m |
| `scl` | scl | — | 20m (classification) |

### Common Names — Landsat Collection 2

| Common Name | Asset Key | Wavelength | Resolution |
|-------------|-----------|------------|------------|
| `coastal` | coastal | 443 nm | 30m |
| `blue` | blue | 482 nm | 30m |
| `green` | green | 562 nm | 30m |
| `red` | red | 655 nm | 30m |
| `nir08` | nir08 | 865 nm | 30m |
| `swir16` | swir16 | 1609 nm | 30m |
| `swir22` | swir22 | 2201 nm | 30m |
| `pan` | pan | 590 nm | 15m |
| `cirrus` | cirrus | 1373 nm | 30m |
| `lwir11` | lwir11 | 10895 nm | 100m |
| `lwir12` | lwir12 | 12005 nm | 100m |
| `qa_pixel` | qa_pixel | — | 30m (QA) |
| `qa_radsat` | qa_radsat | — | 30m (QA) |

**Note:** Landsat NIR is `nir08`, not `nir`. Sentinel-2 has both `nir` (B08, 10m)
and `nir08` (B8A, 20m).

### Hardware Aliases

Users may pass hardware band designations. These are resolved before processing:

| Alias | Resolves To | Satellite |
|-------|-------------|-----------|
| `B01` | `coastal` | Sentinel-2 |
| `B02` | `blue` | Sentinel-2 |
| `B03` | `green` | Sentinel-2 |
| `B04` | `red` | Sentinel-2 |
| `B05` | `rededge1` | Sentinel-2 |
| `B06` | `rededge2` | Sentinel-2 |
| `B07` | `rededge3` | Sentinel-2 |
| `B08` | `nir` | Sentinel-2 |
| `B8A` | `nir08` | Sentinel-2 |
| `B09` | `nir09` | Sentinel-2 |
| `B11` | `swir16` | Sentinel-2 |
| `B12` | `swir22` | Sentinel-2 |
| `SR_B1` | `coastal` | Landsat |
| `SR_B2` | `blue` | Landsat |
| `SR_B3` | `green` | Landsat |
| `SR_B4` | `red` | Landsat |
| `SR_B5` | `nir08` | Landsat |
| `SR_B6` | `swir16` | Landsat |
| `SR_B7` | `swir22` | Landsat |

---

## Tools

### Search Tools

### Common Parameter

All tools accept the following optional parameter:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_mode` | `str` | `json` | Response format: `json` (structured) or `text` (human-readable) |

---

#### `stac_list_catalogs`

List all known STAC catalog endpoints.

**Parameters:** `output_mode` only

**Response:** `CatalogsResponse`

| Field | Type | Description |
|-------|------|-------------|
| `catalogs` | `CatalogInfo[]` | Catalog name/URL pairs |
| `default` | `str` | Default catalog name |
| `message` | `str` | Result message |

---

#### `stac_list_collections`

List available collections in a STAC catalog.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `catalog` | `str?` | `earth_search` | Catalog name or URL |

**Response:** `CollectionsResponse`

| Field | Type | Description |
|-------|------|-------------|
| `catalog` | `str` | Catalog queried |
| `collection_count` | `int` | Number of collections |
| `collections` | `CollectionInfo[]` | Collection details |
| `message` | `str` | Result message |

---

#### `stac_search`

Search for satellite scenes matching spatial and temporal criteria. Results are
cached for follow-up describe/download operations.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bbox` | `float[4]` | *required* | Bounding box `[west, south, east, north]` EPSG:4326 |
| `collection` | `str?` | `sentinel-2-l2a` | STAC collection ID |
| `date_range` | `str?` | `None` | `YYYY-MM-DD/YYYY-MM-DD` |
| `max_cloud_cover` | `int?` | `20` | Maximum cloud cover % (0-100) |
| `max_items` | `int?` | `10` | Maximum results |
| `catalog` | `str?` | `earth_search` | Catalog name or URL |

**Response:** `SearchResponse`

| Field | Type | Description |
|-------|------|-------------|
| `catalog` | `str` | Catalog searched |
| `collection` | `str` | Collection searched |
| `bbox` | `float[]` | Search bounding box |
| `date_range` | `str?` | Date range used |
| `max_cloud_cover` | `int?` | Cloud cover filter |
| `scene_count` | `int` | Number of scenes found |
| `scenes` | `SceneInfo[]` | Matching scenes (sorted by cloud cover ascending) |
| `message` | `str` | Result message |

---

#### `stac_describe_scene`

Get detailed information about a cached scene including all assets/bands.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier from a search result |

**Response:** `SceneDetailResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | `str` | Scene identifier |
| `collection` | `str` | Collection name |
| `datetime` | `str` | Acquisition date/time |
| `bbox` | `float[]` | Scene bounding box |
| `cloud_cover` | `float?` | Cloud cover % |
| `crs` | `str?` | CRS (e.g., `EPSG:32631`) |
| `assets` | `SceneAsset[]` | Data assets (metadata assets filtered out) |
| `properties` | `dict` | Full STAC properties |
| `message` | `str` | Result message |

---

#### `stac_preview`

Get a preview/thumbnail URL for a cached scene.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier from a search result |

**Response:** `PreviewResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | `str` | Scene identifier |
| `preview_url` | `str` | URL to the preview image |
| `asset_key` | `str` | Asset key used (`rendered_preview` preferred over `thumbnail`) |
| `media_type` | `str?` | MIME type |
| `message` | `str` | Result message |

---

### Download Tools

All download tools share two common parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_format` | `str` | `geotiff` | `geotiff` or `png` (2nd-98th percentile stretch) |
| `cloud_mask` | `bool` | `false` | SCL-based cloud masking (Sentinel-2 only) |

#### `stac_download_bands`

Download specific bands from a scene.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier |
| `bands` | `str[]` | *required* | Band names (common names or hardware aliases) |
| `bbox` | `float[4]?` | `None` | Crop bbox in EPSG:4326 |
| `output_format` | `str` | `geotiff` | Output format |
| `cloud_mask` | `bool` | `false` | Cloud masking |

**Response:** `BandDownloadResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | `str` | Source scene |
| `bands` | `str[]` | Bands downloaded |
| `artifact_ref` | `str` | Artifact store reference |
| `preview_ref` | `str?` | PNG preview artifact (auto-generated for GeoTIFF) |
| `bbox` | `float[]` | Data bounding box |
| `crs` | `str` | Output CRS |
| `shape` | `int[]` | Array shape `[bands, height, width]` |
| `dtype` | `str` | Data type |
| `output_format` | `str` | Output format used |
| `message` | `str` | Result message |

---

#### `stac_download_rgb`

Download a true-colour RGB composite (red, green, blue bands).

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier |
| `bbox` | `float[4]?` | `None` | Crop bbox |
| `output_format` | `str` | `geotiff` | Output format |
| `cloud_mask` | `bool` | `false` | Cloud masking |

**Response:** `CompositeResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | `str` | Source scene |
| `composite_type` | `str` | Always `rgb` |
| `bands` | `str[]` | `["red", "green", "blue"]` |
| `artifact_ref` | `str` | Artifact store reference |
| `preview_ref` | `str?` | PNG preview artifact (auto-generated for GeoTIFF) |
| `bbox` | `float[]` | Data bounding box |
| `crs` | `str` | Output CRS |
| `shape` | `int[]` | Array shape |
| `output_format` | `str` | Output format used |
| `message` | `str` | Result message |

---

#### `stac_download_composite`

Download a multi-band composite with any band combination.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier |
| `bands` | `str[]` | *required* | Band names for the composite |
| `composite_name` | `str` | `custom` | Label for the composite type |
| `bbox` | `float[4]?` | `None` | Crop bbox |
| `output_format` | `str` | `geotiff` | Output format |
| `cloud_mask` | `bool` | `false` | Cloud masking |

**Response:** `CompositeResponse` (same as `stac_download_rgb`)

---

#### `stac_mosaic`

Merge bands from multiple scenes into a single raster.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_ids` | `str[]` | *required* | Scene identifiers to mosaic |
| `bands` | `str[]` | *required* | Bands to include |
| `bbox` | `float[4]?` | `None` | Output bbox |
| `method` | `str` | `last` | Merge method: `last` (overlay) or `quality` (SCL-based best pixel) |
| `output_format` | `str` | `geotiff` | Output format |
| `cloud_mask` | `bool` | `false` | Cloud masking per scene before merge |

**Response:** `MosaicResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_ids` | `str[]` | Source scenes |
| `bands` | `str[]` | Bands included |
| `method` | `str` | Merge method used |
| `artifact_ref` | `str` | Artifact store reference |
| `preview_ref` | `str?` | PNG preview artifact (auto-generated for GeoTIFF) |
| `bbox` | `float[]` | Mosaic bounding box |
| `crs` | `str` | Output CRS |
| `shape` | `int[]` | Array shape |
| `output_format` | `str` | Output format used |
| `message` | `str` | Result message |

---

#### `stac_compute_index`

Compute a spectral index for a scene.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier |
| `index_name` | `str` | *required* | Index name (see table below) |
| `bbox` | `float[4]?` | `None` | Crop bbox |
| `cloud_mask` | `bool` | `false` | Cloud masking (masked pixels → NaN) |
| `output_format` | `str` | `geotiff` | Output format |

**Response:** `IndexResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | `str` | Source scene |
| `index_name` | `str` | Index computed |
| `required_bands` | `str[]` | Bands used |
| `value_range` | `float[2]` | `[min, max]` excluding NaN |
| `artifact_ref` | `str` | Artifact store reference |
| `preview_ref` | `str?` | PNG preview artifact (auto-generated for GeoTIFF) |
| `bbox` | `float[]` | Data bounding box |
| `crs` | `str` | Output CRS |
| `shape` | `int[]` | Array shape `[1, height, width]` |
| `output_format` | `str` | Output format used |
| `message` | `str` | Result message |

---

#### `stac_time_series`

Extract a temporal stack of band data over an area. Searches, downloads, and
returns per-date artifact references.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bbox` | `float[4]` | *required* | Area of interest |
| `bands` | `str[]` | *required* | Bands to extract |
| `date_range` | `str` | *required* | `YYYY-MM-DD/YYYY-MM-DD` |
| `collection` | `str?` | `sentinel-2-l2a` | Collection |
| `max_cloud_cover` | `int?` | `20` | Cloud cover filter |
| `max_items` | `int?` | `50` | Maximum scenes |
| `catalog` | `str?` | `earth_search` | Catalog |

**Response:** `TimeSeriesResponse`

| Field | Type | Description |
|-------|------|-------------|
| `bbox` | `float[]` | Area of interest |
| `collection` | `str` | Collection used |
| `bands` | `str[]` | Bands extracted |
| `date_count` | `int` | Number of dates |
| `entries` | `TimeSeriesEntry[]` | Per-date results with artifact refs |
| `message` | `str` | Result message |

---

### Discovery Tools

#### `stac_status`

Get server status and configuration.

**Parameters:** None

**Response:** `StatusResponse`

| Field | Type | Description |
|-------|------|-------------|
| `server` | `str` | Server name |
| `version` | `str` | Server version |
| `storage_provider` | `str` | Active storage backend |
| `default_catalog` | `str` | Default catalog |
| `artifact_store_available` | `bool` | Whether store is ready |

---

#### `stac_capabilities`

List full server capabilities for LLM workflow planning.

**Parameters:** None

**Response:** `CapabilitiesResponse`

| Field | Type | Description |
|-------|------|-------------|
| `server` | `str` | Server name |
| `version` | `str` | Server version |
| `catalogs` | `CatalogInfo[]` | Available catalogs |
| `default_catalog` | `str` | Default catalog |
| `known_collections` | `str[]` | Known collection IDs |
| `spectral_indices` | `SpectralIndexInfo[]` | Available indices with required bands |
| `tool_count` | `int` | Number of registered tools |
| `band_mappings` | `dict` | Band names by platform |

---

## Spectral Indices

| Index | Formula | Required Bands | Value Range |
|-------|---------|----------------|-------------|
| `ndvi` | (NIR - Red) / (NIR + Red) | `red`, `nir` | -1 to 1 |
| `ndwi` | (Green - NIR) / (Green + NIR) | `green`, `nir` | -1 to 1 |
| `ndbi` | (SWIR16 - NIR) / (SWIR16 + NIR) | `swir16`, `nir` | -1 to 1 |
| `evi` | 2.5 * (NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1) | `blue`, `red`, `nir` | ~-1 to 1 |
| `savi` | ((NIR - Red) / (NIR + Red + 0.5)) * 1.5 | `red`, `nir` | ~-1 to 1 |
| `bsi` | ((SWIR16 + Red) - (NIR + Blue)) / ((SWIR16 + Red) + (NIR + Blue)) | `blue`, `red`, `nir`, `swir16` | -1 to 1 |

All indices output single-band float32 GeoTIFFs with NaN as the nodata value.

---

## Output Formats

### GeoTIFF (default)

Multi-band GeoTIFF with embedded CRS and transform metadata. Preserves original
data types (uint16 for reflectance bands, float32 for indices). Suitable for
GIS analysis and further processing.

### PNG

Auto-stretched 8-bit RGB/grayscale PNG for visual inspection. Uses 2nd-98th
percentile stretch to handle outliers. LLMs with vision can render these inline.

**Stretch algorithm:**
1. Compute 2nd and 98th percentile values per band
2. Clip data to percentile range
3. Scale linearly to 0-255 uint8

---

## Cloud Masking

Cloud masking uses the Sentinel-2 Scene Classification Layer (SCL). It is only
available for Sentinel-2 L2A collections (`sentinel-2-l2a`, `sentinel-2-c1-l2a`).

### SCL Good Values

| Value | Class | Included |
|-------|-------|----------|
| 4 | Vegetation | Yes |
| 5 | Bare soil | Yes |
| 6 | Water | Yes |
| 7 | Cloud low probability | Yes |
| 11 | Snow/ice | Yes |
| 0-3, 8-10 | No data / saturated / shadows / clouds | No |

### Behaviour

- **Integer bands** (reflectance): masked pixels set to 0
- **Float bands** (spectral indices): masked pixels set to NaN
- **SCL band** is read with nearest-neighbour resampling to preserve class values
- Requesting `cloud_mask=true` on a scene without SCL raises a `ValueError`

---

## Artifact Storage

Downloaded rasters are stored via chuk-artifacts with enriched metadata:

```json
{
  "type": "satellite_raster",
  "schema_version": "1.0",
  "scene_id": "S2B_MSIL2A_...",
  "bands": ["red", "green", "blue"],
  "bbox": [0.85, 51.85, 0.95, 51.92],
  "crs": "EPSG:32631",
  "shape": [3, 512, 512],
  "dtype": "uint16",
  "collection": "sentinel-2-l2a",
  "datetime": "2024-07-15T10:56:29Z",
  "band_wavelengths": {"red": 665, "green": 560, "blue": 490},
  "sun_elevation": 52.3,
  "sun_azimuth": 145.7,
  "view_off_nadir": 3.1
}
```

Optional fields (`collection`, `datetime`, `band_wavelengths`, `sun_elevation`,
`sun_azimuth`, `view_off_nadir`) are omitted when not available.

### Storage Providers

| Provider | Env Variable | Value |
|----------|-------------|-------|
| Memory (default) | `CHUK_ARTIFACTS_PROVIDER` | `memory` |
| Filesystem | `CHUK_ARTIFACTS_PROVIDER` | `filesystem` |
| Amazon S3 | `CHUK_ARTIFACTS_PROVIDER` | `s3` |

Additional environment variables for S3: `BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`.

---

## Error Handling

All tools return `ErrorResponse` on failure:

```json
{
  "error": "Scene 'nonexistent' not found"
}
```

### Common Error Scenarios

| Scenario | Error Message |
|----------|---------------|
| Invalid bbox length | "Invalid bounding box: must be [west, south, east, north]" |
| Invalid bbox values | "Invalid bounding box values: west (...) must be < east (...)" |
| Scene not cached | "Scene '{id}' not found" |
| Band not in scene | "Band '{name}' not found in scene assets" |
| No artifact store | "No artifact store available. Configure CHUK_ARTIFACTS_PROVIDER..." |
| Unknown catalog | "Unknown catalog '{name}'. Known catalogs: [...]" |
| Unknown index | "Unknown index '{name}'. Available: [ndvi, ndwi, ...]" |
| Cloud mask without SCL | "Cloud masking requires 'scl' band..." |

---

### Introspection Tools

#### `stac_estimate_size`

Estimate download size using COG headers only (no pixel data read).

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scene_id` | `str` | *required* | Scene identifier |
| `bands` | `str[]` | *required* | Band names to estimate |
| `bbox` | `float[4]?` | `None` | Crop bbox in EPSG:4326 |

**Response:** `SizeEstimateResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | `str` | Scene identifier |
| `band_count` | `int` | Number of bands estimated |
| `per_band` | `BandSizeDetail[]` | Per-band width, height, dtype, bytes |
| `total_pixels` | `int` | Total pixels across all bands |
| `estimated_bytes` | `int` | Estimated total bytes |
| `estimated_mb` | `float` | Estimated total megabytes |
| `crs` | `str` | Coordinate reference system |
| `bbox` | `float[]` | Crop bbox if provided |
| `warnings` | `str[]` | Warnings for large downloads (>=500MB, >=1GB) |
| `message` | `str` | Result message |

---

#### `stac_describe_collection`

Get detailed collection metadata with band wavelengths, composites, and LLM guidance.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `collection_id` | `str` | *required* | Collection identifier |
| `catalog` | `str?` | `earth_search` | Catalog name or URL |

**Response:** `CollectionDetailResponse`

| Field | Type | Description |
|-------|------|-------------|
| `collection_id` | `str` | Collection identifier |
| `catalog` | `str` | Catalog queried |
| `title` | `str?` | Human-readable title |
| `description` | `str?` | Collection description |
| `spatial_extent` | `float[]?` | Spatial extent bbox |
| `temporal_extent` | `str[]?` | Temporal extent [start, end] |
| `platform` | `str?` | Satellite platform |
| `instrument` | `str?` | Instrument name |
| `bands` | `BandDetail[]` | Band details with wavelengths and resolutions |
| `composites` | `CompositeRecipe[]` | Named composite recipes |
| `spectral_indices` | `str[]` | Supported spectral index names |
| `cloud_mask_band` | `str?` | Band name for cloud masking |
| `llm_guidance` | `str?` | LLM-friendly usage guidance |
| `message` | `str` | Result message |

---

#### `stac_get_conformance`

Check which STAC API features a catalog supports.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `catalog` | `str?` | `earth_search` | Catalog name or URL |

**Response:** `ConformanceResponse`

| Field | Type | Description |
|-------|------|-------------|
| `catalog` | `str` | Catalog queried |
| `conformance_available` | `bool` | Whether catalog exposes conformance |
| `features` | `ConformanceFeature[]` | Feature support flags |
| `raw_uris` | `str[]` | Raw conformance URIs |
| `message` | `str` | Result message |

---

#### `stac_find_pairs`

Find before/after scene pairs for change detection over a bounding box.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bbox` | `float[4]` | *required* | Bounding box `[west, south, east, north]` |
| `before_range` | `str` | *required* | Before date range `YYYY-MM-DD/YYYY-MM-DD` |
| `after_range` | `str` | *required* | After date range `YYYY-MM-DD/YYYY-MM-DD` |
| `collection` | `str?` | `sentinel-2-l2a` | Collection ID |
| `max_cloud_cover` | `int?` | `20` | Max cloud cover % |
| `catalog` | `str?` | `earth_search` | Catalog name or URL |

**Response:** `FindPairsResponse`

| Field | Type | Description |
|-------|------|-------------|
| `bbox` | `float[]` | Search bounding box |
| `collection` | `str` | Collection used |
| `before_range` | `str` | Before date range |
| `after_range` | `str` | After date range |
| `pair_count` | `int` | Number of pairs found |
| `pairs` | `ScenePair[]` | Matching pairs sorted by overlap % descending |
| `message` | `str` | Result message |

---

#### `stac_coverage_check`

Check if cached scenes fully cover a target bounding box.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bbox` | `float[4]` | *required* | Target bounding box |
| `scene_ids` | `str[]` | *required* | Scene identifiers to check |

**Response:** `CoverageCheckResponse`

| Field | Type | Description |
|-------|------|-------------|
| `bbox` | `float[]` | Target bounding box |
| `scene_count` | `int` | Number of scenes checked |
| `fully_covered` | `bool` | Whether bbox is fully covered |
| `coverage_percent` | `float` | Percentage of bbox covered |
| `uncovered_areas` | `float[][]` | Uncovered sub-bbox areas |
| `scene_ids` | `str[]` | Scenes checked |
| `message` | `str` | Result message |

---

#### `stac_queryables`

Fetch queryable properties from a STAC API for advanced filtering.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `catalog` | `str?` | `earth_search` | Catalog name or URL |
| `collection` | `str?` | `None` | Collection to scope queryables |

**Response:** `QueryablesResponse`

| Field | Type | Description |
|-------|------|-------------|
| `catalog` | `str` | Catalog queried |
| `collection` | `str?` | Collection scoped (if any) |
| `queryable_count` | `int` | Number of queryable properties |
| `queryables` | `QueryableProperty[]` | Available queryable properties |
| `message` | `str` | Result message |

---

#### `stac_temporal_composite`

Combine multiple scenes into a single raster via per-pixel statistical method.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bbox` | `float[4]` | *required* | Area of interest |
| `bands` | `str[]` | *required* | Bands to composite |
| `date_range` | `str` | *required* | `YYYY-MM-DD/YYYY-MM-DD` |
| `method` | `str` | `median` | Statistical method: `median`, `mean`, `max`, `min` |
| `collection` | `str?` | `sentinel-2-l2a` | Collection |
| `max_cloud_cover` | `int?` | `20` | Cloud cover filter |
| `max_items` | `int?` | `10` | Maximum scenes |
| `catalog` | `str?` | `earth_search` | Catalog |
| `cloud_mask` | `bool` | `false` | SCL cloud masking per scene |
| `output_format` | `str` | `geotiff` | Output format |

**Response:** `TemporalCompositeResponse`

| Field | Type | Description |
|-------|------|-------------|
| `scene_ids` | `str[]` | Source scenes used |
| `bands` | `str[]` | Bands composited |
| `method` | `str` | Statistical method used |
| `artifact_ref` | `str` | Artifact store reference |
| `preview_ref` | `str?` | PNG preview artifact |
| `bbox` | `float[]` | Output bounding box |
| `crs` | `str` | Output CRS |
| `shape` | `int[]` | Array shape |
| `date_range` | `str` | Date range covered |
| `message` | `str` | Result message |

---

## Auto-Preview

All download tools (`stac_download_bands`, `stac_download_rgb`, `stac_download_composite`,
`stac_mosaic`, `stac_compute_index`, `stac_time_series`) automatically generate a PNG
preview alongside every GeoTIFF download. The preview reference is returned in the
`preview_ref` field (null for PNG output format since the main artifact is the preview).

Preview generation is non-fatal — if it fails, `preview_ref` is null and the download
still succeeds.

---

## Performance

### In-Memory Raster Cache

CatalogManager maintains an LRU cache for recently downloaded raster data
(100 MB total, 10 MB per item). Repeated `download_bands` calls with the same
scene/bands/bbox parameters skip the COG read and serve cached bytes.

### Progress Callbacks

CatalogManager accepts an optional `progress_callback(stage, current, total)`
for tracking long-running operations. Stages: `reading_bands`, `reading_scene`,
`merging`, `compositing`.

---

## Roadmap

### Note on Geocoding

Geocoding (place name → bbox) is planned as a **separate MCP server**, not part
of chuk-mcp-stac. This server accepts only coordinate-based bounding boxes.
