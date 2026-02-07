#!/usr/bin/env python3
"""
Port Activity -- Singapore

Singapore is the world's busiest port. At 10m resolution, large
container ships are 3-4 pixels long. Compare activity across
multiple dates to see trade pattern variation.

Demonstrates:
    stac_time_series -> stac_download_rgb (per scene)
    Visual inspection of port/shipping activity

Usage:
    python examples/singapore_port_demo.py

Output:
    examples/output/singapore_port.png

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

BBOX = [103.7, 1.2, 104.0, 1.35]  # Singapore Strait
DATE_RANGE = "2024-01-01/2024-06-30"  # Half year for variety
MAX_CLOUD_COVER = 40  # Tropical = cloudy, accept more
MAX_ITEMS = 6
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
    print("Port Activity -- Singapore Strait")
    print("=" * 60)
    print(f"\n  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")
    print(f"  max cloud: {MAX_CLOUD_COVER}% (tropical region)")

    # Step 1: Get time series
    print("\nStep 1: Extracting RGB time series...")
    ts = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=["red", "green", "blue"],
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in ts:
        print(f"  ERROR: {ts['error']}")
        sys.exit(1)

    entries = ts.get("entries", [])
    print(f"  Found {len(entries)} scene(s)")

    if not entries:
        print("\nNo scenes found. Try wider date range or higher cloud cover.")
        sys.exit(1)

    # Step 2: Load RGB data for each date
    print("\nStep 2: Loading RGB data...")
    store = runner.manager._get_store()
    panels = []

    for entry in entries:
        data = await store.retrieve(entry["artifact_ref"])
        with rasterio.open(io.BytesIO(data)) as src:
            stack = src.read()
        date_label = entry["datetime"][:10]
        cloud = entry["cloud_cover"]
        panels.append((date_label, cloud, stack))
        print(f"    {date_label}: cloud={cloud:.0f}%  shape={stack.shape}")

    # Step 3: Render multi-panel
    print("\nStep 3: Rendering port activity grid...")
    n = len(panels)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(7 * cols, 6 * rows), squeeze=False)

    for idx, (date_label, cloud, stack) in enumerate(panels):
        r, c = divmod(idx, cols)
        ax = axes[r][c]
        rgb_img = normalize_rgb(stack)
        ax.imshow(rgb_img)
        ax.set_title(f"{date_label}\ncloud: {cloud:.0f}%", fontsize=11)
        ax.axis("off")

    for idx in range(n, rows * cols):
        r, c = divmod(idx, cols)
        axes[r][c].axis("off")

    fig.suptitle(
        "Singapore Strait -- Port Activity\nShips visible as bright dots at 10m resolution",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "singapore_port.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  {n} dates captured across {DATE_RANGE}")
    print("  Large container ships are 3-4 pixels at 10m resolution.")
    print("  Busier days have more white dots in the strait.")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
