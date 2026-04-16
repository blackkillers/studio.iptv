import logging
import asyncio
from typing import List, Dict, Any
from engine.core.rss_manager import get_rss_manager
from engine.core.youtube_intelligence import YouTubeIntelligence
from engine.core.web_intelligence import WebScraperIntelligence

logger = logging.getLogger("LEVIATHAN.IntelligenceHub")

class IntelligenceHub:
    def __init__(self):
        self.yt = YouTubeIntelligence()
        self.web = WebScraperIntelligence()

    async def get_all_pro_trends(self) -> List[Dict[str, Any]]:
        """
        Combines RSS, YouTube Trends, and Web Scraping into a single master trend list.
        """
        logger.info("📡 Hub Intelligence : Scan global en cours (RSS + YT + WEB)...")
        
        # 1. Fetch RSS (Consensus L2)
        rss_mgr = await get_rss_manager(threshold=2)
        rss_task = rss_mgr.get_pro_trends()
        
        # 2. Fetch YT Trending
        yt_task = self.yt.get_trending_news()
        
        # 3. Fetch Web Breaking
        web_task = self.web.get_breaking_news()
        
        # Run everything in parallel
        results = await asyncio.gather(rss_task, yt_task, web_task, return_exceptions=True)
        
        rss_trends = results[0] if not isinstance(results[0], Exception) else []
        yt_trends = results[1] if not isinstance(results[1], Exception) else []
        web_trends = results[2] if not isinstance(results[2], Exception) else []
        
        # Normalize and merge
        master_trends = []
        
        # RSS
        if isinstance(rss_trends, list):
            for t in rss_trends:
                master_trends.append({
                    "title": t.get("representative_title", "Unknown"),
                    "reason": f"Consensus RSS ({t.get('source_count', 0)} sources)",
                    "source_type": "rss",
                    "heat": t.get("source_count", 0) * 10
                })
            
        # YouTube
        if isinstance(yt_trends, list):
            for t in yt_trends:
                master_trends.append({
                    "title": t.get("title", "Unknown"),
                    "reason": f"Trending YouTube ({t.get('views', 0)} vues)",
                    "source_type": "youtube",
                    "heat": 80 # High priority
                })
            
        # Web
        if isinstance(web_trends, list):
            for t in web_trends:
                 master_trends.append({
                    "title": t.get("title", "Unknown"),
                    "reason": f"Breaking Web : {t.get('summary', '')}",
                    "source_type": "web",
                    "heat": t.get("intensity", 50)
                })
             
        # Sort by heat
        master_trends.sort(key=lambda x: x["heat"], reverse=True)
        
        logger.info(f"OK : Hub Intelligence a identifi\xE9 {len(master_trends)} trends potentiels.")
        return master_trends

# Singleton
hub = IntelligenceHub()

async def get_intelligence_hub():
    return hub
