#!/usr/bin/env python3
"""
Temporal Composite Demo -- chuk-mcp-stac

Create cloud-free median and mean composites from multiple satellite scenes.
This is the standard technique for producing clean basemaps from cloudy
time-series imagery. Also demonstrates catalog exploration via
list_collections and queryables.

Demonstrates:
    stac_list_collections -> stac_queryables -> stac_search ->
    stac_temporal_composite (median, mean)

Usage:
    python examples/temporal_composite_demo.py

Output:
    examples/output/temporal_comparison.png

Requirements:
    pip install chuk-mcp-stac matplotlib
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio
import io
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio

from tool_runner import ToolRunner

# -- Configuration -----------------------------------------------------------

BBOX = [0.85, 51.85, 0.95, 51.93]  # Colchester, Essex, UK
DATE_RANGE = "2024-06-01/2024-08-31"  # Summer, 3 months for scene variety
BANDS = ["red", "green", "blue"]
MAX_CLOUD_COVER = 40  # Relaxed -- median composite handles cloudy scenes
MAX_ITEMS = 8
OUTPUT_DIR = Path(__file__).parent / "output"


# -- Rendering helpers -------------------------------------------------------


def normalize_rgb(rgb_stack: np.ndarray) -> np.ndarray:
    """Normalize Sentinel-2 reflectance to 0-1 using 2nd-98th percentile."""
    rgb = rgb_stack.astype(np.float32)
    for i in range(3):
        band = rgb[i]
        valid = band[band > 0]
        if len(valid) == 0:
            continue
        p2, p98 = np.percentile(valid, [2, 98])
        band = np.clip(band, p2, p98)
        band = (band - p2) / (p98 - p2 + 1e-10)
        rgb[i] = band
    return np.transpose(rgb, (1, 2, 0))


# -- Main pipeline -----------------------------------------------------------


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Temporal Composite Demo")
    print("=" * 60)

    # Step 1: Explore available collections
    print("\nStep 1: Listing collections in Earth Search catalog...")
    collections = await runner.run("stac_list_collections", catalog="earth_search")

    if "error" in collections:
        print(f"  ERROR: {collections['error']}")
        sys.exit(1)

    coll_list = collections.get("collections", [])
    print(f"  Found {len(coll_list)} collection(s):")
    for coll in coll_list[:8]:
        desc = coll.get("description", "")[:60]
        print(f"    {coll['collection_id']}: {desc}")
    if len(coll_list) > 8:
        print(f"    ... and {len(coll_list) - 8} more")

    # Step 2: Discover queryable properties
    print("\nStep 2: Discovering queryable properties for sentinel-2-l2a...")
    queryables = await runner.run(
        "stac_queryables",
        catalog="earth_search",
        collection="sentinel-2-l2a",
    )

    if "error" in queryables:
        print(f"  ERROR: {queryables['error']}")
        # Non-fatal: queryables API may not be supported by all catalogs
        print("  (Continuing without queryable info)")
    else:
        qlist = queryables.get("queryables", [])
        print(f"  Found {queryables.get('queryable_count', len(qlist))} queryable properties:")
        for q in qlist[:10]:
            desc = f" -- {q['description']}" if q.get("description") else ""
            enum = (
                f" [{', '.join(str(v) for v in q['enum_values'][:3])}...]"
                if q.get("enum_values")
                else ""
            )
            print(f"    {q['name']} ({q.get('type', '?')}){desc}{enum}")

    # Step 3: Search with relaxed cloud cover to show many scenes
    print(f"\nStep 3: Searching for scenes (cloud cover up to {MAX_CLOUD_COVER}%)...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")

    search_result = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if search_result["scene_count"] == 0:
        print("\nNo scenes found. Try widening the date range.")
        sys.exit(1)

    print(f"\n  Found {search_result['scene_count']} scene(s):")
    for scene in search_result["scenes"]:
        print(f"    {scene['scene_id']}  cloud={scene['cloud_cover']}%  {scene['datetime'][:10]}")

    print("\n  These scenes may have clouds individually, but a median")
    print("  composite combines them to produce a clean, cloud-free result.")

    store = runner.manager._get_store()

    # Step 4: Create median temporal composite
    print(f"\nStep 4: Creating median composite from {DATE_RANGE}...")
    print(f"  bands: {BANDS}")
    print("  method: median (most robust for cloud removal)")

    median_result = await runner.run(
        "stac_temporal_composite",
        bbox=BBOX,
        bands=BANDS,
        date_range=DATE_RANGE,
        method="median",
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in median_result:
        print(f"  ERROR: {median_result['error']}")
        sys.exit(1)

    print(f"  Artifact: {median_result['artifact_ref']}")
    print(f"  Shape: {median_result['shape']}  CRS: {median_result['crs']}")
    print(f"  Source scenes: {len(median_result.get('scene_ids', []))}")

    median_data = await store.retrieve(median_result["artifact_ref"])
    with rasterio.open(io.BytesIO(median_data)) as src:
        median_stack = src.read()

    # Step 5: Create mean composite for comparison
    print("\nStep 5: Creating mean composite for comparison...")
    print("  method: mean (smoother but may show cloud ghosting)")

    mean_result = await runner.run(
        "stac_temporal_composite",
        bbox=BBOX,
        bands=BANDS,
        date_range=DATE_RANGE,
        method="mean",
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in mean_result:
        print(f"  ERROR: {mean_result['error']}")
        sys.exit(1)

    print(f"  Artifact: {mean_result['artifact_ref']}")
    print(f"  Shape: {mean_result['shape']}")

    mean_data = await store.retrieve(mean_result["artifact_ref"])
    with rasterio.open(io.BytesIO(mean_data)) as src:
        mean_stack = src.read()

    # Step 6: Render comparison
    print("\nStep 6: Rendering comparison...")
    median_img = normalize_rgb(median_stack)
    mean_img = normalize_rgb(mean_stack)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    axes[0].imshow(median_img)
    axes[0].set_title("Median Composite", fontsize=13)
    axes[0].text(
        0.5,
        -0.05,
        "Most robust -- removes clouds and outliers",
        transform=axes[0].transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    axes[0].axis("off")

    axes[1].imshow(mean_img)
    axes[1].set_title("Mean Composite", fontsize=13)
    axes[1].text(
        0.5,
        -0.05,
        "Smoother -- but cloud ghosting possible",
        transform=axes[1].transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    axes[1].axis("off")

    scene_count = len(median_result.get("scene_ids", []))
    fig.suptitle(
        f"Temporal Composites -- Colchester, UK\n"
        f"Sentinel-2 | {DATE_RANGE} | {scene_count} scenes | "
        f"cloud cover up to {MAX_CLOUD_COVER}%",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "temporal_comparison.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Date range: {DATE_RANGE}")
    print(f"  Source scenes: {scene_count}")
    print("  Methods: median (cloud-free), mean (smooth)")
    print(f"  Shape: {median_stack.shape[1]}x{median_stack.shape[2]} pixels")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
