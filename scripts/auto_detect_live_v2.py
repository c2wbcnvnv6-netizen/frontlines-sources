#!/usr/bin/env python3
"""
Auto-detect live streams from sources.json for infiltruth.com / Frontlines

Supports YouTube + Twitch.
Uses environment variables for API keys (secure + Vercel-friendly).
Outputs embed_url fields so streams can play in-site via iframe.

Run this periodically (cron, GitHub Action, or Vercel Cron) to keep live_streams.json fresh.
"""

import os
import json
import time
from datetime import datetime
import requests

# ==================== CONFIG ====================
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')

if not YOUTUBE_API_KEY:
    print('WARNING: YOUTUBE_API_KEY not set')

# ==================== HELPERS ====================

def get_twitch_token():
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': TWITCH_CLIENT_ID,
        'client_secret': TWITCH_CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    try:
        r = requests.post(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get('access_token')
    except Exception as e:
        print(f'Twitch token error: {e}')
        return None


def check_youtube_live(channel_id):
    if not YOUTUBE_API_KEY or not channel_id:
        return []
    url = 'https://www.googleapis.com/youtube/v3/search'
    params = {
        'part': 'snippet',
        'channelId': channel_id,
        'eventType': 'live',
        'type': 'video',
        'key': YOUTUBE_API_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get('items', [])
        results = []
        for item in items:
            vid = item['id']['videoId']
            results.append({
                'platform': 'YouTube',
                'video_id': vid,
                'title': item['snippet']['title'],
                'embed_url': f'https://www.youtube.com/embed/{vid}?autoplay=1&rel=0&modestbranding=1',
                'watch_url': f'https://www.youtube.com/watch?v={vid}',
                'live': True
            })
        return results
    except Exception as e:
        print(f'YouTube error for channel {channel_id}: {e}')
        return []


def check_twitch_live(handle):
    if not handle:
        return []
    token = get_twitch_token()
    if not token:
        return []
    url = 'https://api.twitch.tv/helix/streams'
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
        'Authorization': f'Bearer {token}'
    }
    params = {'user_login': handle}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get('data', [])
        results = []
        for stream in data:
            results.append({
                'platform': 'Twitch',
                'channel': stream['user_name'],
                'title': stream['title'],
                'viewer_count': stream.get('viewer_count', 0),
                'embed_url': f'https://player.twitch.tv/?channel={stream["user_name"]}&parent=infiltruth.com&autoplay=true',
                'watch_url': f'https://www.twitch.tv/{stream["user_name"]}',
                'live': True
            })
        return results
    except Exception as e:
        print(f'Twitch error for {handle}: {e}')
        return []

# ==================== MAIN ====================

def main():
    # Load sources
    try:
        with open('sources.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print('sources.json not found in current directory')
        return

    journalists = data.get('journalists_reporters_livestreamers', [])
    tiktoks = data.get('tiktok_livestreamers', [])
    sources = journalists + tiktoks

    live_streams = []

    for source in sources:
        name = source.get('name', 'Unknown')
        channel_id = source.get('channel_id')
        twitch_handle = source.get('twitch_handle')
        priority = source.get('priority', 'medium')
        focus = source.get('focus', [])

        # YouTube
        yt_results = check_youtube_live(channel_id)
        for item in yt_results:
            item.update({
                'source': name,
                'priority': priority,
                'focus': focus,
                'discovered_at': datetime.utcnow().isoformat()
            })
            live_streams.append(item)

        # Twitch
        twitch_results = check_twitch_live(twitch_handle)
        for item in twitch_results:
            item.update({
                'source': name,
                'priority': priority,
                'focus': focus,
                'discovered_at': datetime.utcnow().isoformat()
            })
            live_streams.append(item)

    # Save output
    output = {
        'updated': datetime.utcnow().isoformat(),
        'count': len(live_streams),
        'streams': live_streams
    }

    with open('live_streams.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f'\u2705 Detected {len(live_streams)} live streams. Saved to live_streams.json')
    print('   Use "embed_url" in your frontend for in-site iframe players.')

if __name__ == '__main__':
    main()