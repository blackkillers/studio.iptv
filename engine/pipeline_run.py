#!/usr/bin/env python3
"""
pipeline_run.py — Lanceur principal du pipeline
Exécute toutes les étapes dans l'ordre avec logging et gestion d'erreurs
"""

import sys
import json
import argparse
import subprocess
import os
import io
import io
import asyncio
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any, List, Dict, Tuple
from dotenv import load_dotenv

# Telegram Notification Integration
try:
    from utils.telegram_notifier import send_telegram_alert
except ImportError:
    send_telegram_alert = None

def notify_sync(message: str):
    """Synchronous wrapper for Telegram alerts."""
    if send_telegram_alert:
        try:
            asyncio.run(send_telegram_alert(message))
        except Exception as e:
            print(f"  [Telegram] Notification error: {e}")

# Force UTF-8 output on Windows to support emoji
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

SCRIPTS_DIR = Path(__file__).resolve().parent
STEPS = [
    ("📰 Scraping news",          "fetch_news.py"),
    ("🧠 Génération script",      "generate_script.py"),
    ("🔊 Synthèse vocale",        "generate_tts.py"),
    ("🖼️  Génération images",     "generate_images.py"),
    ("🎬 Assemblage ULTRA (v8)",  "ultra_renderer.py"), # NEW V8 Ultra Engine
    ("📝 Sous-titres",            "add_subtitles_moviepy.py"),
    ("🔍 Validation assets",      "validate_assets.py"),
    ("🎵 Musique de fond",        "add_music.py"),
    ("📤 Publication réseaux",    "post_social.py"),
]

LOG_DIR = BASE_DIR / "output"


def run_step(script: str, args: argparse.Namespace, extra_args: Optional[List[str]] = None,
              dry_run: bool = False) -> Tuple[bool, str]:
    """Exécute un script Python et affiche sa sortie en temps réel."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script)]
    if extra_args:
        cmd += extra_args
    if dry_run:
        if script == "post_social.py":
            cmd += ["--test"]
        else:
            cmd += ["--dry-run"]
    
    if script == "assemble_video.py" and getattr(args, 'black_screen', False):
        cmd += ["--blue-screen"] # We keep the internal flag for now for compatibility with the old script if called
    
    if script == "add_music.py" and getattr(args, 'music_volume', None) is not None:
        cmd += ["--music-volume", str(args.music_volume)]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # On merge stderr dans stdout pour simplifier le stream
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(BASE_DIR),
        bufsize=1 # Line buffered
    )

    full_output = []
    # Lecture en temps réel
    std_out = process.stdout
    if std_out is not None:
        for line in std_out:
            line_clean = line.strip()
            if line_clean:
                print(f"    {line_clean}", flush=True)
                full_output.append(line_clean)
        try:
            std_out.close()
        except: pass

    return_code = process.wait()
    return return_code == 0, "\n".join(full_output)


def main(args: argparse.Namespace) -> None:
    start_time = datetime.now()
    log: Dict[str, Any] = {
        "date": str(date.today()),
        "start": start_time.isoformat(),
        "steps": [],
        "success": False,
        "dry_run": args.dry_run,
    }
    
    # RADICAL CLEANUP: Purge EVERYTHING in the images dir
    if not args.dry_run:
        img_dir = BASE_DIR / "output" / "images"
        if img_dir.exists():
            print(f"🧹 PURGE RADICALE du cache image: {img_dir}...", flush=True)
            import shutil
            for filename in os.listdir(img_dir):
                file_path = os.path.join(img_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'Failed to delete {file_path}. Reason: {e}')

    # Nettoyage profond des dossiers de sortie et des JSONs pour éviter les mélanges
    import shutil
    for folder in ["audio", "images", "videos"]:
        p = BASE_DIR / "output" / folder
        if p.exists():
            try:
                for f in p.iterdir():
                    if f.is_file() and not any(char.isdigit() for char in f.stem): 
                         f.unlink()
            except Exception as e: print(f"  ⚠ Cleanup error {folder}: {e}")
    
    for jf in ["news_data.json", "script_data.json", "tts_data.json"]:
        jp = BASE_DIR / "output" / jf
        if jp.exists():
            try: jp.unlink()
            except: pass

    print(f"\n{'='*60}", flush=True)
    print(f"  🎬 AI NEWS VIDEO PIPELINE — {date.today()}", flush=True)
    print(f"  Mode: {'DRY RUN (pas de posting)' if args.dry_run else 'PRODUCTION'}", flush=True)
    print(f"{'='*60}\n", flush=True)

    lang_label = args.language.upper() if args.language else "FR"
    subj_label = args.title[:30] if args.title else "Auto RSS"
    notify_sync(f"🚀 <b>DEBUT PIPELINE</b>\nSujet: <i>{subj_label}</i>\nLangue: <b>{lang_label}</b>")

    for label, script in STEPS:
        print(f"{'─'*50}", flush=True)
        print(f"  {label}", flush=True)
        print(f"  → {script}", flush=True)
        
        notify_sync(f"⏳ <b>ÉTAPE :</b> {label}...")

        extra = []
        if script == "fetch_news.py":
            if args.title:
                extra = ["--query", args.title]
            if args.category:
                extra += ["--category", args.category]
        elif script == "post_social.py":
            if args.platforms:
                extra = ["--platforms", args.platforms]
            if args.publish_at:
                extra += ["--publish-at", args.publish_at]
        elif script == "generate_script.py":
            if args.title:
                extra = ["--custom-prompt", args.title]
            elif args.custom_prompt:
                extra = ["--custom-prompt", args.custom_prompt]
            
            if args.theme:
                extra += ["--theme", args.theme]
            if args.language:
                extra += ["--language", args.language]
            if getattr(args, 'long', False):
                extra += ["--long"]
                
        elif script == "generate_tts.py":
            if args.voice:
                extra = ["--voice", args.voice]
            if args.language:
                extra += ["--language", args.language]
            if getattr(args, 'voice_rate', None):
                extra += [f"--voice-rate={args.voice_rate}"]
            if getattr(args, 'tts_engine', None):
                extra += ["--engine", args.tts_engine]
                
            if getattr(args, 'long', False):
                extra += ["--long"]
        
        elif script == "assemble_video_moviepy.py":
            if getattr(args, "format", None):
                extra += ["--format", args.format]

        elif script == "generate_images.py":
            if getattr(args, "selected_images", None):
                extra += ["--selected-images", args.selected_images]

        elif script == "add_music.py":
            if getattr(args, "bgm", None):
                extra += ["--bgm", args.bgm]
        elif script == "add_subtitles_moviepy.py":
            if getattr(args, "no_text", False):
                extra += ["--no-subtitles"]

        step_start = datetime.now()
        success, output = run_step(script, args, extra_args=extra, dry_run=args.dry_run)
        step_duration = (datetime.now() - step_start).total_seconds()

        # Explicitly handle output with cast and explicit slice to satisfy linter
        from typing import cast
        output_str: str = str(output) if output else ""
        truncated_output: str = cast(str, output_str)[0:500]
        
        step_log: Dict[str, Any] = {
            "script":   script,
            "success":  success,
            "duration": step_duration,
            "output":   truncated_output,
        }
        log["steps"].append(step_log)

        if not success and script not in ("add_music.py", "post_social.py"):
            print(f"\n  ❌ Étape critique échouée: {script}", flush=True)
            print(f"  Pipeline arrêté.", flush=True)
            notify_sync(f"❌ <b>ERREUR CRITIQUE</b>\nScript: <code>{script}</code>\nÉtape: {label}")
            break
        elif success and script == "post_social.py":
            try:
                # Tentative d'extraction de l'ID YouTube si dispo
                res_data = json.loads(output)
                yt_id = res_data.get("youtube", {}).get("id")
                if yt_id:
                    notify_sync(f"✅ <b>PUBLIÉ !</b>\nLien: https://youtube.com/shorts/{yt_id}")
                else:
                    notify_sync(f"✅ <b>PUBLICATION TERMINÉE</b>\n(Vérifiez le Studio)")
            except:
                notify_sync(f"✅ <b>PUBLICATION TERMINÉE</b>")
    else:
        log["success"] = True

    duration = (datetime.now() - start_time).total_seconds()
    log["end"]      = datetime.now().isoformat()
    log["duration"] = duration

    print(f"\n{'='*60}", flush=True)
    if log["success"]:
        print(f"  ✅ Pipeline terminé en {duration:.0f}s", flush=True)
        notify_sync(f"🏁 <b>FIN PIPELINE</b>\nDurée: {duration:.0f}s\nStatut: Succès ✅")
    else:
        print(f"  ❌ Pipeline échoué après {duration:.0f}s", flush=True)
        notify_sync(f"🏁 <b>FIN PIPELINE</b>\nDurée: {duration:.0f}s\nStatut: Échec ❌")
    print(f"{'='*60}\n", flush=True)

    # Sauvegarde du log
    log_path = LOG_DIR / f"pipeline_log_{date.today()}.json"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"  📋 Log: {log_path}", flush=True)

    # Backup de la vidéo si succès
    if log["success"]:
        final_video = LOG_DIR / "videos" / "video_final.mp4"
        if not final_video.exists():
            final_video = LOG_DIR / "videos" / "video_with_subs.mp4"
        
        if final_video.exists():
            category_slug = args.category if args.category else "daily"
            backup_name = f"video_{category_slug}_{date.today()}.mp4"
            backup_path = LOG_DIR / "videos" / backup_name
            import shutil
            shutil.copy(str(final_video), str(backup_path))
            print(f"  💾 Vidéo sauvegardée sous : {backup_path}", flush=True)

    sys.exit(0 if log["success"] else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full video pipeline")
    parser.add_argument("--dry-run",  action="store_true", help="Generate video but don't post")
    parser.add_argument("--category", default="",            help="Override news category")
    parser.add_argument("--custom-prompt", default="", help="Custom prompt for AI script generation")
    parser.add_argument("--black-screen", action="store_true", help="Use solid black background for video")
    parser.add_argument("--music-volume", type=float, help="Volume of background music (0.0 to 1.0)")
    parser.add_argument("--long", action="store_true", help="Generate 3-5 minute video")
    parser.add_argument("--voice", default="", help="TTS voice name")
    parser.add_argument("--voice-rate", default="-5%", help="TTS speech rate (e.g. -5%%, +10%%)")
    parser.add_argument("--tts-engine", default="edge", choices=["edge", "vibe"], help="TTS engine (standard: edge, premium: vibe)")
    parser.add_argument("--language", default="fr", help="Target language")
    parser.add_argument("--theme", default="actualités", help="Video theme/tone")
    parser.add_argument("--title", default="", help="Custom title/topic override")
    parser.add_argument("--selected-images", default="", help="Comma separated list of pre-selected image paths")
    parser.add_argument("--platforms", default="", help="Comma separated list of platforms")
    parser.add_argument("--format", default="9:16", choices=["9:16", "1:1"], help="Video format")
    parser.add_argument("--bgm", default="", help="Background music flag parameter")
    parser.add_argument("--no-text", action="store_true", help="Skip adding subtitles to the video")
    parser.add_argument("--publish-at", default=None, help="ISO 8601 timestamp for scheduled publish")
    main(parser.parse_args())
