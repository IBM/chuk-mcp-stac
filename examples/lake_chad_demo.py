#!/usr/bin/env python3
"""
Seasonal Lake -- Lake Chad Shrinkage

Lake Chad has shrunk ~90% since 1960. Track seasonal variation across
2024 using NDWI (water index) to measure water extent month by month.

Demonstrates:
    stac_time_series -> stac_compute_index (ndwi)
    Seasonal water body monitoring

Usage:
    python examples/lake_chad_demo.py

Output:
    examples/output/lake_chad.png

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

BBOX = [13.5, 12.5, 14.5, 13.5]  # Lake Chad
DATE_RANGE = "2024-01-01/2024-12-31"  # Full year
MAX_CLOUD_COVER = 20
MAX_ITEMS = 12  # ~1 per month
OUTPUT_DIR = Path(__file__).parent / "output"


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("Lake Chad -- Seasonal Water Extent 2024")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  year: {DATE_RANGE}")

    # Step 1: Get time series
    print("\nStep 1: Extracting time series across 2024...")
    ts = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=["green", "nir"],
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in ts:
        print(f"  ERROR: {ts['error']}")
        sys.exit(1)

    entries = ts.get("entries", [])
    print(f"  Found {len(entries)} scene(s)")

    if len(entries) < 3:
        print("\nNeed at least 3 scenes. Try relaxing cloud cover.")
        sys.exit(1)

    # Step 2: Compute NDWI for each scene
    print("\nStep 2: Computing NDWI per scene...")
    store = runner.manager._get_store()
    dates = []
    water_pcts = []
    ndwi_images = []

    for entry in entries:
        data = await store.retrieve(entry["artifact_ref"])
        with rasterio.open(io.BytesIO(data)) as src:
            stack = src.read()

        green = stack[0].astype(np.float32)
        nir = stack[1].astype(np.float32)
        denom = green + nir
        ndwi = np.where(denom > 0, (green - nir) / denom, np.nan)

        # Water = NDWI > 0
        water_pixels = np.nansum(ndwi > 0.0)
        total = ndwi.size
        water_pct = 100 * water_pixels / total

        date_label = entry["datetime"][:10]
        dates.append(date_label)
        water_pcts.append(water_pct)
        ndwi_images.append(ndwi)
        print(f"    {date_label}: water = {water_pct:.1f}%  cloud={entry['cloud_cover']:.0f}%")

    # Step 3: Analyze seasonal pattern
    max_idx = np.argmax(water_pcts)
    min_idx = np.argmin(water_pcts)
    print(f"\n  Maximum water: {dates[max_idx]} ({water_pcts[max_idx]:.1f}%)")
    print(f"  Minimum water: {dates[min_idx]} ({water_pcts[min_idx]:.1f}%)")
    range_pct = water_pcts[max_idx] - water_pcts[min_idx]
    print(f"  Seasonal range: {range_pct:.1f} percentage points")

    # Step 4: Render
    print("\nStep 3: Rendering seasonal water extent...")
    n_images = min(len(ndwi_images), 6)

    fig = plt.figure(figsize=(18, 10))
    gs = fig.add_gridspec(2, n_images, height_ratios=[1, 1.2])

    # Top: NDWI panels (binary water mask)
    for idx in range(n_images):
        ax = fig.add_subplot(gs[0, idx])
        # Show water mask: blue = water, brown = land
        water_mask = ndwi_images[idx] > 0.0
        ax.imshow(water_mask, cmap="Blues", vmin=0, vmax=1)
        ax.set_title(f"{dates[idx]}\n{water_pcts[idx]:.1f}% water", fontsize=9)
        ax.axis("off")

    # Bottom: water extent time series
    ax_ts = fig.add_subplot(gs[1, :])
    ax_ts.plot(dates, water_pcts, "o-", color="steelblue", linewidth=2, markersize=8)
    ax_ts.fill_between(dates, water_pcts, alpha=0.2, color="steelblue")
    ax_ts.set_ylabel("Water Extent (%)", fontsize=12)
    ax_ts.set_xlabel("Date", fontsize=12)
    ax_ts.set_title("Lake Chad -- Seasonal Water Extent", fontsize=12)
    ax_ts.tick_params(axis="x", rotation=45)
    ax_ts.grid(True, alpha=0.3)

    fig.suptitle(
        "Lake Chad -- Seasonal Variation 2024\nRainy season swells the lake, dry season shrinks it",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "lake_chad.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Peak: {dates[max_idx]} ({water_pcts[max_idx]:.1f}% water)")
    print(f"  Low:  {dates[min_idx]} ({water_pcts[min_idx]:.1f}% water)")
    print("  The long-term trend: the lake keeps shrinking.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
