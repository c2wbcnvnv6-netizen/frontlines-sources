#!/usr/bin/env python3
"""
fuse_intel.py - Multi-source fusion for frontlines intel.

Loads:
- live_streams.json (root, from auto_detect_live_v2.py)
- data/planned_actions.json (from collect or curated)

Produces fused_hotspots.json with correlations by:
- location (city/region key match e.g. minneapolis-mn, portland-or)
- keyword/tag/hint overlap
- date proximity (planned date vs stream discovered_at within ~3 days)
- livestream_hints direct streamer matches

Output schema:
  version, last_updated, count, hotspots[]
Each hotspot merges planned action fields + correlated_live_streams[], hotspot_score (0-100), intel_summary.

Pure stdlib (json, os, re, datetime, collections). No external deps.
Runnable in GH Actions after live/planned collects.

Intended: run after detectors in workflows; commit fused_hotspots.json;
optionally sync to CF R2 frontlines-processed/fused-intel/ (see workflow comments).

Version: 0.1 (initial multi-source fusion)
"""

import json
import os
import re
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def normalize_text(text):
    """Lowercase, strip non-alphanum to spaces, return list of tokens."""
    if not text:
        return []
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', str(text).lower())
    return [t for t in cleaned.split() if len(t) > 1]


def get_location_key(text):
    """Simple geo bucketing for common hotspots in data."""
    t = (text or '').lower()
    if any(k in t for k in ('minneapolis', 'st. paul', 'twin cities', 'mn -', 'minnesota')):
        return 'minneapolis-mn'
    if any(k in t for k in ('portland', 'pdx', 'oregon')):
        return 'portland-or'
    return 'other'


def parse_action_date(d):
    """Parse YYYY-MM-DD or iso prefix."""
    if not d:
        return None
    try:
        return datetime.strptime(d[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def date_proximity_bonus(action_date, stream_discovered):
    if not action_date or not stream_discovered:
        return 0
    try:
        sd = stream_discovered.replace('Z', '+00:00')
        sdate = datetime.fromisoformat(sd).date() if 'T' in sd else datetime.strptime(sd[:10], '%Y-%m-%d').date()
        delta = abs((sdate - action_date).days)
        if delta <= 1:
            return 12
        if delta <= 3:
            return 6
        if delta <= 7:
            return 2
    except Exception:
        pass
    return 0


def compute_keyword_set(action):
    """Aggregate keywords from planned action fields for matching."""
    parts = []
    parts.extend(action.get('related_keywords', []) or [])
    parts.extend(action.get('tags', []) or [])
    parts.extend(action.get('livestream_hints', []) or [])
    parts.append(action.get('location', ''))
    parts.append(action.get('description', ''))
    parts.append(' '.join(action.get('organizing_groups', []) or []))
    return set(normalize_text(' '.join(parts)))


def stream_to_text(s):
    """Flatten stream record for keyword/location matching."""
    parts = [
        s.get('title', ''),
        s.get('description', ''),
        s.get('source', ''),
        s.get('uploader', ''),
        ' '.join(s.get('focus', []) or [])
    ]
    return ' '.join(p for p in parts if p)


def match_stream_to_action(action, action_kws, action_loc_key, action_date, s):
    """Return match_score >0 if correlates, plus details."""
    s_text = stream_to_text(s)
    s_kws = set(normalize_text(s_text))
    kw_overlap = len(action_kws & s_kws)
    kw_score = kw_overlap * 4

    s_loc_key = get_location_key(s_text)
    loc_score = 18 if (action_loc_key != 'other' and action_loc_key == s_loc_key) else 0

    date_bonus = date_proximity_bonus(action_date, s.get('discovered_at') or s.get('updated'))

    hint_score = 0
    hints = action.get('livestream_hints', []) or []
    s_lower = s_text.lower()
    for h in hints:
        hl = (h or '').lower().strip()
        if not hl:
            continue
        if hl in s_lower or any(hl in f.lower() for f in (s.get('focus') or [])):
            hint_score += 9
        if any(tok in s_lower for tok in hl.split() if len(tok) > 3):
            hint_score += 4

    total = kw_score + loc_score + date_bonus + hint_score
    # Require meaningful correlation: either loc match or decent combined score
    if (total <= 10) or (loc_score == 0 and total < 18):
        return 0, None

    matched = {
        "platform": s.get("platform"),
        "video_id": s.get("video_id") or s.get("id"),
        "title": s.get("title"),
        "source": s.get("source") or s.get("uploader"),
        "watch_url": s.get("watch_url"),
        "embed_url": s.get("embed_url"),
        "viewer_count": s.get("view_count") or s.get("concurrent_viewers") or s.get("viewer_count"),
        "discovered_at": s.get("discovered_at"),
        "detection_method": s.get("detection_method"),
        "match_score": total,
    }
    return total, matched


def generate_intel_summary(action, correlated, base_score):
    n = len(correlated)
    pri = action.get('priority', 'medium')
    groups = ', '.join((action.get('organizing_groups') or [])[:2])
    streamers = ', '.join(c.get('source') or c.get('title', '')[:30] for c in correlated[:3]) if correlated else "none active now"
    parts = [
        f"{n} correlated live stream(s) detected.",
        f"Priority {pri}.",
    ]
    if groups:
        parts.append(f"Key groups: {groups}.")
    if n:
        parts.append(f"Active sources: {streamers}.")
    parts.append(f"Base intel score contribution: {base_score}.")
    return " ".join(parts)


def main():
    print("\uD83D\uDD00 Starting intel fusion (live + planned)...")
    planned_path = os.path.join('data', 'planned_actions.json')
    live_path = 'live_streams.json'
    out_path = 'fused_hotspots.json'

    pa = load_json(planned_path, {"actions": []})
    actions = pa.get('actions', []) or pa.get('planned', [])  # tolerant

    live = load_json(live_path, {"streams": []})
    streams = live.get('streams', []) or []

    print(f"  Loaded {len(actions)} planned actions, {len(streams)} live streams.")

    hotspots = []
    matched_stream_ids = set()

    for action in actions:
        aid = action.get('id', 'unknown')
        loc_str = action.get('location', '') + ' ' + str(action.get('geo', {}).get('place', ''))
        loc_key = get_location_key(loc_str)
        action_date = parse_action_date(action.get('date'))
        action_kws = compute_keyword_set(action)

        base = 8 if action.get('priority') == 'high' else (5 if action.get('priority') == 'medium' else 3)
        correlated = []
        total_match_points = 0

        for s in streams:
            sid = s.get('video_id') or s.get('id') or (s.get('platform', '') + '|' + (s.get('title') or '')[:40])
            mscore, mrec = match_stream_to_action(action, action_kws, loc_key, action_date, s)
            if mrec:
                correlated.append(mrec)
                total_match_points += mrec.get('match_score', 0)
                matched_stream_ids.add(sid)

        hs_score = min(100, base + total_match_points)
        intel_summary = generate_intel_summary(action, correlated, base)

        hotspot = {
            "id": f"hs-{aid.replace('pa-', '')}",
            "location": action.get("location"),
            "geo": action.get("geo"),
            "date": action.get("date"),
            "time": action.get("time"),
            "description": action.get("description"),
            "organizing_groups": action.get("organizing_groups", []),
            "link": action.get("link"),
            "expected_turnout": action.get("expected_turnout"),
            "priority": action.get("priority"),
            "tags": action.get("tags", []),
            "livestream_hints": action.get("livestream_hints", []),
            "related_keywords": action.get("related_keywords", []),
            "source": action.get("source"),
            "discovered_at": action.get("discovered_at"),
            "correlated_live_streams": correlated,
            "hotspot_score": hs_score,
            "intel_summary": intel_summary,
            "notes": action.get("notes", ""),
        }
        hotspots.append(hotspot)

    # unmatched streams (current lives not tied to known planned)
    unmatched = []
    for s in streams:
        sid = s.get('video_id') or s.get('id') or (s.get('platform', '') + '|' + (s.get('title') or '')[:40])
        if sid not in matched_stream_ids:
            unmatched.append({
                "platform": s.get("platform"),
                "title": s.get("title"),
                "source": s.get("source"),
                "watch_url": s.get("watch_url"),
                "discovered_at": s.get("discovered_at"),
            })

    output = {
        "version": "1.0",
        "last_updated": _now_iso(),
        "count": len(hotspots),
        "hotspots": hotspots,
        "unmatched_live_streams_count": len(unmatched),
        "unmatched_live_streams": unmatched[:10],
        "stats": {
            "planned_actions": len(actions),
            "live_streams": len(streams),
            "correlated_pairs": sum(len(h.get('correlated_live_streams', [])) for h in hotspots),
        },
        "notes": "Simple fusion (stdlib only): location bucketing + keyword/hint overlap + date proximity. Run after live detector + planned collector. Output intended for frontlines-processed/fused-intel/ on R2 and frontlines-intel D1 ingestion."
    }

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\u2705 Fusion complete. {len(hotspots)} hotspots written to {out_path}")
    print(f"   Correlated pairs: {output['stats']['correlated_pairs']} | Unmatched lives: {len(unmatched)}")
    for h in hotspots:
        print(f"   - {h['id']}: score={h['hotspot_score']} loc={h['location'][:40]}... streams={len(h['correlated_live_streams'])}")


if __name__ == "__main__":
    main()
