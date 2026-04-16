import asyncio
import os
import json
import logging
import httpx
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger("STUDIO.Analytics")
# Robust path resolution for CloudNode or Local
ROOT_DIR = Path("/app") if os.path.exists("/app") else Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"

async def get_channel_stats(lang: str):
    """Fetches real-time stats for a given language channel (fr, en, ru)."""
    token_path = CONFIG_DIR / f"token_{lang}.json"
    
    if not token_path.exists():
        logger.warning(f"Token skipping: {token_path.absolute()} not found.")
        return None

    try:
        # Load credentials
        creds = Credentials.from_authorized_user_file(str(token_path))
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        
        async with httpx.AsyncClient() as client:
            # 1. Get Channel Stats
            ch_url = "https://www.googleapis.com/youtube/v3/channels"
            params = {
                "part": "statistics,snippet",
                "mine": "true",
                "access_token": creds.token
            }
            resp = await client.get(ch_url, params=params)
            ch_data = resp.json()
            
            if "items" not in ch_data or not ch_data["items"]:
                return {"error": "Channel not found"}
            
            item = ch_data["items"][0]
            stats = item["statistics"]
            snippet = item["snippet"]
            
            # 2. Get Last Video Stats for "Rate"
            v_url = "https://www.googleapis.com/youtube/v3/search"
            v_params = {
                "part": "snippet",
                "forMine": "true",
                "type": "video",
                "maxResults": 1,
                "order": "date",
                "access_token": creds.token
            }
            v_resp = await client.get(v_url, params=v_params)
            v_data = v_resp.json()
            
            last_video_views = "N/A"
            if "items" in v_data and v_data["items"]:
                video_id = v_data["items"][0]["id"]["videoId"]
                # Get video stats
                vs_url = "https://www.googleapis.com/youtube/v3/videos"
                vs_params = {
                    "part": "statistics",
                    "id": video_id,
                    "access_token": creds.token
                }
                vs_resp = await client.get(vs_url, params=vs_params)
                vs_data = vs_resp.json()
                if "items" in vs_data and vs_data["items"]:
                    last_video_views = vs_data["items"][0]["statistics"].get("viewCount", "0")

            return {
                "name": snippet["title"],
                "thumbnail": snippet["thumbnails"]["default"]["url"],
                "subscribers": stats["subscriberCount"],
                "views": stats["viewCount"],
                "videos": stats["videoCount"],
                "last_video_views": last_video_views,
                "lang": lang
            }

    except Exception as e:
        logger.error(f"Analytics error for {lang}: {e}")
        return {"error": str(e), "lang": lang}

async def get_all_empire_stats():
    """Aggregates stats for the 3 major channels."""
    langs = ["fr", "en", "ru"]
    tasks = [get_channel_stats(l) for l in langs]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
