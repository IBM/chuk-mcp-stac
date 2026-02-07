#!/usr/bin/env python3
"""
UK Flooding -- Before and After Storm Babet

Storm Babet (October 2023) caused severe flooding across eastern England.
Satellite imagery with NDWI (water index) reveals the flood extent --
water where there shouldn't be water.

Demonstrates:
    stac_search -> stac_compute_index (ndwi) with cloud_mask
    Before/after flood comparison

Usage:
    python examples/uk_flooding_demo.py

Output:
    examples/output/uk_flooding_comparison.png

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

BBOX = [-0.6, 53.1, 0.1, 53.4]  # Lincolnshire
PRE_STORM = "2023-09-01/2023-10-15"  # Before Storm Babet (wider window)
POST_STORM = "2023-10-20/2023-11-15"  # After Storm Babet (wider window)
OUTPUT_DIR = Path(__file__).parent / "output"


def normalize_rgb(rgb_stack: np.ndarray) -> np.ndarray:
    """Normalize reflectance to 0-1 using 2nd-98th percentile."""
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


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("UK Flooding -- Storm Babet (October 2023)")
    print("=" * 60)
    print(f"\n  bbox: {BBOX} (Lincolnshire)")
    print(f"  pre-storm:  {PRE_STORM}")
    print(f"  post-storm: {POST_STORM}")

    # Step 1: Find pre-storm scene
    print("\nStep 1: Searching for pre-storm baseline...")
    pre = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=PRE_STORM,
        max_cloud_cover=30,
        max_items=5,
    )
    if pre["scene_count"] == 0:
        print("  No pre-storm scenes found.")
        sys.exit(1)

    pre_scene = pre["scenes"][0]
    print(f"  Found: {pre_scene['scene_id']}  cloud={pre_scene['cloud_cover']}%")

    # Step 2: Find post-storm scene (accept more cloud -- storm aftermath)
    print("\nStep 2: Searching for post-storm imagery...")
    post = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=POST_STORM,
        max_cloud_cover=50,
        max_items=5,
    )
    if post["scene_count"] == 0:
        print("  No post-storm scenes found.")
        sys.exit(1)

    post_scene = post["scenes"][0]
    print(f"  Found: {post_scene['scene_id']}  cloud={post_scene['cloud_cover']}%")

    store = runner.manager._get_store()

    # Step 3: Download RGB for visual context
    print("\nStep 3: Downloading RGB for visual comparison...")
    pre_rgb = await runner.run("stac_download_rgb", scene_id=pre_scene["scene_id"], bbox=BBOX)
    post_rgb = await runner.run("stac_download_rgb", scene_id=post_scene["scene_id"], bbox=BBOX)

    pre_rgb_data = await store.retrieve(pre_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(pre_rgb_data)) as src:
        pre_rgb_stack = src.read()

    post_rgb_data = await store.retrieve(post_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(post_rgb_data)) as src:
        post_rgb_stack = src.read()

    # Step 4: Compute NDWI with cloud masking
    print("\nStep 4: Computing NDWI (water index) with cloud masking...")
    pre_ndwi = await runner.run(
        "stac_compute_index",
        scene_id=pre_scene["scene_id"],
        index_name="ndwi",
        bbox=BBOX,
        cloud_mask=True,
    )
    if "error" in pre_ndwi:
        print(f"  Pre-storm NDWI error: {pre_ndwi['error']}")
        sys.exit(1)
    print(f"  Pre-storm NDWI:  {pre_ndwi['value_range']}")

    post_ndwi = await runner.run(
        "stac_compute_index",
        scene_id=post_scene["scene_id"],
        index_name="ndwi",
        bbox=BBOX,
        cloud_mask=True,
    )
    if "error" in post_ndwi:
        print(f"  Post-storm NDWI error: {post_ndwi['error']}")
        sys.exit(1)
    print(f"  Post-storm NDWI: {post_ndwi['value_range']}")

    # Read NDWI arrays
    pre_ndwi_data = await store.retrieve(pre_ndwi["artifact_ref"])
    with rasterio.open(io.BytesIO(pre_ndwi_data)) as src:
        pre_ndwi_arr = src.read(1)

    post_ndwi_data = await store.retrieve(post_ndwi["artifact_ref"])
    with rasterio.open(io.BytesIO(post_ndwi_data)) as src:
        post_ndwi_arr = src.read(1)

    # Threshold: NDWI > 0.0 indicates water
    pre_water = np.nansum(pre_ndwi_arr > 0.0)
    post_water = np.nansum(post_ndwi_arr > 0.0)
    total_pixels = pre_ndwi_arr.size
    print(f"\n  Water pixels before: {pre_water:,} ({100 * pre_water / total_pixels:.1f}%)")
    print(f"  Water pixels after:  {post_water:,} ({100 * post_water / total_pixels:.1f}%)")
    if post_water > pre_water:
        increase = post_water - pre_water
        print(
            f"  Flood extent: +{increase:,} pixels ({100 * increase / total_pixels:.1f}% of area)"
        )

    # Step 5: Render
    print("\nStep 5: Rendering comparison...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))

    axes[0, 0].imshow(normalize_rgb(pre_rgb_stack))
    axes[0, 0].set_title(f"Before Storm\n{pre_scene['datetime'][:10]}", fontsize=12)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(normalize_rgb(post_rgb_stack))
    axes[0, 1].set_title(f"After Storm Babet\n{post_scene['datetime'][:10]}", fontsize=12)
    axes[0, 1].axis("off")

    im1 = axes[1, 0].imshow(pre_ndwi_arr, cmap="RdYlBu", vmin=-0.5, vmax=0.5)
    axes[1, 0].set_title("NDWI Before\n(blue = water)", fontsize=12)
    axes[1, 0].axis("off")
    fig.colorbar(im1, ax=axes[1, 0], shrink=0.7)

    im2 = axes[1, 1].imshow(post_ndwi_arr, cmap="RdYlBu", vmin=-0.5, vmax=0.5)
    axes[1, 1].set_title("NDWI After\n(blue = water, more = flooding)", fontsize=12)
    axes[1, 1].axis("off")
    fig.colorbar(im2, ax=axes[1, 1], shrink=0.7)

    fig.suptitle(
        "UK Flooding -- Storm Babet, Lincolnshire\nNDWI shows water where there shouldn't be water",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "uk_flooding_comparison.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("  Fields that were brown before the storm are blue after.")
    print("  NDWI reveals flood extent invisible in RGB alone.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
