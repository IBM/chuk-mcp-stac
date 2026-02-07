# chuk-mcp-stac Roadmap

## Current State (v0.1.0)

**Working:** All 20 tools functional with full STAC search -> download -> artifact pipeline.

**Infrastructure:** Tests (504 passing, 94%+ coverage), CI/CD (GitHub Actions), README, LICENSE, Makefile, Dockerfile, Fly.io deployment.

**Implemented:** Mosaic (standard + quality-weighted), time series, temporal compositing, spectral indices, cloud masking, PNG output, preview, band aliases, auto-preview, size estimation, collection intelligence, conformance checking, dual output mode, find pairs, coverage check, queryables, in-memory raster cache, progress callbacks, Planetary Computer auth, USGS catalog, Sentinel-1 SAR, Copernicus DEM, enriched artifact metadata.

---

## Phase 1: Ship-Ready (v0.1.1) — COMPLETE

### 1.1 Project Infrastructure

- [x] Initialize git repo with `.gitignore`
- [x] Write `README.md` (overview, install, quick start, tool reference)
- [x] Create `tests/` directory structure
- [x] Add `LICENSE` file (Apache-2.0)
- [x] Add `Makefile` with full target set
- [x] Add `Dockerfile` (multi-stage, GDAL/rasterio)
- [x] Add `fly.toml` for Fly.io deployment
- [x] Add `mypy.ini`, `MANIFEST.in`, `.dockerignore`, `.python-version`

### 1.2 Core Test Coverage

- [x] `tests/conftest.py` — fixtures for mock STAC catalog, mock artifact store
- [x] `tests/test_catalog_manager.py` — scene caching, URL resolution, download pipeline
- [x] `tests/test_raster_io.py` — COG reading, CRS reprojection, GeoTIFF output, merge
- [x] `tests/test_search_tools.py` — search, describe, list operations
- [x] `tests/test_download_tools.py` — band download, RGB composite, mosaic, time series
- [x] `tests/test_models.py` — Pydantic model validation
- [x] `tests/test_discovery_tools.py` — status, capabilities
- [x] `tests/test_constants.py` — constant validation
- [x] `tests/test_server.py` — server entry point

### 1.3 CI/CD

- [x] `.github/workflows/test.yml` — lint, typecheck, security, tests (multi-OS, multi-Python)
- [x] `.github/workflows/publish.yml` — PyPI publishing via trusted publishing
- [x] `.github/workflows/release.yml` — auto-generate changelog and GitHub release
- [x] `.github/workflows/fly-deploy.yml` — deploy to Fly.io on push to main
- [x] `.pre-commit-config.yaml` — ruff formatting and linting hooks

---

## Phase 2: Complete Features (v0.2.0) — COMPLETE

### 2.1 Mosaic Implementation

- [x] Read bands from each scene via `manager.download_bands()`
- [x] Use `rasterio.merge.merge()` to combine scenes
- [x] Store merged result in artifact store
- [x] Handle CRS alignment via rasterio merge
- [x] Return real artifact ref (replaced `pending://` stubs)

### 2.2 Time Series Download

- [x] After search, iterate scenes and call `manager.download_bands()` for each
- [x] Store individual scene artifacts
- [x] Return list of real artifact refs with datetime metadata
- [x] Concurrent downloads via `asyncio.gather`

### 2.3 Enhanced Error Handling

- [x] HTTP timeout handling for COG reads (`GDAL_HTTP_TIMEOUT=30`)
- [x] Tenacity retry logic for STAC client connections and COG reads
- [x] Specific error messages with scene/band context

---

## Phase 3: Production Hardening (v0.3.0) — COMPLETE

### 3.1 Performance

- [x] Parallel band downloads within a scene (ThreadPoolExecutor)
- [x] STAC client caching (TTL-based, thread-safe)
- [x] In-memory raster cache (100 MB LRU, 10 MB per item)
- [x] Progress callbacks for long downloads

### 3.2 Additional Catalogs

- [x] Generic STAC catalog URL input (pass any https:// URL)
- [x] Microsoft Planetary Computer auth integration (auto-detect + sign)
- [x] USGS STAC catalog support

### 3.3 Extended Collections

- [x] Landsat collection support with band mapping
- [x] Sentinel-1 SAR support (VV, VH polarisation)
- [x] DEM collections (Copernicus GLO-30)

### 3.4 Advanced Processing

- [x] Cloud masking using SCL band (Sentinel-2 L2A)
- [x] Spectral indices (NDVI, NDWI, NDBI, EVI, SAVI, BSI)
- [x] PNG output with 2nd-98th percentile stretch
- [x] Scene preview/thumbnail URL retrieval
- [x] Hardware band alias resolution (B04 → red, SR_B4 → red)
- [x] Temporal compositing (median, mean, max, min)
- [x] Quality-weighted mosaics (prefer low-cloud pixels via SCL)

---

## Phase 4: Integration (v0.4.0) — COMPLETE

Bridge to chuk-mcp-geo analysis pipeline.

### 4.1 Artifact Handoff

- [x] Standardize artifact metadata schema (schema_version: "1.0")
- [x] Include band wavelength info in artifact metadata
- [x] Include acquisition geometry (sun angle, view angle) for advanced analysis

### 4.2 Convenience Tools

- [x] `stac_compute_index` — compute spectral indices with automatic band selection
- [x] `stac_find_pairs` — find before/after scenes for change detection
- [x] `stac_coverage_check` — verify full bbox coverage before download

---

## Phase 5: Extended Capabilities — COMPLETE

### 5.1 Collection & Catalog Introspection

- [x] `stac_describe_collection` — collection intelligence with band wavelengths, composites, LLM guidance
- [x] `stac_get_conformance` — parse STAC API conformance URIs into feature flags
- [x] `stac_queryables` — expose queryable properties for a catalog

### 5.2 Pre-Download Analysis

- [x] `stac_estimate_size` — COG header-only reads for size estimation with warnings

### 5.3 UX Enhancements

- [x] Dual output mode — `output_mode="text"` for human-readable responses on all 20 tools
- [x] Auto-preview — PNG preview auto-generated alongside every GeoTIFF download (`preview_ref`)
- [x] Demo scripts — 6 examples (capabilities, collection intel, colchester, mosaic, time series, landsat)

### 5.4 Advanced Compositing

- [x] Temporal compositing methods (median, mean, max, min) via `stac_temporal_composite`
- [x] Quality-weighted mosaics using SCL band (`stac_mosaic` method="quality")

### Note on Geocoding

Geocoding (place name → bbox) is planned as a **separate MCP server**, not part
of chuk-mcp-stac. This server accepts only coordinate-based bounding boxes.

---

## Future Considerations

### Not in Scope (for now)

- **LiDAR/point cloud support** — different server
- **Drone/photogrammetry ingest** — likely manual raster import
- **GPR data** — specialized format, separate concern

---

## Version Summary

| Version | Focus | Key Deliverables |
|---------|-------|------------------|
| 0.1.1 | Ship-ready | Tests, README, git, CI, Dockerfile, Fly.io |
| 0.2.0 | Complete | Mosaic, time series download, retry logic |
| 0.3.0 | Production | Parallel I/O, client caching, Landsat, cloud mask, indices, PNG, preview, raster cache, PC auth, USGS, S1, DEM, temporal composite, quality mosaic |
| 0.4.0 | Integration | Artifact metadata enrichment, find_pairs, coverage_check |
| 0.5.0 | Extended | Collection intelligence, conformance, size estimation, queryables, dual output, auto-preview |

---

*Last updated: 2026-02*
