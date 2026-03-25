# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-03-24

### Added

- Initial plugin scaffolding with `CloudflarePlugin` class
- `r2.py` module — Cloudflare R2 upload and object existence check via boto3 S3-compatible API
- `R2Config` frozen dataclass with endpoint, bucket, credentials, public URL base, region, and bandwidth throttle
- `upload_file()` — uploads local file to R2, returns public CDN URL
- `object_exists()` — checks if an object key exists in the bucket
- `upload_video` feature flag — enables video upload on `POST_RENDER` hook
- `dry_run` config field — logs upload actions without executing them
- Environment variable-based credential resolution (config stores env var names, not secrets)
- Bandwidth throttle support via `upload_max_kbps` config field
- Custom key prefix support via `upload_prefix` config field
- Shared context output: `context.shared["video_url"]` = public CDN URL
- `ON_GAME_FINISH` hook handler — forward-compatible cleanup hook
- 100% line + branch test coverage
