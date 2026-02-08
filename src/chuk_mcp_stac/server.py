#!/usr/bin/env python3
"""
STAC MCP Server - Entry Point

This module provides the async MCP server for satellite imagery
discovery and retrieval via STAC catalogs.
Supports both stdio (for Claude Desktop) and HTTP (for API access) transports.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .constants import EnvVar, SessionProvider, StorageProvider

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


def _init_artifact_store() -> bool:
    """
    Initialize the artifact store from environment variables.

    Returns:
        True if artifact store was initialized, False otherwise
    """
    provider = os.environ.get(EnvVar.ARTIFACTS_PROVIDER, StorageProvider.MEMORY)
    bucket = os.environ.get(EnvVar.BUCKET_NAME)
    redis_url = os.environ.get(EnvVar.REDIS_URL)
    artifacts_path = os.environ.get(EnvVar.ARTIFACTS_PATH)

    if provider == StorageProvider.S3:
        aws_key = os.environ.get(EnvVar.AWS_ACCESS_KEY_ID)
        aws_secret = os.environ.get(EnvVar.AWS_SECRET_ACCESS_KEY)
        aws_endpoint = os.environ.get(EnvVar.AWS_ENDPOINT_URL_S3)

        if not all([bucket, aws_key, aws_secret]):
            logger.warning(
                "S3 provider configured but missing credentials. "
                f"Set {EnvVar.AWS_ACCESS_KEY_ID}, {EnvVar.AWS_SECRET_ACCESS_KEY}, "
                f"and {EnvVar.BUCKET_NAME}."
            )
            return False

        logger.info(f"Initializing artifact store with S3 provider (bucket: {bucket})")
        logger.info(f"  Endpoint: {aws_endpoint}")
        logger.info(f"  Redis URL: {'configured' if redis_url else 'not configured'}")

    elif provider == StorageProvider.FILESYSTEM:
        if artifacts_path:
            path_obj = Path(artifacts_path)
            path_obj.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Initializing artifact store with filesystem provider (path: {artifacts_path})"
            )
        else:
            logger.warning(
                f"Filesystem provider configured but {EnvVar.ARTIFACTS_PATH} not set. "
                "Defaulting to memory provider."
            )
            provider = StorageProvider.MEMORY

    try:
        from chuk_artifacts import ArtifactStore
        from chuk_mcp_server import set_global_artifact_store

        # Use .value to ensure plain strings are passed to ArtifactStore
        # (Python 3.11+ str(Enum) returns "EnumClass.MEMBER" not the value)
        provider_str = provider.value if isinstance(provider, StorageProvider) else provider
        session_str = (
            SessionProvider.REDIS.value if redis_url else SessionProvider.MEMORY.value
        )

        store_kwargs: dict[str, Any] = {
            "storage_provider": provider_str,
            "session_provider": session_str,
        }

        if provider_str == StorageProvider.S3.value and bucket:
            store_kwargs["bucket"] = bucket
        elif provider_str == StorageProvider.FILESYSTEM.value and artifacts_path:
            store_kwargs["bucket"] = artifacts_path

        store = ArtifactStore(**store_kwargs)
        set_global_artifact_store(store)

        logger.info(f"Artifact store initialized successfully (provider: {provider})")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize artifact store: {e}")
        return False


# Import mcp instance and all registered tools from async server
from .async_server import mcp  # noqa: F401, E402


def main() -> None:
    """Main entry point for the MCP server."""
    import argparse

    # Initialize artifact store at startup, not at import time
    _init_artifact_store()

    parser = argparse.ArgumentParser(description="STAC MCP Server")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["stdio", "http"],
        default=None,
        help="Transport mode (stdio for Claude Desktop, http for API)",
    )
    parser.add_argument(
        "--host", default="localhost", help="Host for HTTP mode (default: localhost)"
    )
    parser.add_argument("--port", type=int, default=8002, help="Port for HTTP mode (default: 8002)")

    args = parser.parse_args()

    if args.mode == "stdio":
        print("STAC MCP Server starting in STDIO mode", file=sys.stderr)
        mcp.run(stdio=True)
    elif args.mode == "http":
        print(
            f"STAC MCP Server starting in HTTP mode on {args.host}:{args.port}",
            file=sys.stderr,
        )
        mcp.run(host=args.host, port=args.port, stdio=False)
    else:
        if os.environ.get(EnvVar.MCP_STDIO) or (not sys.stdin.isatty()):
            print("STAC MCP Server starting in STDIO mode (auto-detected)", file=sys.stderr)
            mcp.run(stdio=True)
        else:
            print(
                f"STAC MCP Server starting in HTTP mode on {args.host}:{args.port}",
                file=sys.stderr,
            )
            mcp.run(host=args.host, port=args.port, stdio=False)


if __name__ == "__main__":
    main()
