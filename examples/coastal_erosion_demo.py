#!/usr/bin/env python3
"""
Coastal Erosion -- Holderness Coast, Yorkshire

The Holderness coast erodes at ~2m/year -- among the fastest in Europe.
Compare satellite imagery from 2019 and 2024 using RGB and NDWI to
track the retreating coastline.

Demonstrates:
    stac_search -> stac_download_rgb -> stac_compute_index (ndwi)
    Multi-year coastline comparison

Usage:
    python examples/coastal_erosion_demo.py

Output:
    examples/output/coastal_erosion.png

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

BBOX = [-0.30, 53.70, -0.05, 53.85]  # Holderness coast, Yorkshire
EARLY_RANGE = "2019-06-01/2019-08-31"  # 2019 summer
RECENT_RANGE = "2024-06-01/2024-08-31"  # 2024 summer
MAX_CLOUD_COVER = 15
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
    print("Coastal Erosion -- Holderness Coast, Yorkshire")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  2019: {EARLY_RANGE}")
    print(f"  2024: {RECENT_RANGE}")

    # Step 1: Find 2019 summer scene
    print("\nStep 1: Searching for 2019 summer baseline...")
    early = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=EARLY_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=5,
    )
    if early["scene_count"] == 0:
        print("  No 2019 scenes found.")
        sys.exit(1)

    early_scene = early["scenes"][0]
    print(f"  Found: {early_scene['scene_id']}  cloud={early_scene['cloud_cover']}%")

    # Step 2: Find 2024 summer scene
    print("\nStep 2: Searching for 2024 summer current...")
    recent = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=RECENT_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=5,
    )
    if recent["scene_count"] == 0:
        print("  No 2024 scenes found.")
        sys.exit(1)

    recent_scene = recent["scenes"][0]
    print(f"  Found: {recent_scene['scene_id']}  cloud={recent_scene['cloud_cover']}%")

    store = runner.manager._get_store()

    # Step 3: Download RGB
    print("\nStep 3: Downloading RGB composites...")
    early_rgb = await runner.run("stac_download_rgb", scene_id=early_scene["scene_id"], bbox=BBOX)
    if "error" in early_rgb:
        print(f"  ERROR: {early_rgb['error']}")
        sys.exit(1)
    recent_rgb = await runner.run("stac_download_rgb", scene_id=recent_scene["scene_id"], bbox=BBOX)
    if "error" in recent_rgb:
        print(f"  ERROR: {recent_rgb['error']}")
        sys.exit(1)

    early_data = await store.retrieve(early_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(early_data)) as src:
        early_stack = src.read()

    recent_data = await store.retrieve(recent_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(recent_data)) as src:
        recent_stack = src.read()

    # Step 4: Compute NDWI for coastline mapping
    print("\nStep 4: Computing NDWI (coastline from water index)...")
    early_ndwi = await runner.run(
        "stac_compute_index",
        scene_id=early_scene["scene_id"],
        index_name="ndwi",
        bbox=BBOX,
    )
    recent_ndwi = await runner.run(
        "stac_compute_index",
        scene_id=recent_scene["scene_id"],
        index_name="ndwi",
        bbox=BBOX,
    )

    if "error" in early_ndwi or "error" in recent_ndwi:
        print("  NDWI computation failed.")
        sys.exit(1)

    early_ndwi_data = await store.retrieve(early_ndwi["artifact_ref"])
    with rasterio.open(io.BytesIO(early_ndwi_data)) as src:
        early_ndwi_arr = src.read(1)

    recent_ndwi_data = await store.retrieve(recent_ndwi["artifact_ref"])
    with rasterio.open(io.BytesIO(recent_ndwi_data)) as src:
        recent_ndwi_arr = src.read(1)

    # Water pixels comparison
    early_water = np.nansum(early_ndwi_arr > 0.0)
    recent_water = np.nansum(recent_ndwi_arr > 0.0)
    total = early_ndwi_arr.size
    print(f"\n  2019 water pixels: {early_water:,} ({100 * early_water / total:.1f}%)")
    print(f"  2024 water pixels: {recent_water:,} ({100 * recent_water / total:.1f}%)")
    if recent_water > early_water:
        gain = recent_water - early_water
        print(f"  Coastline retreat: +{gain:,} water pixels ({100 * gain / total:.2f}%)")

    # Step 5: Render
    print("\nStep 5: Rendering comparison...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))

    axes[0, 0].imshow(normalize_rgb(early_stack))
    axes[0, 0].set_title(f"2019\n{early_scene['datetime'][:10]}", fontsize=12)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(normalize_rgb(recent_stack))
    axes[0, 1].set_title(f"2024\n{recent_scene['datetime'][:10]}", fontsize=12)
    axes[0, 1].axis("off")

    im1 = axes[1, 0].imshow(early_ndwi_arr, cmap="RdYlBu", vmin=-0.5, vmax=0.5)
    axes[1, 0].set_title("2019 NDWI\n(blue = water)", fontsize=12)
    axes[1, 0].axis("off")
    fig.colorbar(im1, ax=axes[1, 0], shrink=0.7)

    im2 = axes[1, 1].imshow(recent_ndwi_arr, cmap="RdYlBu", vmin=-0.5, vmax=0.5)
    axes[1, 1].set_title("2024 NDWI\n(blue = water)", fontsize=12)
    axes[1, 1].axis("off")
    fig.colorbar(im2, ax=axes[1, 1], shrink=0.7)

    fig.suptitle(
        "Coastal Erosion -- Holderness Coast, Yorkshire\n"
        "~2m/year retreat | Compare coastline position in NDWI",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "coastal_erosion.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("  The cliff edge has moved inland over 5 years.")
    print("  At 10m resolution we can see multi-year retreat.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
