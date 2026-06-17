# frontlines-sources

Expanded list of journalists, reporters, and independent livestreamers for protest and high-tension event coverage. Includes platform handles and discovery keywords for live stream monitoring.

Canonical data source for frontlines / infiltruth monitoring, research agents, and site data.

## Files

- `sources.json`: The source of truth. Curated list with `journalists_reporters_livestreamers` + `tiktok_livestreamers`. Supports `channel_id` (YouTube), `handles.{youtube,twitch,x,...}`, `discovery_keywords`, `priority`, `focus`.
- `scripts/auto_detect_live_v2.py`: Main live stream detector (hardened v2.2; yt-dlp primary).
- `scripts/auto_detect_live.py`: Legacy v1 (deprecated; kept for reference).
- `scripts/fuse_intel.py`: Multi-source fusion script. Combines `live_streams.json` (root) + `data/planned_actions.json` into `fused_hotspots.json` using location/keyword/date/livestream_hints correlations.
- `scripts/collect_planned_actions.py`: Planned actions curator (maintains `data/planned_actions.json` schema; stub ready for ACLED + public calendar automation).
- `.github/workflows/detect-live.yml`: Scheduled CI runner for live (every 15min + manual) + fusion.
- `.github/workflows/detect-planned.yml`: Scheduled collector for planned actions (every 4h + manual) + fusion.
- `live_streams.json`: Generated output (committed by CI).
- `fused_hotspots.json`: Generated fused intel (version, hotspots[] with correlated_live_streams, hotspot_score, intel_summary; committed by CI).
- `data/planned_actions.json`: Curated/planned events layer (see data/README.md for schema).
- `data/README.md`: Detailed docs for all data layers (sources, planned schema, generated, future ACLED).
- `requirements.txt`, `data/`, `AGENTS.md`, etc.

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
USE_YT_DLP=0 YOUTUBE_API_KEY=xxx TWITCH_CLIENT_ID=... TWITCH_CLIENT_SECRET=... python scripts/auto_detect_live_v2.py
```

**GitHub Action** automatically uses the hardened path + commits results (and archives if enabled).

**Notes on archiving / transcripts**: When using yt-dlp path + `ARCHIVE_STREAM_META`, the `.info.json` files contain everything needed to re-invoke yt-dlp for the exact stream (or use with external tools). For live capture of long-running streams, extend with `yt-dlp --live-from-start --hls-use-mpegts ...` (ffmpeg required).

See script source header + `log_event` calls for more.

## Multi-Source Intel Fusion

`python scripts/fuse_intel.py`

Simple pure-stdlib fusion that merges live streams (current detections) with planned actions (curated calendar/events data) to produce actionable `fused_hotspots.json`.

**Correlations (lightweight, no deps):**
- Location bucketing (minneapolis-mn / portland-or etc. from location strings + geo.place)
- Keyword / tag / related_keywords overlap (normalized tokens)
- Livestream_hints matching against stream source/title/focus (e.g. "Unicorn Riot", "Carissa Dez")
- Date proximity (planned date vs stream discovered_at, bonuses for <=1d / <=3d)

**Output** (`fused_hotspots.json` at repo root):
```json
{
  "version": "1.0",
  "last_updated": "...Z",
  "count": N,
  "hotspots": [{
    "id": "hs-...",
    "location": "...",
    "geo": {...},
    "date": "YYYY-MM-DD",
    "description": "...",
    "organizing_groups": [...],
    "priority": "high",
    "tags": [...],
    "correlated_live_streams": [ {platform, title, source, watch_url, embed_url, match_score, ...} ],
    "hotspot_score": 85,
    "intel_summary": "3 correlated live stream(s) detected. Priority high. Key groups: ... Active sources: Unicorn Riot, ...",
    ...
  }],
  "unmatched_live_streams": [...],
  "stats": {"planned_actions": , "live_streams": , "correlated_pairs": }
}
```

**In workflows**: `detect-live.yml` runs fusion after live detector (primary). `detect-planned.yml` runs it after collector. Both commit the fused output + upload examples to R2 (frontlines-processed/fused-intel/ + snapshots/).

**Usage**: Consume hotspots for prioritized monitoring, UI clustering, or downstream D1/KV sync. Future: ACLED integration per prior pseudocode.

Run locally (after a detector pass or with committed jsons):
```bash
python scripts/fuse_intel.py
```

## Workflow

- Edit `sources.json` (add/remove reporters, update handles/channel_ids).
- Edit `data/planned_actions.json` for curated events (or extend `scripts/collect_planned_actions.py` for ACLED/automation).
- CI detects + fuses on schedule or dispatch (full stack: GH Actions + CF R2 + future ACLED).
- Consume `live_streams.json` and `fused_hotspots.json` (or sync to R2 / your frontend / frontlines-intel D1).
- For non-YT/Twitch (FB/IG/TT): rely on discovery_keywords + external agents (X search, Firecrawl, etc.).

## Data Documentation

See `data/README.md` for planned_actions schema, fusion outputs, sources details, and future layer notes.

## Security / Secrets

Never commit keys. Use repo secrets for `YOUTUBE_API_KEY`, `TWITCH_*`, optional R2 creds.

## Contributing

PRs welcome for new high-value on-the-ground sources. Prefer primary `channel_id` (YouTube) and clean `handles.twitch` etc. Update `last_updated` and notes.

Also contributions to fusion heuristics, `collect_planned_actions.py` (ACLED), R2/D1 pipelines, or agent rules welcome.

See AGENTS.md for agent-specific instructions (MCP GitHub/CF usage, edit-in-place, etc.).

Last updated for repo-updates (collect script, AGENTS, data/README, full stack docs): 2026-06-17

(Previous README content was minimal/placeholder; this is the authoritative current doc.)
