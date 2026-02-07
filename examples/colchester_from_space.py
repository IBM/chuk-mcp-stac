#!/usr/bin/env python3
"""
Colchester from Space -- chuk-mcp-stac Demo

Pull Sentinel-2 imagery of Colchester using the MCP tools directly,
download RGB and NIR bands, render true-colour and NDVI images.

Demonstrates the full STAC pipeline via MCP tool calls:
    stac_search -> stac_download_rgb -> stac_download_bands -> NDVI

Each tool returns JSON with artifact references and metadata.

Usage:
    python examples/colchester_from_space.py

Output:
    examples/output/colchester_rgb.png
    examples/output/colchester_ndvi.png
    examples/output/colchester_combined.png

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
DATE_RANGE = "2024-06-01/2024-08-31"  # Summer for clear skies + green vegetation
MAX_CLOUD_COVER = 15
MAX_ITEMS = 5
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


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute NDVI = (NIR - RED) / (NIR + RED)."""
    red_f = red.astype(np.float32)
    nir_f = nir.astype(np.float32)
    denom = nir_f + red_f
    return np.where(denom > 0, (nir_f - red_f) / denom, 0.0)


def render_combined(
    rgb_stack: np.ndarray,
    ndvi: np.ndarray,
    scene_id: str,
    cloud_cover: float,
    output_path: Path,
) -> None:
    """Side-by-side RGB and NDVI rendering."""
    rgb_img = normalize_rgb(rgb_stack)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 9))

    ax1.imshow(rgb_img)
    ax1.set_title("True Colour RGB", fontsize=13)
    ax1.axis("off")

    im = ax2.imshow(ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    ax2.set_title("NDVI -- Vegetation Index", fontsize=13)
    ax2.axis("off")
    fig.colorbar(im, ax=ax2, label="NDVI", shrink=0.7)

    fig.suptitle(
        f"Colchester from Space\nSentinel-2 | {scene_id} | cloud {cloud_cover}%",
        fontsize=15,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def render_rgb(rgb_stack: np.ndarray, output_path: Path) -> None:
    """Render and save the RGB composite."""
    rgb_img = normalize_rgb(rgb_stack)
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(rgb_img)
    ax.set_title("Colchester from Space -- Sentinel-2 True Colour", fontsize=14)
    ax.set_xlabel(f"bbox: {BBOX}")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def render_ndvi(ndvi: np.ndarray, output_path: Path) -> None:
    """Render and save the NDVI image."""
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    im = ax.imshow(ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    ax.set_title("Colchester NDVI -- Vegetation Index", fontsize=14)
    ax.set_xlabel("Green = vegetation  |  Red/yellow = urban/bare")
    ax.axis("off")
    fig.colorbar(im, ax=ax, label="NDVI", shrink=0.7)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


# -- Main pipeline -----------------------------------------------------------


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    # Step 1: Search for scenes
    # Equivalent MCP call: stac_search(bbox=BBOX, date_range=..., max_cloud_cover=15)
    print("Step 1: Searching for Sentinel-2 scenes over Colchester...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")
    print(f"  max cloud: {MAX_CLOUD_COVER}%")

    search_result = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if search_result["scene_count"] == 0:
        print("\nNo scenes found. Try widening the date range or cloud cover threshold.")
        sys.exit(1)

    print(f"  Found {search_result['scene_count']} scene(s)")
    for scene in search_result["scenes"]:
        print(f"    {scene['scene_id']}  cloud={scene['cloud_cover']}%  date={scene['datetime']}")

    best = search_result["scenes"][0]
    scene_id = best["scene_id"]
    cloud_cover = best["cloud_cover"]
    print(f"\nUsing best scene: {scene_id}")

    # Step 2: Describe the scene (shows available bands)
    # Equivalent MCP call: stac_describe_scene(scene_id=...)
    print("\nStep 2: Describing scene assets...")
    detail = await runner.run("stac_describe_scene", scene_id=scene_id)
    print(f"  CRS: {detail['crs']}")
    print(f"  Assets: {len(detail['assets'])} data bands")
    for asset in detail["assets"][:6]:
        res = f"  {asset['resolution_m']}m" if asset["resolution_m"] else ""
        print(f"    {asset['key']}{res}")

    # Step 3: Download RGB bands
    # Equivalent MCP call: stac_download_rgb(scene_id=..., bbox=BBOX)
    print("\nStep 3: Downloading RGB composite...")
    rgb_result = await runner.run("stac_download_rgb", scene_id=scene_id, bbox=BBOX)
    if "error" in rgb_result:
        print(f"  ERROR: {rgb_result['error']}")
        sys.exit(1)
    print(f"  Artifact: {rgb_result['artifact_ref']}")
    print(f"  Shape: {rgb_result['shape']}  CRS: {rgb_result['crs']}")

    # Retrieve raster bytes from artifact store and read with rasterio
    store = runner.manager._get_store()
    rgb_data = await store.retrieve(rgb_result["artifact_ref"])
    with rasterio.open(io.BytesIO(rgb_data)) as src:
        rgb_stack = src.read()
    print(f"  Array shape: {rgb_stack.shape}")

    # Step 4: Download RED + NIR for NDVI
    # Equivalent MCP call: stac_download_bands(scene_id=..., bands=["red", "nir"], bbox=BBOX)
    print("\nStep 4: Downloading RED + NIR bands...")
    ndvi_result = await runner.run(
        "stac_download_bands", scene_id=scene_id, bands=["red", "nir"], bbox=BBOX
    )
    if "error" in ndvi_result:
        print(f"  ERROR: {ndvi_result['error']}")
        sys.exit(1)
    ndvi_data = await store.retrieve(ndvi_result["artifact_ref"])
    with rasterio.open(io.BytesIO(ndvi_data)) as src:
        ndvi_stack = src.read()

    # Step 5: Compute NDVI
    print("\nStep 5: Computing NDVI...")
    red_band = ndvi_stack[0]
    nir_band = ndvi_stack[1]
    ndvi = compute_ndvi(red_band, nir_band)
    ndvi_mean = np.nanmean(ndvi)
    ndvi_min, ndvi_max = np.nanmin(ndvi), np.nanmax(ndvi)
    print(f"  NDVI range: [{ndvi_min:.3f}, {ndvi_max:.3f}]  mean: {ndvi_mean:.3f}")

    # Step 6: Render outputs
    print("\nStep 6: Rendering outputs...")
    render_rgb(rgb_stack, OUTPUT_DIR / "colchester_rgb.png")
    render_ndvi(ndvi, OUTPUT_DIR / "colchester_ndvi.png")
    render_combined(rgb_stack, ndvi, scene_id, cloud_cover, OUTPUT_DIR / "colchester_combined.png")

    # Summary
    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Scene:  {scene_id}")
    print(f"  Cloud:  {cloud_cover}%")
    print(f"  Shape:  {rgb_stack.shape[1]}x{rgb_stack.shape[2]} pixels")
    print(f"  NDVI:   mean={ndvi_mean:.3f} [{ndvi_min:.3f}, {ndvi_max:.3f}]")
    print(f"\nOutputs in {OUTPUT_DIR}/:")
    print("  colchester_rgb.png       -- true colour satellite image")
    print("  colchester_ndvi.png      -- vegetation index (green=plants)")
    print("  colchester_combined.png  -- side-by-side comparison")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
