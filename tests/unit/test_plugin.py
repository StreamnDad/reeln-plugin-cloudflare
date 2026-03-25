"""Tests for plugin module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import HookRegistry

from reeln_cloudflare_plugin.plugin import CloudflarePlugin
from reeln_cloudflare_plugin.r2 import R2Error
from tests.conftest import FakeRenderResult


class TestCloudflarePluginAttributes:
    def test_name(self) -> None:
        plugin = CloudflarePlugin()
        assert plugin.name == "cloudflare"

    def test_version(self) -> None:
        plugin = CloudflarePlugin()
        assert plugin.version == "0.2.0"

    def test_api_version(self) -> None:
        plugin = CloudflarePlugin()
        assert plugin.api_version == 1


class TestCloudflarePluginConfigSchema:
    def test_r2_endpoint_required(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("r2_endpoint")
        assert field is not None
        assert field.required is True

    def test_r2_bucket_required(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("r2_bucket")
        assert field is not None
        assert field.required is True

    def test_r2_access_key_env_required(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("r2_access_key_env")
        assert field is not None
        assert field.required is True

    def test_r2_secret_key_env_required(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("r2_secret_key_env")
        assert field is not None
        assert field.required is True

    def test_public_url_base_required(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("public_url_base")
        assert field is not None
        assert field.required is True

    def test_upload_video_default_false(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("upload_video")
        assert field is not None
        assert field.default is False

    def test_upload_prefix_default_empty(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("upload_prefix")
        assert field is not None
        assert field.default == ""

    def test_upload_max_kbps_default_zero(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("upload_max_kbps")
        assert field is not None
        assert field.default == 0

    def test_dry_run_default_false(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("dry_run")
        assert field is not None
        assert field.default is False

    def test_r2_region_default_auto(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("r2_region")
        assert field is not None
        assert field.default == "auto"


class TestCloudflarePluginConfigSchemaCleanup:
    def test_cleanup_after_game_default_false(self) -> None:
        schema = CloudflarePlugin.config_schema
        field = schema.field_by_name("cleanup_after_game")
        assert field is not None
        assert field.default is False


class TestRegisterHooks:
    def test_registers_post_render_and_game_finish(self) -> None:
        plugin = CloudflarePlugin()
        registry = HookRegistry()
        plugin.register(registry)

        assert registry.has_handlers(Hook.POST_RENDER)
        assert registry.has_handlers(Hook.ON_GAME_FINISH)
        assert registry.has_handlers(Hook.ON_POST_GAME_FINISH)


def _make_context(
    data: dict[str, Any] | None = None,
    shared: dict[str, Any] | None = None,
) -> HookContext:
    return HookContext(
        hook=Hook.POST_RENDER,
        data=data or {},
        shared=shared if shared is not None else {},
    )


class TestOnPostRenderDisabled:
    def test_feature_flag_disabled(self) -> None:
        plugin = CloudflarePlugin({"upload_video": False})
        context = _make_context()
        plugin.on_post_render(context)
        assert "video_url" not in context.shared

    def test_feature_flag_missing(self) -> None:
        plugin = CloudflarePlugin({})
        context = _make_context()
        plugin.on_post_render(context)
        assert "video_url" not in context.shared


class TestOnPostRenderMissingData:
    def test_missing_result(
        self, plugin_config: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "no result" in caplog.text
        assert "video_url" not in context.shared

    def test_missing_output_file(
        self,
        plugin_config: dict[str, Any],
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        result = FakeRenderResult(output=tmp_path / "nonexistent.mp4")
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "output file not found" in caplog.text
        assert "video_url" not in context.shared

    def test_result_without_output_attr(
        self,
        plugin_config: dict[str, Any],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": object()})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "output file not found" in caplog.text


class TestOnPostRenderCredentials:
    def test_missing_env_var_names(
        self, video_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config: dict[str, Any] = {
            "upload_video": True,
            "r2_endpoint": "https://x.r2.cloudflarestorage.com",
            "r2_bucket": "b",
            "r2_access_key_env": "",
            "r2_secret_key_env": "",
            "public_url_base": "https://cdn.example.com",
        }
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(config)
        context = _make_context(data={"result": result})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "must be configured" in caplog.text
        assert "video_url" not in context.shared

    def test_empty_env_vars(
        self,
        plugin_config: dict[str, Any],
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "")
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "empty or not set" in caplog.text
        assert "video_url" not in context.shared

    def test_missing_access_key_env(
        self,
        plugin_config: dict[str, Any],
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "empty or not set" in caplog.text

    def test_missing_secret_key_env(
        self,
        plugin_config: dict[str, Any],
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})
        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)
        assert "empty or not set" in caplog.text


class TestOnPostRenderDryRun:
    def test_dry_run_logs_without_uploading(
        self,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        plugin_config["dry_run"] = True
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})
        with caplog.at_level(logging.INFO):
            plugin.on_post_render(context)
        assert "DRY RUN" in caplog.text
        assert "video_url" not in context.shared


class TestOnPostRenderFullFlow:
    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_success(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/highlight.mp4"
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        assert context.shared["video_url"] == "https://cdn.example.com/highlight.mp4"
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        # positional: (config, source, key)
        assert call_args[0][1] == video_file
        assert call_args[0][2] == "highlight.mp4"

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_with_prefix(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/reels/highlight.mp4"
        plugin_config["upload_prefix"] = "reels"
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        call_args = mock_upload.call_args
        assert call_args[0][2] == "reels/highlight.mp4"

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_with_empty_prefix(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/highlight.mp4"
        plugin_config["upload_prefix"] = ""
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        call_args = mock_upload.call_args
        assert call_args[0][2] == "highlight.mp4"

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_error_non_fatal(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_upload.side_effect = R2Error("Connection refused")
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        with caplog.at_level(logging.WARNING):
            plugin.on_post_render(context)

        assert "upload failed" in caplog.text
        assert "video_url" not in context.shared

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_passes_config_fields(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/highlight.mp4"
        plugin_config["r2_region"] = "us-east-1"
        plugin_config["upload_max_kbps"] = 1000
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        call_args = mock_upload.call_args
        r2_config = call_args[0][0]
        assert r2_config.region == "us-east-1"
        assert r2_config.upload_max_kbps == 1000
        assert r2_config.endpoint == "https://account-id.r2.cloudflarestorage.com"
        assert r2_config.bucket == "test-bucket"
        assert r2_config.public_url_base == "https://cdn.example.com"

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_trailing_slash_on_public_url_base(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/highlight.mp4"
        plugin_config["public_url_base"] = "https://cdn.example.com/"
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        # The R2Config is constructed with trailing slash — r2.upload_file handles stripping
        call_args = mock_upload.call_args
        r2_config = call_args[0][0]
        assert r2_config.public_url_base == "https://cdn.example.com/"


class TestOnPostRenderTracksKeys:
    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_appends_key(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/highlight.mp4"
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        assert plugin._uploaded_keys == ["highlight.mp4"]

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_with_prefix_appends_prefixed_key(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/reels/highlight.mp4"
        plugin_config["upload_prefix"] = "reels"
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        assert plugin._uploaded_keys == ["reels/highlight.mp4"]

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    def test_upload_failure_does_not_track_key(
        self,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.side_effect = R2Error("fail")
        result = FakeRenderResult(output=video_file)
        plugin = CloudflarePlugin(plugin_config)
        context = _make_context(data={"result": result})

        plugin.on_post_render(context)

        assert plugin._uploaded_keys == []


class TestOnGameFinish:
    def test_on_game_finish_resets_uploaded_keys(self) -> None:
        plugin = CloudflarePlugin()
        plugin._uploaded_keys = ["key1.mp4", "key2.mp4"]
        context = HookContext(hook=Hook.ON_GAME_FINISH, data={}, shared={})
        plugin.on_game_finish(context)
        assert plugin._uploaded_keys == []


def _make_post_game_context(
    shared: dict[str, Any] | None = None,
) -> HookContext:
    return HookContext(
        hook=Hook.ON_POST_GAME_FINISH,
        data={},
        shared=shared if shared is not None else {},
    )


class TestOnPostGameFinishDisabled:
    def test_cleanup_disabled_by_default(self) -> None:
        plugin = CloudflarePlugin({})
        plugin._uploaded_keys = ["key.mp4"]
        context = _make_post_game_context()
        plugin.on_post_game_finish(context)
        # Keys not cleared — handler returned early
        assert plugin._uploaded_keys == ["key.mp4"]

    def test_cleanup_explicitly_disabled(self) -> None:
        plugin = CloudflarePlugin({"cleanup_after_game": False})
        plugin._uploaded_keys = ["key.mp4"]
        context = _make_post_game_context()
        plugin.on_post_game_finish(context)
        assert plugin._uploaded_keys == ["key.mp4"]


class TestOnPostGameFinishNoUploads:
    def test_no_uploads_no_deletes(self, r2_env: None) -> None:
        plugin = CloudflarePlugin({"cleanup_after_game": True})
        context = _make_post_game_context()
        plugin.on_post_game_finish(context)
        assert plugin._uploaded_keys == []


class TestOnPostGameFinishCredentialFailure:
    def test_credential_failure_warns(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        plugin = CloudflarePlugin({
            "cleanup_after_game": True,
            "r2_access_key_env": "",
            "r2_secret_key_env": "",
        })
        plugin._uploaded_keys = ["key.mp4"]
        context = _make_post_game_context()
        with caplog.at_level(logging.WARNING):
            plugin.on_post_game_finish(context)
        assert "credentials unavailable" in caplog.text


class TestOnPostGameFinishDryRun:
    def test_dry_run_logs_without_deleting(
        self,
        plugin_config: dict[str, Any],
        r2_env: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        plugin_config["cleanup_after_game"] = True
        plugin_config["dry_run"] = True
        plugin = CloudflarePlugin(plugin_config)
        plugin._uploaded_keys = ["key1.mp4", "key2.mp4"]
        context = _make_post_game_context()
        with caplog.at_level(logging.INFO):
            plugin.on_post_game_finish(context)
        assert "DRY RUN" in caplog.text
        assert "key1.mp4" in caplog.text
        assert "key2.mp4" in caplog.text


class TestOnPostGameFinishFullFlow:
    @patch("reeln_cloudflare_plugin.r2.delete_object")
    def test_deletes_all_uploaded_keys(
        self,
        mock_delete: Any,
        plugin_config: dict[str, Any],
        r2_env: None,
    ) -> None:
        plugin_config["cleanup_after_game"] = True
        plugin = CloudflarePlugin(plugin_config)
        plugin._uploaded_keys = ["a.mp4", "b.mp4", "c.mp4"]
        context = _make_post_game_context()

        plugin.on_post_game_finish(context)

        assert mock_delete.call_count == 3
        deleted_keys = [call[0][1] for call in mock_delete.call_args_list]
        assert deleted_keys == ["a.mp4", "b.mp4", "c.mp4"]

    @patch("reeln_cloudflare_plugin.r2.delete_object")
    def test_delete_failure_non_fatal(
        self,
        mock_delete: Any,
        plugin_config: dict[str, Any],
        r2_env: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_delete.side_effect = [
            None,
            R2Error("Access denied"),
            None,
        ]
        plugin_config["cleanup_after_game"] = True
        plugin = CloudflarePlugin(plugin_config)
        plugin._uploaded_keys = ["a.mp4", "b.mp4", "c.mp4"]
        context = _make_post_game_context()

        with caplog.at_level(logging.WARNING):
            plugin.on_post_game_finish(context)

        assert mock_delete.call_count == 3
        assert "failed to delete" in caplog.text
        assert "b.mp4" in caplog.text

    @patch("reeln_cloudflare_plugin.r2.delete_object")
    def test_passes_correct_r2_config(
        self,
        mock_delete: Any,
        plugin_config: dict[str, Any],
        r2_env: None,
    ) -> None:
        plugin_config["cleanup_after_game"] = True
        plugin_config["r2_region"] = "us-east-1"
        plugin = CloudflarePlugin(plugin_config)
        plugin._uploaded_keys = ["key.mp4"]
        context = _make_post_game_context()

        plugin.on_post_game_finish(context)

        call_args = mock_delete.call_args
        r2_config = call_args[0][0]
        assert r2_config.endpoint == "https://account-id.r2.cloudflarestorage.com"
        assert r2_config.bucket == "test-bucket"
        assert r2_config.region == "us-east-1"

    @patch("reeln_cloudflare_plugin.r2.upload_file")
    @patch("reeln_cloudflare_plugin.r2.delete_object")
    def test_full_upload_then_cleanup(
        self,
        mock_delete: Any,
        mock_upload: Any,
        plugin_config: dict[str, Any],
        video_file: Path,
        r2_env: None,
    ) -> None:
        mock_upload.return_value = "https://cdn.example.com/highlight.mp4"
        plugin_config["cleanup_after_game"] = True
        plugin = CloudflarePlugin(plugin_config)

        # Simulate POST_RENDER
        result = FakeRenderResult(output=video_file)
        render_ctx = _make_context(data={"result": result})
        plugin.on_post_render(render_ctx)

        assert plugin._uploaded_keys == ["highlight.mp4"]

        # Simulate ON_POST_GAME_FINISH
        finish_ctx = _make_post_game_context()
        plugin.on_post_game_finish(finish_ctx)

        mock_delete.assert_called_once()
        assert mock_delete.call_args[0][1] == "highlight.mp4"


class TestDefaultConfig:
    def test_empty_config(self) -> None:
        plugin = CloudflarePlugin()
        assert plugin._config == {}

    def test_none_config(self) -> None:
        plugin = CloudflarePlugin(None)
        assert plugin._config == {}
