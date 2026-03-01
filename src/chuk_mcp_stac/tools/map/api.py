"""Map tools — STAC scene footprint and change-detection visualisation."""

from __future__ import annotations

import logging
import math
from typing import Any

from chuk_view_schemas import LayerStyle, MapContent, MapLayer, PopupTemplate
from chuk_view_schemas.chuk_mcp import map_tool
from chuk_view_schemas.map import ClusterConfig, MapCenter, MapControls

logger = logging.getLogger(__name__)


# ============================================================================
# Styling
# ============================================================================

_COLLECTION_STYLE: dict[str, LayerStyle] = {
    "sentinel-2-l2a": LayerStyle(color="#1565c0", fill_color="#42a5f5", fill_opacity=0.3, weight=2),
    "sentinel-2-c1-l2a": LayerStyle(
        color="#1565c0", fill_color="#42a5f5", fill_opacity=0.3, weight=2
    ),
    "landsat-c2-l2": LayerStyle(color="#e65100", fill_color="#ff9800", fill_opacity=0.3, weight=2),
    "sentinel-1-grd": LayerStyle(color="#1b5e20", fill_color="#4caf50", fill_opacity=0.3, weight=2),
    "cop-dem-glo-30": LayerStyle(color="#4a148c", fill_color="#ab47bc", fill_opacity=0.3, weight=2),
}
_DEFAULT_STYLE = LayerStyle(color="#546e7a", fill_color="#90a4ae", fill_opacity=0.3, weight=2)

_PAIRS_STYLE: dict[str, LayerStyle] = {
    "before": LayerStyle(color="#1565c0", fill_color="#42a5f5", fill_opacity=0.3, weight=2),
    "after": LayerStyle(color="#b71c1c", fill_color="#ef5350", fill_opacity=0.3, weight=2),
}

_COLLECTION_LABELS: dict[str, str] = {
    "sentinel-2-l2a": "Sentinel-2 L2A",
    "sentinel-2-c1-l2a": "Sentinel-2 C1 L2A",
    "landsat-c2-l2": "Landsat C2 L2",
    "sentinel-1-grd": "Sentinel-1 GRD",
    "cop-dem-glo-30": "Copernicus DEM GLO-30",
}

_EMPTY_UK = MapContent(
    center=MapCenter(lat=54.0, lon=-2.0),
    zoom=5,
    basemap="osm",  # type: ignore[arg-type]
    layers=[],
)


# ============================================================================
# Private helpers
# ============================================================================


def _bbox_to_polygon(bbox: list[float]) -> dict[str, Any]:
    """Convert [west, south, east, north] bbox to a GeoJSON Polygon."""
    w, s, e, n = bbox[:4]
    return {
        "type": "Polygon",
        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    }


def _zoom_from_extent(lat_extent: float, lon_extent: float) -> int:
    extent = max(lat_extent, lon_extent, 0.001)
    return max(5, min(14, round(10 - math.log2(extent))))


def _scene_to_feature(scene_id: str, item: Any) -> dict[str, Any] | None:
    """Convert a cached STACItem to a GeoJSON Feature (bbox polygon)."""
    if not item.bbox or len(item.bbox) < 4:
        return None
    props: dict[str, Any] = {
        "scene_id": scene_id,
        "collection": item.collection or "",
        "datetime": item.properties.datetime or "",
    }
    if item.properties.cloud_cover is not None:
        props["cloud_cover_pct"] = round(item.properties.cloud_cover, 1)
    thumb = item.assets.get("thumbnail") or item.assets.get("rendered_preview")
    if thumb:
        props["thumbnail_url"] = thumb.href
    return {
        "type": "Feature",
        "geometry": _bbox_to_polygon(list(item.bbox)),
        "properties": props,
    }


def _center_and_zoom(bboxes: list[list[float]]) -> tuple[float, float, int]:
    lons = [b[0] for b in bboxes] + [b[2] for b in bboxes]
    lats = [b[1] for b in bboxes] + [b[3] for b in bboxes]
    clat = (min(lats) + max(lats)) / 2
    clon = (min(lons) + max(lons)) / 2
    zoom = _zoom_from_extent(max(lats) - min(lats), max(lons) - min(lons))
    return clat, clon, zoom


# ============================================================================
# Tool registration
# ============================================================================


def register_map_tools(mcp: object, manager: object) -> None:
    """Register STAC map visualisation tools."""

    @map_tool(  # type: ignore[arg-type]
        mcp,
        "stac_map",
        description=(
            "Visualise STAC scene search results as a multi-layer footprint map. "
            "Scenes appear as bounding-box polygons, grouped by collection, with "
            "cloud cover, acquisition date, and thumbnail URL in the popup. "
            "Run stac_search first, then pass the scene_ids here."
        ),
        read_only_hint=True,
    )
    async def stac_map(
        scene_ids: str = "",
        basemap: str = "osm",
    ) -> MapContent:
        """Visualise STAC scene footprints as bbox polygons on an interactive map.

        Shows scenes from stac_search as bounding-box polygon footprints grouped
        by collection. Popup shows cloud cover, acquisition date, and thumbnail URL.

        Args:
            scene_ids: Comma-separated scene IDs from stac_search results
            basemap: Map background — "osm" (default), "satellite", "terrain", "dark"

        Returns:
            Multi-layer scene footprint map, one layer per collection

        Tips for LLMs:
            - Run stac_search first, then pass all scene_id values here
            - Each collection is a separately togglable layer
            - Cloud cover is shown in the popup — click a footprint to see it
            - Satellite basemap helps assess cloud cover visually
        """
        if basemap not in ("osm", "satellite", "terrain", "dark"):
            basemap = "osm"

        ids = [s.strip() for s in scene_ids.split(",") if s.strip()]
        if not ids:
            return MapContent(
                center=MapCenter(lat=30.0, lon=0.0),
                zoom=2,
                basemap=basemap,  # type: ignore[arg-type]
                layers=[],
            )

        by_collection: dict[str, list[dict[str, Any]]] = {}
        all_bboxes: list[list[float]] = []

        for sid in ids:
            item = manager.get_cached_scene(sid)  # type: ignore[union-attr]
            if item is None:
                continue
            feat = _scene_to_feature(sid, item)
            if feat is None:
                continue
            col = item.collection or "unknown"
            by_collection.setdefault(col, []).append(feat)
            all_bboxes.append(list(item.bbox[:4]))

        if not all_bboxes:
            return MapContent(
                center=MapCenter(lat=30.0, lon=0.0),
                zoom=2,
                basemap=basemap,  # type: ignore[arg-type]
                layers=[],
            )

        clat, clon, zoom = _center_and_zoom(all_bboxes)
        popup = PopupTemplate(
            title="{scene_id}",
            fields=["collection", "datetime", "cloud_cover_pct", "thumbnail_url"],
        )
        cluster = ClusterConfig(enabled=False, radius=40)
        layers: list[MapLayer] = []

        for col, feats in by_collection.items():
            layers.append(
                MapLayer(
                    id=f"scenes_{col.replace('-', '_')}",
                    label=f"{_COLLECTION_LABELS.get(col, col)} ({len(feats)})",
                    features={"type": "FeatureCollection", "features": feats},
                    style=_COLLECTION_STYLE.get(col, _DEFAULT_STYLE),
                    cluster=cluster,
                    popup=popup,
                )
            )

        return MapContent(
            center=MapCenter(lat=clat, lon=clon),
            zoom=zoom,
            basemap=basemap,  # type: ignore[arg-type]
            layers=layers,
            controls=MapControls(zoom=True, layers=True, scale=True, fullscreen=True),
        )

    @map_tool(  # type: ignore[arg-type]
        mcp,
        "stac_pairs_map",
        description=(
            "Visualise before/after scene pairs from stac_find_pairs as a two-layer map. "
            "Blue = before, red = after. Toggle layers to compare footprint coverage "
            "between time periods."
        ),
        read_only_hint=True,
    )
    async def stac_pairs_map(
        before_scene_ids: str = "",
        after_scene_ids: str = "",
        basemap: str = "satellite",
    ) -> MapContent:
        """Visualise before/after STAC scene pairs as a two-layer footprint map.

        Shows before (blue) and after (red) scenes from stac_find_pairs as bbox
        polygon footprints. Toggle layers to compare spatial coverage between
        the two time periods.

        Args:
            before_scene_ids: Comma-separated scene IDs for the before period
            after_scene_ids: Comma-separated scene IDs for the after period
            basemap: Map background — "satellite" (default), "osm", "terrain", "dark"

        Returns:
            Two-layer before/after scene footprint map

        Tips for LLMs:
            - Run stac_find_pairs first, then pass before_scene_id and after_scene_id
              values from each pair returned
            - Satellite basemap helps visually assess footprint coverage
            - Toggle layers to isolate before vs after coverage
            - Overlapping footprints indicate good spatial coverage for comparison
        """
        if basemap not in ("osm", "satellite", "terrain", "dark"):
            basemap = "satellite"

        before_ids = [s.strip() for s in before_scene_ids.split(",") if s.strip()]
        after_ids = [s.strip() for s in after_scene_ids.split(",") if s.strip()]
        all_bboxes: list[list[float]] = []
        cluster = ClusterConfig(enabled=False, radius=40)
        popup = PopupTemplate(
            title="{scene_id}",
            fields=["collection", "datetime", "cloud_cover_pct"],
        )
        layers: list[MapLayer] = []

        def _build_layer(
            ids: list[str], layer_id: str, label_prefix: str, style: LayerStyle
        ) -> MapLayer | None:
            feats = []
            for sid in ids:
                item = manager.get_cached_scene(sid)  # type: ignore[union-attr]
                if item is None:
                    continue
                feat = _scene_to_feature(sid, item)
                if feat is None:
                    continue
                feats.append(feat)
                all_bboxes.append(list(item.bbox[:4]))
            if not feats:
                return None
            return MapLayer(
                id=layer_id,
                label=f"{label_prefix} ({len(feats)})",
                features={"type": "FeatureCollection", "features": feats},
                style=style,
                cluster=cluster,
                popup=popup,
            )

        before_layer = _build_layer(before_ids, "before", "Before", _PAIRS_STYLE["before"])
        after_layer = _build_layer(after_ids, "after", "After", _PAIRS_STYLE["after"])
        if before_layer:
            layers.append(before_layer)
        if after_layer:
            layers.append(after_layer)

        if not all_bboxes:
            return MapContent(
                center=MapCenter(lat=30.0, lon=0.0),
                zoom=2,
                basemap=basemap,  # type: ignore[arg-type]
                layers=[],
            )

        clat, clon, zoom = _center_and_zoom(all_bboxes)
        return MapContent(
            center=MapCenter(lat=clat, lon=clon),
            zoom=zoom,
            basemap=basemap,  # type: ignore[arg-type]
            layers=layers,
            controls=MapControls(zoom=True, layers=True, scale=True, fullscreen=True),
        )
