#!/usr/bin/env python3
"""
False Color Composite Demo -- chuk-mcp-stac

Create false-color composites that reveal features invisible in true-color
imagery. Compares standard RGB with false-color infrared (vegetation in
bright red) and agriculture composite (crop health).

Demonstrates:
    stac_describe_collection -> stac_search -> stac_download_rgb ->
    stac_download_composite (false-color IR, agriculture)

Usage:
    python examples/false_color_demo.py

Output:
    examples/output/false_color_comparison.png

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

BBOX = [0.85, 51.85, 0.95, 51.93]  # Colchester, Essex, UK
DATE_RANGE = "2024-06-01/2024-08-31"  # Summer for clear skies
MAX_CLOUD_COVER = 15
OUTPUT_DIR = Path(__file__).parent / "output"


# -- Rendering helpers -------------------------------------------------------


def normalize_rgb(rgb_stack: np.ndarray) -> np.ndarray:
    """Normalize Sentinel-2 reflectance to 0-1 using 2nd-98th percentile."""
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


# -- Main pipeline -----------------------------------------------------------


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- False Color Composite Demo")
    print("=" * 60)

    # Step 1: Explore collection intelligence for composite recipes
    print("\nStep 1: Exploring Sentinel-2 composite recipes...")
    collection_info = await runner.run("stac_describe_collection", collection_id="sentinel-2-l2a")

    if "error" in collection_info:
        print(f"  ERROR: {collection_info['error']}")
        sys.exit(1)

    intel = collection_info.get("intelligence", {})
    composites = intel.get("recommended_composites", {})
    print(f"  Collection: {collection_info.get('collection_id', 'sentinel-2-l2a')}")
    print(f"  Available composites ({len(composites)}):")
    for name, recipe in composites.items():
        bands = recipe if isinstance(recipe, list) else recipe.get("bands", recipe)
        print(f"    {name}: {bands}")

    # Step 2: Search for a clear scene
    print("\nStep 2: Searching for clear scenes over Colchester...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")

    search_result = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=5,
    )

    if search_result["scene_count"] == 0:
        print("\nNo scenes found. Try widening the date range or cloud cover.")
        sys.exit(1)

    print(f"  Found {search_result['scene_count']} scene(s)")
    for scene in search_result["scenes"][:3]:
        print(f"    {scene['scene_id']}  cloud={scene['cloud_cover']}%")

    best = search_result["scenes"][0]
    scene_id = best["scene_id"]
    print(f"\n  Using: {scene_id} (cloud={best['cloud_cover']}%)")

    store = runner.manager._get_store()

    # Step 3: Download true-color RGB
    print("\nStep 3: Downloading true-color RGB...")
    rgb_result = await runner.run("stac_download_rgb", scene_id=scene_id, bbox=BBOX)
    if "error" in rgb_result:
        print(f"  ERROR: {rgb_result['error']}")
        sys.exit(1)
    print(f"  Shape: {rgb_result['shape']}  CRS: {rgb_result['crs']}")

    rgb_data = await store.retrieve(rgb_result["artifact_ref"])
    with rasterio.open(io.BytesIO(rgb_data)) as src:
        rgb_stack = src.read()

    # Step 4: Download false-color infrared composite (nir, red, green)
    # Vegetation appears bright red/magenta, water appears dark
    print("\nStep 4: Downloading false-color infrared (NIR, Red, Green)...")
    fcir_result = await runner.run(
        "stac_download_composite",
        scene_id=scene_id,
        bands=["nir", "red", "green"],
        composite_name="false_color_ir",
        bbox=BBOX,
    )
    if "error" in fcir_result:
        print(f"  ERROR: {fcir_result['error']}")
        sys.exit(1)
    print(f"  Shape: {fcir_result['shape']}  CRS: {fcir_result['crs']}")

    fcir_data = await store.retrieve(fcir_result["artifact_ref"])
    with rasterio.open(io.BytesIO(fcir_data)) as src:
        fcir_stack = src.read()

    # Step 5: Download agriculture composite (swir16, nir, blue)
    # Healthy crops appear green, stressed crops in brown
    print("\nStep 5: Downloading agriculture composite (SWIR, NIR, Blue)...")
    agri_result = await runner.run(
        "stac_download_composite",
        scene_id=scene_id,
        bands=["swir16", "nir", "blue"],
        composite_name="agriculture",
        bbox=BBOX,
    )
    if "error" in agri_result:
        print(f"  ERROR: {agri_result['error']}")
        sys.exit(1)
    print(f"  Shape: {agri_result['shape']}  CRS: {agri_result['crs']}")

    agri_data = await store.retrieve(agri_result["artifact_ref"])
    with rasterio.open(io.BytesIO(agri_data)) as src:
        agri_stack = src.read()

    # Step 6: Render 3-panel comparison
    print("\nStep 6: Rendering comparison...")
    rgb_img = normalize_rgb(rgb_stack)
    fcir_img = normalize_rgb(fcir_stack)
    agri_img = normalize_rgb(agri_stack)

    fig, axes = plt.subplots(1, 3, figsize=(21, 7))

    axes[0].imshow(rgb_img)
    axes[0].set_title("True Color\n(Red, Green, Blue)", fontsize=12)
    axes[0].axis("off")

    axes[1].imshow(fcir_img)
    axes[1].set_title("False Color Infrared\n(NIR, Red, Green)", fontsize=12)
    axes[1].text(
        0.5,
        -0.05,
        "Vegetation = bright red/pink",
        transform=axes[1].transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    axes[1].axis("off")

    axes[2].imshow(agri_img)
    axes[2].set_title("Agriculture\n(SWIR, NIR, Blue)", fontsize=12)
    axes[2].text(
        0.5,
        -0.05,
        "Healthy crops = green, stressed = brown",
        transform=axes[2].transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    axes[2].axis("off")

    fig.suptitle(
        f"False Color Composites -- Colchester, UK\nSentinel-2 | {scene_id}",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    output_path = OUTPUT_DIR / "false_color_comparison.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Scene: {scene_id}")
    print(f"  Cloud: {best['cloud_cover']}%")
    print("  Composites rendered:")
    print("    True Color     -- standard RGB (red, green, blue)")
    print("    False Color IR -- vegetation highlights (nir, red, green)")
    print("    Agriculture    -- crop health (swir16, nir, blue)")
    print(f"\nOutput: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
