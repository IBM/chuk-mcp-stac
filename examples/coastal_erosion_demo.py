#!/usr/bin/env python3
"""
Coastline mapping -- Holderness Coast, Yorkshire

The Holderness coast is among the fastest-eroding in Europe (~1.8-2 m/yr of
boulder-clay cliff retreat). This demo maps the land/water boundary with
Sentinel-2 NDWI for two summers and shows *why optical NDWI alone cannot
measure that retreat* -- a deliberately honest example.

What it shows:
    stac_search -> stac_download_rgb -> stac_compute_index (ndwi)
    McFeeters NDWI = (Green - NIR) / (Green + NIR); >0 water, <0 land.
    The cyan line is the NDWI=0 coastline for each epoch.

What it does NOT claim:
    At 10 m GSD, ~8 years of ~1.9 m/yr retreat is ~15 m (~1.5 pixels), and the
    visible waterline swings hundreds of metres with the tide on this macrotidal
    coast. So any apparent shift here is dominated by tide/phenology/registration,
    NOT cliff retreat. Measuring the real rate needs the tide-independent
    cliff-top break-of-slope from repeat LiDAR/DEM differencing -- see the notes
    printed at the end.

Usage:
    python examples/coastal_erosion_demo.py

Output:
    examples/output/coastal_erosion.png

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

# Undefended Mappleton-Aldbrough cliff segment (boulder-clay tableland meeting
# the North Sea). West edge is the ~20 m till plateau; east edge is open sea.
BBOX = [-0.16, 53.79, -0.06, 53.89]
# Two clear-sky summers. The baseline length is deliberately not load-bearing:
# this demo maps the coastline, it does not measure retreat from it.
EARLY_RANGE = "2019-06-01/2019-08-31"
RECENT_RANGE = "2024-06-01/2024-08-31"
MAX_CLOUD_COVER = 25
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


async def find_scene(runner: ToolRunner, label: str, date_range: str) -> dict:
    """Search for the least-cloudy scene in a date range, or exit."""
    print(f"\nSearching {label} ({date_range})...")
    result = await runner.run(
        "stac_search",
        bbox=BBOX,
        date_range=date_range,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=10,
    )
    if result["scene_count"] == 0:
        print(f"  No {label} scenes found under {MAX_CLOUD_COVER}% cloud.")
        sys.exit(1)
    scene = min(result["scenes"], key=lambda s: s["cloud_cover"])
    print(f"  Found: {scene['scene_id']}  cloud={scene['cloud_cover']:.1f}%")
    return scene


async def load_rgb(runner: ToolRunner, store, scene: dict) -> np.ndarray:
    """Download an RGB composite and return it as a (3, H, W) array."""
    rgb = await runner.run("stac_download_rgb", scene_id=scene["scene_id"], bbox=BBOX)
    if "error" in rgb:
        print(f"  ERROR (rgb): {rgb['error']}")
        sys.exit(1)
    data = await store.retrieve(rgb["artifact_ref"])
    with rasterio.open(io.BytesIO(data)) as src:
        return src.read()


async def load_ndwi(runner: ToolRunner, store, scene: dict) -> np.ndarray:
    """Compute NDWI and return it as a 2-D float array (NaN = no data)."""
    ndwi = await runner.run(
        "stac_compute_index",
        scene_id=scene["scene_id"],
        index_name="ndwi",
        bbox=BBOX,
    )
    if "error" in ndwi:
        print(f"  ERROR (ndwi): {ndwi['error']}")
        sys.exit(1)
    data = await store.retrieve(ndwi["artifact_ref"])
    with rasterio.open(io.BytesIO(data)) as src:
        return src.read(1)


def water_fraction(ndwi: np.ndarray) -> float:
    """Fraction of valid pixels classified as water (NDWI > 0)."""
    valid = ~np.isnan(ndwi)
    if not np.any(valid):
        return 0.0
    return float(np.sum(ndwi[valid] > 0.0) / np.sum(valid))


def render_panel(ax, ndwi: np.ndarray, title: str):
    """NDWI heatmap with the NDWI=0 coastline drawn on top."""
    im = ax.imshow(ndwi, cmap="RdYlBu", vmin=-0.5, vmax=0.5)
    # Draw the land/water boundary explicitly so its position is legible.
    masked = np.where(np.isnan(ndwi), -1.0, ndwi)
    ax.contour(masked, levels=[0.0], colors="cyan", linewidths=0.8)
    ax.set_title(title, fontsize=12)
    ax.axis("off")
    return im


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner()

    print("=" * 64)
    print("Coastline mapping -- Holderness Coast (Mappleton-Aldbrough)")
    print("=" * 64)
    print(f"\n  bbox: {BBOX}")

    early_scene = await find_scene(runner, "early baseline", EARLY_RANGE)
    recent_scene = await find_scene(runner, "recent", RECENT_RANGE)

    store = runner.manager._get_store()

    print("\nDownloading RGB composites...")
    early_rgb = await load_rgb(runner, store, early_scene)
    recent_rgb = await load_rgb(runner, store, recent_scene)

    print("Computing NDWI (McFeeters water index)...")
    early_ndwi = await load_ndwi(runner, store, early_scene)
    recent_ndwi = await load_ndwi(runner, store, recent_scene)

    early_wf = water_fraction(early_ndwi)
    recent_wf = water_fraction(recent_ndwi)
    early_year = early_scene["datetime"][:4]
    recent_year = recent_scene["datetime"][:4]
    print(f"\n  {early_year} water fraction: {early_wf * 100:.1f}%")
    print(f"  {recent_year} water fraction: {recent_wf * 100:.1f}%")
    print(
        "  NOTE: the difference is tide + phenology + registration, NOT erosion.\n"
        "        (Sanity check: a correct NDWI here is well under 50%; the old\n"
        "         demo reported 100% because of a uint16 band-math overflow.)"
    )

    # -- Render ---------------------------------------------------------------
    print("\nRendering comparison...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))

    axes[0, 0].imshow(normalize_rgb(early_rgb))
    axes[0, 0].set_title(f"{early_year} RGB\n{early_scene['datetime'][:10]}", fontsize=12)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(normalize_rgb(recent_rgb))
    axes[0, 1].set_title(f"{recent_year} RGB\n{recent_scene['datetime'][:10]}", fontsize=12)
    axes[0, 1].axis("off")

    im = render_panel(axes[1, 0], early_ndwi, f"{early_year} NDWI (cyan = NDWI=0 coastline)")
    render_panel(axes[1, 1], recent_ndwi, f"{recent_year} NDWI (cyan = NDWI=0 coastline)")
    fig.colorbar(im, ax=axes[1, :], shrink=0.6, label="NDWI  (blue = water, red = land)")

    fig.suptitle(
        "Holderness Coast -- NDWI coastline mapping (Sentinel-2, 10 m)\n"
        "The waterline is tide-dependent; optical NDWI cannot resolve ~2 m/yr cliff retreat",
        fontsize=14,
        fontweight="bold",
    )

    output_path = OUTPUT_DIR / "coastal_erosion.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")

    print("\n" + "=" * 64)
    print("Demo complete.")
    print("  What this shows : NDWI correctly separates land (red) from sea (blue),")
    print("                    and the cyan line is the mapped coastline per epoch.")
    print("  What it can't do: measure ~1.9 m/yr retreat. ~8 yr ~= 15 m ~= 1.5 px at")
    print("                    10 m, and tide swings the waterline by hundreds of m.")
    print("  Right instrument: cliff-top break-of-slope from repeat LiDAR/DEM")
    print("                    differencing (tide-independent, metres directly).")
    print(f"\nOutput: {output_path}")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
