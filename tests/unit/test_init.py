"""Tests for package __init__."""

from __future__ import annotations

import reeln_cloudflare_plugin
from reeln_cloudflare_plugin.plugin import CloudflarePlugin


class TestPackageExports:
    def test_version_string(self) -> None:
        assert isinstance(reeln_cloudflare_plugin.__version__, str)
        assert reeln_cloudflare_plugin.__version__ == CloudflarePlugin.version

    def test_cloudflare_plugin_export(self) -> None:
        assert hasattr(reeln_cloudflare_plugin, "CloudflarePlugin")
        assert reeln_cloudflare_plugin.CloudflarePlugin is not None

    def test_all_exports(self) -> None:
        assert "CloudflarePlugin" in reeln_cloudflare_plugin.__all__
        assert "__version__" in reeln_cloudflare_plugin.__all__

    def test_version_matches_plugin(self) -> None:
        assert reeln_cloudflare_plugin.__version__ == CloudflarePlugin.version
