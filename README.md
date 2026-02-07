# Chuk MCP STAC

**Satellite Imagery Discovery & Retrieval MCP Server** - A comprehensive Model Context Protocol (MCP) server for searching STAC catalogs, downloading satellite bands, and creating composites.

> This is a demonstration project provided as-is for learning and testing purposes.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Features

This MCP server provides access to satellite imagery through STAC (SpatioTemporal Asset Catalog) APIs via twenty tools.

**All tools return fully-typed Pydantic v2 models** for type safety, validation, and excellent IDE support. All tools support `output_mode="text"` for human-readable output alongside the default JSON.

### 1. Catalog Discovery (`stac_list_catalogs`)
List available STAC catalogs:
- Earth Search (AWS) and Planetary Computer (Microsoft)
- Shows default catalog and available endpoints

### 2. Collection Browsing (`stac_list_collections`)
Browse collections in a catalog:
- List all available satellite collections
- Spatial and temporal extents
- Collection descriptions and metadata

### 3. Scene Search (`stac_search`)
Search for satellite scenes:
- Bounding box spatial queries
- Date range filtering
- Cloud cover thresholds
- Collection filtering (Sentinel-2, Landsat, etc.)
- Configurable result limits

### 4. Scene Details (`stac_describe_scene`)
Get detailed metadata for a scene:
- Available bands and assets
- CRS and projection info
- Cloud cover, datetime, spatial extent
- Filters out metadata-only assets

### 5. Scene Preview (`stac_preview`)
Get a preview/thumbnail URL for a scene:
- Returns `rendered_preview` or `thumbnail` asset URL
- Prefers rendered previews over thumbnails
- Fast visual browsing without downloading full bands

### 6. Band Download (`stac_download_bands`)
Download specific bands from a scene:
- Any combination of bands (red, green, blue, nir, etc.)
- Hardware band aliases supported (B04, B08, SR_B4, etc.)
- Optional bbox cropping in EPSG:4326
- Output as GeoTIFF or PNG (auto-stretched)
- SCL-based cloud masking (Sentinel-2 only)

### 7. RGB Composite (`stac_download_rgb`)
Download true-color RGB composites:
- Convenience wrapper for red, green, blue bands
- Automatic band resolution matching
- PNG output for inline LLM rendering

### 8. Custom Composite (`stac_download_composite`)
Create multi-band composites:
- Any band combination (e.g., false-color infrared: nir, red, green)
- Named composites for easy identification
- Cloud masking and PNG output support

### 9. Spectral Index (`stac_compute_index`)
Compute spectral indices for a scene:
- NDVI, NDWI, NDBI, EVI, SAVI, BSI
- Automatically selects required bands
- Cloud masking (masked pixels → NaN)
- Output as float32 GeoTIFF or stretched PNG

### 10. Mosaic (`stac_mosaic`)
Merge multiple scenes into a single raster:
- Combines overlapping scenes
- Standard merge (last) or quality-weighted (best pixel via SCL)
- Per-scene cloud masking before merge

### 11. Time Series (`stac_time_series`)
Extract temporal band data:
- Searches scenes across a date range
- Downloads bands for each date
- Concurrent downloads for performance
- Cloud cover filtering

### 12. Server Status (`stac_status`)
Check server configuration:
- Server version and storage provider
- Default catalog
- Artifact store availability

### 13. Capabilities (`stac_capabilities`)
List full server capabilities for LLM workflow planning:
- Available catalogs and collections
- Spectral indices with required bands
- Band mappings by satellite platform
- Tool count

### 14. Size Estimation (`stac_estimate_size`)
Estimate download size before committing to a full download:
- Reads only COG headers (no pixel data transferred)
- Per-band dimensions, dtype, and byte estimates
- Warnings for large downloads (>=500MB, >=1GB)

### 15. Collection Intelligence (`stac_describe_collection`)
Get detailed collection metadata with LLM-friendly guidance:
- Band wavelengths and resolutions
- Recommended composite recipes
- Supported spectral indices
- Cloud masking info and usage guidance

### 16. Conformance Checking (`stac_get_conformance`)
Check which STAC API features a catalog supports:
- Parses conformance URIs into feature flags
- Core, item_search, filter, sort, fields, query, collections

### 17. Find Scene Pairs (`stac_find_pairs`)
Find before/after scene pairs for change detection:
- Separate before and after date ranges
- Computes spatial overlap percentage per pair
- Caches all found scenes for follow-up download

### 18. Coverage Check (`stac_coverage_check`)
Verify cached scenes fully cover a target area:
- Rasterizes bounding box into a 100x100 grid
- Returns coverage percentage and uncovered areas
- Ensures full spatial coverage before download

### 19. Queryable Properties (`stac_queryables`)
Fetch queryable properties from a STAC API:
- Catalog-level or collection-scoped queryables
- Property names, types, descriptions, and enum values
- Enables advanced CQL2 filter construction

### 20. Temporal Composite (`stac_temporal_composite`)
Combine multiple scenes via per-pixel statistics:
- Methods: median, mean, max, min
- Reduces cloud contamination in time series
- SCL-based cloud masking per scene before compositing

## Installation

### Using uvx (Recommended - No Installation Required!)

```bash
uvx chuk-mcp-stac
```

### Using uv (Recommended for Development)

```bash
# Install from PyPI
uv pip install chuk-mcp-stac

# Or clone and install from source
git clone <repository-url>
cd chuk-mcp-stac
uv sync --dev
```

### Using pip (Traditional)

```bash
pip install chuk-mcp-stac
```

## Usage

### With Claude Desktop

#### Option 1: Run Locally with uvx

**MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "stac": {
      "command": "uvx",
      "args": ["chuk-mcp-stac"]
    }
  }
}
```

#### Option 2: Run Locally with pip

```json
{
  "mcpServers": {
    "stac": {
      "command": "chuk-mcp-stac"
    }
  }
}
```

### Standalone

Run the server directly:

```bash
# With uvx (recommended - always latest version)
uvx chuk-mcp-stac

# With uvx in HTTP mode
uvx chuk-mcp-stac http

# Or if installed locally
chuk-mcp-stac
chuk-mcp-stac http
```

Or with uv/Python:

```bash
# STDIO mode (default, for MCP clients)
uv run chuk-mcp-stac
# or: python -m chuk_mcp_stac.server

# HTTP mode (for web access)
uv run chuk-mcp-stac http
# or: python -m chuk_mcp_stac.server http
```

**STDIO mode** is for MCP clients like Claude Desktop and mcp-cli.
**HTTP mode** runs a web server on http://localhost:8002 for HTTP-based MCP clients.

## Example Usage

Once configured, you can ask Claude questions like:

- "Search for Sentinel-2 imagery over London from last month"
- "Download an RGB composite of that scene"
- "Show me a false-color infrared view using NIR, red, and green bands"
- "Compute the NDVI for this scene with cloud masking"
- "Create a mosaic of these overlapping scenes"
- "Get a time series of NDVI data for this farm over the growing season"
- "What collections are available on Earth Search?"
- "Describe the Sentinel-2 collection — what bands and composites are available?"
- "How big would downloading 4 bands from that scene be?"
- "What STAC API features does Earth Search support?"

### Demo Scripts

The `examples/` directory contains runnable demos:

| Script | Network? | Description |
|--------|----------|-------------|
| `capabilities_demo.py` | No | Server capabilities, catalogs, band mappings, text output mode |
| `collection_intel_demo.py` | Yes | Collection intelligence, conformance, size estimation |
| `colchester_from_space.py` | Yes | Full pipeline: search → RGB → NDVI with rendering |
| `mosaic_demo.py` | Yes | Multi-scene mosaic merge |
| `time_series_demo.py` | Yes | Temporal NDVI extraction across dates |
| `landsat_demo.py` | Yes | Landsat-specific band naming and download |

```bash
cd examples
python capabilities_demo.py      # no network required
python colchester_from_space.py   # requires matplotlib
```

## Tool Reference

All tools accept an optional `output_mode` parameter (`"json"` default, or `"text"` for human-readable output).
Download tools that produce GeoTIFF output automatically generate a PNG preview (`preview_ref` in the response).

### stac_search

```python
{
  "bbox": [0.85, 51.85, 0.95, 51.92],        # [west, south, east, north]
  "collection": "sentinel-2-c1-l2a",           # optional
  "date_range": "2024-06-01/2024-08-31",       # optional
  "max_cloud_cover": 20,                        # 0-100, optional
  "max_items": 10,                              # optional
  "catalog": "earth_search"                     # optional
}
```

### stac_download_bands

```python
{
  "scene_id": "S2B_...",                        # from search results
  "bands": ["red", "green", "blue", "nir"],     # common names or aliases (B04, SR_B4)
  "bbox": [0.85, 51.85, 0.95, 51.92],          # optional crop
  "output_format": "geotiff",                   # "geotiff" or "png"
  "cloud_mask": false                            # Sentinel-2 only
}
```

### stac_download_rgb

```python
{
  "scene_id": "S2B_...",
  "bbox": [0.85, 51.85, 0.95, 51.92],          # optional crop
  "output_format": "png",                        # "geotiff" or "png"
  "cloud_mask": false                            # Sentinel-2 only
}
```

### stac_download_composite

```python
{
  "scene_id": "S2B_...",
  "bands": ["nir", "red", "green"],             # false-color infrared
  "composite_name": "false_color_ir",           # optional label
  "bbox": [0.85, 51.85, 0.95, 51.92],          # optional crop
  "output_format": "geotiff",                   # "geotiff" or "png"
  "cloud_mask": false                            # Sentinel-2 only
}
```

### stac_compute_index

```python
{
  "scene_id": "S2B_...",
  "index_name": "ndvi",                         # ndvi, ndwi, ndbi, evi, savi, bsi
  "bbox": [0.85, 51.85, 0.95, 51.92],          # optional crop
  "cloud_mask": true,                            # mask clouds with NaN
  "output_format": "geotiff"                    # "geotiff" or "png"
}
```

### stac_mosaic

```python
{
  "scene_ids": ["S2B_001", "S2B_002"],
  "bands": ["red", "green", "blue"],
  "bbox": [0.85, 51.85, 0.95, 51.92],          # optional
  "method": "last",                              # "last" or "quality" (SCL-based)
  "output_format": "geotiff",                   # "geotiff" or "png"
  "cloud_mask": false                            # per-scene masking before merge
}
```

### stac_time_series

```python
{
  "bbox": [0.85, 51.85, 0.95, 51.92],
  "bands": ["red", "nir"],
  "date_range": "2024-01-01/2024-12-31",
  "collection": "sentinel-2-c1-l2a",            # optional
  "max_cloud_cover": 10,                         # optional
  "max_items": 50,                               # optional
  "catalog": "earth_search"                      # optional
}
```

### stac_estimate_size

```python
{
  "scene_id": "S2B_...",
  "bands": ["red", "green", "blue", "nir"],
  "bbox": [0.85, 51.85, 0.95, 51.92]            # optional crop
}
```

### stac_describe_collection

```python
{
  "collection_id": "sentinel-2-l2a",
  "catalog": "earth_search",                     # optional
  "output_mode": "text"                          # optional: "json" or "text"
}
```

### stac_get_conformance

```python
{
  "catalog": "earth_search",                     # optional
  "output_mode": "json"                          # optional: "json" or "text"
}
```

## Development

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd chuk-mcp-stac

# Install with uv (recommended)
uv sync --dev

# Or with pip
pip install -e ".[dev]"
```

### Running Tests

```bash
make test              # Run tests
make test-cov          # Run tests with coverage
make coverage-report   # Show coverage report
```

### Code Quality

```bash
make lint      # Run linters
make format    # Auto-format code
make typecheck # Run type checking
make security  # Run security checks
make check     # Run all checks
```

### Building

```bash
make build         # Build package
make docker-build  # Build Docker image
```

## Deployment

### Fly.io

Deploy to Fly.io with a single command:

```bash
# First time setup
fly launch

# Deploy updates
fly deploy
```

### Docker

```bash
# Build the image
docker build -t chuk-mcp-stac .

# Run the container
docker run -p 8002:8002 chuk-mcp-stac
```

## Architecture

Built on top of chuk-mcp-server, this server uses:

- **Async-First**: Native async/await with sync rasterio wrapped in `asyncio.to_thread()`
- **Type-Safe**: Pydantic v2 models with `extra="forbid"` for all responses
- **Efficient I/O**: Cloud-Optimized GeoTIFF (COG) reading with windowed access
- **Smart Caching**: LRU scene cache (200 entries), TTL client cache (300s), in-memory raster cache (100 MB LRU)
- **Band Resolution Matching**: Automatic bilinear resampling when bands differ in resolution
- **Band Aliases**: Hardware names (B04, SR_B4) resolved to common names at entry
- **Artifact Storage**: Pluggable storage via chuk-artifacts (memory, filesystem, S3)
- **CRS Handling**: Automatic EPSG:4326 to native CRS reprojection for bbox queries
- **Cloud Masking**: SCL-based masking for Sentinel-2 (integer → 0, float → NaN)
- **Spectral Indices**: NDVI, NDWI, NDBI, EVI, SAVI, BSI with automatic band selection
- **PNG Output**: 2nd-98th percentile stretch for visual inspection and LLM rendering
- **Auto-Preview**: PNG preview auto-generated alongside every GeoTIFF download (`preview_ref`)
- **Temporal Compositing**: Pixel-by-pixel statistical composites (median, mean, max, min)
- **Quality Mosaics**: SCL-based best-pixel selection for quality-weighted merges
- **Progress Callbacks**: Optional progress reporting for long-running operations
- **PC Auth**: Automatic Planetary Computer asset signing when package is installed
- **Dual Output**: All 20 tools support `output_mode="text"` for human-readable responses

See [ARCHITECTURE.md](ARCHITECTURE.md) for design principles and data flow diagrams.
See [SPEC.md](SPEC.md) for the full tool specification with parameter tables.
See [ROADMAP.md](ROADMAP.md) for development status and planned features.

### Supported Catalogs

| Catalog | Collections | URL |
|---------|------------|-----|
| Earth Search (AWS) | Sentinel-2, Landsat, NAIP, MODIS | earth-search.aws.element84.com |
| Planetary Computer (Microsoft) | Sentinel-2, Landsat, MODIS | planetarycomputer.microsoft.com |
| USGS Landsat Look | Landsat | landsatlook.usgs.gov |

Also supports Sentinel-1 SAR (VV/VH) and Copernicus DEM GLO-30 collections.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

## Acknowledgments

- [STAC Spec](https://stacspec.org/) for the SpatioTemporal Asset Catalog specification
- [pystac-client](https://github.com/stac-utils/pystac-client) for the STAC client library
- [rasterio](https://rasterio.readthedocs.io/) for raster data I/O
- [Model Context Protocol](https://modelcontextprotocol.io/) for the MCP specification
- [Anthropic](https://www.anthropic.com/) for Claude and MCP support
