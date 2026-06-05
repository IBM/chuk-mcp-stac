"""
Analysis tools for chuk-mcp-stac.

Tools: stac_zonal_stats
"""

import asyncio
import logging
from typing import Any

import numpy as np
from pyproj import Transformer
from rasterio.io import MemoryFile

from ...constants import ErrorMessages
from ...core.zonal import circular_values, polygon_values, zone_record
from ...models import ErrorResponse, ZonalStatsResponse, ZoneStat, format_response

logger = logging.getLogger(__name__)


def _reproject_coords(coords: Any, tf: Transformer) -> Any:
    """Recursively reproject a GeoJSON coordinate structure with a transformer."""
    if isinstance(coords[0], (int, float)):
        x, y = tf.transform(coords[0], coords[1])
        return [x, y]
    return [_reproject_coords(c, tf) for c in coords]


def _geometries(geojson: dict) -> list[tuple[str, dict]]:
    """Normalise a geometry / Feature / FeatureCollection into (label, geometry) pairs."""
    t = geojson.get("type")
    if t == "FeatureCollection":
        out = []
        for i, feat in enumerate(geojson.get("features", [])):
            label = str((feat.get("properties") or {}).get("name", f"poly_{i}"))
            out.append((label, feat["geometry"]))
        return out
    if t == "Feature":
        label = str((geojson.get("properties") or {}).get("name", "poly_0"))
        return [(label, geojson["geometry"])]
    return [("poly_0", geojson)]  # bare geometry


def _run(
    data: bytes,
    band: int,
    points: list[list[float]] | None,
    labels: list[str] | None,
    buffer_m: float,
    background_m: float | None,
    geojson: dict | None,
    zones_crs: str,
    z_threshold: float,
) -> tuple[str, list[dict]]:
    """Open the GeoTIFF, reproject zones into its CRS, and compute per-zone stats.

    Synchronous (rasterio + pyproj + numpy) — call via asyncio.to_thread.
    """
    with MemoryFile(data) as mf, mf.open() as src:
        arr = src.read(band).astype("float64")
        transform = src.transform
        raster_crs = str(src.crs)
        is_projected = bool(src.crs and src.crs.is_projected)
        nodata = src.nodata
    if nodata is not None:
        arr[arr == nodata] = np.nan

    tf = Transformer.from_crs(zones_crs, raster_crs, always_xy=True)
    records: list[dict] = []

    if points:
        if not is_projected:
            raise ValueError(ErrorMessages.GEOGRAPHIC_BUFFER.format(raster_crs))
        for i, (x, y) in enumerate(points):
            label = labels[i] if labels and i < len(labels) else f"pt_{i}"
            rx, ry = tf.transform(x, y)
            inner, background = circular_values(arr, transform, rx, ry, buffer_m, background_m)
            rec = zone_record(label, inner, background, z_threshold)
            rec["center"] = [x, y]
            records.append(rec)

    if geojson:
        for label, geom in _geometries(geojson):
            geom_proj = {"type": geom["type"], "coordinates": _reproject_coords(geom["coordinates"], tf)}
            vals = polygon_values(arr, transform, geom_proj)
            records.append(zone_record(label, vals, np.array([]), z_threshold))

    return raster_crs, records


def register_analysis_tools(mcp: object, manager: object) -> None:
    """Register analysis tools with the MCP server."""

    @mcp.tool  # type: ignore[union-attr]
    async def stac_zonal_stats(
        artifact_id: str,
        points: list[list[float]] | None = None,
        buffer_m: float = 30.0,
        background_m: float | None = None,
        geojson: dict | None = None,
        zones_crs: str = "EPSG:4326",
        labels: list[str] | None = None,
        band: int = 1,
        z_threshold: float = 2.0,
        output_mode: str = "json",
    ) -> str:
        """Read out a raster's values within zones — the inference step after a fetch.

        Given a stored raster artifact (e.g. an NDVI index from stac_compute_index,
        or any GeoTIFF from stac_download_bands) and target zones, return per-zone
        statistics (n_valid, mean, std, min, max, median, p10, p90).

        Zones are either circular buffers around points, or GeoJSON polygons:
        - points: [[x, y], ...] centres in `zones_crs`, each summarised within `buffer_m`.
        - geojson: a geometry / Feature / FeatureCollection (polygons) in `zones_crs`.

        Pass `background_m` (> buffer_m) to also get a LOCAL ANOMALY readout: each
        point's mean is compared to the surrounding annulus (buffer_m..background_m)
        and reported as a z-score, with `anomalous` set when |z| >= z_threshold. This
        is the direct "is the signal at this location anomalous vs its surroundings?"
        answer — e.g. a cropmark/soil-mark over a buried feature in an NDVI raster.

        Args:
            artifact_id: A GeoTIFF raster artifact (NOT a PNG preview).
            points: Zone centres [[x, y], ...] in zones_crs (e.g. BNG eastings/northings).
            buffer_m: Circular zone radius in metres (raster must be projected).
            background_m: Outer annulus radius in metres → enables the z-score readout.
            geojson: Alternative polygon zones (geometry/Feature/FeatureCollection).
            zones_crs: CRS of points/geojson, e.g. "EPSG:27700" (BNG) or "EPSG:4326".
            labels: Optional labels for points (e.g. HER refs).
            band: 1-based band index to read.
            z_threshold: |z| at/above which a point is flagged anomalous (default 2.0).
            output_mode: "json" or "text".

        Returns:
            Per-zone statistics, plus a local z-score when background_m is given.
        """
        try:
            if not points and not geojson:
                return format_response(ErrorResponse(error=ErrorMessages.NO_ZONES), output_mode)

            store = manager._get_store()  # type: ignore[attr-defined]
            if not store:
                return format_response(
                    ErrorResponse(error=ErrorMessages.NO_ARTIFACT_STORE), output_mode
                )

            try:
                data: bytes = await store.retrieve(artifact_id)
            except Exception:
                return format_response(
                    ErrorResponse(error=ErrorMessages.ARTIFACT_NOT_FOUND.format(artifact_id)),
                    output_mode,
                )

            mime = ""
            try:
                meta_obj = await store.metadata(artifact_id)
                mime = getattr(meta_obj, "mime", "") or ""
            except Exception:
                pass
            if "tif" not in mime.lower():
                return format_response(
                    ErrorResponse(error=ErrorMessages.ARTIFACT_NOT_RASTER.format(artifact_id, mime)),
                    output_mode,
                )

            raster_crs, records = await asyncio.to_thread(
                _run, data, band, points, labels, buffer_m, background_m, geojson, zones_crs, z_threshold
            )

            zones = [ZoneStat(**rec) for rec in records]
            n_anom = sum(1 for z in zones if z.anomalous)
            msg = f"Zonal stats for {len(zones)} zone(s) on {artifact_id} (band {band})"
            if background_m:
                msg += f"; {n_anom} anomalous (|z|>={z_threshold})"

            return format_response(
                ZonalStatsResponse(
                    artifact_id=artifact_id,
                    band=band,
                    raster_crs=raster_crs,
                    zones_crs=zones_crs,
                    zone_count=len(zones),
                    zones=zones,
                    message=msg,
                ),
                output_mode,
            )
        except Exception as e:
            logger.error(f"stac_zonal_stats failed: {e}", exc_info=True)
            return format_response(ErrorResponse(error=str(e)), output_mode)
