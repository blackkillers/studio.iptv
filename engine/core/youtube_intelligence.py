import os
import logging
import asyncio
from pathlib import Path
from googleapiclient.discovery import build
from typing import List, Dict, Any

logger = logging.getLogger("LEVIATHAN.YouTubeIntelligence")

class YouTubeIntelligence:
    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if self.api_key:
            self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        else:
            self.youtube = None

    async def get_trending_news(self, region_code="FR") -> List[Dict[str, Any]]:
        """Fetches trending news videos from YouTube."""
        if not self.youtube:
            logger.error("YouTube API Key missing.")
            return []
            
        try:
            # Category 25 is News & Politics
            request = self.youtube.videos().list(
                part="snippet,statistics",
                chart="mostPopular",
                regionCode=region_code,
                videoCategoryId="25",
                maxResults=10
            )
            
            # Using run_in_executor because google-api-python-client is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, request.execute)
            
            trends = []
            for item in response.get("items", []):
                snippet = item["snippet"]
                stats = item["statistics"]
                trends.append({
                    "title": snippet["title"],
                    "description": snippet["description"],
                    "views": stats.get("viewCount", "0"),
                    "source": f"YouTube Trending ({region_code})",
                    "url": f"https://youtu.be/{item['id']}",
                    "type": "youtube_trend"
                })
            return trends
        except Exception as e:
            logger.error(f"YouTube Intelligence Error: {e}")
            return []

    async def search_highly_relevant(self, query: str) -> List[Dict[str, Any]]:
        """Searches for videos related to a query that are performing well."""
        if not self.youtube: return []
        try:
            request = self.youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                order="viewCount",
                maxResults=5,
                publishedAfter="2026-03-01T00:00:00Z" # Recent only
            )
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, request.execute)
            
            results = []
            for item in response.get("items", []):
                results.append({
                    "title": item["snippet"]["title"],
                    "description": item["snippet"]["description"],
                    "source": "YouTube Search",
                    "url": f"https://youtu.be/{item['id']['videoId']}",
                    "type": "youtube_search"
                })
            return results
        except Exception as e:
            logger.error(f"YouTube Search Error: {e}")
            return []
