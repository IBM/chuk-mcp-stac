# chuk-mcp-stac Roadmap

## Current State (v0.1.0)

**Working:** All 11 tools functional with full STAC search -> download -> artifact pipeline.

**Infrastructure:** Tests (178 passing, 95%+ coverage), CI/CD (GitHub Actions), README, LICENSE, Makefile, Dockerfile, Fly.io deployment.

**Implemented:** Mosaic (`stac_mosaic`) and time series (`stac_time_series`) with concurrent downloads via `asyncio.gather`.

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

## Phase 3: Production Hardening (v0.3.0) — IN PROGRESS

### 3.1 Performance

- [x] Parallel band downloads within a scene (ThreadPoolExecutor)
- [x] STAC client caching (TTL-based, thread-safe)
- [ ] Optional in-memory caching for small rasters
- [ ] Progress callbacks for long downloads

### 3.2 Additional Catalogs

- [x] Generic STAC catalog URL input (pass any https:// URL)
- [ ] Microsoft Planetary Computer auth integration
- [ ] USGS STAC catalog support

### 3.3 Extended Collections

- [x] Landsat collection support with band mapping
- [ ] Sentinel-1 SAR support
- [ ] DEM collections (Copernicus GLO-30)

### 3.4 Advanced Compositing

- [ ] Cloud masking using SCL band
- [ ] Temporal compositing (median, max NDVI, etc.)
- [ ] Quality-weighted mosaics (prefer low-cloud pixels)

---

## Phase 4: Integration (v0.4.0)

Bridge to chuk-mcp-geo analysis pipeline.

### 4.1 Artifact Handoff

- [ ] Standardize artifact metadata schema for geo interop
- [ ] Include band wavelength info in artifact metadata
- [ ] Include acquisition geometry (sun angle, view angle) for advanced analysis

### 4.2 Convenience Tools

- [ ] `stac_download_for_index` — auto-download bands needed for a spectral index
- [ ] `stac_find_pairs` — find before/after scenes for change detection
- [ ] `stac_coverage_check` — verify full bbox coverage before download

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
| 0.3.0 | Production | Parallel I/O, client caching, generic URLs, Landsat |
| 0.4.0 | Integration | Geo handoff, convenience tools |

---

*Last updated: 2025-02*
