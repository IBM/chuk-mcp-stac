# Architecture

This document describes the design principles, module structure, and key patterns
used in chuk-mcp-stac.

## Design Principles

### 1. Async-First

All tool entry points are `async`. Synchronous I/O (rasterio COG reads, GDAL HTTP)
is wrapped in `asyncio.to_thread()` so the event loop is never blocked.

### 2. Single Responsibility — Tools Never Handle Bytes

Tool functions validate inputs, call `CatalogManager`, and format JSON responses.
They never touch raw raster bytes. `CatalogManager.download_bands()` owns the full
I/O pipeline: COG read → optional cloud mask → optional PNG conversion → artifact store.

### 3. Pydantic v2 Native — No Dict Goop

All responses use Pydantic models with `model_config = ConfigDict(extra="forbid")`.
This catches typos at serialisation time rather than silently passing unknown fields.
STAC models use `extra="allow"` to accept arbitrary STAC extensions.

### 4. No Magic Strings

Every repeated string lives in `constants.py` as an enum, class attribute, or
module-level constant. Band names, STAC property keys, error messages, MIME types,
and catalog URLs are all constants — never inline strings.

### 5. Pluggable Storage via chuk-artifacts

Downloaded rasters are stored through the `chuk-artifacts` abstraction layer.
Supported backends (memory, filesystem, S3) are selected via the
`CHUK_ARTIFACTS_PROVIDER` environment variable. The artifact store is initialised
at server startup, not at module import time.

### 6. Test Coverage >90% per File, >95% Overall

Every module maintains at least 90% line coverage. Overall project coverage
target is 95%+. Tests mock at the `manager.get_stac_client` boundary (not
`pystac_client.Client.open`) because the client cache sits between them.

### 7. Common Band Names — Hardware Aliases Resolved at Entry

The canonical vocabulary is common spectral names: `red`, `nir`, `swir16`, etc.
Hardware designations (`B04`, `B08`, `SR_B4`) are resolved to common names via
`resolve_band_name()` at the top of every download/mosaic method. Downstream code
never sees hardware aliases.

### 8. Graceful Degradation

Errors return structured JSON (`{"error": "..."}`) — never unhandled exceptions
or stack traces. Network failures are retried (tenacity, 3 attempts with exponential
backoff). Missing capabilities (no artifact store, unsupported band) produce clear
error messages explaining what to configure.

---

## Module Dependency Graph

```
server.py                     # CLI entry point (sync)
  └─ async_server.py          # Async server setup, tool registration
       ├─ tools/search/api.py       # Search, list, describe, preview tools
       ├─ tools/download/api.py     # Download, RGB, composite, mosaic, index, time-series tools
       ├─ tools/discovery/api.py    # Status, capabilities tools
       └─ core/catalog_manager.py   # Cache, download pipeline, artifact storage
            └─ core/raster_io.py    # COG reading, merging, indices, cloud mask, PNG

models/responses.py           # Pydantic response models (extra="forbid")
models/stac.py                # Pydantic STAC models (extra="allow")
constants.py                  # Enums, band mappings, aliases, messages
```

---

## Component Responsibilities

### `server.py`

Synchronous entry point. Parses environment variables, configures the artifact store
provider, and calls `asyncio.run()` on the async server. This is the only file that
touches `sys.argv` or `os.environ` directly.

### `async_server.py`

Creates the `chuk-mcp-server` MCP instance, instantiates `CatalogManager`, and
registers all tool modules. Each tool module receives the MCP instance and the
shared `CatalogManager`.

### `core/catalog_manager.py`

The central orchestrator. Manages:
- **Scene cache**: LRU dict mapping scene IDs to `STACItem` models
- **Client cache**: TTL-based cache of `pystac_client.Client` connections
- **Download pipeline**: `download_bands()`, `download_mosaic()`, `compute_index()`
- **Artifact storage**: `_store_raster()` writes bytes + metadata to chuk-artifacts

### `core/raster_io.py`

Pure I/O layer — all functions are synchronous (called via `to_thread()`):
- `read_bands_from_cogs()`: Parallel band reads with resolution matching
- `read_bands_as_arrays()`: Raw array reads for index computation
- `merge_rasters()`: Multi-scene merging via `rasterio.merge`
- `compute_spectral_index()`: NDVI, NDWI, NDBI, EVI, SAVI, BSI formulas
- `apply_cloud_mask()` / `apply_cloud_mask_float()`: SCL-based cloud masking
- `geotiff_to_png()`: Percentile-stretch PNG conversion
- `arrays_to_geotiff()`: NumPy arrays → GeoTIFF bytes via MemoryFile

### `models/responses.py`

Pydantic v2 response models for every tool. All use `extra="forbid"` to catch
serialisation errors early. Includes `SearchResponse`, `BandDownloadResponse`,
`CompositeResponse`, `IndexResponse`, `PreviewResponse`, etc.

### `models/stac.py`

Pydantic models for STAC items (`STACItem`) and assets (`STACAsset`). Uses
`extra="allow"` so arbitrary STAC extensions pass through without validation errors.

### `constants.py`

All magic strings, band mappings, and configuration values. Includes:
- `STACEndpoints`, `SatelliteCollection` — catalog/collection identifiers
- `SENTINEL2_BANDS`, `LANDSAT_BANDS` — common name → asset key mappings
- `BAND_ALIASES`, `resolve_band_name()` — hardware name → common name resolution
- `INDEX_BANDS` — spectral index → required band lists
- `SCL_GOOD_VALUES`, `SCL_COLLECTIONS` — cloud masking configuration
- `ErrorMessages`, `SuccessMessages` — format-string message templates

---

## Data Flows

### Search → Cache → Download

```
1. stac_search(bbox, collection, ...)
   └─ manager.get_stac_client(url) → pystac_client search
   └─ manager.cache_scene(id, STACItem, catalog)  ← LRU cache

2. stac_download_bands(scene_id, bands, ...)
   └─ manager.download_bands()
      ├─ resolve_band_name() on each band     ← alias resolution
      ├─ get_cached_scene(scene_id)            ← cache lookup
      ├─ validate bands exist in item.assets
      ├─ to_thread(read_bands_from_cogs)       ← parallel COG reads
      ├─ optional: to_thread(geotiff_to_png)   ← PNG conversion
      └─ _store_raster() → chuk-artifacts      ← artifact storage
```

### Index Computation

```
stac_compute_index(scene_id, "ndvi", ...)
  └─ manager.compute_index()
     ├─ INDEX_BANDS["ndvi"] → ["red", "nir"]
     ├─ to_thread(read_bands_as_arrays)        ← raw NumPy arrays
     ├─ optional: apply_cloud_mask_float()     ← NaN masking
     ├─ to_thread(compute_spectral_index)      ← (nir - red) / (nir + red)
     ├─ to_thread(arrays_to_geotiff)           ← float32 GeoTIFF
     ├─ optional: to_thread(geotiff_to_png)    ← stretched PNG
     └─ _store_raster()                        ← artifact storage
```

### Cloud Masking

```
download_bands(..., cloud_mask=True)
  ├─ read_bands_as_arrays([requested_bands + "scl"], classification_bands={"scl"})
  │   └─ SCL band read with Resampling.nearest (preserves class values)
  │   └─ Data bands read with Resampling.bilinear (standard interpolation)
  ├─ apply_cloud_mask(data_arrays, scl_array, SCL_GOOD_VALUES)
  │   └─ For integer bands: pixels where SCL ∉ {4,5,6,7,11} → 0
  └─ apply_cloud_mask_float(data_arrays, scl_array, SCL_GOOD_VALUES)
      └─ For float bands (indices): masked pixels → NaN
```

---

## Key Patterns

### LRU Scene Cache

`CatalogManager._scene_cache` is a plain `dict` used as an ordered map (Python 3.7+
insertion order). On access, entries are deleted and re-inserted to move them to the
end. When the cache exceeds 200 entries, the oldest (first) entry is evicted.

### TTL Client Cache

STAC client connections are cached for 300 seconds. A `threading.Lock` protects the
cache dict since `get_stac_client()` may be called from multiple threads (via
`to_thread`). Connection creation happens outside the lock to avoid blocking.

### Parallel Band Reads

`read_bands_from_cogs()` uses `ThreadPoolExecutor(max_workers=min(N, 4))` to read
multiple COG bands concurrently. The first band's spatial dimensions set the target
grid; subsequent bands are resampled to match using `Resampling.bilinear`.

### Resolution Matching

Sentinel-2 bands have different native resolutions (10m, 20m, 60m). All bands
are resampled to the first band's grid via rasterio's `out_shape` parameter.
Classification bands (SCL) use `Resampling.nearest` to preserve integer class values.

### Retry with Backoff

Network operations use `tenacity` with:
- 3 attempts
- Exponential backoff (1s min, 10s max)
- Retry only on `ConnectionError`, `TimeoutError`, `OSError`
- Reraise on non-retryable errors
