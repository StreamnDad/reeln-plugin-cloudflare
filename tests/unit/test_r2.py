"""Tests for r2 module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from reeln_cloudflare_plugin.r2 import (
    R2Config,
    R2Error,
    delete_object,
    object_exists,
    upload_file,
)


@pytest.fixture()
def r2_config() -> R2Config:
    return R2Config(
        endpoint="https://account.r2.cloudflarestorage.com",
        bucket="test-bucket",
        access_key_id="test-key",
        secret_access_key="test-secret",
        public_url_base="https://cdn.example.com",
    )


@pytest.fixture()
def r2_config_with_throttle() -> R2Config:
    return R2Config(
        endpoint="https://account.r2.cloudflarestorage.com",
        bucket="test-bucket",
        access_key_id="test-key",
        secret_access_key="test-secret",
        public_url_base="https://cdn.example.com",
        upload_max_kbps=500,
    )


class TestCreateClient:
    @patch("reeln_cloudflare_plugin.r2.boto3")
    def test_creates_s3_client(self, mock_boto3: MagicMock, r2_config: R2Config) -> None:
        from reeln_cloudflare_plugin.r2 import _create_client

        _create_client(r2_config)

        mock_boto3.client.assert_called_once()
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["endpoint_url"] == r2_config.endpoint
        assert call_kwargs["aws_access_key_id"] == r2_config.access_key_id
        assert call_kwargs["aws_secret_access_key"] == r2_config.secret_access_key
        assert call_kwargs["region_name"] == "auto"


class TestR2Config:
    def test_frozen(self, r2_config: R2Config) -> None:
        with pytest.raises(AttributeError):
            r2_config.bucket = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        config = R2Config(
            endpoint="https://x.r2.cloudflarestorage.com",
            bucket="b",
            access_key_id="k",
            secret_access_key="s",
            public_url_base="https://cdn.example.com",
        )
        assert config.region == "auto"
        assert config.upload_max_kbps == 0


class TestUploadFile:
    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_upload_success(
        self, mock_create: MagicMock, r2_config: R2Config, video_file: Path
    ) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        url = upload_file(r2_config, video_file, "videos/highlight.mp4")

        mock_client.upload_file.assert_called_once_with(
            str(video_file), "test-bucket", "videos/highlight.mp4"
        )
        assert url == "https://cdn.example.com/videos/highlight.mp4"

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_upload_returns_correct_url_trailing_slash(
        self, mock_create: MagicMock, video_file: Path
    ) -> None:
        config = R2Config(
            endpoint="https://x.r2.cloudflarestorage.com",
            bucket="b",
            access_key_id="k",
            secret_access_key="s",
            public_url_base="https://cdn.example.com/",
        )
        mock_create.return_value = MagicMock()

        url = upload_file(config, video_file, "file.mp4")
        assert url == "https://cdn.example.com/file.mp4"

    def test_upload_missing_source(self, r2_config: R2Config, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.mp4"
        with pytest.raises(R2Error, match="source not found"):
            upload_file(r2_config, missing, "key.mp4")

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_upload_boto3_failure(
        self, mock_create: MagicMock, r2_config: R2Config, video_file: Path
    ) -> None:
        mock_client = MagicMock()
        mock_client.upload_file.side_effect = Exception("Network error")
        mock_create.return_value = mock_client

        with pytest.raises(R2Error, match="upload failed"):
            upload_file(r2_config, video_file, "key.mp4")

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_upload_client_creation_failure(
        self, mock_create: MagicMock, r2_config: R2Config, video_file: Path
    ) -> None:
        mock_create.side_effect = Exception("Bad credentials")

        with pytest.raises(R2Error, match="Failed to create R2 client"):
            upload_file(r2_config, video_file, "key.mp4")

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_upload_with_bandwidth_throttle(
        self,
        mock_create: MagicMock,
        r2_config_with_throttle: R2Config,
        video_file: Path,
    ) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        upload_file(r2_config_with_throttle, video_file, "key.mp4")

        call_args = mock_client.upload_file.call_args
        assert call_args is not None
        assert "Config" in call_args.kwargs
        transfer_config = call_args.kwargs["Config"]
        assert transfer_config.max_bandwidth == 500 * 1024

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_upload_without_throttle(
        self, mock_create: MagicMock, r2_config: R2Config, video_file: Path
    ) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        upload_file(r2_config, video_file, "key.mp4")

        call_args = mock_client.upload_file.call_args
        assert call_args is not None
        # No Config kwarg when throttle is disabled
        assert "Config" not in call_args.kwargs


class TestDeleteObject:
    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_delete_success(self, mock_create: MagicMock, r2_config: R2Config) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        delete_object(r2_config, "videos/highlight.mp4")

        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="videos/highlight.mp4"
        )

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_delete_client_creation_failure(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_create.side_effect = Exception("Bad credentials")

        with pytest.raises(R2Error, match="Failed to create R2 client"):
            delete_object(r2_config, "key.mp4")

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_delete_boto3_failure(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_client = MagicMock()
        mock_client.delete_object.side_effect = Exception("Access denied")
        mock_create.return_value = mock_client

        with pytest.raises(R2Error, match="R2 delete failed"):
            delete_object(r2_config, "key.mp4")


class TestObjectExists:
    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_exists_true(self, mock_create: MagicMock, r2_config: R2Config) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        assert object_exists(r2_config, "existing.mp4") is True
        mock_client.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="existing.mp4"
        )

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_exists_false_404(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_client = MagicMock()
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )
        mock_create.return_value = mock_client

        assert object_exists(r2_config, "missing.mp4") is False

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_exists_false_no_such_key(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_client = MagicMock()
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "HeadObject"
        )
        mock_create.return_value = mock_client

        assert object_exists(r2_config, "missing.mp4") is False

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_exists_false_not_found(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_client = MagicMock()
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "NotFound"}}, "HeadObject"
        )
        mock_create.return_value = mock_client

        assert object_exists(r2_config, "missing.mp4") is False

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_exists_unexpected_error(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_client = MagicMock()
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "403"}}, "HeadObject"
        )
        mock_create.return_value = mock_client

        with pytest.raises(R2Error, match="head_object failed"):
            object_exists(r2_config, "forbidden.mp4")

    @patch("reeln_cloudflare_plugin.r2._create_client")
    def test_exists_client_creation_failure(
        self, mock_create: MagicMock, r2_config: R2Config
    ) -> None:
        mock_create.side_effect = Exception("Bad credentials")

        with pytest.raises(R2Error, match="Failed to create R2 client"):
            object_exists(r2_config, "key.mp4")
