import requests
import json
from datetime import datetime

# TODO: Set your API keys as environment variables
YOUTUBE_API_KEY = 'YOUR_YOUTUBE_API_KEY_HERE'

# Load sources
with open('sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

sources = data.get('journalists_reporters_livestreamers', []) + data.get('tiktok_livestreamers', [])

live_streams = []

for source in sources:
    name = source.get('name')
    channel_id = source.get('channel_id')
    
    if channel_id:
        # YouTube live search
        url = f'https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}'
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                for item in items:
                    video_id = item['id']['videoId']
                    live_streams.append({
                        'source': name,
                        'platform': 'YouTube',
                        'video_id': video_id,
                        'title': item['snippet']['title'],
                        'embed_url': f'https://www.youtube.com/embed/{video_id}',
                        'watch_url': f'https://www.youtube.com/watch?v={video_id}',
                        'live': True,
                        'discovered_at': datetime.now().isoformat(),
                        'priority': source.get('priority', 'medium'),
                        'focus': source.get('focus', [])
                    })
        except Exception as e:
            print(f'Error checking {name}: {e}')

# Save
with open('live_streams.json', 'w', encoding='utf-8') as f:
    json.dump({'streams': live_streams, 'updated': datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)

print(f'Detected {len(live_streams)} live streams. Saved to live_streams.json with embed_url for in-site viewing.')
print('Important: Update your frontend to prefer "embed_url" or "video_id" for embedded players instead of watch_url.')
