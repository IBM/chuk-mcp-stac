#!/usr/bin/env python3
"""
Capabilities Demo -- chuk-mcp-stac

Quick-start script showing what the server can do, without any network
access. Lists catalogs, collections, band mappings, spectral indices,
and server status.

Usage:
    python examples/capabilities_demo.py
"""

import asyncio

from tool_runner import ToolRunner


async def main() -> None:
    runner = ToolRunner()

    print("=" * 60)
    print("chuk-mcp-stac -- Server Capabilities")
    print("=" * 60)

    # List all registered tools
    print(f"\nRegistered tools ({len(runner.tool_names)}):")
    for name in sorted(runner.tool_names):
        print(f"  - {name}")

    # Server capabilities
    caps = await runner.run("stac_capabilities")
    print(f"\nServer: {caps['server']} v{caps['version']}")

    # Catalogs
    print(f"\nSTAC Catalogs ({len(caps['catalogs'])}):")
    for cat in caps["catalogs"]:
        default = " (default)" if cat["name"] == caps["default_catalog"] else ""
        print(f"  {cat['name']}{default}")
        print(f"    {cat['url']}")

    # Collections
    print(f"\nKnown Collections ({len(caps['known_collections'])}):")
    for coll in caps["known_collections"]:
        print(f"  - {coll}")

    # Band mappings
    print("\nBand Mappings:")
    for platform, bands in caps["band_mappings"].items():
        print(f"  {platform}: {', '.join(bands)}")

    # Spectral indices
    print(f"\nSpectral Indices ({len(caps['spectral_indices'])}):")
    for idx in caps["spectral_indices"]:
        print(f"  {idx['name']:6s}  requires: {', '.join(idx['required_bands'])}")

    # List catalogs (separate tool)
    catalogs = await runner.run("stac_list_catalogs")
    print(f"\nstac_list_catalogs: {catalogs['message']}")

    print("\n" + "=" * 60)
    print("All capabilities shown above require no network access.")
    print("Run other demos (colchester, mosaic, time_series, landsat)")
    print("to see the full STAC search and download pipeline in action.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
