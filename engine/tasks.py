# -*- coding: utf-8 -*-
import os
import asyncio
import json
import logging
import time
import redis
from pathlib import Path
from celery import Celery
import sys

# Ensure root directory is in sys.path for background worker imports
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine.celery_app import app as celery_app

# Logger setup
logger = logging.getLogger("STUDIO.Tasks")

# Redis for Status
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6373/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

def update_status(is_running: bool, progress: int, step: str, output: str, metadata: dict = None):
    """Updates the global machine status in Redis for the UI."""
    try:
        status = {
            "is_running": is_running,
            "progress": progress,
            "current_step": step,
            "last_output": output,
            "metadata": metadata or {},
            "timestamp": time.time()
        }
        r.set("studio:status", json.dumps(status))
    except Exception as e:
        logger.debug(f"Redis Status Update failed (ignoring): {e}")

@celery_app.task(bind=True, max_retries=3)
def produce_video_task(self, subject, langs, bgm_pref=None, master_script=None, platforms=["youtube"], style="viral"):
    """
    Main background production task (V20).
    Orchestrates trilingual generation and publishing.
    """
    import yaml
    from main import process_channel, cleanup_workspace
    from utils.social_publisher import publish_via_webhook
    from utils.telegram_notifier import send_telegram_alert
    
    # Init Status
    update_status(True, 5, "Initialisation", f"Lancement Empire Celery ({', '.join(langs)}) [Style: {style}]")
    
    async def run_logic():
        try:
            # Load config
            root = Path(__file__).resolve().parent.parent
            with open(root / "config/settings.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            cleanup_workspace()
            render_semaphore = asyncio.Semaphore(1)
            
            update_status(True, 20, "Production Séquentielle", "Démarrage des branches linguistiques...")
            
            results = []
            total_langs = len(langs)
            for lang in langs:
                # Progress capped at 90% during production
                progress = min(90, 30 + int(60 * len(results) / total_langs))
                update_status(True, progress, f"Branche {lang.upper()}", f"Génération {lang} ({style})...")
                res = await process_channel(lang, subject, config, render_semaphore, bgm_pref, master_script, platforms, style=style)
                results.append(res)

            # Webhooks & Publishing
            domain = os.getenv("CloudNode_PUBLIC_DOMAIN", "studio-admin.up.CloudNode.app")
            if not domain.startswith("http"): domain = f"https://{domain}"
            
            urls = []
            for res in results:
                if res and res.get("status") == "success":
                    video_url = res.get("video_url")
                    urls.append(video_url)
                    
                    video_filename = os.path.basename(res.get("video_path"))
                    absolute_video_url = f"{domain}/outputs/{video_filename}"
                    
                    webhook_platforms = [p for p in platforms if p in ["instagram", "facebook", "tiktok"]]
                    if webhook_platforms:
                        script_data = res.get("script", {})
                        script_text = script_data.get("scenes", [{}])[0].get("text", "Production Le Le Presentateur")
                        await publish_via_webhook(absolute_video_url, script_text, webhook_platforms)
            
            summary = f"Publié sur {', '.join(platforms)}. Links: {', '.join(urls)}"
            update_status(False, 100, "Terminé", f"Production réussie ! {summary}")
            await send_telegram_alert(f"🎬 <b>CELERY WORKER : PRODUCTION TERMINÉE</b>\nSujet: {subject}\nPlateformes: {', '.join(platforms)}")
            
            # V26.0 : Trigger Community Manager Poll Task (2 hours delay)
            for res in results:
                if res and res.get("status") == "success":
                    video_title = res.get("script", {}).get("title", subject)
                    # Agglutine le texte pour l'agent
                    script_text = "\n".join([s.get("text", "") for s in res.get("script", {}).get("scenes", [])])
                    community_manager_task.apply_async(
                        args=[video_title, script_text, res.get("lang", "fr")],
                        countdown=7200 # 2 hours
                    )
                    logger.info(f"[{res.get('lang')}] Mission 2 - Community Poll scheduled (+2h).")

        except Exception as e:
            logger.error(f"Task Error: {e}")
            update_status(False, 0, "Erreur", str(e))
            await send_telegram_alert(f"🚨 <b>CELERY WORKER : ERREUR</b>\nSujet: {subject}\nDétails: {str(e)[:200]}")
            # Re-raise so the sync wrapper can handle Celery retry
            raise

    # Run the async logic in the sync Celery worker
    try:
        return asyncio.run(run_logic())
    except Exception as e:
        # Celery retry must be raised from the synchronous context
        raise self.retry(exc=e, countdown=60)

@celery_app.task
def community_manager_task(video_title: str, script_text: str, lang: str):
    """V26.0 : Mission 2 - Génère un sondage et alerte Telegram."""
    from engine.growth.community_manager import CommunityManager
    import asyncio
    import yaml
    
    root = Path(__file__).resolve().parent.parent
    with open(root / "config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    async def run():
        mgr = CommunityManager(config)
        await mgr.schedule_manual_poll(video_title, script_text, lang)
        
    asyncio.run(run())

@celery_app.task
def growth_analytics_task(lang: str = "fr"):
    """V26.0 : Mission 3 - Cron Job pour l'audit de performance hebdomadaire."""
    from engine.growth.analytics_analyzer import AnalyticsAnalyzer
    import asyncio
    import yaml
    
    root = Path(__file__).resolve().parent.parent
    with open(root / "config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    async def run():
        analyzer = AnalyticsAnalyzer(config)
        await analyzer.analyze_performance(lang)
        
    asyncio.run(run())

# Run the async logic in the sync Celery worker
try:
    if len(sys.argv) > 1 and sys.argv[1] == 'worker':
         pass # Normal celery behavior
except: pass
