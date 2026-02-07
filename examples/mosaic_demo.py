#!/usr/bin/env python3
"""
Mosaic Demo -- chuk-mcp-stac

Search for multiple Sentinel-2 scenes from different dates and merge
them into a single mosaic raster using the stac_mosaic tool.
Renders the mosaic as a true-colour RGB image.

Demonstrates:
    stac_search -> stac_mosaic -> render PNG

Usage:
    python examples/mosaic_demo.py

Output:
    examples/output/mosaic_rgb.png

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

# Tight bbox within a single UTM zone to avoid CRS mismatch
BBOX = [0.85, 51.85, 0.95, 51.93]  # Colchester, same UTM zone 30
DATE_RANGE = "2024-06-01/2024-08-31"
MAX_CLOUD_COVER = 20
MAX_ITEMS = 5
BANDS = ["red", "green", "blue"]
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
    print("chuk-mcp-stac -- Mosaic Demo")
    print("=" * 60)

    # Step 1: Search for scenes (multiple dates, same tile/CRS)
    print("\nSearching for scenes over Colchester (same UTM zone)...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")

    result = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if result["scene_count"] < 2:
        print(f"\nNeed at least 2 scenes for mosaic, found {result['scene_count']}.")
        print("Try widening the date range or cloud cover threshold.")
        return

    print(f"\nFound {result['scene_count']} scene(s):")
    for scene in result["scenes"]:
        print(f"  {scene['scene_id']}  cloud={scene['cloud_cover']}%  date={scene['datetime']}")

    # Filter to same tile prefix so CRS matches (e.g., all 30UYC scenes)
    first_tile = result["scenes"][0]["scene_id"].split("_")[1]
    same_tile = [s for s in result["scenes"] if first_tile in s["scene_id"]]

    if len(same_tile) < 2:
        print(f"\nOnly {len(same_tile)} scene(s) from tile {first_tile}.")
        same_tile = result["scenes"][:2]
    else:
        print(f"\nFiltered to {len(same_tile)} scenes from tile {first_tile}")

    # Step 2: Take 2 scenes and mosaic them
    scene_ids = [s["scene_id"] for s in same_tile[:2]]
    print(f"\nCreating mosaic from {len(scene_ids)} scenes...")
    print(f"  Scenes: {scene_ids}")
    print(f"  Bands: {BANDS}")

    mosaic_result = await runner.run(
        "stac_mosaic",
        scene_ids=scene_ids,
        bands=BANDS,
        bbox=BBOX,
    )

    if "error" in mosaic_result:
        print(f"\nMosaic failed: {mosaic_result['error']}")
        return

    print(f"\n  Artifact: {mosaic_result['artifact_ref']}")
    print(f"  CRS: {mosaic_result['crs']}")
    print(f"  Shape: {mosaic_result['shape']}")
    if mosaic_result.get("preview_ref"):
        print(f"  Preview: {mosaic_result['preview_ref']}")

    # Step 3: Retrieve and render the mosaic
    print("\nRendering mosaic RGB...")
    store = runner.manager._get_store()
    data = await store.retrieve(mosaic_result["artifact_ref"])
    with rasterio.open(io.BytesIO(data)) as src:
        rgb_stack = src.read()

    rgb_img = normalize_rgb(rgb_stack)
    output_path = OUTPUT_DIR / "mosaic_rgb.png"

    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(rgb_img)
    ax.set_title(
        f"Mosaic -- {len(scene_ids)} Sentinel-2 scenes\n"
        f"{', '.join(s.split('_')[0] + ' ' + s.split('_')[1] for s in scene_ids)}",
        fontsize=13,
    )
    ax.set_xlabel(f"bbox: {BBOX}")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Scenes: {len(scene_ids)}")
    print(f"  Shape:  {rgb_stack.shape[1]}x{rgb_stack.shape[2]} pixels")
    print(f"  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
