#!/usr/bin/env python3
"""
Mosaic Demo -- chuk-mcp-stac

Search for multiple Sentinel-2 scenes and merge them into a single
mosaic raster using the stac_mosaic tool.

Demonstrates:
    stac_search -> stac_mosaic

Usage:
    python examples/mosaic_demo.py

Requirements:
    pip install chuk-mcp-stac
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio

from tool_runner import ToolRunner

# Wider bbox to catch multiple tiles around the Essex coast
BBOX = [0.5, 51.7, 1.2, 52.0]
DATE_RANGE = "2024-06-01/2024-08-31"
MAX_CLOUD_COVER = 15
MAX_ITEMS = 5
BANDS = ["red", "green", "blue"]


async def main() -> None:
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Mosaic Demo")
    print("=" * 60)

    # Step 1: Search for scenes
    print("\nSearching for scenes over wider Essex coast area...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")

    result = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if result["scene_count"] < 2:
        print(f"\nNeed at least 2 scenes for mosaic, found {result['scene_count']}.")
        print("Try widening the date range or bbox.")
        return

    print(f"\nFound {result['scene_count']} scene(s):")
    for scene in result["scenes"]:
        print(f"  {scene['scene_id']}  cloud={scene['cloud_cover']}%  date={scene['datetime']}")

    # Step 2: Take the first 2 scenes and mosaic them
    scene_ids = [s["scene_id"] for s in result["scenes"][:2]]
    print(f"\nCreating mosaic from {len(scene_ids)} scenes...")
    print(f"  Scenes: {scene_ids}")
    print(f"  Bands: {BANDS}")

    mosaic_result = await runner.run(
        "stac_mosaic",
        scene_ids=scene_ids,
        bands=BANDS,
        bbox=BBOX,
    )

    if "error" in mosaic_result:
        print(f"\nMosaic failed: {mosaic_result['error']}")
        return

    print("\nMosaic complete:")
    print(f"  Artifact: {mosaic_result['artifact_ref']}")
    print(f"  CRS: {mosaic_result['crs']}")
    print(f"  Shape: {mosaic_result['shape']}")
    print(f"  Message: {mosaic_result['message']}")

    print("\n" + "=" * 60)
    print("The mosaic artifact can be retrieved from the artifact store")
    print("for further processing or visualization.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
