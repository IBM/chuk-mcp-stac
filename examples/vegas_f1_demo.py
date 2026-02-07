#!/usr/bin/env python3
"""
Las Vegas Strip -- Race Weekend Transformation

The Las Vegas Grand Prix requires massive temporary infrastructure --
grandstands, barriers, pit buildings. The transformation is visible
from space via NDBI (Normalized Difference Built-up Index).

Demonstrates:
    stac_search -> stac_download_rgb -> stac_compute_index (ndbi)
    Before/after comparison using built-up index

Usage:
    python examples/vegas_f1_demo.py

Output:
    examples/output/vegas_f1_comparison.png

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

BBOX = [-115.19, 36.11, -115.15, 36.14]  # Las Vegas Strip
SUMMER_RANGE = "2024-07-01/2024-07-31"  # Summer baseline
RACE_RANGE = "2024-11-15/2024-11-25"  # Race week
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
    print("Las Vegas Strip -- F1 Race Weekend Transformation")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  summer baseline: {SUMMER_RANGE}")
    print(f"  race week:       {RACE_RANGE}")

    # Step 1: Find summer baseline scene
    print("\nStep 1: Searching for summer baseline scene...")
    summer = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=SUMMER_RANGE,
        max_cloud_cover=10,
        max_items=5,
    )
    if summer["scene_count"] == 0:
        print("  No summer scenes found.")
        sys.exit(1)

    summer_scene = summer["scenes"][0]
    print(f"  Found: {summer_scene['scene_id']}  cloud={summer_scene['cloud_cover']}%")

    # Step 2: Find race week scene
    print("\nStep 2: Searching for race week scene...")
    race = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=RACE_RANGE,
        max_cloud_cover=20,
        max_items=5,
    )
    if race["scene_count"] == 0:
        print("  No race week scenes found.")
        sys.exit(1)

    race_scene = race["scenes"][0]
    print(f"  Found: {race_scene['scene_id']}  cloud={race_scene['cloud_cover']}%")

    store = runner.manager._get_store()

    # Step 3: Download RGB for both
    print("\nStep 3: Downloading RGB composites...")
    summer_rgb = await runner.run("stac_download_rgb", scene_id=summer_scene["scene_id"], bbox=BBOX)
    if "error" in summer_rgb:
        print(f"  ERROR: {summer_rgb['error']}")
        sys.exit(1)

    race_rgb = await runner.run("stac_download_rgb", scene_id=race_scene["scene_id"], bbox=BBOX)
    if "error" in race_rgb:
        print(f"  ERROR: {race_rgb['error']}")
        sys.exit(1)

    summer_data = await store.retrieve(summer_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(summer_data)) as src:
        summer_stack = src.read()

    race_data = await store.retrieve(race_rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(race_data)) as src:
        race_stack = src.read()

    # Step 4: Compute NDBI for both
    print("\nStep 4: Computing NDBI (built-up index)...")
    summer_ndbi = await runner.run(
        "stac_compute_index",
        scene_id=summer_scene["scene_id"],
        index_name="ndbi",
        bbox=BBOX,
    )
    if "error" in summer_ndbi:
        print(f"  ERROR: {summer_ndbi['error']}")
        sys.exit(1)
    print(f"  Summer NDBI: {summer_ndbi['value_range']}")

    race_ndbi = await runner.run(
        "stac_compute_index",
        scene_id=race_scene["scene_id"],
        index_name="ndbi",
        bbox=BBOX,
    )
    if "error" in race_ndbi:
        print(f"  ERROR: {race_ndbi['error']}")
        sys.exit(1)
    print(f"  Race NDBI:   {race_ndbi['value_range']}")

    # Read NDBI arrays
    summer_ndbi_data = await store.retrieve(summer_ndbi["artifact_ref"])
    with rasterio.open(io.BytesIO(summer_ndbi_data)) as src:
        summer_ndbi_arr = src.read(1)

    race_ndbi_data = await store.retrieve(race_ndbi["artifact_ref"])
    with rasterio.open(io.BytesIO(race_ndbi_data)) as src:
        race_ndbi_arr = src.read(1)

    ndbi_diff = race_ndbi_arr - summer_ndbi_arr
    print(f"\n  NDBI change: mean={np.nanmean(ndbi_diff):.4f}")
    print("  Positive = new built-up structures (grandstands, barriers)")

    # Step 5: Render
    print("\nStep 5: Rendering comparison...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))

    axes[0, 0].imshow(normalize_rgb(summer_stack))
    axes[0, 0].set_title(f"Summer Baseline\n{summer_scene['datetime'][:10]}", fontsize=12)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(normalize_rgb(race_stack))
    axes[0, 1].set_title(f"Race Week\n{race_scene['datetime'][:10]}", fontsize=12)
    axes[0, 1].axis("off")

    im1 = axes[1, 0].imshow(summer_ndbi_arr, cmap="RdYlBu_r", vmin=-0.3, vmax=0.3)
    axes[1, 0].set_title("Summer NDBI", fontsize=12)
    axes[1, 0].axis("off")
    fig.colorbar(im1, ax=axes[1, 0], shrink=0.7)

    im2 = axes[1, 1].imshow(ndbi_diff, cmap="RdBu_r", vmin=-0.2, vmax=0.2)
    axes[1, 1].set_title("NDBI Change\n(Race - Summer)", fontsize=12)
    axes[1, 1].axis("off")
    fig.colorbar(im2, ax=axes[1, 1], shrink=0.7, label="NDBI change")

    fig.suptitle(
        "Las Vegas Strip -- F1 Grand Prix Transformation\n"
        "Temporary grandstands and barriers visible from 786km altitude",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "vegas_f1_comparison.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("  The Strip literally looks different from space.")
    print("  NDBI increase = new temporary structures for the race.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
