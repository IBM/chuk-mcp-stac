#!/usr/bin/env python3
"""
Collection Intelligence Demo -- chuk-mcp-stac

Demonstrates the Phase 5 introspection tools that help LLMs (and humans)
understand satellite collections before searching or downloading data.

Tools demonstrated:
    stac_describe_collection  -- band wavelengths, composites, LLM guidance
    stac_get_conformance      -- which STAC API features a catalog supports
    stac_estimate_size        -- estimate download size (header-only, no pixels)

The first two tools require network access to the STAC catalog.
stac_estimate_size requires a cached scene (run colchester_from_space.py first).

Usage:
    python examples/collection_intel_demo.py

Requirements:
    pip install chuk-mcp-stac
    (Requires network access to Earth Search STAC catalog)
"""

import asyncio

from tool_runner import ToolRunner


async def main() -> None:
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Collection Intelligence Demo")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Describe Collection -- rich metadata + LLM guidance
    # ------------------------------------------------------------------
    print("\n--- stac_describe_collection ---\n")
    print("Fetching Sentinel-2 L2A collection metadata...")

    detail = await runner.run(
        "stac_describe_collection",
        collection_id="sentinel-2-l2a",
        catalog="earth_search",
    )

    if "error" in detail:
        print(f"  Error: {detail['error']}")
    else:
        print(f"  Collection: {detail['collection_id']}")
        print(f"  Title: {detail.get('title', 'N/A')}")
        print(f"  Platform: {detail.get('platform', 'N/A')}")

        # Band info
        bands = detail.get("bands", [])
        if bands:
            print(f"\n  Bands ({len(bands)}):")
            for b in bands[:8]:
                wl = f"  {b['wavelength_nm']}nm" if b.get("wavelength_nm") else ""
                res = f"  {b['resolution_m']}m" if b.get("resolution_m") else ""
                print(f"    {b['name']:12s}{wl}{res}")
            if len(bands) > 8:
                print(f"    ... and {len(bands) - 8} more")

        # Composite recipes
        composites = detail.get("composites", [])
        if composites:
            print(f"\n  Recommended Composites ({len(composites)}):")
            for c in composites:
                print(f"    {c['name']:20s}  bands: {', '.join(c['bands'])}")
                if c.get("description"):
                    print(f"      {c['description']}")

        # Spectral indices
        indices = detail.get("spectral_indices", [])
        if indices:
            print(f"\n  Supported Spectral Indices: {', '.join(indices)}")

        # Cloud mask info
        if detail.get("cloud_mask_band"):
            print(f"\n  Cloud Mask Band: {detail['cloud_mask_band']}")

        # LLM guidance
        if detail.get("llm_guidance"):
            print(f"\n  LLM Guidance:\n    {detail['llm_guidance']}")

    # Same call in text mode for comparison
    print("\n  --- Text output mode ---")
    text = await runner.run_text(
        "stac_describe_collection",
        collection_id="sentinel-2-l2a",
        catalog="earth_search",
    )
    print(text)

    # ------------------------------------------------------------------
    # 2. Conformance -- what does the catalog support?
    # ------------------------------------------------------------------
    print("\n--- stac_get_conformance ---\n")
    print("Checking Earth Search API conformance...")

    conf = await runner.run("stac_get_conformance", catalog="earth_search")

    if "error" in conf:
        print(f"  Error: {conf['error']}")
    else:
        print(f"  Catalog: {conf['catalog']}")
        print(f"  Conformance available: {conf['conformance_available']}")

        features = conf.get("features", [])
        if features:
            print(f"\n  Feature Flags ({len(features)}):")
            for f in features:
                status = "YES" if f["supported"] else "no"
                print(f"    {f['name']:15s}  {status}")

        uris = conf.get("raw_uris", [])
        if uris:
            print(f"\n  Raw URIs ({len(uris)}):")
            for uri in uris[:5]:
                print(f"    {uri}")
            if len(uris) > 5:
                print(f"    ... and {len(uris) - 5} more")

    # Text mode
    print("\n  --- Text output mode ---")
    text = await runner.run_text("stac_get_conformance", catalog="earth_search")
    print(text)

    # ------------------------------------------------------------------
    # 3. Size Estimation -- requires a cached scene
    # ------------------------------------------------------------------
    print("\n--- stac_estimate_size ---\n")
    print("Estimating download size (requires a cached scene)...")
    print("Searching for a scene to cache first...\n")

    bbox = [0.85, 51.85, 0.95, 51.93]
    search = await runner.run(
        "stac_search",
        bbox=bbox,
        date_range="2024-06-01/2024-08-31",
        max_cloud_cover=20,
        max_items=1,
    )

    if search["scene_count"] == 0:
        print("  No scenes found. Skipping size estimation.")
    else:
        scene_id = search["scenes"][0]["scene_id"]
        print(f"  Scene: {scene_id}")

        estimate = await runner.run(
            "stac_estimate_size",
            scene_id=scene_id,
            bands=["red", "green", "blue", "nir"],
            bbox=bbox,
        )

        if "error" in estimate:
            print(f"  Error: {estimate['error']}")
        else:
            print(f"  Bands: {estimate['band_count']}")
            print(f"  Estimated size: {estimate['estimated_mb']:.1f} MB")
            print(f"  Total pixels: {estimate['total_pixels']:,}")
            print(f"  CRS: {estimate.get('crs', 'N/A')}")

            per_band = estimate.get("per_band", [])
            if per_band:
                print("\n  Per-band details:")
                for b in per_band:
                    print(
                        f"    {b['band']:8s}  "
                        f"{b['width']}x{b['height']}  "
                        f"{b['dtype']}  "
                        f"{b['bytes']:,} bytes"
                    )

            warnings = estimate.get("warnings", [])
            if warnings:
                print("\n  Warnings:")
                for w in warnings:
                    print(f"    {w}")

        # Text mode
        print("\n  --- Text output mode ---")
        text = await runner.run_text(
            "stac_estimate_size",
            scene_id=scene_id,
            bands=["red", "green", "blue", "nir"],
            bbox=bbox,
        )
        print(text)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("  stac_describe_collection: Band wavelengths, composites,")
    print("    spectral indices, cloud masking info, and LLM guidance")
    print("  stac_get_conformance: Feature flags parsed from STAC URIs")
    print("  stac_estimate_size: Download size from COG headers only")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
