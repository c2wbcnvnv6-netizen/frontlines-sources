# AGENTS.md - frontlines-sources (InfilTruth/Frontlines protest monitoring)

Canonical data + scripts repo for journalist/livestreamer sources, live detection (yt-dlp hardened v2), planned actions, multi-source fusion to hotspots, and downstream intel (GH Actions + Cloudflare R2 + future ACLED).

## Core Identity & Rules
- You are a maximally capable agent (Grok Build / Cursor / etc). Complete tasks directly and efficiently.
- **Be concise and action-oriented**. Lead with the answer or next action. Use bullets and short paras. Prioritize developer experience, readability, security/correctness.
- For non-trivial work: consider `todo_write`, brief design notes, or implement-review. Proactively spawn subagents for parallel exploration if available.
- **Use MCP for ALL repo operations** (mandatory):
  - First `search_tool` to get schema, then `use_tool` with exact names: `github__get_repository_tree`, `github__get_file_contents`, `github__list_commits`, `github__search_code`, `github__push_files`, `github__create_or_update_file` (or grok_com_github__ variants).
  - For Cloudflare R2/storage: use cloudflare MCP (r2_* tools) when touching buckets (frontlines-processed/*).
  - For Vercel (if frontend syncs): vercel MCP tools.
  - Never rely on local git push, gh CLI, or manual edits for the remote; MCP is the source of truth for changes.
- Prefer **editing existing files** cleanly (use search/replace patterns in mind) over full rewrites. Show minimal impact.
- Always check `grok inspect` (or Cursor equiv) when in doubt about loaded context or rules.
- Update per-project rules here or in .cursor/rules/ sparingly; global ones (from ~/.cursor/Agents.md, /Users/daboss/Agents.md, .cursor/rules/global-preferences.md) take precedence unless tailored.

## Repo-Specific Context
- **Domain**: InfilTruth / Frontlines - protest, direct action, immigration, campus, high-tension event monitoring via on-ground livestreams + planned action intel.
- Key artifacts:
  - `sources.json`: truth for YT/Twitch/FB/IG/TT discovery (channel_id, handles, discovery_keywords, priority, focus).
  - `scripts/auto_detect_live_v2.py`: hardened detector (yt-dlp primary for zero-quota rich meta + fallback APIs; structured logs; Twitch sanitize).
  - `scripts/collect_planned_actions.py`: curator (current) / future ACLED + calendar scrapes. Maintains `data/planned_actions.json` schema.
  - `scripts/fuse_intel.py`: stdlib fusion (loc/keyword/hint/date) -> `fused_hotspots.json` (hotspot_score, correlated_live_streams, intel_summary).
  - Workflows: `.github/workflows/detect-live.yml` (15m), `detect-planned.yml` (4h) - commit outputs, optional R2.
  - Generated committed by CI: live_streams.json, fused_hotspots.json.
  - Data: `data/planned_actions.json` (curated events with livestream_hints/geo for correlation).
- Full stack references: GH Actions schedules + CF R2 (frontlines-processed/live-streams/, /planned-actions/, /fused-intel/ when R2 secrets present) + future ACLED layer in collect.
- Security: NO hardcoded keys/tokens. Use repo secrets (YOUTUBE_API_KEY, TWITCH_*, R2_*). .gitignore any local creds.
- CF R2: uploads commented in workflows (ready per prior subagent); use MCP cloudflare tools to manage buckets if extending.
- ACLED future: extend collect_planned_actions.py with ACLED data pulls for validation/enrichment of hotspots.

## Development Preferences (tailored)
- Favor modern clean patterns. Scripts: stdlib-first (see fuse/collect), yt-dlp for live.
- Update README.md, data/README.md, AGENTS.md, workflow comments on changes.
- Test locally: `python scripts/*.py` (after pip -r requirements + yt-dlp).
- CI is source of live/fused data; manual edits to sources/planned for curation.
- PRs: focus on high-value sources, better fusion heuristics, ACLED support, R2/D1 sync improvements.
- When editing data: keep schema for fusion (livestream_hints, geo.place keys like minneapolis-mn/portland-or, related_keywords).

## Collaboration
- With other agents: use GitHub issues, shared coordination files, or user as relay. Divide: one designs/verifies, other executes via MCP.
- Name yourself in updates ("repo-updates subagent here...").
- When complete: report status, commit links, recommendations clearly.

Last updated: 2026-06-17 (repo-updates task: post-fusion, post-hardening, planned layer, CF ready).
