#!/usr/bin/env python3
"""
Landsat Demo -- chuk-mcp-stac

Search for Landsat Collection 2 Level-2 imagery and demonstrate
the Landsat-specific band naming conventions.

Key difference from Sentinel-2: Landsat uses "nir08" (not "nir")
for the near-infrared band.

Demonstrates:
    stac_capabilities (band mappings)
    stac_search (Landsat collection)
    stac_describe_scene

Usage:
    python examples/landsat_demo.py

Requirements:
    pip install chuk-mcp-stac
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio

from tool_runner import ToolRunner

# San Francisco Bay Area -- good Landsat coverage
BBOX = [-122.5, 37.5, -122.0, 37.9]
DATE_RANGE = "2024-06-01/2024-08-31"
COLLECTION = "landsat-c2-l2"
MAX_CLOUD_COVER = 20
MAX_ITEMS = 3


async def main() -> None:
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Landsat Demo")
    print("=" * 60)

    # Step 1: Show band mapping differences
    caps = await runner.run("stac_capabilities")

    print("\nBand Naming Comparison:")
    s2_bands = caps["band_mappings"]["sentinel-2"]
    ls_bands = caps["band_mappings"]["landsat"]

    print(f"\n  Sentinel-2 bands ({len(s2_bands)}):")
    print(f"    {', '.join(s2_bands)}")
    print(f"\n  Landsat bands ({len(ls_bands)}):")
    print(f"    {', '.join(ls_bands)}")

    print("\n  Key difference: Landsat uses 'nir08' not 'nir'")
    print("  Landsat also has thermal bands (lwir11, lwir12)")

    # Step 2: Search for Landsat scenes
    print(f"\nSearching {COLLECTION} over San Francisco Bay...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")

    result = await runner.run(
        "stac_search",
        bbox=BBOX,
        collection=COLLECTION,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if result["scene_count"] == 0:
        print("\nNo Landsat scenes found. This may be due to the collection name")
        print("or STAC catalog availability. Try adjusting parameters.")
        return

    print(f"\nFound {result['scene_count']} Landsat scene(s):")
    for scene in result["scenes"]:
        print(f"  {scene['scene_id']}")
        print(f"    date={scene['datetime']}  cloud={scene['cloud_cover']}%")
        print(f"    assets={scene['asset_count']} bands")

    # Step 3: Describe the best scene
    best = result["scenes"][0]
    print(f"\nDescribing scene: {best['scene_id']}")

    detail = await runner.run("stac_describe_scene", scene_id=best["scene_id"])

    print(f"  CRS: {detail['crs']}")
    print(f"  Assets ({len(detail['assets'])}):")
    for asset in detail["assets"]:
        res = f"  {asset['resolution_m']}m" if asset["resolution_m"] else ""
        print(f"    {asset['key']}{res}  ({asset['media_type'] or 'unknown'})")

    print("\n" + "=" * 60)
    print("To download Landsat bands, use the same tools as Sentinel-2:")
    print(f'  stac_download_bands(scene_id="{best["scene_id"]}",')
    print('    bands=["red", "nir08", "swir16"])')
    print("\nNote: use 'nir08' for NIR, not 'nir'")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
