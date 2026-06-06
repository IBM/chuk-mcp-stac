"""Tests for zonal statistics (core + the raster→stats path used by stac_zonal_stats)."""

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import Affine

from chuk_mcp_stac.core.zonal import circular_values, polygon_values, zone_record
from chuk_mcp_stac.tools.analysis.api import _run

# A projected (UTM) synthetic raster: 200x200 @ 10 m, NDVI-like background 0.2
# with a bright disc (0.6) of radius ~60 m centred on pixel (100, 100).
CRS = "EPSG:32631"
TRANSFORM = Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 5000000.0)
CX = 500000.0 + 10.0 * (100 + 0.5)  # 501005.0
CY = 5000000.0 - 10.0 * (100 + 0.5)  # 4998995.0


def _make_raster() -> np.ndarray:
    arr = np.full((200, 200), 0.2, dtype="float64")
    rows, cols = np.mgrid[0:200, 0:200]
    xs = TRANSFORM.c + TRANSFORM.a * (cols + 0.5)
    ys = TRANSFORM.f + TRANSFORM.e * (rows + 0.5)
    arr[np.hypot(xs - CX, ys - CY) <= 60.0] = 0.6
    return arr


def _geotiff_bytes(arr: np.ndarray) -> bytes:
    with MemoryFile() as mf:
        with mf.open(
            driver="GTiff",
            height=arr.shape[0],
            width=arr.shape[1],
            count=1,
            dtype="float64",
            crs=CRS,
            transform=TRANSFORM,
        ) as dst:
            dst.write(arr, 1)
        return mf.read()


def test_circular_values_window_and_radius():
    arr = _make_raster()
    inner, background = circular_values(arr, TRANSFORM, CX, CY, r_inner=30.0, r_outer=150.0)
    assert inner.size > 0
    assert np.allclose(inner, 0.6)  # all inside the disc
    assert background.size > inner.size  # annulus is larger
    assert background.min() == 0.2  # annulus reaches background


def test_zone_record_flags_anomaly():
    arr = _make_raster()
    inner, background = circular_values(arr, TRANSFORM, CX, CY, 30.0, 150.0)
    rec = zone_record("disc", inner, background, z_threshold=2.0)
    assert rec["mean"] > 0.5
    assert rec["z_score"] > 2.0
    assert rec["anomalous"] is True


def test_zone_record_flat_area_not_anomalous():
    arr = _make_raster()
    fx, fy = 500000.0 + 10 * 30.5, 5000000.0 - 10 * 30.5  # well away from the disc
    inner, background = circular_values(arr, TRANSFORM, fx, fy, 30.0, 150.0)
    rec = zone_record("flat", inner, background, z_threshold=2.0)
    assert rec["anomalous"] is False


def test_polygon_values():
    arr = _make_raster()
    # A box covering the disc centre.
    geom = {
        "type": "Polygon",
        "coordinates": [
            [
                [CX - 40, CY - 40],
                [CX + 40, CY - 40],
                [CX + 40, CY + 40],
                [CX - 40, CY + 40],
                [CX - 40, CY - 40],
            ]
        ],
    }
    vals = polygon_values(arr, TRANSFORM, geom)
    assert vals.size > 0
    assert vals.max() == 0.6


def test_run_end_to_end_points():
    data = _geotiff_bytes(_make_raster())
    raster_crs, records = _run(
        data,
        band=1,
        points=[[CX, CY]],
        labels=["disc"],
        buffer_m=30.0,
        background_m=150.0,
        geojson=None,
        zones_crs=CRS,
        z_threshold=2.0,
    )
    assert "32631" in raster_crs
    assert len(records) == 1
    assert records[0]["anomalous"] is True
    assert records[0]["center"] == [CX, CY]


def test_run_nodata_ignored():
    arr = _make_raster()
    arr[150:, :] = -9999.0  # nodata band
    with MemoryFile() as mf:
        with mf.open(
            driver="GTiff",
            height=arr.shape[0],
            width=arr.shape[1],
            count=1,
            dtype="float64",
            crs=CRS,
            transform=TRANSFORM,
            nodata=-9999.0,
        ) as dst:
            dst.write(arr, 1)
        data = mf.read()
    _, records = _run(
        data,
        band=1,
        points=[[CX, CY]],
        labels=None,
        buffer_m=30.0,
        background_m=None,
        geojson=None,
        zones_crs=CRS,
        z_threshold=2.0,
    )
    assert abs(records[0]["mean"] - 0.6) < 1e-9  # nodata far away didn't pollute the disc
