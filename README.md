# frontlines-sources

Expanded list of journalists, reporters, and independent livestreamers for protest and high-tension event coverage. Includes platform handles and discovery keywords for live stream monitoring.

Canonical data source for frontlines / infiltruth monitoring, research agents, and site data.

## Files

- `sources.json`: The source of truth. Curated list with `journalists_reporters_livestreamers` + `tiktok_livestreamers`. Supports `channel_id` (YouTube), `handles.{youtube,twitch,x,...}`, `discovery_keywords`, `priority`, `focus`.
- `scripts/auto_detect_live_v2.py`: Main live stream detector (see below).
- `scripts/auto_detect_live.py`: Legacy v1 (deprecated; kept for reference).
- `.github/workflows/detect-live.yml`: Scheduled CI runner (every 15min + manual).
- `live_streams.json`: Generated output (committed by CI).
- `requirements.txt`, `data/`, etc.

## Live Stream Detector (v2.2.0 — hardened)

`python scripts/auto_detect_live_v2.py`

**Key features / hardening in 2.2:**

- **yt-dlp first-class support** (recommended, default): Uses yt-dlp (CLI or Python module) for robust, quota-free live detection on YouTube (`/channel/UC.../live`) and Twitch. Provides far richer per-stream metadata than the legacy search API (thumbnail, description, viewer counts, duration, upload_date, etc.). These fields double as "archived stream metadata" snapshots at detection time. yt-dlp is excellent for follow-on use (transcripts via Whisper, direct m3u8/hls capture, `--write-info-json`).
- **Graceful API fallback**: If yt-dlp unavailable or `USE_YT_DLP=0`/`FORCE_YT_API=1`, falls back to YouTube Data API (search.list live) + Twitch Helix /streams.
- **Twitch handle robustness**: `sanitize_handle()` supports nested `handles.twitch`, legacy `twitch_handle`, full URLs (`https://www.twitch.tv/foo`), `@` prefixes, query strings, and normalizes case for Twitch.
- **Structured logging**: All key events emitted as single-line JSON (`{"ts":..., "level":..., "msg":..., ...}`) + human prints. Easy to grep/parse in Actions logs or aggregators. Control with `LOG_LEVEL`.
- **Retries + resilience**: `_retry_request` (3x exponential backoff) for HTTP; yt-dlp wrapped with timeouts + internal error tolerance (non-live cases are silent).
- **Quota awareness**: Strongly prefers yt-dlp path (0 units). Tracks `yt_api_calls`, `ytdlp_checks` in output. Default daily YT quota is low (~10k units); each search.list costs 100. With yt-dlp we avoid this entirely for polling.
- **Config via env**:
  - `USE_YT_DLP=1` (default)
  - `FORCE_YT_API=1`
  - `ARCHIVE_STREAM_META=1` — write `stream_archives/<id>.info.json` (full yt-dlp dumps) + populates `archive_meta_path` / `archived_at` on stream records.
  - `TWITCH_EMBED_PARENT=...` (default: infiltruth.com) for Twitch player iframe parent param.
  - API keys for fallback only.
- **Output**: `live_streams.json` with `detector_version`, `stats`, `quota_note`, and `streams[]` containing `embed_url` (ready for iframe), `watch_url`, `detection_method`, plus optional rich fields.
- **Runner updates**: `detect-live.yml` installs `yt-dlp` + `ffmpeg` (latter for potential capture/transcode extensions).

**Local run example (full hardened path):**
```bash
pip install -r requirements.txt
pip install -U yt-dlp
# optional: export ARCHIVE_STREAM_META=1
USE_YT_DLP=1 python scripts/auto_detect_live_v2.py
# or force legacy APIs:
USE_YT_DLP=0 YOUTUBE_API_KEY=xxx TWITCH_CLIENT_ID=... python scripts/auto_detect_live_v2.py
```

**GitHub Action** automatically uses the hardened path + commits results (and archives if enabled).

**Notes on archiving / transcripts**: When using yt-dlp path + `ARCHIVE_STREAM_META`, the `.info.json` files contain everything needed to re-invoke yt-dlp for the exact stream (or use with external tools). For live capture of long-running streams, extend with `yt-dlp --live-from-start --hls-use-mpegts ...` (ffmpeg required).

See script source header + `log_event` calls for more.

## Workflow

- Edit `sources.json` (add/remove reporters, update handles/channel_ids).
- CI detects on schedule or dispatch.
- Consume `live_streams.json` (or sync to R2 / your frontend).
- For non-YT/Twitch (FB/IG/TT): rely on discovery_keywords + external agents (X search, Firecrawl, etc.).

## Security / Secrets

Never commit keys. Use repo secrets for `YOUTUBE_API_KEY`, `TWITCH_*`, optional R2 creds.

## Contributing

PRs welcome for new high-value on-the-ground sources. Prefer primary `channel_id` (YouTube) and clean `handles.twitch` etc. Update `last_updated` and notes.

Last updated for v2.2 hardening: 2026-06-16

(Previous README content was minimal/placeholder; this is the authoritative current doc.)
