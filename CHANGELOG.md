# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0] - 2026-03-25

### Added

- Initial plugin scaffolding with `CloudflarePlugin` class
- `r2.py` module — Cloudflare R2 upload, delete, and object existence check via boto3 S3-compatible API
- `R2Config` frozen dataclass with endpoint, bucket, credentials, public URL base, region, and bandwidth throttle
- `upload_file()` — uploads local file to R2, returns public CDN URL
- `delete_object()` — deletes an object from the R2 bucket
- `object_exists()` — checks if an object key exists in the bucket
- `upload_video` feature flag — enables video upload on `POST_RENDER` hook
- `cleanup_after_game` feature flag — deletes uploaded R2 objects on `ON_POST_GAME_FINISH`
- `dry_run` config field — logs upload and delete actions without executing them
- Environment variable-based credential resolution (config stores env var names, not secrets)
- Bandwidth throttle support via `upload_max_kbps` config field
- Custom key prefix support via `upload_prefix` config field
- Shared context output: `context.shared["video_url"]` = public CDN URL
- Upload key tracking across `POST_RENDER` calls for post-game cleanup
- `ON_GAME_FINISH` hook handler — resets uploaded keys list
- `ON_POST_GAME_FINISH` hook handler — cleans up temporary R2 uploads after all downstream plugins finish
- 100% line + branch test coverage
