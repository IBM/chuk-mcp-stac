# Chuk MCP STAC

**Satellite Imagery Discovery & Retrieval MCP Server** - A comprehensive Model Context Protocol (MCP) server for searching STAC catalogs, downloading satellite bands, and creating composites.

> This is a demonstration project provided as-is for learning and testing purposes.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Features

This MCP server provides access to satellite imagery through STAC (SpatioTemporal Asset Catalog) APIs via eleven powerful tools.

**All tools return fully-typed Pydantic v2 models** for type safety, validation, and excellent IDE support.

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

### 5. Band Download (`stac_download_bands`)
Download specific bands from a scene:
- Any combination of bands (red, green, blue, nir, etc.)
- Optional bbox cropping in EPSG:4326
- Automatic CRS reprojection
- Stored as GeoTIFF in artifact store

### 6. RGB Composite (`stac_download_rgb`)
Download true-color RGB composites:
- Convenience wrapper for red, green, blue bands
- Automatic band resolution matching

### 7. Custom Composite (`stac_download_composite`)
Create multi-band composites:
- Any band combination (e.g., false-color infrared: nir, red, green)
- Named composites for easy identification

### 8. Mosaic (`stac_mosaic`)
Merge multiple scenes into a single raster:
- Combines overlapping scenes
- Later scenes fill gaps from earlier ones
- Useful for covering large areas

### 9. Time Series (`stac_time_series`)
Extract temporal band data:
- Searches scenes across a date range
- Downloads bands for each date
- Concurrent downloads for performance
- Cloud cover filtering

### 10. Server Status (`stac_status`)
Check server capabilities:
- Lists all available tools
- Shows supported catalogs and collections
- Reports cache statistics

### 11. Help (`stac_help`)
Get usage guidance:
- Example workflows
- Band combination suggestions
- Supported collections reference

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
- "Create a mosaic of these overlapping scenes"
- "Get a time series of NDVI data for this farm over the growing season"
- "What collections are available on Earth Search?"

## Tool Reference

### stac_search

Parameters:
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

Parameters:
```python
{
  "scene_id": "S2B_...",                        # from search results
  "bands": ["red", "green", "blue", "nir"],     # band names
  "bbox": [0.85, 51.85, 0.95, 51.92]           # optional crop
}
```

### stac_download_rgb

Parameters:
```python
{
  "scene_id": "S2B_...",
  "bbox": [0.85, 51.85, 0.95, 51.92]           # optional crop
}
```

### stac_mosaic

Parameters:
```python
{
  "scene_ids": ["S2B_001", "S2B_002"],
  "bands": ["red", "green", "blue"],
  "bbox": [0.85, 51.85, 0.95, 51.92]           # optional
}
```

### stac_time_series

Parameters:
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
- **Type-Safe**: Pydantic v2 models for all requests and responses
- **Efficient I/O**: Cloud-Optimized GeoTIFF (COG) reading with windowed access
- **Smart Caching**: LRU scene cache (200 entries) for fast repeated access
- **Band Resolution Matching**: Automatic bilinear resampling when bands differ in resolution
- **Artifact Storage**: Pluggable storage via chuk-artifacts (memory, filesystem, S3)
- **CRS Handling**: Automatic EPSG:4326 to native CRS reprojection for bbox queries

### Supported Catalogs

| Catalog | Collections | URL |
|---------|------------|-----|
| Earth Search (AWS) | Sentinel-2, Landsat, NAIP, MODIS | earth-search.aws.element84.com |
| Planetary Computer (Microsoft) | Sentinel-2, Landsat, MODIS | planetarycomputer.microsoft.com |

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
