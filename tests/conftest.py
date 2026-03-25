"""Shared test fixtures for reeln-plugin-cloudflare."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@dataclass
class FakeRenderResult:
    """Minimal stand-in for ``reeln.models.render_plan.RenderResult``."""

    output: Path
    duration_seconds: float = 30.0
    file_size_bytes: int = 1024
    ffmpeg_command: str = "ffmpeg -i input.mp4 output.mp4"


@pytest.fixture()
def video_file(tmp_path: Path) -> Path:
    """Create a temporary video file and return its path."""
    video = tmp_path / "highlight.mp4"
    video.write_bytes(b"\x00" * 1024)
    return video


@pytest.fixture()
def plugin_config() -> dict[str, Any]:
    """Return a minimal valid plugin config."""
    return {
        "r2_endpoint": "https://account-id.r2.cloudflarestorage.com",
        "r2_bucket": "test-bucket",
        "r2_access_key_env": "R2_ACCESS_KEY_ID",
        "r2_secret_key_env": "R2_SECRET_ACCESS_KEY",
        "public_url_base": "https://cdn.example.com",
        "upload_video": True,
    }


@pytest.fixture()
def r2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set R2 credential environment variables."""
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret-key")


@pytest.fixture()
def mock_boto3_client() -> MagicMock:
    """Return a mock boto3 S3 client."""
    client = MagicMock()
    client.upload_file = MagicMock()
    client.head_object = MagicMock()
    return client
