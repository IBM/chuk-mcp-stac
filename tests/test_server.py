"""Tests for chuk_mcp_stac.server."""

import os
from unittest.mock import MagicMock, patch

from chuk_mcp_stac.server import _init_artifact_store


class TestInitArtifactStore:
    def test_memory_provider_default(self):
        mock_store_cls = MagicMock()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("chuk_mcp_stac.server.ArtifactStore", mock_store_cls, create=True),
            patch("chuk_artifacts.ArtifactStore", mock_store_cls, create=True),
            patch("chuk_mcp_server.set_global_artifact_store"),
        ):
            result = _init_artifact_store()
        assert result is True
        mock_store_cls.assert_called_once()
        call_kwargs = mock_store_cls.call_args[1]
        assert call_kwargs["storage_provider"] == "memory"

    def test_s3_provider_missing_creds(self):
        with patch.dict(
            os.environ,
            {"CHUK_ARTIFACTS_PROVIDER": "s3"},
            clear=True,
        ):
            result = _init_artifact_store()
        assert result is False

    def test_s3_provider_with_creds(self):
        mock_store_cls = MagicMock()
        env = {
            "CHUK_ARTIFACTS_PROVIDER": "s3",
            "BUCKET_NAME": "test-bucket",
            "AWS_ACCESS_KEY_ID": "AKID",
            "AWS_SECRET_ACCESS_KEY": "secret",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("chuk_artifacts.ArtifactStore", mock_store_cls),
            patch("chuk_mcp_server.set_global_artifact_store"),
        ):
            result = _init_artifact_store()
        assert result is True
        call_kwargs = mock_store_cls.call_args[1]
        assert call_kwargs["storage_provider"] == "s3"
        assert call_kwargs["bucket"] == "test-bucket"

    def test_filesystem_provider_creates_dir(self, tmp_path):
        artifacts_dir = tmp_path / "artifacts"
        mock_store_cls = MagicMock()
        env = {
            "CHUK_ARTIFACTS_PROVIDER": "filesystem",
            "CHUK_ARTIFACTS_PATH": str(artifacts_dir),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("chuk_artifacts.ArtifactStore", mock_store_cls),
            patch("chuk_mcp_server.set_global_artifact_store"),
        ):
            result = _init_artifact_store()
        assert result is True
        assert artifacts_dir.exists()

    def test_filesystem_without_path_falls_back(self):
        mock_store_cls = MagicMock()
        env = {"CHUK_ARTIFACTS_PROVIDER": "filesystem"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("chuk_artifacts.ArtifactStore", mock_store_cls),
            patch("chuk_mcp_server.set_global_artifact_store"),
        ):
            result = _init_artifact_store()
        assert result is True
        call_kwargs = mock_store_cls.call_args[1]
        assert call_kwargs["storage_provider"] == "memory"

    def test_import_error_returns_false(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("builtins.__import__", side_effect=ImportError("no module")),
        ):
            result = _init_artifact_store()
        assert result is False


class TestMain:
    def test_stdio_mode(self):
        from chuk_mcp_stac.server import main

        mock_mcp = MagicMock()
        with (
            patch("chuk_mcp_stac.server.mcp", mock_mcp),
            patch("chuk_mcp_stac.server._init_artifact_store", return_value=True),
            patch("sys.argv", ["chuk-mcp-stac", "stdio"]),
        ):
            main()
        mock_mcp.run.assert_called_once_with(stdio=True)

    def test_http_mode(self):
        from chuk_mcp_stac.server import main

        mock_mcp = MagicMock()
        with (
            patch("chuk_mcp_stac.server.mcp", mock_mcp),
            patch("chuk_mcp_stac.server._init_artifact_store", return_value=True),
            patch("sys.argv", ["chuk-mcp-stac", "http", "--port", "9000"]),
        ):
            main()
        mock_mcp.run.assert_called_once_with(host="localhost", port=9000, stdio=False)

    def test_auto_detect_stdio(self):
        from chuk_mcp_stac.server import main

        mock_mcp = MagicMock()
        with (
            patch("chuk_mcp_stac.server.mcp", mock_mcp),
            patch("chuk_mcp_stac.server._init_artifact_store", return_value=True),
            patch("sys.argv", ["chuk-mcp-stac"]),
            patch.dict(os.environ, {"MCP_STDIO": "1"}),
        ):
            main()
        mock_mcp.run.assert_called_once_with(stdio=True)

    def test_auto_detect_http(self):
        from chuk_mcp_stac.server import main

        mock_mcp = MagicMock()
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("chuk_mcp_stac.server.mcp", mock_mcp),
            patch("chuk_mcp_stac.server._init_artifact_store", return_value=True),
            patch("sys.argv", ["chuk-mcp-stac"]),
            patch("sys.stdin", mock_stdin),
            patch.dict(os.environ, {}, clear=True),
        ):
            main()
        mock_mcp.run.assert_called_once_with(host="localhost", port=8002, stdio=False)
