#!/usr/bin/env python3
"""
Time Series Demo -- chuk-mcp-stac

Extract a temporal stack of satellite data over an area using the
stac_time_series tool. Searches for all scenes in a date range,
downloads the requested bands for each, and returns per-date
artifact references.

Demonstrates:
    stac_time_series (search + concurrent band downloads)

Usage:
    python examples/time_series_demo.py

Requirements:
    pip install chuk-mcp-stac
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio

from tool_runner import ToolRunner

# Colchester, tight bbox
BBOX = [0.85, 51.85, 0.95, 51.93]
DATE_RANGE = "2024-06-01/2024-08-31"
BANDS = ["red", "nir"]  # For NDVI computation across time
MAX_CLOUD_COVER = 15
MAX_ITEMS = 5


async def main() -> None:
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Time Series Demo")
    print("=" * 60)

    print("\nExtracting time series over Colchester...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")
    print(f"  bands: {BANDS}")
    print(f"  max cloud: {MAX_CLOUD_COVER}%")
    print(f"  max items: {MAX_ITEMS}")

    result = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=BANDS,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in result:
        print(f"\nTime series failed: {result['error']}")
        return

    print(f"\nTime series extracted: {result['date_count']} date(s)")
    print(f"  Collection: {result['collection']}")
    print(f"  Bands: {result['bands']}")

    if result["entries"]:
        print("\nEntries:")
        for entry in result["entries"]:
            cloud = f"{entry['cloud_cover']:.1f}%" if entry["cloud_cover"] is not None else "N/A"
            print(f"  {entry['datetime']}  cloud={cloud}  artifact={entry['artifact_ref']}")
    else:
        print("\nNo entries found. Try widening the date range or cloud cover threshold.")

    print("\n" + "=" * 60)
    print("Each entry has an artifact reference pointing to a GeoTIFF")
    print("with the requested bands for that date. Use these to compute")
    print("temporal NDVI, change detection, or other multi-date analyses.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
