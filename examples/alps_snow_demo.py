#!/usr/bin/env python3
"""
Snow Cover -- Alps Ski Season

Track snow cover in the Mont Blanc area through the 2023-2024 ski season.
Uses SWIR and Green bands to compute a snow index (NDSI) and RGB for
visual context. Snow: NDSI > 0.4.

Demonstrates:
    stac_time_series -> stac_download_bands (green, swir16)
    Custom band math for snow index (NDSI)

Usage:
    python examples/alps_snow_demo.py

Output:
    examples/output/alps_snow.png

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

BBOX = [6.8, 45.8, 7.2, 46.1]  # Mont Blanc area, Alps
DATE_RANGE = "2023-12-01/2024-03-31"  # Ski season
MAX_CLOUD_COVER = 30
MAX_ITEMS = 8
OUTPUT_DIR = Path(__file__).parent / "output"


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("Alps Snow Cover -- Ski Season 2023-2024")
    print("=" * 60)
    print(f"\n  bbox: {BBOX} (Mont Blanc area)")
    print(f"  ski season: {DATE_RANGE}")
    print(f"  max cloud: {MAX_CLOUD_COVER}%")

    # Step 1: Get time series with green and SWIR bands for NDSI
    print("\nStep 1: Extracting time series (green + swir16 for snow index)...")
    ts = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=["green", "swir16"],
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in ts:
        print(f"  ERROR: {ts['error']}")
        sys.exit(1)

    entries = ts.get("entries", [])
    print(f"  Found {len(entries)} scene(s)")

    if len(entries) < 2:
        print("\nNeed at least 2 scenes. Try relaxing cloud cover.")
        sys.exit(1)

    # Step 2: Compute NDSI for each scene
    # NDSI = (Green - SWIR) / (Green + SWIR), Snow > 0.4
    print("\nStep 2: Computing NDSI (snow index) per scene...")
    store = runner.manager._get_store()
    dates = []
    snow_pcts = []
    ndsi_images = []

    for entry in entries:
        data = await store.retrieve(entry["artifact_ref"])
        with rasterio.open(io.BytesIO(data)) as src:
            stack = src.read()

        green = stack[0].astype(np.float32)
        swir = stack[1].astype(np.float32)
        denom = green + swir
        ndsi = np.where(denom > 0, (green - swir) / denom, np.nan)

        # Snow = NDSI > 0.4
        snow_pixels = np.nansum(ndsi > 0.4)
        total = ndsi.size
        snow_pct = 100 * snow_pixels / total

        date_label = entry["datetime"][:10]
        dates.append(date_label)
        snow_pcts.append(snow_pct)
        ndsi_images.append(ndsi)
        print(f"    {date_label}: snow = {snow_pct:.1f}%  cloud={entry['cloud_cover']:.0f}%")

    # Step 3: Analyze snow patterns
    max_idx = np.argmax(snow_pcts)
    min_idx = np.argmin(snow_pcts)
    print(f"\n  Maximum snow: {dates[max_idx]} ({snow_pcts[max_idx]:.1f}%)")
    print(f"  Minimum snow: {dates[min_idx]} ({snow_pcts[min_idx]:.1f}%)")

    # Step 4: Render
    print("\nStep 3: Rendering snow cover timeline...")
    n_images = min(len(ndsi_images), 4)

    fig = plt.figure(figsize=(18, 10))
    gs = fig.add_gridspec(2, max(n_images, 2), height_ratios=[1, 1.2])

    # Top: snow maps
    for idx in range(n_images):
        ax = fig.add_subplot(gs[0, idx])
        snow_mask = ndsi_images[idx] > 0.4
        # Blue = snow, gray = land
        display = np.where(snow_mask, 1.0, 0.3)
        ax.imshow(display, cmap="coolwarm", vmin=0, vmax=1)
        ax.set_title(f"{dates[idx]}\n{snow_pcts[idx]:.0f}% snow", fontsize=10)
        ax.axis("off")

    # Bottom: snow extent timeline
    ax_ts = fig.add_subplot(gs[1, :])
    ax_ts.plot(dates, snow_pcts, "o-", color="steelblue", linewidth=2, markersize=8)
    ax_ts.fill_between(dates, snow_pcts, alpha=0.2, color="steelblue")
    ax_ts.set_ylabel("Snow Cover (%)", fontsize=12)
    ax_ts.set_xlabel("Date", fontsize=12)
    ax_ts.set_title("Snow Cover Timeline -- NDSI > 0.4", fontsize=12)
    ax_ts.tick_params(axis="x", rotation=45)
    ax_ts.grid(True, alpha=0.3)

    fig.suptitle(
        "Alps Snow Cover -- Mont Blanc, Ski Season 2023-2024\n"
        "NDSI = (Green - SWIR) / (Green + SWIR) | Snow: NDSI > 0.4",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "alps_snow.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Best snow:  {dates[max_idx]} ({snow_pcts[max_idx]:.0f}%)")
    print(f"  Least snow: {dates[min_idx]} ({snow_pcts[min_idx]:.0f}%)")
    print("  Track thaws, dumps, and the start of spring melt.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
