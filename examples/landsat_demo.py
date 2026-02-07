#!/usr/bin/env python3
"""
Landsat Demo -- chuk-mcp-stac

Search for Landsat Collection 2 Level-2 imagery, download RGB bands,
and render a true-colour image. Also demonstrates the Landsat-specific
band naming conventions (e.g. "nir08" instead of "nir").

Demonstrates:
    stac_capabilities (band mappings)
    stac_search (Landsat collection)
    stac_describe_scene
    stac_download_bands (Landsat RGB)

Usage:
    python examples/landsat_demo.py

Output:
    examples/output/landsat_rgb.png

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

# San Francisco Bay Area -- good Landsat coverage
BBOX = [-122.5, 37.5, -122.0, 37.9]
DATE_RANGE = "2024-06-01/2024-08-31"
COLLECTION = "landsat-c2-l2"
MAX_CLOUD_COVER = 20
MAX_ITEMS = 3
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
    print("chuk-mcp-stac -- Landsat Demo")
    print("=" * 60)

    # Step 1: Show band mapping differences
    caps = await runner.run("stac_capabilities")

    print("\nBand Naming Comparison:")
    s2_bands = caps["band_mappings"]["sentinel-2"]
    ls_bands = caps["band_mappings"]["landsat"]

    print(f"\n  Sentinel-2 bands ({len(s2_bands)}):")
    print(f"    {', '.join(s2_bands)}")
    print(f"\n  Landsat bands ({len(ls_bands)}):")
    print(f"    {', '.join(ls_bands)}")

    print("\n  Key difference: Landsat uses 'nir08' not 'nir'")
    print("  Landsat also has thermal bands (lwir11, lwir12)")

    # Step 2: Search for Landsat scenes
    print(f"\nSearching {COLLECTION} over San Francisco Bay...")
    print(f"  bbox: {BBOX}")
    print(f"  dates: {DATE_RANGE}")

    result = await runner.run(
        "stac_search",
        bbox=BBOX,
        collection=COLLECTION,
        date_range=DATE_RANGE,
        max_cloud_cover=MAX_CLOUD_COVER,
        max_items=MAX_ITEMS,
    )

    if result["scene_count"] == 0:
        print("\nNo Landsat scenes found. This may be due to the collection name")
        print("or STAC catalog availability. Try adjusting parameters.")
        return

    print(f"\nFound {result['scene_count']} Landsat scene(s):")
    for scene in result["scenes"]:
        print(f"  {scene['scene_id']}")
        print(f"    date={scene['datetime']}  cloud={scene['cloud_cover']}%")
        print(f"    assets={scene['asset_count']} bands")

    # Step 3: Describe the best scene
    best = result["scenes"][0]
    scene_id = best["scene_id"]
    print(f"\nDescribing scene: {scene_id}")

    detail = await runner.run("stac_describe_scene", scene_id=scene_id)

    print(f"  CRS: {detail['crs']}")
    print(f"  Assets ({len(detail['assets'])}):")
    for asset in detail["assets"][:8]:
        res = f"  {asset['resolution_m']}m" if asset["resolution_m"] else ""
        print(f"    {asset['key']}{res}  ({asset['media_type'] or 'unknown'})")

    # Step 4: Download RGB bands
    print(f"\nDownloading Landsat RGB bands: {BANDS}")
    dl_result = await runner.run(
        "stac_download_bands",
        scene_id=scene_id,
        bands=BANDS,
        bbox=BBOX,
    )

    if "error" in dl_result:
        print(f"\n  Download failed: {dl_result['error']}")
        if "403" in dl_result["error"] or "AWS" in dl_result["error"]:
            print("\n  Landsat COGs are in a requester-pays S3 bucket.")
            print("  To download, configure AWS credentials:")
            print("    export AWS_ACCESS_KEY_ID=<your-key>")
            print("    export AWS_SECRET_ACCESS_KEY=<your-secret>")
            print("  (You will be charged standard S3 data transfer fees.)")
        return

    print(f"  Artifact: {dl_result['artifact_ref']}")
    print(f"  Shape: {dl_result['shape']}  CRS: {dl_result['crs']}")
    if dl_result.get("preview_ref"):
        print(f"  Preview: {dl_result['preview_ref']}")

    # Step 5: Render the image
    print("\nRendering Landsat RGB...")
    store = runner.manager._get_store()
    data = await store.retrieve(dl_result["artifact_ref"])
    with rasterio.open(io.BytesIO(data)) as src:
        rgb_stack = src.read()

    rgb_img = normalize_rgb(rgb_stack)
    output_path = OUTPUT_DIR / "landsat_rgb.png"

    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(rgb_img)
    ax.set_title(
        f"Landsat -- San Francisco Bay\n{scene_id}\ncloud: {best['cloud_cover']}%",
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
    print(f"  Scene:  {scene_id}")
    print(f"  Cloud:  {best['cloud_cover']}%")
    print(f"  Shape:  {rgb_stack.shape[1]}x{rgb_stack.shape[2]} pixels")
    print(f"  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
