#!/usr/bin/env python3
"""
Auto-detect live streams from sources.json for infiltruth.com / Frontlines

Supports YouTube + Twitch.
Uses environment variables for API keys (secure + Vercel-friendly and GitHub Actions).
Outputs embed_url fields so streams can play in-site via iframe.

yt-dlp is preferred (zero quota, richer metadata, robust parsing) with graceful fallback to APIs.

Run this periodically (cron, GitHub Action, or Vercel Cron) to keep live_streams.json fresh.

Detector version: 2.2.0 (hardened)

Changes in 2.2:
- yt-dlp primary for live checks (YouTube channel/live + Twitch) when available (pip install yt-dlp or system). Falls back to YouTube Data API / Twitch Helix.
- Structured JSON logging (log lines are parseable).
- Robust Twitch handle extraction/sanitization (handles URLs, @, case, legacy fields).
- Enhanced retries for both API and yt-dlp.
- Quota awareness: prefers yt-dlp (0 cost), tracks api_calls vs ytdlp_checks, detailed note.
- Richer stream metadata (thumbnail, description, view_count etc from yt-dlp; serves as archived snapshot metadata).
- Optional full archive metadata: set ARCHIVE_STREAM_META=1 to write stream_archives/<video_id>.info.json (full yt-dlp dump for transcripts, capture, etc).
- Version bump, improved error handling, better stats in output.
- CI runner now installs yt-dlp + ffmpeg.
"""

import os
import json
import time
import shutil
import subprocess
from datetime import datetime, timezone
import requests
import logging

# ==================== CONFIG ====================
DETECTOR_VERSION = "2.2.0"
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
USE_YT_DLP = os.getenv('USE_YT_DLP', '1').lower() in ('1', 'true', 'yes', 'on')
FORCE_API = os.getenv('FORCE_YT_API', '0').lower() in ('1', 'true', 'yes', 'on')
ARCHIVE_META = os.getenv('ARCHIVE_STREAM_META', '0').lower() in ('1', 'true', 'yes', 'on')
TWITCH_EMBED_PARENT = os.getenv('TWITCH_EMBED_PARENT', 'infiltruth.com')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Setup structured logging: each log is a single JSON line for easy parsing in CI/logs
logger = logging.getLogger("live_detector")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(handler)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def log_event(level: str, message: str, **fields):
    """Emit structured log line as JSON."""
    entry = {
        'ts': _now_iso(),
        'level': level,
        'msg': message,
        'detector_version': DETECTOR_VERSION,
        **fields
    }
    print(json.dumps(entry, ensure_ascii=False, separators=(',', ':')))
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message)

# ==================== HELPERS ====================

def _retry_request(method, url, max_retries=3, **kwargs):
    """Simple retry helper for transient errors. Exponential backoff."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = method(url, timeout=20, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log_event('warning', 'retrying_request', attempt=attempt+1, url=url[:80], error=str(e)[:100], wait=wait)
                time.sleep(wait)
    log_event('error', 'request_failed_after_retries', url=url[:80], error=str(last_exc)[:200])
    raise last_exc

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
        r = _retry_request(requests.post, url, params=params)
        if r:
            return r.json().get('access_token')
    except Exception as e:
        log_event('error', 'twitch_token_error', error=str(e))
    return None

def sanitize_handle(raw, platform='twitch'):
    """Robust extraction and cleanup for platform handles/URLs."""
    if not raw or not isinstance(raw, str):
        return None
    h = raw.strip()
    for prefix in ('https://', 'http://'):
        if h.lower().startswith(prefix):
            h = h[len(prefix):]
    h = h.lstrip('www.').lstrip('m.')
    if 'twitch.tv/' in h:
        h = h.split('twitch.tv/', 1)[1]
    h = h.split('/')[0].split('?')[0].split('&')[0].lstrip('@').strip()
    if platform == 'twitch':
        h = h.lower()
    if not h or h in ('', 'none', 'null'):
        return None
    return h

def has_yt_dlp():
    """Check if yt-dlp is usable: either importable module or CLI in PATH."""
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        pass
    return shutil.which('yt-dlp') is not None

def _extract_yt_dlp_json(url, timeout=45):
    """Run yt-dlp to get info json for url (live page). Returns dict or None."""
    try:
        import yt_dlp
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if isinstance(info, dict):
                if 'entries' in info and info['entries']:
                    info = info['entries'][0]
                return info
            return None
    except ImportError:
        pass
    except Exception as e:
        log_event('warning', 'ytdlp_python_extract_failed', url=url[:100], error=str(e)[:150], mode='python')

    # CLI fallback
    if shutil.which('yt-dlp'):
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-download',
                '--no-warnings',
                '--ignore-errors',
                url
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if proc.returncode != 0:
                return None
            stdout = proc.stdout.strip()
            if not stdout:
                return None
            first = stdout.split('\n', 1)[0].strip()
            return json.loads(first)
        except subprocess.TimeoutExpired:
            log_event('warning', 'ytdlp_cli_timeout', url=url[:80])
            return None
        except Exception as e:
            log_event('warning', 'ytdlp_cli_extract_failed', url=url[:80], error=str(e)[:150])
            return None
    return None

def check_youtube_live_yt_dlp(channel_id):
    if not channel_id:
        return []
    url = f"https://www.youtube.com/channel/{channel_id}/live"
    info = _extract_yt_dlp_json(url)
    if not info:
        return []
    live_status = info.get('live_status') or ('is_live' if info.get('is_live') else None)
    if live_status not in ('is_live', 'live') and not info.get('is_live'):
        return []
    vid = info.get('id') or info.get('video_id')
    if not vid:
        return []
    result = {
        'platform': 'YouTube',
        'video_id': vid,
        'title': info.get('title', ''),
        'embed_url': f'https://www.youtube.com/embed/{vid}?autoplay=1&rel=0&modestbranding=1',
        'watch_url': info.get('webpage_url') or f'https://www.youtube.com/watch?v={vid}',
        'live': True,
        'thumbnail': info.get('thumbnail'),
        'description': (info.get('description') or '')[:500],
        'uploader': info.get('uploader') or info.get('channel'),
        'view_count': info.get('view_count'),
        'concurrent_viewers': info.get('concurrent_viewers') or info.get('view_count'),
        'duration': info.get('duration'),
        'upload_date': info.get('upload_date'),
    }
    if ARCHIVE_META:
        try:
            os.makedirs('stream_archives', exist_ok=True)
            meta_path = os.path.join('stream_archives', f"{vid}.info.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
            result['archive_meta_path'] = meta_path
            result['archived_at'] = _now_iso()
        except Exception as e:
            log_event('warning', 'archive_meta_write_failed', video_id=vid, error=str(e))
    return [result]

def check_twitch_live_yt_dlp(handle):
    if not handle:
        return []
    clean = sanitize_handle(handle, 'twitch')
    if not clean:
        return []
    url = f"https://www.twitch.tv/{clean}"
    info = _extract_yt_dlp_json(url, timeout=30)
    if not info:
        return []
    live_status = info.get('live_status') or ('is_live' if info.get('is_live') else None)
    if live_status not in ('is_live', 'live') and not info.get('is_live'):
        return []
    channel_name = info.get('uploader') or info.get('channel') or info.get('display_id') or clean
    result = {
        'platform': 'Twitch',
        'channel': channel_name,
        'title': info.get('title', ''),
        'viewer_count': info.get('view_count') or info.get('concurrent_viewers') or 0,
        'embed_url': f'https://player.twitch.tv/?channel={channel_name}&parent={TWITCH_EMBED_PARENT}&autoplay=true',
        'watch_url': info.get('webpage_url') or f'https://www.twitch.tv/{channel_name}',
        'live': True,
        'thumbnail': info.get('thumbnail'),
        'description': (info.get('description') or '')[:300],
        'uploader': info.get('uploader'),
    }
    if ARCHIVE_META:
        try:
            os.makedirs('stream_archives', exist_ok=True)
            safe = sanitize_handle(channel_name, 'twitch') or 'twitch'
            meta_path = os.path.join('stream_archives', f"twitch-{safe}-{int(time.time())}.info.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
            result['archive_meta_path'] = meta_path
            result['archived_at'] = _now_iso()
        except Exception as e:
            log_event('warning', 'archive_meta_write_failed', channel=channel_name, error=str(e))
    return [result]

# API fallbacks (quota costing)
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
        r = _retry_request(requests.get, url, params=params)
        if not r:
            return []
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
        log_event('error', 'youtube_api_error', channel_id=channel_id, error=str(e)[:150])
        return []

def check_twitch_live(handle):
    if not handle:
        return []
    token = get_twitch_token()
    if not token:
        log_event('warning', 'no_twitch_token', handle=handle)
        return []
    clean = sanitize_handle(handle, 'twitch') or handle
    url = 'https://api.twitch.tv/helix/streams'
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
        'Authorization': f'Bearer {token}'
    }
    params = {'user_login': clean}
    try:
        r = _retry_request(requests.get, url, headers=headers, params=params)
        if not r:
            return []
        data = r.json().get('data', [])
        results = []
        for stream in data:
            results.append({
                'platform': 'Twitch',
                'channel': stream['user_name'],
                'title': stream['title'],
                'viewer_count': stream.get('viewer_count', 0),
                'embed_url': f'https://player.twitch.tv/?channel={stream["user_name"]}&parent={TWITCH_EMBED_PARENT}&autoplay=true',
                'watch_url': f'https://www.twitch.tv/{stream["user_name"]}',
                'live': True
            })
        return results
    except Exception as e:
        log_event('error', 'twitch_api_error', handle=handle, error=str(e)[:150])
        return []

def get_live_detector_for_source(source):
    """Choose detector impl based on config and availability."""
    use_dlp = USE_YT_DLP and not FORCE_API and has_yt_dlp()
    name = source.get('name', 'Unknown')
    channel_id = source.get('channel_id')
    twitch_raw = source.get('twitch_handle') or source.get('handles', {}).get('twitch')
    twitch_handle = sanitize_handle(twitch_raw, 'twitch')
    results = []
    if channel_id:
        if use_dlp:
            yt_res = check_youtube_live_yt_dlp(channel_id)
            method = 'yt-dlp'
        else:
            yt_res = check_youtube_live(channel_id)
            method = 'youtube-api'
        for item in yt_res:
            item.update({
                'source': name,
                'priority': source.get('priority', 'medium'),
                'focus': source.get('focus', []),
                'discovered_at': _now_iso(),
                'detection_method': method
            })
            results.append(item)
    if twitch_handle:
        if use_dlp:
            tw_res = check_twitch_live_yt_dlp(twitch_handle)
            method = 'yt-dlp'
        else:
            tw_res = check_twitch_live(twitch_handle)
            method = 'twitch-api'
        for item in tw_res:
            item.update({
                'source': name,
                'priority': source.get('priority', 'medium'),
                'focus': source.get('focus', []),
                'discovered_at': _now_iso(),
                'detection_method': method
            })
            results.append(item)
    return results, use_dlp

# ==================== MAIN ====================

def main():
    log_event('info', 'detector_start', version=DETECTOR_VERSION, use_ytdlp_pref=USE_YT_DLP, force_api=FORCE_API, archive_meta=ARCHIVE_META)
    ytdlp_available = has_yt_dlp()
    log_event('info', 'ytdlp_status', available=ytdlp_available)
    if not YOUTUBE_API_KEY:
        log_event('warning', 'no_youtube_api_key')
    if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
        log_event('info', 'no_twitch_creds', note='ok if using yt-dlp')

    try:
        with open('sources.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        log_event('error', 'sources_json_not_found')
        return
    except Exception as e:
        log_event('error', 'sources_load_failed', error=str(e))
        return

    journalists = data.get('journalists_reporters_livestreamers', [])
    tiktoks = data.get('tiktok_livestreamers', [])
    sources = journalists + tiktoks

    live_streams = []
    stats = {'yt_api_calls': 0, 'twitch_api_calls': 0, 'ytdlp_checks': 0, 'sources_checked': len(sources)}

    for source in sources:
        res_list, used_dlp = get_live_detector_for_source(source)
        if used_dlp:
            stats['ytdlp_checks'] += 1
        else:
            if source.get('channel_id'):
                stats['yt_api_calls'] += 1
            if source.get('twitch_handle') or source.get('handles', {}).get('twitch'):
                stats['twitch_api_calls'] += 1
        for item in res_list:
            live_streams.append(item)

    output = {
        'detector_version': DETECTOR_VERSION,
        'updated': _now_iso(),
        'count': len(live_streams),
        'stats': stats,
        'ytdlp_available': ytdlp_available,
        'quota_note': 'yt-dlp used when available (0 quota units). YouTube search.list ~100 units/call when API fallback. Monitor at https://console.cloud.google.com/iam-admin/quotas . Set USE_YT_DLP=0 to force API.',
        'streams': live_streams
    }

    with open('live_streams.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log_event('info', 'detector_complete', count=len(live_streams), ytdlp_checks=stats['ytdlp_checks'], yt_api_calls=stats['yt_api_calls'], output='live_streams.json')
    print(f'✅ Detected {len(live_streams)} live streams. Saved to live_streams.json (v{DETECTOR_VERSION})')
    print(f'   YT-dlp available: {ytdlp_available} | Used for checks on sources preferring it.')
    print(f'   Stats: {stats}')
    print('   Use "embed_url" for in-site iframe. Richer metadata included when yt-dlp path taken.')

if __name__ == '__main__':
    main()
