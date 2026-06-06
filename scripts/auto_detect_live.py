import requests
import json
from datetime import datetime

# Placeholder for API keys - set as env vars
YOUTUBE_API_KEY = 'YOUR_YOUTUBE_API_KEY'
# Add Twitch Client-ID and secret for Helix

# Load sources
with open('sources.json', 'r') as f:
    data = json.load(f)

sources = data.get('journalists_reporters_livestreamers', []) + data.get('tiktok_livestreamers', [])

live_streams = []

for source in sources:
    # Example for YouTube
    if 'youtube' in source.get('platforms', []) or 'channel_id' in source:
        channel_id = source.get('channel_id')
        if channel_id:
            url = f'https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}'
            try:
                resp = requests.get(url)
                if resp.status_code == 200:
                    items = resp.json().get('items', [])
                    if items:
                        live_streams.append({
                            'source': source['name'],
                            'platform': 'YouTube',
                            'live': True,
                            'items': items,
                            'timestamp': datetime.now().isoformat()
                        })
            except Exception as e:
                print(e)
    # Add Twitch logic here

# Save detected
with open('live_streams.json', 'w') as f:
    json.dump(live_streams, f, indent=2)

print(f'Detected {len(live_streams)} live streams')
# TODO: Integrate with site data pipeline, AI relevance, transcript start
