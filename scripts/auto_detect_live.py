# Auto-detect live streams script for Frontlines / infiltruth.com
# Uses sources.json (journalists, channel_ids, handles, discovery_keywords) to poll YouTube Data API and Twitch Helix for live streams.
# Outputs live_streams.json for easy import into the Vercel static site data pipeline.

import json
import os
import time
from datetime import datetime

# Placeholder for API keys (use env vars in production or Vercel)
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')

# Load sources from repo
SOURCES_FILE = 'sources.json'
LIVE_OUTPUT = 'live_streams.json'


def load_sources():
    if not os.path.exists(SOURCES_FILE):
        print('sources.json not found. Run from repo root.')
        return []
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('journalists', [])


def check_youtube_live(channel_id):
    # Simple YouTube search for live on channel
    url = f'https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}'
    # Add requests.get logic here (implement with requests library)
    # Return video_id if live, else None
    pass  # Placeholder - replace with full implementation


def check_twitch_live(handle):
    # Twitch Helix /streams?user_login=handle
    # Placeholder - implement with requests + auth
    pass


def main():
    sources = load_sources()
    live_streams = []
    for source in sources:
        # Check YT
        if source.get('youtube_channel_id'):
            video_id = check_youtube_live(source['youtube_channel_id'])
            if video_id:
                live_streams.append({
                    'platform': 'youtube',
                    'channel': source['name'],
                    'video_id': video_id,
                    'title': 'LIVE - detected',
                    'discovered_at': datetime.utcnow().isoformat(),
                    'priority': source.get('priority', 5)
                })
        # Check Twitch
        if source.get('twitch_handle'):
            twitch_data = check_twitch_live(source['twitch_handle'])
            if twitch_data:
                live_streams.append(twitch_data)
        # Keyword search for broader discovery
        # e.g., search YT with discovery_keywords
    
    # Save output
    with open(LIVE_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(live_streams, f, indent=2)
    print(f'Detected {len(live_streams)} live streams. Saved to {LIVE_OUTPUT}.')
    # Integrate with generate-data.py or Vercel data refresh

if __name__ == '__main__':
    main()

# TODO: Add full requests implementation, OAuth for Twitch, relevance AI filter, error handling, rate limits.
# Integrate with Vercel Cron or GitHub Actions for autonomous operation.
# This script directly addresses the auto-detect challenge by leveraging the curated sources list.