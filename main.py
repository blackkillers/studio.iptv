import asyncio
import argparse
import os
import sys
import json
import time
import logging
import yaml
import shutil
from dotenv import load_dotenv
from pathlib import Path

# Fix for Windows console encoding (Safely check for attribute availability in workers)
if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from engine.core.content_manager import ContentManager
from engine.core.media_scraper import MediaScraper
from engine.core.render_engine import RenderEngine
from engine.tts.edge_tts_wrapper import EdgeTTSWrapper
from engine.core.youtube_publisher import YouTubePublisher
from utils.telegram_notifier import send_telegram_alert

# Load environment variables
load_dotenv()

# Status integration V20
from engine.tasks import update_status

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LEVIATHAN")

def cleanup_workspace():
    """V12.11 : Nettoyage des dossiers de sortie."""
    folders = ["output/audio", "output/images", "output/videos", "output/subtitles", "output/temp_ultra"]
    for folder in folders:
        path = Path(folder)
        if path.exists():
            for file in path.iterdir():
                if file.is_file():
                    try:
                        file.unlink()
                    except Exception:
                        pass

async def process_channel(lang: str, subject: str, config: dict, render_semaphore: asyncio.Semaphore, bgm_pref: str = None, script: dict = None, platforms: list = ["youtube"], style: str = "viral"):
    """Orchestre la production complète avec Style Support (v20)."""
    channel_config = config['channels'].get(lang)
    if not channel_config:
        logger.error(f"[{lang}] Profil de langue introuvable.")
        return {"status": "error", "message": "Language profile not found"}

    logger.info(f"🚀 [START] Channel: {lang} | Subject: {subject}")
    
    # V18.7 : Setup Mode String
    is_long = config.get("rendering", {}).get("resolution") == [1920, 1080]
    mode_str = "LONG-FORM (5-8 min)" if is_long else "SHORT (60s)"

    try:
        # ÉTAPE 1 : AGENTIC STORYTELLING
        if script is None:
            update_status(True, 15, lang.upper(), f"Génération du Script IA ({style})...")
            logger.info(f"[{lang}] Agentic Workflow : Création du script ({style})...")
            manager = ContentManager(config)
            script = await manager.generate_workflow(subject, lang, style=style)
            await send_telegram_alert(f"📝 <b>[{lang.upper()}] Script Généré</b>\nTitre: {script.get('seo_title', 'N/A')}\nDurée estimée: {mode_str}")
        else:
            logger.info(f"[{lang}] Empire Mode : Script injecté.")

        # ÉTAPE 2 : MEDIA SCRAPING
        logger.info(f"[{lang}] Visual Director & Scraper...")
        from engine.agents.visual_director import VisualDirectorAgent
        visual_director = VisualDirectorAgent()
        try:
            visual_plans = await visual_director.direct_visuals(script, style=style)
            if not visual_plans: raise ValueError("AI Visual Director returned empty.")
        except Exception as e:
            logger.warning(f"[{lang}] ⚠️ Visual Director Fail (Quota ?): {e}. Using script defaults.")
            # Fallback direct : on utilise les keywords déjà présents dans le script
            visual_plans = {"music_mood": "documentary", "visual_scenes": []}
            
        music_mood = visual_plans.get("music_mood", "documentary")
        
        # Dynamic Orientation
        res = config.get("rendering", {}).get("resolution", [1080, 1920])
        orientation = "PORTRAIT" if res[0] < res[1] else "LANDSCAPE"

        scraper = MediaScraper(config)
        update_status(True, 30, lang.upper(), f"Scraping Média ({orientation})...")
        image_paths, bg_music_path = await scraper.fetch_all_media(script, lang, music_mood, bgm_pref)
        
        # EXPOSE STORYBOARD TO UI
        metadata = {
            "photos": [os.path.basename(p) for p in image_paths],
            "music": os.path.basename(bg_music_path) if bg_music_path else "Standard BGM",
            "music_mood": music_mood
        }
        update_status(True, 45, lang.upper(), f"Storyboard Prêt : {len(image_paths)} images.", metadata=metadata)
        
        script["image_paths"] = image_paths
        await send_telegram_alert(f"🖼️ <b>[{lang.upper()}] Média Prêt</b>\n{len(image_paths)} images téléchargées en {orientation}.")

        # ÉTAPE 3 : THUMBNAIL & TTS
        if is_long:
            thumb_path = await scraper.generate_thumbnail(script.get("seo_title", subject), lang)
            if thumb_path:
                 script["thumbnail_path"] = thumb_path
                 await send_telegram_alert(f"🎨 <b>[{lang.upper()}] Miniature DALL-E Créée</b>")
        
        audio_path_template = str(Path("output/audio") / f"voice_{lang}.mp3")
        full_text = "... ".join([s["text"] for s in script["scenes"]])

        tts = EdgeTTSWrapper(config)
        voice_path, srt_path = await tts.generate_audio(full_text, channel_config['voice_id'], channel_config['language_code'], audio_path_template)
        if not voice_path:
            raise RuntimeError("Échec TTS.")
        await send_telegram_alert(f"🎙️ <b>[{lang.upper()}] Audio & SRT OK</b>")

        # ÉTAPE 4 : RENDU
        async with render_semaphore:
            logger.info(f"[{lang}] 🎥 RenderEngine : Master Pass...")
            await send_telegram_alert(f"🎥 <b>[{lang.upper()}] Rendu en cours...</b>")
            renderer = RenderEngine(config)
            video_filename = f"video_{lang}.mp4"
            video_path = str(Path("output/videos") / video_filename)
            update_status(True, 80, lang.upper(), f"Rendu FFmpeg (Master Pass - {style})...")
            await renderer.assemble_video(script, image_paths, voice_path, srt_path, bg_music_path, video_path, lang, style=style)
            
            # ÉTAPE 5 : PUBLISH
            video_url = None
            if "youtube" in platforms:
                publisher = YouTubePublisher(config)
                title = script.get("seo_title", subject)
                desc = f"{script.get('title', subject)}\n\n{' '.join(script.get('hashtags', []))}"
                video_url = await publisher.upload_video(video_path, title, desc, lang)
                if video_url:
                     await send_telegram_alert(f"🚀 <b>[{lang.upper()}] VIDÉO EN LIGNE !</b>\nURL: {video_url}")
            
            if not video_url:
                video_url = f"https://archive.studioengine.com/{lang}/{int(time.time())}"
            
            return {"status": "success", "video_url": video_url, "video_path": video_path, "script": script, "lang": lang}

    except Exception as e:
        logger.error(f"[{lang}] ❌ Crash de production : {e}")
        return {"status": "error", "message": str(e)}

async def main():
    parser = argparse.ArgumentParser(description="Le Pr\xE9sentateur - Leviathan V18.7")
    parser.add_argument("--subject", help="Main subject/prompt")
    parser.add_argument("--langs", default="fr,en,ru", help="Langues")
    parser.add_argument("--platforms", default="youtube", help="Platforms")
    parser.add_argument("--format", default="short", choices=["short", "long"], help="Format")
    parser.add_argument("--style", default="viral", choices=["viral", "hugo"], help="Visual style")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--payload", help="Path to JSON payload for direct rendering")
    args = parser.parse_args()

    config_path = Path("config/settings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if args.format == "long":
        config["rendering"]["resolution"] = [1920, 1080]
        logger.info("📐 Mode LONG-FORM (16:9) Activé.")
    else:
        config["rendering"]["resolution"] = [1080, 1920]

    # ÉTAPE SUPRÊME : TEST PAYLOAD (V25.0)
    if args.payload:
        with open(args.payload, 'r', encoding='utf-8') as f:
            script = json.load(f)
        render_semaphore = asyncio.Semaphore(1)
        platforms_list = args.platforms.split(",") if args.platforms else ["youtube"]
        await process_channel(script.get("lang", "fr"), script.get("seo_title", "Payload Render"), config, render_semaphore, script=script, platforms=platforms_list, style=args.style)
        return

    langs = [l.strip() for l in args.langs.split(",")]
    render_semaphore = asyncio.Semaphore(1)

    subject = args.subject
    if subject.upper() == "AUTO":
        from engine.auto_produce import get_best_trend
        subject, reason = await get_best_trend()
    elif subject.upper() == "AUTO_WEEKLY":
        from engine.auto_produce import get_weekly_top_10
        subject, reason = await get_weekly_top_10()

    cleanup_workspace()

    results = []
    for lang in langs:
        logger.info(f"🚀 DÉBUT PRODUCTION [{lang}] (Style: {args.style})...")
        platforms_list = [p.strip() for p in args.platforms.split(",")]
        res = await process_channel(lang, subject, config, render_semaphore, platforms=platforms_list, style=args.style)
        results.append(res)
        
        if res and res.get("status") == "success":
            src_tts = Path("output/tts_data.json")
            if src_tts.exists():
                dst_tts = Path("output") / f"tts_data_{lang}.json"
                shutil.copy(src_tts, dst_tts)

    success_count = sum(1 for r in results if r and r.get("status") == "success")
    logger.info(f"Done. Success: {success_count}/{len(langs)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Interruption manuelle.")
