#!/usr/bin/env python3
"""
Urban Sprawl -- Dubai Expansion

Dubai's growth is legendary. Track new development appearing over 2 years
using NDBI (built-up index) and RGB comparison. Desert = usually clear,
so cloud cover is rarely a problem.

Demonstrates:
    stac_search -> stac_download_rgb -> stac_compute_index (ndbi)
    Multi-year urban expansion tracking

Usage:
    python examples/dubai_growth_demo.py

Output:
    examples/output/dubai_growth.png

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

BBOX = [55.1, 25.0, 55.4, 25.3]  # Dubai
EARLY_RANGE = "2022-01-01/2022-03-31"  # 2022 baseline
RECENT_RANGE = "2024-01-01/2024-03-31"  # 2024 current
MAX_CLOUD_COVER = 5  # Desert = usually clear
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
    print("Urban Sprawl -- Dubai Expansion 2022 vs 2024")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  2022 baseline: {EARLY_RANGE}")
    print(f"  2024 current:  {RECENT_RANGE}")

    # Step 1: Find 2022 scene
    print("\nStep 1: Searching for 2022 baseline...")
    early = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=EARLY_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=5,
    )
    if early["scene_count"] == 0:
        print("  No 2022 scenes found.")
        sys.exit(1)

    early_scene = early["scenes"][0]
    print(f"  Found: {early_scene['scene_id']}  cloud={early_scene['cloud_cover']}%")

    # Step 2: Find 2024 scene
    print("\nStep 2: Searching for 2024 current...")
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
    recent_rgb = await runner.run("stac_download_rgb", scene_id=recent_scene["scene_id"], bbox=BBOX)

    if "error" in early_rgb or "error" in recent_rgb:
        print("  Download failed.")
        sys.exit(1)

    early_data = await store.retrieve(early_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(early_data)) as src:
        early_stack = src.read()

    recent_data = await store.retrieve(recent_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(recent_data)) as src:
        recent_stack = src.read()

    # Step 4: Compute NDBI
    print("\nStep 4: Computing NDBI (built-up index)...")
    early_ndbi = await runner.run(
        "stac_compute_index",
        scene_id=early_scene["scene_id"],
        index_name="ndbi",
        bbox=BBOX,
    )
    recent_ndbi = await runner.run(
        "stac_compute_index",
        scene_id=recent_scene["scene_id"],
        index_name="ndbi",
        bbox=BBOX,
    )

    if "error" in early_ndbi or "error" in recent_ndbi:
        print("  NDBI computation failed.")
        sys.exit(1)

    print(f"  2022 NDBI: {early_ndbi['value_range']}")
    print(f"  2024 NDBI: {recent_ndbi['value_range']}")

    early_ndbi_data = await store.retrieve(early_ndbi["artifact_ref"])
    with rasterio.open(io.BytesIO(early_ndbi_data)) as src:
        early_ndbi_arr = src.read(1)

    recent_ndbi_data = await store.retrieve(recent_ndbi["artifact_ref"])
    with rasterio.open(io.BytesIO(recent_ndbi_data)) as src:
        recent_ndbi_arr = src.read(1)

    ndbi_diff = recent_ndbi_arr - early_ndbi_arr
    print(f"\n  NDBI change: mean={np.nanmean(ndbi_diff):.4f}")
    print("  Positive = new built-up areas (construction, buildings)")

    # Step 5: Render
    print("\nStep 5: Rendering comparison...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))

    axes[0, 0].imshow(normalize_rgb(early_stack))
    axes[0, 0].set_title(f"2022 Baseline\n{early_scene['datetime'][:10]}", fontsize=12)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(normalize_rgb(recent_stack))
    axes[0, 1].set_title(f"2024 Current\n{recent_scene['datetime'][:10]}", fontsize=12)
    axes[0, 1].axis("off")

    im1 = axes[1, 0].imshow(early_ndbi_arr, cmap="RdYlBu_r", vmin=-0.3, vmax=0.3)
    axes[1, 0].set_title("2022 NDBI\n(warm = built-up)", fontsize=12)
    axes[1, 0].axis("off")
    fig.colorbar(im1, ax=axes[1, 0], shrink=0.7)

    im2 = axes[1, 1].imshow(ndbi_diff, cmap="RdBu_r", vmin=-0.15, vmax=0.15)
    axes[1, 1].set_title("NDBI Change 2022-2024\n(red = new development)", fontsize=12)
    axes[1, 1].axis("off")
    fig.colorbar(im2, ax=axes[1, 1], shrink=0.7, label="NDBI change")

    fig.suptitle(
        "Dubai Urban Expansion -- 2022 vs 2024\n"
        "Empty desert becomes construction sites, then neighbourhoods",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "dubai_growth.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("  New developments appear as NDBI hotspots.")
    print("  Empty desert in 2022 -> construction in 2024.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
