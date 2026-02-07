#!/usr/bin/env python3
"""
Wildfire Scar -- California Park Fire (Before & After)

The Park Fire (July-August 2024) in Butte County, California was one of
the largest in state history. Compare before and after imagery using
RGB, false-colour burn scar composite, and NDVI to quantify vegetation
loss from the fire.

Demonstrates:
    stac_search -> stac_download_rgb -> stac_download_composite
    -> stac_compute_index (ndvi before/after)

Usage:
    python examples/wildfire_scar_demo.py

Output:
    examples/output/wildfire_scar.png

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

BBOX = [-121.8, 39.7, -121.3, 40.1]  # Butte County, California
PRE_FIRE = "2024-06-01/2024-07-15"  # Before the Park Fire (started July 24)
POST_FIRE = "2024-08-10/2024-08-31"  # After the fire
MAX_CLOUD_COVER = 20
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
    print("Wildfire Scar -- California Park Fire (Before & After)")
    print("=" * 60)
    print(f"\n  bbox: {BBOX} (Butte County)")
    print(f"  pre-fire:  {PRE_FIRE}")
    print(f"  post-fire: {POST_FIRE}")

    # Step 1: Find pre-fire scene
    print("\nStep 1: Searching for pre-fire baseline...")
    pre = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=PRE_FIRE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=5,
    )
    if pre["scene_count"] == 0:
        print("  No pre-fire scenes found.")
        sys.exit(1)

    for scene in pre["scenes"]:
        print(f"    {scene['scene_id']}  cloud={scene['cloud_cover']}%")

    # Step 2: Find post-fire scene
    print("\nStep 2: Searching for post-fire imagery...")
    post = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=POST_FIRE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=10,
    )
    if post["scene_count"] == 0:
        print("  No post-fire scenes found.")
        sys.exit(1)

    for scene in post["scenes"]:
        print(f"    {scene['scene_id']}  cloud={scene['cloud_cover']}%")

    # Match tiles: pick pre/post scenes from the same Sentinel-2 tile
    def get_tile(scene_id: str) -> str:
        """Extract tile grid square from scene ID (e.g. '10TEK' from 'S2A_10TEK_...')."""
        parts = scene_id.split("_")
        return parts[1] if len(parts) > 1 else ""

    pre_scene = None
    post_scene = None
    for ps in pre["scenes"]:
        tile = get_tile(ps["scene_id"])
        for qs in post["scenes"]:
            if get_tile(qs["scene_id"]) == tile:
                pre_scene = ps
                post_scene = qs
                break
        if pre_scene:
            break

    if not pre_scene or not post_scene:
        # Fallback: use first of each
        pre_scene = pre["scenes"][0]
        post_scene = post["scenes"][0]
        print("  Warning: no matching tiles found, using best available scenes")

    print(f"\n  Pre-fire:  {pre_scene['scene_id']}  cloud={pre_scene['cloud_cover']}%")
    print(f"  Post-fire: {post_scene['scene_id']}  cloud={post_scene['cloud_cover']}%")

    store = runner.manager._get_store()

    # Step 3: Download RGB for both
    print("\nStep 3: Downloading RGB composites...")
    pre_rgb = await runner.run("stac_download_rgb", scene_id=pre_scene["scene_id"], bbox=BBOX)
    if "error" in pre_rgb:
        print(f"  ERROR: {pre_rgb['error']}")
        sys.exit(1)

    post_rgb = await runner.run("stac_download_rgb", scene_id=post_scene["scene_id"], bbox=BBOX)
    if "error" in post_rgb:
        print(f"  ERROR: {post_rgb['error']}")
        sys.exit(1)

    pre_rgb_data = await store.retrieve(pre_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(pre_rgb_data)) as src:
        pre_rgb_stack = src.read()

    post_rgb_data = await store.retrieve(post_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(post_rgb_data)) as src:
        post_rgb_stack = src.read()

    # Step 4: False-colour burn scar composite (SWIR2, NIR, Green) -- post-fire
    print("\nStep 4: Downloading burn scar composite (SWIR2, NIR, Green)...")
    burn_result = await runner.run(
        "stac_download_composite",
        scene_id=post_scene["scene_id"],
        bands=["swir22", "nir", "green"],
        composite_name="burn_scar",
        bbox=BBOX,
    )
    if "error" in burn_result:
        print(f"  ERROR: {burn_result['error']}")
        sys.exit(1)

    burn_data = await store.retrieve(burn_result["artifact_ref"])
    with rasterio.open(io.BytesIO(burn_data)) as src:
        burn_stack = src.read()

    # Step 5: Compute NDVI for both scenes
    print("\nStep 5: Computing NDVI before and after fire...")
    pre_ndvi_result = await runner.run(
        "stac_compute_index",
        scene_id=pre_scene["scene_id"],
        index_name="ndvi",
        bbox=BBOX,
    )
    if "error" in pre_ndvi_result:
        print(f"  ERROR: {pre_ndvi_result['error']}")
        sys.exit(1)
    print(f"  Pre-fire NDVI:  {pre_ndvi_result['value_range']}")

    post_ndvi_result = await runner.run(
        "stac_compute_index",
        scene_id=post_scene["scene_id"],
        index_name="ndvi",
        bbox=BBOX,
    )
    if "error" in post_ndvi_result:
        print(f"  ERROR: {post_ndvi_result['error']}")
        sys.exit(1)
    print(f"  Post-fire NDVI: {post_ndvi_result['value_range']}")

    pre_ndvi_data = await store.retrieve(pre_ndvi_result["artifact_ref"])
    with rasterio.open(io.BytesIO(pre_ndvi_data)) as src:
        pre_ndvi = src.read(1)

    post_ndvi_data = await store.retrieve(post_ndvi_result["artifact_ref"])
    with rasterio.open(io.BytesIO(post_ndvi_data)) as src:
        post_ndvi = src.read(1)

    # Resize if scenes come from different tiles (different pixel grids)
    if pre_ndvi.shape != post_ndvi.shape:
        target_shape = post_ndvi.shape
        row_idx = (np.arange(target_shape[0]) * pre_ndvi.shape[0] / target_shape[0]).astype(int)
        col_idx = (np.arange(target_shape[1]) * pre_ndvi.shape[1] / target_shape[1]).astype(int)
        row_idx = np.clip(row_idx, 0, pre_ndvi.shape[0] - 1)
        col_idx = np.clip(col_idx, 0, pre_ndvi.shape[1] - 1)
        pre_ndvi = pre_ndvi[np.ix_(row_idx, col_idx)]

    # NDVI difference
    ndvi_diff = post_ndvi - pre_ndvi

    # Statistics
    burned_pixels = np.nansum(post_ndvi < 0.15)
    total = post_ndvi.size
    print(
        f"\n  Post-fire burned area (NDVI < 0.15): {burned_pixels:,} pixels "
        f"({100 * burned_pixels / total:.1f}%)"
    )
    print(f"  NDVI change: mean={np.nanmean(ndvi_diff):.3f}")
    print("  Negative = vegetation destroyed by fire")

    # Step 6: Render 2x3 comparison
    print("\nStep 6: Rendering before/after comparison...")
    fig, axes = plt.subplots(2, 3, figsize=(21, 13))

    # Top row: before
    axes[0, 0].imshow(normalize_rgb(pre_rgb_stack))
    axes[0, 0].set_title(f"Before Fire -- RGB\n{pre_scene['datetime'][:10]}", fontsize=11)
    axes[0, 0].axis("off")

    im1 = axes[0, 1].imshow(pre_ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    axes[0, 1].set_title("Before Fire -- NDVI\n(green = healthy forest)", fontsize=11)
    axes[0, 1].axis("off")
    fig.colorbar(im1, ax=axes[0, 1], shrink=0.7)

    axes[0, 2].axis("off")
    axes[0, 2].text(
        0.5,
        0.5,
        "Park Fire\nStarted July 24, 2024\nButte County, CA\n\n"
        "One of the largest\nwildfires in California\nhistory",
        transform=axes[0, 2].transAxes,
        ha="center",
        va="center",
        fontsize=14,
        bbox={"boxstyle": "round", "facecolor": "lightyellow", "alpha": 0.8},
    )

    # Bottom row: after
    axes[1, 0].imshow(normalize_rgb(post_rgb_stack))
    axes[1, 0].set_title(f"After Fire -- RGB\n{post_scene['datetime'][:10]}", fontsize=11)
    axes[1, 0].axis("off")

    axes[1, 1].imshow(normalize_rgb(burn_stack))
    axes[1, 1].set_title("After Fire -- Burn Scar\n(SWIR2, NIR, Green)", fontsize=11)
    axes[1, 1].text(
        0.5,
        -0.05,
        "Burn scar = bright magenta/red",
        transform=axes[1, 1].transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    axes[1, 1].axis("off")

    im2 = axes[1, 2].imshow(ndvi_diff, cmap="RdYlGn", vmin=-0.8, vmax=0.3)
    axes[1, 2].set_title("NDVI Change\n(red = vegetation loss)", fontsize=11)
    axes[1, 2].axis("off")
    fig.colorbar(im2, ax=axes[1, 2], shrink=0.7, label="NDVI change")

    fig.suptitle(
        "Park Fire Burn Scar -- Butte County, California\n"
        "Before vs After | Healthy forest NDVI ~0.7 drops to ~0.1 in burn scar",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "wildfire_scar.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Before: {pre_scene['scene_id']} ({pre_scene['datetime'][:10]})")
    print(f"  After:  {post_scene['scene_id']} ({post_scene['datetime'][:10]})")
    print(f"  Burned area: ~{100 * burned_pixels / total:.0f}% of the scene")
    print("  The false-colour composite makes the fire perimeter unmistakable.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
