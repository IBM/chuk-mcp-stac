#!/usr/bin/env python3
"""
Map Tools Demo -- chuk-mcp-stac

Demonstrates stac_map and stac_pairs_map by running a real STAC search,
then building multi-layer map structured content from the results.

Demonstrates:
    stac_search -> stac_map
    stac_find_pairs -> stac_pairs_map

Usage:
    python examples/map_demo.py

Requirements:
    pip install chuk-mcp-stac chuk-view-schemas
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from tool_runner import ToolRunner

# -- Configuration ------------------------------------------------------------

BBOX = [0.85, 51.85, 0.95, 51.93]  # Colchester, Essex, UK
BEFORE_RANGE = "2024-01-01/2024-03-31"
AFTER_RANGE = "2024-07-01/2024-09-30"
MAX_CLOUD = 30
OUTPUT_DIR = Path(__file__).parent / "output"


# -- Helpers ------------------------------------------------------------------


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}\n")


def print_map(mc: dict) -> None:
    """Print a human-readable summary of a MapContent structuredContent dict."""
    print(f"  type    : {mc.get('type')}")
    print(f"  center  : lat={mc['center']['lat']:.4f}, lon={mc['center']['lon']:.4f}")
    print(f"  zoom    : {mc.get('zoom')}")
    print(f"  basemap : {mc.get('basemap')}")
    layers = mc.get("layers", [])
    print(f"  layers  : {len(layers)}")
    for layer in layers:
        feats = layer.get("features", {}).get("features", [])
        print(f"    [{layer['id']}]  {layer['label']}  —  {len(feats)} feature(s)")
        for feat in feats[:2]:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {}).get("type", "?")
            cc = props.get("cloud_cover_pct")
            dt = props.get("datetime", "")[:10]
            sid = props.get("scene_id", "")[:40]
            cc_str = f"  cloud={cc}%" if cc is not None else ""
            print(f"      {geom}  {sid}  {dt}{cc_str}")
        if len(feats) > 2:
            print(f"      ... and {len(feats) - 2} more")


# -- Main demo ----------------------------------------------------------------


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Map Tools Demo")
    print("=" * 60)
    print(f"Study area : Colchester, Essex  {BBOX}")

    # ------------------------------------------------------------------ 1
    section("1. Search for Sentinel-2 scenes")

    search = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range="2024-01-01/2024-12-31",
        max_cloud_cover=MAX_CLOUD,
        max_items=8,
    )
    scenes = search.get("scenes", [])
    print(f"  Found {len(scenes)} scene(s)")
    for s in scenes:
        cc = s.get("cloud_cover")
        cc_str = f"  cloud={cc:.1f}%" if cc is not None else ""
        print(f"  • {s['scene_id'][:50]}  {s['datetime'][:10]}{cc_str}")

    if not scenes:
        print("  No scenes found — check network / STAC catalog.")
        return

    scene_ids = ",".join(s["scene_id"] for s in scenes)

    # ------------------------------------------------------------------ 2
    section("2. stac_map — scene footprint map")

    map_result = await runner.run_map("stac_map", scene_ids=scene_ids, basemap="osm")
    print_map(map_result)

    out_path = OUTPUT_DIR / "stac_map.json"
    out_path.write_text(json.dumps(map_result, indent=2))
    print(f"\n  Full map JSON saved to: {out_path}")

    # ------------------------------------------------------------------ 3
    section("3. Find before/after scene pairs")

    pairs_result = await runner.run(
        "stac_find_pairs",
        bbox=BBOX,
        before_range=BEFORE_RANGE,
        after_range=AFTER_RANGE,
        max_cloud_cover=MAX_CLOUD,
    )
    pairs = pairs_result.get("pairs", [])
    print(f"  Found {len(pairs)} pair(s)")
    for p in pairs[:3]:
        print(
            f"  • before={p['before_scene_id'][:35]}  "
            f"after={p['after_scene_id'][:35]}  "
            f"overlap={p['overlap_percent']:.1f}%"
        )

    if not pairs:
        print("  No pairs found — skipping pairs map.")
        return

    # ------------------------------------------------------------------ 4
    section("4. stac_pairs_map — before/after change detection map")

    before_ids = ",".join(p["before_scene_id"] for p in pairs[:4])
    after_ids = ",".join(p["after_scene_id"] for p in pairs[:4])

    pairs_map = await runner.run_map(
        "stac_pairs_map",
        before_scene_ids=before_ids,
        after_scene_ids=after_ids,
        basemap="satellite",
    )
    print_map(pairs_map)

    out_path = OUTPUT_DIR / "stac_pairs_map.json"
    out_path.write_text(json.dumps(pairs_map, indent=2))
    print(f"\n  Full map JSON saved to: {out_path}")

    # ------------------------------------------------------------------ 5
    section("5. Verification summary")

    stac_map_layers = len(map_result.get("layers", []))
    pairs_map_layers = len(pairs_map.get("layers", []))
    all_pass = (
        map_result.get("type") == "map"
        and stac_map_layers >= 1
        and pairs_map.get("type") == "map"
        and pairs_map_layers == 2
    )

    print(f"  stac_map       type=map ✓   layers={stac_map_layers}")
    print(f"  stac_pairs_map type=map ✓   layers={pairs_map_layers} (before + after)")
    print(f"\n  {'✓ All checks passed' if all_pass else '✗ Some checks failed'}")


if __name__ == "__main__":
    asyncio.run(main())
