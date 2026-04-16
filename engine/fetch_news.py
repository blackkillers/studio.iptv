#!/usr/bin/env python3
"""
fetch_news.py — Récupère l'actualité tendance du jour
Sources : Google News RSS + Google Trends (pytrends)
"""

import sys
import json
import random
import argparse
import feedparser
import requests
import io
from datetime import date
from pytrends.request import TrendReq
from newspaper import Article

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── RSS SOURCES V8.5 (Global Agency) ─────────────────────────────────────────
RSS_FEEDS = {
    "world_news": [
        "https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best",
        "https://apnews.com/hub/world-news.rss",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml"
    ],
    "french_news": [
        "https://www.lemonde.fr/international/rss_full_feed.xml",
        "https://www.france24.com/fr/rss",
        "https://www.courrierinternational.com/feed/all/rss.xml"
    ],
    "economy": [
        "https://www.ft.com/?format=rss",
        "https://www.lesechos.fr/rss/rss_monde.xml"
    ],
    "reddit": [
        "https://www.reddit.com/r/news/.rss",
        "https://www.reddit.com/r/worldnews/.rss"
    ]
}

CATEGORIES = {
    "world":        "actualité monde",
    "technology":   "technologie",
    "business":     "économie finance",
    "ai":           "intelligence artificielle",
    "crypto":       "crypto monnaie bitcoin",
    "israel":       "guerre israel gaza",
    "war":          "actualité guerre conflit",
    "trending":     None,   # Déterminé par Google Trends
}

ROTATION = ["world", "technology", "ai", "crypto", "business"]

NEWS_EDITIONS = {
    "fr": {"ceid": "FR:fr", "gl": "FR", "hl": "fr"},
    "en": {"ceid": "US:en", "gl": "US", "hl": "en"},
    "he": {"ceid": "IL:he", "gl": "IL", "hl": "he"}
}

def get_rss_news(category: str = "world_news", max_items: int = 5) -> list[dict]:
    """Récupère les news depuis une liste de flux RSS d'élite."""
    urls = RSS_FEEDS.get(category, RSS_FEEDS["world_news"])
    # Reddit needs special headers
    headers = {"User-Agent": "Mozilla/5.0 StudioEngineV8.5/1.0"}
    
    articles = []
    for url in urls:
        try:
            if "reddit.com" in url:
                resp = requests.get(url, headers=headers, timeout=10)
                feed = feedparser.parse(resp.text)
            else:
                feed = feedparser.parse(url)
                
            for entry in feed.entries[:max_items]:
                articles.append({
                    "title":   entry.get("title", ""),
                    "link":    entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                    "source":  url.split("//")[1].split("/")[0]
                })
        except Exception as e:
            print(f"[fetch_news] Error fetching {url}: {e}", file=sys.stderr)
            
    random.shuffle(articles)
    return articles[:max_items * 2]

def get_google_news(query: str, lang: str = "fr", max_items: int = 15) -> list[dict]:
    """Récupère les articles via Google News RSS avec support multi-éditions (Défaut augmenté à 15)."""
    edition = NEWS_EDITIONS.get(lang.lower(), NEWS_EDITIONS["fr"])
    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl={edition['hl']}&gl={edition['gl']}&ceid={edition['ceid']}"
    )
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries[:max_items]:
        articles.append({
            "title":   entry.get("title", ""),
            "link":    entry.get("link", ""),
            "summary": entry.get("summary", ""),
            "published": entry.get("published", ""),
            "source":  "google-news"
        })
    return articles

def get_reddit_news(category: str = "news", max_items: int = 5) -> list[dict]:
    """Récupère les news tendances sur Reddit via RSS."""
    # Common news subreddits
    subs = ["news", "worldnews", "technology", "artificial"]
    sub = category if category in subs else "news"
    url = f"https://www.reddit.com/r/{sub}/.rss"
    
    # Reddit RSS requires a proper User-Agent
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StudioEngineV8/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(resp.text)
        articles = []
        for entry in feed.entries[:max_items]:
            articles.append({
                "title":   entry.get("title", ""),
                "link":    entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
                "source":  f"reddit-{sub}"
            })
        return articles
    except Exception as e:
        print(f"[fetch_news] Reddit error: {e}", file=sys.stderr)
        return []


def get_trending(lang: str = "fr") -> str:
    """Retourne le sujet tendance #1 Google Trends (FR)."""
    try:
        pytrends = TrendReq(hl=lang, tz=60)
        trending = pytrends.trending_searches(pn="france")
        return str(trending.iloc[0, 0])
    except Exception as e:
        print(f"[fetch_news] Trends error: {e}", file=sys.stderr)
        return "actualité france"


def is_generic_logo(url: str) -> bool:
    """Vérifie si une URL de photo ressemble à un logo ou un favicon générique."""
    blacklist = [
        "google", "favicon", "logo", "icon", "avatar", "fb-", "tw-", "nav-",
        "brand", "placeholder", "sprite", "loading", "transparent"
    ]
    url_lower = url.lower()
    return any(term in url_lower for term in blacklist)

def fetch_article_body(url: str) -> dict:
    """Télécharge et parse le corps d'un article avec newspaper3k.
    Suit les redirections Google News avant de parser."""
    result = {"text": "", "images": []}
    try:
        # Suit la redirection Google News pour obtenir l'URL réelle
        resp = requests.get(url, timeout=15, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0"})
        real_url = resp.url
        article = Article(real_url, language="fr")
        article.download()
        article.parse()
        
        # Filtre les petites images (souvent des icônes/ads) ou les gifs
        imgs = [img for img in article.images if not img.endswith('.gif') and not is_generic_logo(img)]
        
        # Vérifie que la 'top_image' n'est pas un logo générique avant de l'insérer
        if article.top_image and not is_generic_logo(article.top_image):
            imgs.insert(0, article.top_image)
            
        result["images"] = list(dict.fromkeys(imgs))[:5] # Keep max 5 unique images
        
        if article.text and len(article.text) > 100:
            result["text"] = article.text[:12000]
    except Exception as e:
        print(f"[fetch_news] Newspaper error: {e}", file=sys.stderr)
    return result


def strip_html(html: str) -> str:
    """Nettoie le HTML du summary Google News."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "lxml").get_text(separator=" ").strip()
    except Exception:
        import re
        return re.sub(r"<[^>]+>", "", html).strip()


def select_category() -> str:
    """Sélectionne la catégorie du jour en rotation."""
    day_index = date.today().toordinal() % len(ROTATION)
    return ROTATION[day_index]


def main(args: argparse.Namespace) -> None:
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    
    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=BASE_DIR / ".env")

    category = args.category or os.getenv("NEWS_CATEGORY") or select_category()
    
    if args.query:
        # Nettoie la query si c'est un titre RSS trop long (>60 chars)
        raw_query = args.query
        if len(raw_query) > 60:
            # Extrait les 5 premiers mots significatifs
            stop = {"de", "du", "la", "le", "les", "un", "une", "des", "et", "en", "au", "aux",
                    "sur", "-", ":", "...", "…", "l", "d", "à", "par", "pour", "avec"}
            words = [w.strip(".,;:!?…'\"-") for w in raw_query.split()
                     if w.strip(".,;:!?…'\"-").lower() not in stop and len(w) > 2]
            query = " ".join(words[:5]) if words else raw_query[:50]
            print(f"[fetch_news] Query longue tronquée: '{raw_query[:40]}...' → '{query}'", file=sys.stderr)
        else:
            query = raw_query
    elif category == "trending":
        query = get_trending()
        print(f"[fetch_news] Trending topic: {query}", file=sys.stderr)
    else:
        query = CATEGORIES.get(category, "actualité")

    print(f"[fetch_news] category={category}, query='{query}'", file=sys.stderr)

    articles = get_google_news(query, max_items=args.max_items)
    # Fallback vers la catégorie si la query custom ne donne rien
    if not articles and args.query:
        fallback_query = CATEGORIES.get(category, "actualité monde")
        print(f"[fetch_news] 0 résultats pour '{query}', fallback → '{fallback_query}'", file=sys.stderr)
        articles = get_google_news(fallback_query, max_items=args.max_items)
    # --- V14.0: TOP PERFORMANCE SCORING ---
    high_engagement_keywords = ["guerre", "war", "iran", "israel", "conflit", "breaking", "urgent", "moyen-orient", "russie", "ukraine", "nucléaire"]
    
    scored_articles = []
    for art in articles:
        score = 0
        title_lower = art["title"].lower()
        for kw in high_engagement_keywords:
            if kw in title_lower:
                score += 10
        scored_articles.append((score, art))
    
    # Sort by score descending, then by original order
    scored_articles.sort(key=lambda x: x[0], reverse=True)
    articles = [x[1] for x in scored_articles]
    
    if articles:
        print(f"[fetch_news] Top article score: {scored_articles[0][0]}", file=sys.stderr)

    # Choisit l'article le plus pertinent (premier = plus haut score ou plus récent)
    best = articles[0]
    article_data = fetch_article_body(best["link"])
    body = article_data["text"]
    article_images = article_data["images"]

    result = {
        "category":  category,
        "query":     query,
        "title":     best["title"],
        "link":      best["link"],
        "summary":   strip_html(best["summary"]),
        "body":      body or strip_html(best["summary"]),
        "date":      str(date.today()),
        "article_images": article_images,
        "all_articles": articles,
    }

    if args.test:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Écriture dans un fichier temporaire pour la chaîne de scripts
        output_path = BASE_DIR / "output" / "news_data.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[fetch_news] Saved to {output_path}", file=sys.stderr)
        print(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch trending news")
    parser.add_argument("--category", default="", help="Category override")
    parser.add_argument("--query", default="", help="Search query override")
    parser.add_argument("--max-items", type=int, default=15, help="Number of articles to fetch")
    parser.add_argument("--test", action="store_true", help="Print result to stdout")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility flag")
    main(parser.parse_args())
