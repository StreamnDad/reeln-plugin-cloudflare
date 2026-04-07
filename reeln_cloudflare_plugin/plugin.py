"""CloudflarePlugin — reeln-cli plugin for Cloudflare R2 video uploads."""

from __future__ import annotations

import logging
import os
from typing import Any

from reeln.models.auth import AuthCheckResult, AuthStatus
from reeln.models.plugin_schema import ConfigField, PluginConfigSchema
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import HookRegistry

from reeln_cloudflare_plugin import r2

log: logging.Logger = logging.getLogger(__name__)


class CloudflarePlugin:
    """Plugin that uploads rendered videos to Cloudflare R2.

    Subscribes to ``POST_RENDER`` to upload the rendered video file and
    writes the public CDN URL to ``context.shared["video_url"]`` for
    downstream plugins (e.g. Meta Reels publishing).
    """

    name: str = "cloudflare"
    version: str = "0.3.0"
    api_version: int = 1

    config_schema: PluginConfigSchema = PluginConfigSchema(
        fields=(
            ConfigField(
                name="r2_endpoint",
                field_type="str",
                required=True,
                description="Cloudflare R2 S3-compatible endpoint URL",
            ),
            ConfigField(
                name="r2_bucket",
                field_type="str",
                required=True,
                description="R2 bucket name",
            ),
            ConfigField(
                name="r2_access_key_env",
                field_type="str",
                required=True,
                description="Environment variable name containing the R2 access key ID",
            ),
            ConfigField(
                name="r2_secret_key_env",
                field_type="str",
                required=True,
                description="Environment variable name containing the R2 secret access key",
            ),
            ConfigField(
                name="public_url_base",
                field_type="str",
                required=True,
                description="Public CDN base URL for uploaded objects",
            ),
            ConfigField(
                name="upload_video",
                field_type="bool",
                default=False,
                description="Enable video upload to R2 on POST_RENDER",
            ),
            ConfigField(
                name="upload_prefix",
                field_type="str",
                default="",
                description="Optional key prefix (folder) for uploaded objects",
            ),
            ConfigField(
                name="upload_max_kbps",
                field_type="int",
                default=0,
                description="Max upload bandwidth in KB/s (0 = unlimited)",
            ),
            ConfigField(
                name="cleanup_after_game",
                field_type="bool",
                default=False,
                description="Delete uploaded R2 objects on ON_POST_GAME_FINISH",
            ),
            ConfigField(
                name="dry_run",
                field_type="bool",
                default=False,
                description="Log upload actions without executing them",
            ),
            ConfigField(
                name="r2_region",
                field_type="str",
                default="auto",
                description="R2 region (usually 'auto')",
            ),
        )
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}
        self._uploaded_keys: list[str] = []

    def register(self, registry: HookRegistry) -> None:
        """Register hook handlers with the reeln plugin registry."""
        registry.register(Hook.POST_RENDER, self.on_post_render)
        registry.register(Hook.ON_GAME_FINISH, self.on_game_finish)
        registry.register(Hook.ON_POST_GAME_FINISH, self.on_post_game_finish)

    def on_post_render(self, context: HookContext) -> None:
        """Handle ``POST_RENDER`` — upload rendered video to R2."""
        if not self._config.get("upload_video"):
            return

        result = context.data.get("result")
        if result is None:
            log.warning("Cloudflare plugin: no result in context data, skipping")
            return

        output = getattr(result, "output", None)
        if output is None or not output.exists():
            log.warning(
                "Cloudflare plugin: output file not found: %s, skipping", output
            )
            return

        credentials = self._resolve_credentials()
        if credentials is None:
            return

        access_key_id, secret_access_key = credentials

        prefix = self._config.get("upload_prefix", "")
        filename = output.name
        key = f"{prefix}/{filename}" if prefix else filename

        if self._config.get("dry_run"):
            base = self._config.get("public_url_base", "").rstrip("/")
            url = f"{base}/{key}"
            log.info(
                "Cloudflare plugin: [DRY RUN] would upload %s → %s",
                output,
                url,
            )
            return

        config = r2.R2Config(
            endpoint=self._config.get("r2_endpoint", ""),
            bucket=self._config.get("r2_bucket", ""),
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            public_url_base=self._config.get("public_url_base", ""),
            region=self._config.get("r2_region", "auto"),
            upload_max_kbps=int(self._config.get("upload_max_kbps", 0)),
        )

        try:
            public_url = r2.upload_file(config, output, key)
        except r2.R2Error as exc:
            log.warning("Cloudflare plugin: upload failed (non-fatal): %s", exc)
            return

        self._uploaded_keys.append(key)
        context.shared["video_url"] = public_url
        log.info("Cloudflare plugin: uploaded %s → %s", output, public_url)

    def _resolve_credentials(self) -> tuple[str, str] | None:
        """Read R2 credentials from environment variables named in config.

        Returns:
            Tuple of (access_key_id, secret_access_key), or None on failure.
        """
        access_key_env = self._config.get("r2_access_key_env", "")
        secret_key_env = self._config.get("r2_secret_key_env", "")

        if not access_key_env or not secret_key_env:
            log.warning(
                "Cloudflare plugin: r2_access_key_env and r2_secret_key_env "
                "must be configured, skipping"
            )
            return None

        access_key_id = os.environ.get(access_key_env, "")
        secret_access_key = os.environ.get(secret_key_env, "")

        if not access_key_id or not secret_access_key:
            log.warning(
                "Cloudflare plugin: environment variables %s and/or %s are "
                "empty or not set, skipping",
                access_key_env,
                secret_key_env,
            )
            return None

        return access_key_id, secret_access_key

    def auth_check(self) -> list[AuthCheckResult]:
        """Validate R2 credentials by connecting to the bucket."""
        endpoint = self._config.get("r2_endpoint", "")
        bucket = self._config.get("r2_bucket", "")
        if not endpoint or not bucket:
            return [AuthCheckResult(
                service="Cloudflare R2",
                status=AuthStatus.NOT_CONFIGURED,
                message="r2_endpoint and r2_bucket must be configured",
                hint="Set r2_endpoint and r2_bucket in plugin config",
            )]

        creds = self._resolve_credentials()
        if creds is None:
            access_key_env = self._config.get("r2_access_key_env", "")
            secret_key_env = self._config.get("r2_secret_key_env", "")
            return [AuthCheckResult(
                service="Cloudflare R2",
                status=AuthStatus.FAIL,
                message=(
                    f"Environment variables {access_key_env} and/or "
                    f"{secret_key_env} are empty or not set"
                ),
                hint=(
                    f"Set {access_key_env} and {secret_key_env} "
                    f"environment variables"
                ),
            )]

        access_key_id, secret_access_key = creds
        config = r2.R2Config(
            endpoint=endpoint,
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            public_url_base=self._config.get("public_url_base", ""),
            region=self._config.get("r2_region", "auto"),
        )

        try:
            client = r2._create_client(config)
            client.head_bucket(Bucket=bucket)
        except Exception as exc:
            return [AuthCheckResult(
                service="Cloudflare R2",
                status=AuthStatus.FAIL,
                message=f"R2 connection failed: {exc}",
                hint="Verify R2 credentials and endpoint",
            )]

        return [AuthCheckResult(
            service="Cloudflare R2",
            status=AuthStatus.OK,
            message="Connected",
            identity=f"bucket: {bucket}",
        )]

    def auth_refresh(self) -> list[AuthCheckResult]:
        """R2 credentials are env-var based and cannot be refreshed."""
        return [AuthCheckResult(
            service="Cloudflare R2",
            status=AuthStatus.FAIL,
            message=(
                "R2 credentials are set via environment variables "
                "and cannot be refreshed automatically"
            ),
            hint=(
                "Update the environment variables referenced in "
                "r2_access_key_env and r2_secret_key_env"
            ),
        )]

    def on_game_finish(self, context: HookContext) -> None:
        """Handle ``ON_GAME_FINISH`` — reset uploaded keys list."""
        self._uploaded_keys = []

    def on_post_game_finish(self, context: HookContext) -> None:
        """Handle ``ON_POST_GAME_FINISH`` — delete uploaded R2 objects."""
        if not self._config.get("cleanup_after_game"):
            return

        if not self._uploaded_keys:
            return

        credentials = self._resolve_credentials()
        if credentials is None:
            log.warning(
                "Cloudflare plugin: cannot cleanup R2 objects — credentials "
                "unavailable"
            )
            return

        access_key_id, secret_access_key = credentials

        config = r2.R2Config(
            endpoint=self._config.get("r2_endpoint", ""),
            bucket=self._config.get("r2_bucket", ""),
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            public_url_base=self._config.get("public_url_base", ""),
            region=self._config.get("r2_region", "auto"),
        )

        if self._config.get("dry_run"):
            for key in self._uploaded_keys:
                log.info(
                    "Cloudflare plugin: [DRY RUN] would delete R2 object: %s",
                    key,
                )
            return

        for key in self._uploaded_keys:
            try:
                r2.delete_object(config, key)
                log.info("Cloudflare plugin: deleted R2 object: %s", key)
            except r2.R2Error as exc:
                log.warning(
                    "Cloudflare plugin: failed to delete R2 object %s "
                    "(non-fatal): %s",
                    key,
                    exc,
                )
