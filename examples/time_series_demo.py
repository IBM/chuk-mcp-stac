#!/usr/bin/env python3
"""
Time Series Demo -- chuk-mcp-stac

Extract a temporal stack of satellite data over an area using the
stac_time_series tool. Searches for all scenes in a date range,
downloads the requested bands for each, and renders per-date NDVI
images side by side.

Demonstrates:
    stac_time_series (search + concurrent band downloads)
    Per-date NDVI computation and rendering

Usage:
    python examples/time_series_demo.py

Output:
    examples/output/time_series_ndvi.png

Requirements:
    pip install chuk-mcp-stac matplotlib
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio
import io
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio

from tool_runner import ToolRunner

# Colchester, tight bbox
BBOX = [0.85, 51.85, 0.95, 51.93]
DATE_RANGE = "2024-06-01/2024-08-31"
BANDS = ["red", "nir"]  # For NDVI computation across time
MAX_CLOUD_COVER = 15
MAX_ITEMS = 5
OUTPUT_DIR = Path(__file__).parent / "output"


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute NDVI = (NIR - RED) / (NIR + RED)."""
    red_f = red.astype(np.float32)
    nir_f = nir.astype(np.float32)
    denom = nir_f + red_f
    return np.where(denom > 0, (nir_f - red_f) / denom, 0.0)


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Time Series Demo")
    print("=" * 60)

    print("\nExtracting time series over Colchester...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")
    print(f"  bands: {BANDS}")
    print(f"  max cloud: {MAX_CLOUD_COVER}%")
    print(f"  max items: {MAX_ITEMS}")

    result = await runner.run(
        "stac_time_series",
        bbox=BBOX,
        bands=BANDS,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if "error" in result:
        print(f"\nTime series failed: {result['error']}")
        return

    print(f"\nTime series extracted: {result['date_count']} date(s)")
    print(f"  Collection: {result['collection']}")
    print(f"  Bands: {result['bands']}")

    entries = result.get("entries", [])
    if not entries:
        print("\nNo entries found. Try widening the date range or cloud cover threshold.")
        return

    print("\nEntries:")
    for entry in entries:
        cloud = f"{entry['cloud_cover']:.1f}%" if entry["cloud_cover"] is not None else "N/A"
        print(f"  {entry['datetime']}  cloud={cloud}  artifact={entry['artifact_ref']}")

    # Retrieve band data and compute NDVI for each date
    store = runner.manager._get_store()
    ndvi_panels = []

    for entry in entries:
        data = await store.retrieve(entry["artifact_ref"])
        with rasterio.open(io.BytesIO(data)) as src:
            stack = src.read()
        red_band = stack[0]
        nir_band = stack[1]
        ndvi = compute_ndvi(red_band, nir_band)
        date_label = entry["datetime"][:10]
        cloud_pct = entry["cloud_cover"]
        ndvi_panels.append((date_label, cloud_pct, ndvi))

    # Render multi-panel NDVI
    n = len(ndvi_panels)
    cols = min(n, 4)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 5 * rows), squeeze=False)

    for idx, (date_label, cloud_pct, ndvi) in enumerate(ndvi_panels):
        r, c = divmod(idx, cols)
        ax = axes[r][c]
        im = ax.imshow(ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.8)
        cloud_str = f"{cloud_pct:.0f}%" if cloud_pct is not None else "N/A"
        ax.set_title(f"{date_label}\ncloud: {cloud_str}", fontsize=11)
        ax.axis("off")

    # Hide unused panels
    for idx in range(n, rows * cols):
        r, c = divmod(idx, cols)
        axes[r][c].axis("off")

    fig.suptitle(
        f"NDVI Time Series -- Colchester\n{DATE_RANGE}  |  {n} dates",
        fontsize=14,
        fontweight="bold",
    )
    fig.colorbar(im, ax=axes.ravel().tolist(), label="NDVI", shrink=0.6)
    fig.tight_layout()

    output_path = OUTPUT_DIR / "time_series_ndvi.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Dates:  {n}")
    print(f"  Bands:  {BANDS}")
    print(f"  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
