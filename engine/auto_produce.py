import os
import sys
import json
import random
import asyncio
import logging
import time
from pathlib import Path
from datetime import datetime

# Setup Path & Logger
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

logger = logging.getLogger("LEVIATHAN.AutoProduce")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] AutoProduce: %(message)s")

# Imports
from engine.core.intelligence_hub import get_intelligence_hub
from utils.telegram_notifier import send_telegram_alert

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SEEN_FILE = DATA_DIR / "seen_clusters.json"

async def check_for_pro_trends():
    """Detect high-consensus trends and notify Telegram for validation."""
    logger.info("🔍 Sensing Pro Trends (Consensus L2)...")
    try:
        hub = await get_intelligence_hub()
        trends = await hub.get_all_pro_trends()
        
        # Load seen clusters to avoid spam
        seen = []
        if SEEN_FILE.exists():
            try:
                with open(SEEN_FILE, "r") as f: seen = json.load(f)
            except: seen = []

        new_count = 0
        for t in trends[:5]: # Top 5 clusters
            topic = t['title']
            if topic in seen: continue
            
            # Send to Telegram with buttons (Handled by the bot if we just call the API)
            # Actually, auto_produce can use the same logic as /pro command
            from scripts.telegram_bot import send_msg
            
            reason = t['reason']
            btn = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Valider", "callback_data": f"validate|{topic[:50]}"},
                        {"text": "🚫 Bannir", "callback_data": f"ban|{topic[:50]}"}
                    ]
                ]
            }
            await send_msg(f"🌟 <b>DETECTION HAUT CONSENSUS</b>\nSujet: {topic}\nSource: <i>{reason}</i>\n<i>Voulez-vous lancer la production ?</i>", reply_markup=btn)
            
            seen.append(topic)
            new_count += 1
            
        # Keep seen list reasonable
        with open(SEEN_FILE, "w") as f: json.dump(seen[-100:], f)
        
        if new_count > 0:
            logger.info(f"Sent {new_count} new trends to Telegram.")
            
    except Exception as e:
        logger.error(f"Sensing Error: {e}")

# process_approved_queue removed in V20 (Celery handled)

async def get_best_trend() -> tuple:
    """
    Retourne le meilleur trend RSS consensuel pour la production automatique.
    Fallback : sujet générique si aucun trend détecté.
    """
    logger.info("🔍 get_best_trend() : Recherche du meilleur trend GLOBAL (RSS+YT+WEB)...")
    try:
        hub = await get_intelligence_hub()
        trends = await hub.get_all_pro_trends()

        # Load seen clusters to avoid repeating the same topic
        seen = []
        if SEEN_FILE.exists():
            try:
                with open(SEEN_FILE, "r") as f:
                    seen = json.load(f)
            except Exception:
                seen = []

        for t in trends:
            topic = t["title"]
            if topic not in seen:
                # Mark as seen
                seen.append(topic)
                with open(SEEN_FILE, "w") as f:
                    json.dump(seen[-100:], f)
                
                reason = t['reason'] # Use normalized reason from Hub (Source info included)
                logger.info(f"✅ Meilleur trend trouvé : {topic}")
                await send_telegram_alert(
                    f"🌟 <b>Trend Sélectionné</b>\n<b>{topic}</b>\n<i>{reason}</i>"
                )
                return topic, reason

        # If all are seen, pick the top one anyway
        if trends:
            best = trends[0]
            return best["title"], best["reason"]

    except Exception as e:
        logger.error(f"get_best_trend() Error: {e}")

    # Ultimate fallback
    fallback = f"Actualité Mondiale du {datetime.now().strftime('%d/%m/%Y')}"
    logger.warning(f"⚠️ Fallback sujet générique : {fallback}")
    return fallback, "Fallback RSS vide"


async def get_weekly_top_10() -> tuple:
    """
    Retourne un sujet agrégé pour la vidéo longue hebdomadaire (Top 10).
    Utilise la mémoire weekly_memory.json.
    """
    logger.info("📅 get_weekly_top_10() : Construction du sujet hebdomadaire...")
    try:
        from engine.core.weekly_aggregator import get_weekly_top_topics
        topics = get_weekly_top_topics(limit=10)
        if topics:
            titles = [t["topic"] for t in topics]
            subject = f"TOP 10 SEMAINE : {' | '.join(titles[:5])}"
            reason = f"{len(topics)} sujets en mémoire hebdomadaire"
            logger.info(f"✅ Sujet hebdo : {subject}")
            return subject, reason
    except Exception as e:
        logger.error(f"get_weekly_top_10() Error: {e}")

    # Fallback to best RSS trend
    logger.warning("⚠️ Mémoire hebdo vide. Fallback sur RSS trend.")
    return await get_best_trend()

async def run_automation_loop():
    """Infinite loop for the L2 Engine."""
    logger.info("🚀 StudioEngine L2 Engine - ACTIVE")
    
    while True:
        # 1. Sense trends
        await check_for_pro_trends()
        
        # 2. Sleep (Check every 15 minutes for new trends)
        logger.info("Sleeping for 15m...")
        await asyncio.sleep(900)

if __name__ == "__main__":
    try:
        asyncio.run(run_automation_loop())
    except KeyboardInterrupt:
        logger.info("Automation stopped.")
