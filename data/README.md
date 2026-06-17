# Data Layers (frontlines-sources)

Curated + generated data for InfilTruth/Frontlines protest monitoring, livestream detection, planned action intel, and fusion.

**Location**: repo root + `data/` subdir. Consumed by scripts, GH Actions, downstream (R2, site data sync, D1/KV, research agents).

## Primary Sources (human/curated)

- `sources.json` (root)
  - Versioned list of journalists, reporters, independent livestreamers.
  - Sections: `journalists_reporters_livestreamers[]`, `tiktok_livestreamers[]`.
  - Fields per entry: name, description, platforms, handles.{youtube,twitch,x,facebook,...}, channel_id (YT), discovery_keywords[], focus[], priority, notes.
  - Powers `auto_detect_live_v2.py` (YT channel/live + Twitch via yt-dlp or API).
  - Also seeds external discovery (X, Firecrawl for FB/IG/TT).

- `data/planned_actions.json`
  - Version: "1.1"
  - Curated upcoming/planned events focused on MN, PDX, anti-ICE, campus, direct action, prisoner support (aligned with sources.json high-priority regions/sources).
  - `sources_used`: list of origin calendars (curated, igd-upcoming, tcdsa-events, melt-the-ice-organizers, unicorn-riot-coverage, portland-dsa-events).
  - Schema for each `actions[]` entry (used by fusion for correlation):
    ```json
    {
      "id": "pa-YYYYMMDD-loc-###",
      "date": "YYYY-MM-DD",
      "time": "HH:MM-HH:MM or description",
      "location": "City, ST - area",
      "geo": { "lat": number, "lon": number, "accuracy": "neighborhood|city|metro-area", "place": "..." },
      "description": "...",
      "organizing_groups": ["..."],
      "link": "https://...",
      "expected_turnout": "...",
      "priority": "high|medium|low|note",
      "tags": ["anti-ICE", "student", ...],
      "livestream_hints": ["Unicorn Riot", "Carissa Dez", "broadcastify:..."],
      "related_keywords": ["minneapolis", "ice", ...],
      "related_stream_ids": [],
      "source": "...",
      "discovered_at": "ISO8601Z",
      "notes": "..."
    }
    ```
  - `livestream_hints` + `related_keywords` + `geo.place` + `date` are critical for `fuse_intel.py` location/keyword/hint/date matching.

## Generated Outputs (by CI / scripts)

- `live_streams.json` (root, from `scripts/auto_detect_live_v2.py`)
  - detector_version, updated, count, stats (ytdlp_checks, yt_api_calls), streams[] with embed_url, watch_url, platform, source, title, discovered_at, detection_method (yt-dlp|youtube-api|twitch-...), optional rich meta + archive_meta_path.

- `fused_hotspots.json` (root, from `scripts/fuse_intel.py` after live + planned)
  - version, last_updated, count, hotspots[] (merged planned + correlated_live_streams[], hotspot_score 0-100, intel_summary), unmatched_live_streams, stats.
  - Used for prioritized monitoring, clustering. Intended for R2 frontlines-processed/fused-intel/ + D1 ingestion.

## Usage & Pipeline
- Edit sources.json or data/planned_actions.json for curation.
- `python scripts/collect_planned_actions.py` (refreshes ts; future ACLED).
- `python scripts/auto_detect_live_v2.py` (USE_YT_DLP=1 recommended).
- `python scripts/fuse_intel.py` (standalone or in workflows).
- GH Actions auto-run + commit + optional R2 upload.

## Future Layers
- ACLED (Armed Conflict Location & Event Data Project) integration in collect script: historical + near-real-time protest/violence/peaceful events for validation and auto-planning of hotspots.
- Expanded geo, turnout estimates, organizer graphs.
- Snapshots + latest in Cloudflare R2 (see workflow comments for paths: live-streams/, planned-actions/, fused-intel/).

Maintained as part of frontlines-sources canonical source of truth.
Last updated: 2026-06-17 (repo-updates).
