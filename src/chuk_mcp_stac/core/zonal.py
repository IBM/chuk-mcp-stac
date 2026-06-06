"""Zonal statistics — summarise a raster's values within zones.

The "readout" step: given a raster band (e.g. an NDVI index) and target zones
(circular buffers around points, or polygons), compute per-zone statistics. An
optional background annulus around each point yields a local z-score — the
direct "is this location anomalous versus its surroundings?" answer used for
cropmark / feature detection.

Pure NumPy + rasterio.transform/features; no MCP or network dependencies, so it
is independently unit-testable.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from rasterio.features import geometry_mask
from rasterio.transform import rowcol


def _summary(values: np.ndarray) -> dict[str, Any]:
    """Summary statistics for a 1-D array of (already finite) values."""
    finite = values[np.isfinite(values)]
    n = int(finite.size)
    if n == 0:
        return {
            "n_valid": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "median": None,
            "p10": None,
            "p90": None,
        }
    return {
        "n_valid": n,
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "median": float(np.median(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p90": float(np.percentile(finite, 90)),
    }


def _pixel_size(transform) -> float:
    """Approximate ground size of one pixel in raster CRS units."""
    px = math.hypot(transform.a, transform.d)
    py = math.hypot(transform.b, transform.e)
    return max(px, py) or 1.0


def circular_values(
    arr: np.ndarray,
    transform,
    cx: float,
    cy: float,
    r_inner: float,
    r_outer: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Values inside radius ``r_inner`` of (cx, cy), and in the background annulus.

    (cx, cy) are in the raster CRS. Only a window around the zone is scanned, so
    cost is independent of overall raster size. Returns ``(inner, background)``;
    ``background`` is empty when ``r_outer`` is None.
    """
    h, w = arr.shape
    pix = _pixel_size(transform)
    reach = r_outer if r_outer else r_inner
    r_c, c_c = rowcol(transform, cx, cy)
    rad = int(math.ceil(reach / pix)) + 1

    r0, r1 = max(0, r_c - rad), min(h, r_c + rad + 1)
    c0, c1 = max(0, c_c - rad), min(w, c_c + rad + 1)
    if r0 >= r1 or c0 >= c1:
        return np.array([]), np.array([])

    sub = arr[r0:r1, c0:c1]
    cols, rows = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1))
    # Pixel-centre coordinates via the affine transform.
    xs = transform.c + transform.a * (cols + 0.5) + transform.b * (rows + 0.5)
    ys = transform.f + transform.d * (cols + 0.5) + transform.e * (rows + 0.5)
    dist = np.hypot(xs - cx, ys - cy)

    inner = sub[dist <= r_inner]
    background = sub[(dist > r_inner) & (dist <= r_outer)] if r_outer else np.array([])
    return inner, background


def polygon_values(arr: np.ndarray, transform, geometry: dict) -> np.ndarray:
    """Values of pixels whose centre falls inside a GeoJSON geometry (raster CRS)."""
    mask = geometry_mask(
        [geometry], out_shape=arr.shape, transform=transform, invert=True, all_touched=False
    )
    return arr[mask]


def zone_record(
    label: str,
    inner: np.ndarray,
    background: np.ndarray,
    z_threshold: float,
) -> dict[str, Any]:
    """Build a per-zone result, adding a local z-score when a background is given."""
    rec: dict[str, Any] = {"label": label, **_summary(inner)}
    if background.size:
        bg = _summary(background)
        rec["bg_n_valid"] = bg["n_valid"]
        rec["bg_mean"] = bg["mean"]
        rec["bg_std"] = bg["std"]
        mean, bg_mean, bg_std = rec["mean"], bg["mean"], bg["std"]
        # Float-noise floor: a numerically-uniform background has std ~1e-17, which
        # would otherwise manufacture a spurious z-score (and a false anomaly) from
        # rounding error. Real imagery noise is orders of magnitude above this.
        floor = 1e-9 * (abs(bg_mean) + 1.0) if bg_mean is not None else 0.0
        if mean is not None and bg_mean is not None and bg_std is not None and bg_std > floor:
            z = (mean - bg_mean) / bg_std
            rec["z_score"] = float(z)
            rec["anomalous"] = bool(abs(z) >= z_threshold)
        else:
            rec["z_score"] = None
            rec["anomalous"] = False
    return rec
