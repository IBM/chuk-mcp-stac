#!/usr/bin/env python3
"""
Crop Health Monitoring -- UK Wheat Field

Track a wheat field near Cambridge through the growing season using
NDVI with cloud masking. Observe the crop lifecycle: bare soil ->
rapid growth -> peak greenness -> stress/senescence -> harvest.

Demonstrates:
    stac_time_series -> stac_compute_index (ndvi, cloud_mask=true)
    Phenology curve from satellite observations

Usage:
    python examples/crop_health_demo.py

Output:
    examples/output/crop_health.png

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

BBOX = [-0.15, 52.15, -0.05, 52.22]  # Cambridgeshire farmland
DATE_RANGE = "2024-04-01/2024-08-31"  # Growing season
MAX_CLOUD_COVER = 30
MAX_ITEMS = 10
OUTPUT_DIR = Path(__file__).parent / "output"


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("Crop Health Monitoring -- Cambridgeshire, UK")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  growing season: {DATE_RANGE}")
    print(f"  max cloud: {MAX_CLOUD_COVER}%")

    # Step 1: Get time series
    print("\nStep 1: Extracting time series across growing season...")
    ts = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=["red", "nir", "scl"],
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in ts:
        print(f"  ERROR: {ts['error']}")
        sys.exit(1)

    entries = ts.get("entries", [])
    print(f"  Found {len(entries)} usable scene(s)")

    if len(entries) < 3:
        print("\nNeed at least 3 scenes for phenology. Try relaxing cloud cover.")
        sys.exit(1)

    # Step 2: Compute cloud-masked NDVI for each scene
    print("\nStep 2: Computing cloud-masked NDVI per scene...")
    store = runner.manager._get_store()
    dates = []
    mean_ndvis = []
    ndvi_images = []

    for entry in entries:
        scene_id = entry["scene_id"]
        ndvi_result = await runner.run(
            "stac_compute_index",
            scene_id=scene_id,
            index_name="ndvi",
            bbox=BBOX,
            cloud_mask=True,
        )

        if "error" in ndvi_result:
            print(f"    {entry['datetime'][:10]}: skipped ({ndvi_result['error']})")
            continue

        ndvi_data = await store.retrieve(ndvi_result["artifact_ref"])
        with rasterio.open(io.BytesIO(ndvi_data)) as src:
            ndvi = src.read(1)

        mean_val = np.nanmean(ndvi)
        date_label = entry["datetime"][:10]
        dates.append(date_label)
        mean_ndvis.append(mean_val)
        ndvi_images.append(ndvi)
        print(f"    {date_label}: mean NDVI = {mean_val:.3f}  cloud={entry['cloud_cover']:.0f}%")

    if len(dates) < 3:
        print("\nNot enough cloud-free scenes for phenology curve.")
        sys.exit(1)

    # Step 3: Identify growth stages
    peak_idx = np.argmax(mean_ndvis)
    peak_date = dates[peak_idx]
    peak_val = mean_ndvis[peak_idx]
    print(f"\n  Peak greenness: {peak_date} (NDVI={peak_val:.3f})")
    print(f"  Early season:   {dates[0]} (NDVI={mean_ndvis[0]:.3f})")
    print(f"  Late season:    {dates[-1]} (NDVI={mean_ndvis[-1]:.3f})")

    # Step 4: Render phenology curve + NDVI panels
    print("\nStep 3: Rendering phenology curve and NDVI panels...")
    n_images = min(len(ndvi_images), 6)  # Show up to 6 panels

    fig = plt.figure(figsize=(18, 10))
    gs = fig.add_gridspec(2, n_images, height_ratios=[1, 1.2])

    # Top row: NDVI images
    for idx in range(n_images):
        ax = fig.add_subplot(gs[0, idx])
        ax.imshow(ndvi_images[idx], cmap="RdYlGn", vmin=-0.1, vmax=0.8)
        ax.set_title(f"{dates[idx]}\n{mean_ndvis[idx]:.2f}", fontsize=9)
        ax.axis("off")

    # Bottom: phenology curve
    ax_curve = fig.add_subplot(gs[1, :])
    ax_curve.plot(dates, mean_ndvis, "o-", color="green", linewidth=2, markersize=8)
    ax_curve.axhline(y=0.3, color="brown", linestyle="--", alpha=0.5, label="Bare soil threshold")
    ax_curve.axhline(
        y=0.6, color="darkgreen", linestyle="--", alpha=0.5, label="Healthy vegetation"
    )
    ax_curve.fill_between(dates, mean_ndvis, alpha=0.15, color="green")
    ax_curve.set_ylabel("Mean NDVI", fontsize=12)
    ax_curve.set_xlabel("Date", fontsize=12)
    ax_curve.set_title("Phenology Curve -- Crop Growth Cycle", fontsize=12)
    ax_curve.legend(fontsize=9)
    ax_curve.tick_params(axis="x", rotation=45)
    ax_curve.grid(True, alpha=0.3)

    fig.suptitle(
        "Crop Health Monitoring -- Cambridgeshire Farmland\n"
        "NDVI phenology: bare soil -> growth -> peak -> senescence -> harvest",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "crop_health.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Peak greenness on {peak_date} (NDVI={peak_val:.3f})")
    print("  Dips may correlate with heatwaves or drought stress.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
