#!/usr/bin/env python3
"""
Change Detection Demo -- chuk-mcp-stac

Detect seasonal vegetation change between winter and summer using
before/after scene pairs. Demonstrates the change-detection workflow:
find pairs, preview thumbnails, check coverage, then download and compare.

Demonstrates:
    stac_find_pairs -> stac_preview -> stac_coverage_check ->
    stac_download_rgb -> stac_compute_index (NDVI difference)

Usage:
    python examples/change_detection_demo.py

Output:
    examples/output/change_comparison.png

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
BEFORE_RANGE = "2024-01-01/2024-03-31"  # Winter
AFTER_RANGE = "2024-07-01/2024-09-30"  # Summer
MAX_CLOUD_COVER = 20
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
    print("chuk-mcp-stac -- Change Detection Demo")
    print("=" * 60)
    print(f"\n  bbox:   {BBOX}")
    print(f"  winter: {BEFORE_RANGE}")
    print(f"  summer: {AFTER_RANGE}")

    # Step 1: Find before/after scene pairs
    print("\nStep 1: Finding before/after scene pairs...")
    pairs_result = await runner.run(
        "stac_find_pairs",
        bbox=BBOX,
        before_range=BEFORE_RANGE,
        after_range=AFTER_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
    )

    if "error" in pairs_result:
        print(f"  ERROR: {pairs_result['error']}")
        sys.exit(1)

    pair_count = pairs_result["pair_count"]
    print(f"  Found {pair_count} scene pair(s)")

    if pair_count == 0:
        print("\nNo matching pairs found. Try widening the date ranges or cloud cover.")
        sys.exit(1)

    for pair in pairs_result["pairs"][:3]:
        print(
            f"    before={pair['before_scene_id'][:30]}...  "
            f"after={pair['after_scene_id'][:30]}...  "
            f"overlap={pair['overlap_percent']:.1f}%"
        )

    # Pick the best pair (highest overlap)
    best_pair = pairs_result["pairs"][0]
    before_id = best_pair["before_scene_id"]
    after_id = best_pair["after_scene_id"]
    print(f"\n  Best pair: overlap={best_pair['overlap_percent']:.1f}%")
    print(f"    before: {before_id}")
    print(f"    after:  {after_id}")

    # Step 2: Preview thumbnails for quick visual check
    print("\nStep 2: Getting preview thumbnails...")
    before_preview = await runner.run("stac_preview", scene_id=before_id)
    after_preview = await runner.run("stac_preview", scene_id=after_id)

    if "error" not in before_preview:
        print(f"  Before preview: {before_preview.get('preview_url', 'N/A')}")
    else:
        print(f"  Before preview: {before_preview.get('error', 'not available')}")

    if "error" not in after_preview:
        print(f"  After preview:  {after_preview.get('preview_url', 'N/A')}")
    else:
        print(f"  After preview:  {after_preview.get('error', 'not available')}")

    # Step 3: Check coverage
    print("\nStep 3: Checking spatial coverage...")
    coverage = await runner.run(
        "stac_coverage_check",
        bbox=BBOX,
        scene_ids=[before_id, after_id],
    )

    if "error" in coverage:
        print(f"  ERROR: {coverage['error']}")
    else:
        print(f"  Coverage: {coverage['coverage_percent']:.1f}%")
        print(f"  Fully covered: {coverage['fully_covered']}")
        if coverage.get("uncovered_areas"):
            print(f"  Uncovered areas: {coverage['uncovered_areas']}")

    # Step 4: Download RGB for both scenes
    print("\nStep 4: Downloading RGB composites...")
    store = runner.manager._get_store()

    print("  Downloading winter scene...")
    before_rgb = await runner.run("stac_download_rgb", scene_id=before_id, bbox=BBOX)
    if "error" in before_rgb:
        print(f"  ERROR: {before_rgb['error']}")
        sys.exit(1)
    print(f"  Before: {before_rgb['shape']}  CRS: {before_rgb['crs']}")

    print("  Downloading summer scene...")
    after_rgb = await runner.run("stac_download_rgb", scene_id=after_id, bbox=BBOX)
    if "error" in after_rgb:
        print(f"  ERROR: {after_rgb['error']}")
        sys.exit(1)
    print(f"  After:  {after_rgb['shape']}  CRS: {after_rgb['crs']}")

    # Read raster data
    before_data = await store.retrieve(before_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(before_data)) as src:
        before_stack = src.read()

    after_data = await store.retrieve(after_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(after_data)) as src:
        after_stack = src.read()

    # Step 5: Compute NDVI for both scenes
    print("\nStep 5: Computing NDVI for both scenes...")
    before_ndvi_result = await runner.run(
        "stac_compute_index", scene_id=before_id, index_name="ndvi", bbox=BBOX
    )
    if "error" in before_ndvi_result:
        print(f"  ERROR: {before_ndvi_result['error']}")
        sys.exit(1)
    print(f"  Winter NDVI range: {before_ndvi_result['value_range']}")

    after_ndvi_result = await runner.run(
        "stac_compute_index", scene_id=after_id, index_name="ndvi", bbox=BBOX
    )
    if "error" in after_ndvi_result:
        print(f"  ERROR: {after_ndvi_result['error']}")
        sys.exit(1)
    print(f"  Summer NDVI range: {after_ndvi_result['value_range']}")

    # Read NDVI data
    before_ndvi_data = await store.retrieve(before_ndvi_result["artifact_ref"])
    with rasterio.open(io.BytesIO(before_ndvi_data)) as src:
        before_ndvi = src.read(1)

    after_ndvi_data = await store.retrieve(after_ndvi_result["artifact_ref"])
    with rasterio.open(io.BytesIO(after_ndvi_data)) as src:
        after_ndvi = src.read(1)

    # Compute NDVI difference (summer - winter)
    ndvi_diff = after_ndvi - before_ndvi
    print("\n  NDVI difference (summer - winter):")
    print(
        f"    min={np.nanmin(ndvi_diff):.3f}  max={np.nanmax(ndvi_diff):.3f}  "
        f"mean={np.nanmean(ndvi_diff):.3f}"
    )
    print("    Positive = greener in summer, Negative = less vegetation")

    # Step 6: Render comparison
    print("\nStep 6: Rendering comparison...")
    before_img = normalize_rgb(before_stack)
    after_img = normalize_rgb(after_stack)

    fig, axes = plt.subplots(1, 3, figsize=(20, 7))

    axes[0].imshow(before_img)
    axes[0].set_title(f"Winter\n{best_pair['before_datetime'][:10]}", fontsize=12)
    axes[0].axis("off")

    axes[1].imshow(after_img)
    axes[1].set_title(f"Summer\n{best_pair['after_datetime'][:10]}", fontsize=12)
    axes[1].axis("off")

    im = axes[2].imshow(ndvi_diff, cmap="RdYlGn", vmin=-0.4, vmax=0.4)
    axes[2].set_title("NDVI Difference\n(Summer - Winter)", fontsize=12)
    axes[2].axis("off")
    fig.colorbar(im, ax=axes[2], label="NDVI change", shrink=0.7)

    fig.suptitle(
        "Seasonal Change Detection -- Colchester, UK\n"
        "Sentinel-2 | Green = vegetation growth | Red = vegetation loss",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "change_comparison.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Before: {before_id}")
    print(f"  After:  {after_id}")
    print(f"  Overlap: {best_pair['overlap_percent']:.1f}%")
    print(f"  NDVI change: mean={np.nanmean(ndvi_diff):.3f}")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
