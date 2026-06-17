#!/usr/bin/env python3
"""
collect_planned_actions.py - Curated planned actions collector/curator.

Maintains data/planned_actions.json (schema v1.1) for use by fuse_intel.py.

Current: curated from public sources (IGD, DSA, Melt-the-ICE, Unicorn Riot coverage, local calendars).

Future expansions (per ACLED / CF R2 roadmap):
- Pull from ACLED API for protest/riot/PEACEFUL events (filter by location/keyword).
- Firecrawl or requests scrape of IGD/TCDDSA/PDXDSA/etc calendars.
- X semantic/keyword hints via MCP or API.
- Merge + dedupe with existing; preserve livestream_hints, geo, related_keywords for fusion correlation.

Run via .github/workflows/detect-planned.yml (every 4h + dispatch).
Outputs same schema; updates last_updated, count, sources_used note.
Pure stdlib + optional requests. Coordinates with live detector + fusion.
Full stack: GH Actions + CF R2 (frontlines-processed/planned-actions/ when secrets) + future ACLED layer.

Version: 0.1 (stub ready for ACLED integration)
"""

import json
import os
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


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_acled_protests(email=None, password=None, regions=None):
    """Stub for ACLED API integration (OAuth based).

    When ACLED key/credentials available:
    - POST to https://acleddata.com/oauth/token with username, password, grant_type=password, client_id=acled, scope=authenticated
    - Use Bearer token in header for GET https://acleddata.com/api/acled/read
    - Filter e.g. event_type=Protests, event_date recent, country or admin1 for MN/OR etc.
    - Return list of events to merge into actions.

    For now: returns [] if no creds, or mock if ACLED_MOCK=1.
    """
    if os.getenv('ACLED_MOCK') == '1':
        return [{
            'id': 'acled-mock-1',
            'date': '2026-06-18',
            'location': 'Minneapolis, MN',
            'description': 'Mock ACLED protest event for testing fusion.',
            'source': 'acled',
            'link': 'https://acleddata.com',
            'tags': ['protest'],
            'livestream_hints': ['youtube:minneapolis protest live'],
        }]
    if not email or not password:
        email = os.getenv('ACLED_EMAIL')
        password = os.getenv('ACLED_PASSWORD')
    if not email or not password:
        print('[ACLED] No credentials (set ACLED_EMAIL/PASSWORD or use ACLED_MOCK=1); skipping ACLED pull.')
        return []
    # TODO: implement real OAuth token fetch + API call when key ready
    # Example:
    # import requests
    # token_resp = requests.post('https://acleddata.com/oauth/token', data={
    #     'username': email, 'password': password, 'grant_type': 'password',
    #     'client_id': 'acled', 'scope': 'authenticated'
    # })
    # token = token_resp.json()['access_token']
    # headers = {'Authorization': f'Bearer {token}'}
    # data = requests.get('https://acleddata.com/api/acled/read', headers=headers, params={
    #     'event_type': 'Protests', 'event_date': '2026-06-01|2026-06-18', 'limit': 100
    # }).json()
    # ... parse and return list of dicts with date, location, description etc.
    print('[ACLED] Credentials present but real fetch not implemented yet (waiting on key).')
    return []


def main():
    print('[INFO] Running planned actions collector (curated mode)...')
    planned_path = os.path.join('data', 'planned_actions.json')
    pa = load_json(planned_path, {'version': '1.1', 'actions': []})

    actions = pa.get('actions', []) or []
    original_last = pa.get('last_updated')

    # Refresh metadata for 'in good shape' + CI
    pa['last_updated'] = _now_iso()
    pa['count'] = len(actions)
    if 'sources_used' not in pa or not pa.get('sources_used'):
        pa['sources_used'] = ['curated-from-public-calendars', 'igd-upcoming', 'tcdsa-events', 'melt-the-ice-organizers', 'unicorn-riot-coverage', 'portland-dsa-events']

    # Basic schema guard / future hook point
    for a in actions:
        if 'id' not in a:
            a['id'] = f'pa-curated-{len(actions)}'
        if 'livestream_hints' not in a:
            a['livestream_hints'] = []
        if 'related_keywords' not in a:
            a['related_keywords'] = []
        if 'geo' not in a:
            a['geo'] = {}

    # ACLED integration stub
    acled_events = fetch_acled_protests()
    if acled_events:
        # Simple merge example (extend with dedupe by id/date+loc)
        for ev in acled_events:
            actions.append(ev)
        pa['sources_used'].append('acled')

    if pa.get('last_updated') != original_last or True:  # always write to bump ts
        save_json(planned_path, pa)
        print(f'[OK] Updated {planned_path}: last_updated={pa["last_updated"]}, count={pa["count"]}')
        print('   Ready for fuse_intel.py correlation (livestream_hints + geo + keywords).')
        print('   Full stack note: GH Actions (detect-planned) + CF R2 planned-actions/ (commented) + future ACLED.')
    else:
        print('No metadata change; data in good shape.')


if __name__ == '__main__':
    main()
