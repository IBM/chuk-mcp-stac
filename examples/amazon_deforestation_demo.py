#!/usr/bin/env python3
"""
Amazon Deforestation -- Monthly Tracking

Track forest clearing in a known deforestation hotspot in Rondonia, Brazil
across the 2024 dry season. NDVI drops from ~0.75 (healthy forest) to
~0.35 (cleared land) as deforestation progresses.

Demonstrates:
    stac_time_series -> stac_compute_index (ndvi per scene)
    Multi-date NDVI comparison for deforestation monitoring

Usage:
    python examples/amazon_deforestation_demo.py

Output:
    examples/output/amazon_deforestation.png

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

BBOX = [-63.5, -10.5, -63.0, -10.0]  # Rondonia, Brazil -- deforestation hotspot
DATE_RANGE = "2024-05-01/2024-10-31"  # Dry season
MAX_CLOUD_COVER = 20
MAX_ITEMS = 6  # ~1 per month
OUTPUT_DIR = Path(__file__).parent / "output"


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("Amazon Deforestation -- Rondonia Dry Season 2024")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")
    print(f"  max cloud: {MAX_CLOUD_COVER}%")

    # Step 1: Get time series
    print("\nStep 1: Extracting time series across dry season...")
    ts = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=["red", "nir"],
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in ts:
        print(f"  ERROR: {ts['error']}")
        sys.exit(1)

    entries = ts.get("entries", [])
    print(f"  Found {len(entries)} scene(s) across dry season")
    for entry in entries:
        print(f"    {entry['datetime'][:10]}  cloud={entry['cloud_cover']:.0f}%")

    if len(entries) < 2:
        print("\nNeed at least 2 scenes. Try relaxing cloud cover.")
        sys.exit(1)

    # Step 2: Compute NDVI for each date
    print("\nStep 2: Computing NDVI for each scene...")
    store = runner.manager._get_store()
    ndvi_panels = []

    for entry in entries:
        data = await store.retrieve(entry["artifact_ref"])
        with rasterio.open(io.BytesIO(data)) as src:
            stack = src.read()
        red = stack[0].astype(np.float32)
        nir = stack[1].astype(np.float32)
        denom = nir + red
        ndvi = np.where(denom > 0, (nir - red) / denom, np.nan)
        mean_ndvi = np.nanmean(ndvi)
        date_label = entry["datetime"][:10]
        ndvi_panels.append((date_label, ndvi, mean_ndvi))
        print(f"    {date_label}: mean NDVI = {mean_ndvi:.3f}")

    # Step 3: Analyze trend
    first_ndvi = ndvi_panels[0][2]
    last_ndvi = ndvi_panels[-1][2]
    change = last_ndvi - first_ndvi
    print(f"\n  NDVI trend: {first_ndvi:.3f} -> {last_ndvi:.3f} (change: {change:+.3f})")
    if change < -0.1:
        print("  Significant vegetation loss detected!")
    elif change > 0.1:
        print("  Vegetation increase (regrowth or seasonal green-up)")
    else:
        print("  Relatively stable vegetation")

    # Step 4: Render
    print("\nStep 3: Rendering NDVI time series...")
    n = len(ndvi_panels)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows), squeeze=False)

    for idx, (date_label, ndvi, mean_val) in enumerate(ndvi_panels):
        r, c = divmod(idx, cols)
        ax = axes[r][c]
        im = ax.imshow(ndvi, cmap="RdYlGn", vmin=0.0, vmax=0.9)
        ax.set_title(f"{date_label}\nmean NDVI: {mean_val:.3f}", fontsize=11)
        ax.axis("off")

    for idx in range(n, rows * cols):
        r, c = divmod(idx, cols)
        axes[r][c].axis("off")

    fig.suptitle(
        "Amazon Deforestation Monitoring -- Rondonia, Brazil\n"
        f"Dry Season {DATE_RANGE} | Green = forest, Red/yellow = cleared",
        fontsize=14,
        fontweight="bold",
    )
    fig.colorbar(im, ax=axes.ravel().tolist(), label="NDVI", shrink=0.6)
    fig.tight_layout()

    output_path = OUTPUT_DIR / "amazon_deforestation.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("  Watch the forest disappear month by month.")
    print("  No ground visit needed -- just consistent satellite passes.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
