# reeln-plugin-cloudflare

[reeln-cli](https://github.com/StreamnDad/reeln-cli) plugin for uploading rendered videos to Cloudflare R2 storage.

Subscribes to `POST_RENDER` to upload the rendered video file and writes the public CDN URL to `context.shared["video_url"]` for downstream plugins (e.g. [reeln-plugin-meta](https://github.com/StreamnDad/reeln-plugin-meta) Instagram Reels publishing).

## Installation

```bash
uv pip install reeln-plugin-cloudflare
```

Or install editable for development:

```bash
make dev-install
```

## Configuration

<!-- AUTO-GENERATED: config-fields -->

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `r2_endpoint` | str | — | yes | Cloudflare R2 S3-compatible endpoint URL |
| `r2_bucket` | str | — | yes | R2 bucket name |
| `r2_access_key_env` | str | — | yes | Environment variable name containing the R2 access key ID |
| `r2_secret_key_env` | str | — | yes | Environment variable name containing the R2 secret access key |
| `public_url_base` | str | — | yes | Public CDN base URL for uploaded objects |
| `upload_video` | bool | `false` | no | Enable video upload to R2 on POST\_RENDER |
| `upload_prefix` | str | `""` | no | Optional key prefix (folder) for uploaded objects |
| `upload_max_kbps` | int | `0` | no | Max upload bandwidth in KB/s (0 = unlimited) |
| `dry_run` | bool | `false` | no | Log upload actions without executing them |
| `r2_region` | str | `"auto"` | no | R2 region (usually 'auto') |

<!-- AUTO-GENERATED: /config-fields -->

### Example

In your reeln-cli `config.json`, list `cloudflare` **before** any plugin that consumes `video_url` (e.g. `meta`):

```json
{
  "enabled": ["streamn-scoreboard", "openai", "cloudflare", "meta"],
  "cloudflare": {
    "r2_endpoint": "https://<ACCOUNT_ID>.r2.cloudflarestorage.com",
    "r2_bucket": "reeln-videos",
    "r2_access_key_env": "R2_ACCESS_KEY_ID",
    "r2_secret_key_env": "R2_SECRET_ACCESS_KEY",
    "public_url_base": "https://cdn.example.com",
    "upload_video": true,
    "upload_prefix": "reels"
  }
}
```

### Environment Variables

Credentials are resolved indirectly — the config stores the **name** of the environment variable, not the secret itself:

| Env Var (default name) | Description |
|------------------------|-------------|
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key |

<!-- AUTO-GENERATED: dev-commands -->

## Development

| Command | Description |
|---------|-------------|
| `make dev-install` | Create venv, install reeln-cli + plugin with dev deps |
| `make reeln-install` | Install plugin editable into sibling reeln-cli venv |
| `make test` | Run pytest with 100% line+branch coverage (parallel via xdist) |
| `make lint` | Run ruff linter |
| `make format` | Run ruff formatter |
| `make check` | Lint, mypy strict, then test (sequential) |

<!-- AUTO-GENERATED: /dev-commands -->

## License

AGPL-3.0-only
