import asyncio
import httpx
import feedparser
import logging
import re
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] RSS_L2: %(message)s")
logger = logging.getLogger("STUDIO.RSS_L2")

class RSSManager:
    """
    RSS L2 Engine - Deployment V19.2
    Features: Asynchronous Fetching, Consensual Clustering, User-Agent Spoofing.
    """
    
    # CURATED FEEDS (Optimized for reliability - expanded V20.1 from Awesome RSS)
    FEEDS = [
        "https://www.lemonde.fr/rss/une.xml",
        "https://www.france24.com/fr/rss",
        "https://www.rfi.fr/fr/rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://news.google.com/rss/search?q=intelligence+artificielle&hl=fr&gl=FR&ceid=FR:fr",
        "https://news.google.com/rss/search?q=AI+breakthrough&hl=en-US&gl=US&ceid=US:en",
        "https://techcrunch.com/feed/",
        "https://www.numerama.com/feed/",
        "https://www.clubic.com/feed/rss",
        "https://www.sciencesetavenir.fr/rss.xml",
        "https://www.futura-sciences.com/rss/actualites.xml",
        "https://www.nature.com/nature.rss",
        "https://www.wired.com/feed/rss",
        "https://www.theguardian.com/world/rss",
        "https://www.leparisien.fr/arc/outboundfeeds/rss/all/",
        "https://edition.cnn.com/services/rss/rss/world.rss",
        "https://www.cnbc.com/id/100727302/device/rss/rss.html",
        "https://www.rt.com/rss/news/",
        "https://rss.feedspot.com/best_rss_feeds/",
        "https://www.financemagnates.com/fintech/feed",
        "https://www.reddit.com/r/worldnews/top/.rss",
    # Awesome RSS Additions
        "http://www.tagesschau.de/xml/rss2",
        "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
        "https://www.japantimes.co.jp/feed/topstories/",
        "https://lenta.ru/rss",
        "https://www.huffpost.com/section/world-news/feed",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "https://www.dailymail.co.uk/home/index.rss",
        "https://www.scmp.com/rss/91/feed",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://www.dw.com/en/service/rss/s-31500"
    ]

    OPML_SOURCES = [
        "https://raw.githubusercontent.com/spians/awesome-RSS-feeds/master/countries/with_category/France.opml",
        "https://raw.githubusercontent.com/spians/awesome-RSS-feeds/master/recommended/with_category/Tech.opml",
        "https://raw.githubusercontent.com/spians/awesome-RSS-feeds/master/recommended/with_category/Business%20%26%20Economy.opml",
        "https://raw.githubusercontent.com/spians/awesome-RSS-feeds/master/recommended/with_category/Science.opml"
    ]

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        # Use a real browser User-Agent to avoid 403 Forbidden
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=15, follow_redirects=True)
        self.dynamic_feeds_path = Path("data/dynamic_feeds.json")
        self.dynamic_feeds_path.parent.mkdir(exist_ok=True)
        self.dynamic_feeds = self._load_dynamic_feeds()

    async def fetch_feed(self, url: str) -> List[Dict[str, Any]]:
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                logger.debug(f"Feed {url} returned {resp.status_code}")
                return []
            
            feed = feedparser.parse(resp.text)
            entries = []
            source_name = feed.feed.get('title', url)
            
            for entry in feed.entries[:12]:
                entries.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", "") or entry.get("description", ""),
                    "link": entry.get("link", ""),
                    "source": source_name,
                    "published": entry.get("published", "")
                })
            return entries
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return []

    async def fetch_all(self) -> List[Dict[str, Any]]:
        # Merge Curated + Dynamic
        active_feeds = list(set(self.FEEDS) | self.dynamic_feeds)
        tasks = [self.fetch_feed(url) for url in active_feeds]
        results = await asyncio.gather(*tasks)
        all_entries = [item for sublist in results for item in sublist]
        logger.info(f"Fetched {len(all_entries)} articles from {len(active_feeds)} sources.")
        return all_entries

    def _load_dynamic_feeds(self) -> Set[str]:
        if self.dynamic_feeds_path.exists():
            try:
                with open(self.dynamic_feeds_path, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception as e:
                logger.error(f"Error loading dynamic feeds: {e}")
        return set()

    def _save_dynamic_feeds(self):
        with open(self.dynamic_feeds_path, "w", encoding="utf-8") as f:
            json.dump(list(self.dynamic_feeds), f)

    async def import_opml(self, url: str) -> int:
        """Downloads and extracts RSS urls from OPML using Regex for resilience."""
        logger.info(f"IMPORT : OPML from: {url}")
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch OPML: {resp.status_code}")
                return 0
            
            # Using regex to find xmlUrl="..." or xmlUrl='...'
            urls = re.findall(r'xmlUrl=["\'](https?://[^"\']+)["\']', resp.text)
            new_feeds = 0
            for xml_url in urls:
                if xml_url and xml_url not in self.FEEDS and xml_url not in self.dynamic_feeds:
                    self.dynamic_feeds.add(xml_url)
                    new_feeds += 1
            
            if new_feeds > 0:
                self._save_dynamic_feeds()
                logger.info(f"OK : Added {new_feeds} new feeds from OPML.")
            
            return new_feeds
        except Exception as e:
            logger.error(f"OPML Import Error: {e}")
            return 0

    async def sync_all_opml(self):
        """Syncs all predefined OPML sources."""
        for url in self.OPML_SOURCES:
            await self.import_opml(url)

    def normalize_text(self, text: str) -> str:
        if not text: return ""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        stop_words = {'le', 'la', 'les', 'de', 'du', 'des', 'une', 'un', 'pour', 'avec', 'the', 'and', 'for', 'with', 'says', 'was', 'were', 'is', 'in', 'on', 'at'}
        words = [w for w in text.split() if w not in stop_words and len(w) > 2]
        return " ".join(words)

    def is_similar(self, a: str, b: str, threshold: float = 0.35) -> bool:
        """Slightly lower threshold (0.35) for better cross-source detection."""
        na = self.normalize_text(a)
        nb = self.normalize_text(b)
        if not na or not nb: return False
        
        aset = set(na.split())
        bset = set(nb.split())
        if not aset or not bset: return False
        
        intersection = aset.intersection(bset)
        union = aset.union(bset)
        jaccard = len(intersection) / len(union)
        
        return jaccard >= threshold

    def cluster_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clusters = []
        for art in articles:
            found_cluster = False
            for cluster in clusters:
                if self.is_similar(art['title'], cluster['representative_title']):
                    cluster['articles'].append(art)
                    cluster['sources'].add(art['source'])
                    found_cluster = True
                    break
            
            if not found_cluster:
                clusters.append({
                    "representative_title": art['title'],
                    "articles": [art],
                    "sources": {art['source']},
                    "timestamp": datetime.now().isoformat()
                })
        
        for c in clusters:
            c['source_count'] = len(c['sources'])
            c['sources'] = list(c['sources'])
        return clusters

    async def get_pro_trends(self) -> List[Dict[str, Any]]:
        all_articles = await self.fetch_all()
        clusters = self.cluster_articles(all_articles)
        pro_trends = [c for c in clusters if c['source_count'] >= self.threshold]
        pro_trends.sort(key=lambda x: x['source_count'], reverse=True)
        logger.info(f"Found {len(pro_trends)} Pro Trends (Threshold >= {self.threshold}).")
        return pro_trends

    async def close(self):
        await self.client.aclose()

_manager = None

async def get_rss_manager(threshold: int = 3):
    global _manager
    if _manager is None:
        _manager = RSSManager(threshold=threshold)
    return _manager

if __name__ == "__main__":
    async def test():
        mgr = await get_rss_manager(threshold=1) 
        trends = await mgr.get_pro_trends()
        for i, t in enumerate(trends[:10]):
            print(f"[{i+1}] {t['representative_title']} ({t['source_count']} sources)")
        await mgr.close()
    asyncio.run(test())
