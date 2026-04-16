#!/usr/bin/env python3
"""
add_music.py — Télécharge et mixe une musique de fond depuis Pixabay Music API
Lit tts_data.json, produit la vidéo finale avec musique
"""

import sys
import json
import argparse
import subprocess
import os
import random
import requests
import asyncio
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

ASSETS_DIR = BASE_DIR / "assets" / "music"
OUTPUT_DIR = BASE_DIR / "output" / "videos"

# Catégories musicales adaptées à des news
MUSIC_MOODS = ["inspiring", "corporate", "upbeat", "electronic", "ambient", "dramatic", "tense"]



def search_pixabay_music(query: str) -> str | None:
    """Recherche sur Pixabay Music"""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key: return None
    
    # Mood mapping for professional quality
    if any(k in query.lower() for k in ["doux", "sérieux", "pixabay"]):
        query = "corporate calm professional ambient"
        
    print(f"[add_music] Pixabay Search: {query}", file=sys.stderr)
    url = f"https://pixabay.com/api/music/?key={api_key}&q={query.replace(' ', '+')}&per_page=10"
    try:
        import requests
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            if hits:
                hit = random.choice(hits)
                dl_url = hit.get("preview")
                if dl_url:
                    dest = ASSETS_DIR / f"pix_{random.randint(100,999)}.mp3"
                    resp = requests.get(dl_url, timeout=30)
                    if resp.status_code == 200:
                        with open(dest, "wb") as f: f.write(resp.content)
                        return str(dest)
    except Exception as e: 
        print(f"[add_music] Pixabay Music Error: {e}", file=sys.stderr)
    return None

def get_local_music(mood: str = "") -> str | None:
    """Sélectionne une musique depuis le dossier C:\\StudioAutomation\\assets\\music"""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    all_music = list(ASSETS_DIR.glob("*.mp3")) + list(ASSETS_DIR.glob("*.wav"))
    
    if not all_music:
        print(f"[add_music] No music found in {ASSETS_DIR}", file=sys.stderr)
        return None
        
    # Essayer de trouver une musique qui correspond au "mood"
    if mood:
        mood_matches = [m for m in all_music if mood.lower() in m.name.lower()]
        if mood_matches:
            chosen = random.choice(mood_matches)
            print(f"[add_music] Found music matching mood '{mood}': {chosen.name}", file=sys.stderr)
            return str(chosen)
            
    # Sinon, on prend au hasard
    chosen = random.choice(all_music)
    print(f"[add_music] Randomly selected music: {chosen.name}", file=sys.stderr)
    return str(chosen)


def mix_music(video_input: str, music_path: str, video_output: str,
               music_volume: float = None) -> bool:
    """
    Mixe la musique de fond avec la vidéo.
    music_volume=0.12 → musique à ~18dB en dessous de la voix
    """
    if music_volume is None:
        music_volume = float(os.getenv("MUSIC_VOLUME", "0.12"))
    cmd = [
        "ffmpeg", "-y",
        "-i", video_input,
        "-stream_loop", "-1",
        "-i", music_path,
        "-filter_complex",
        (
            f"[1:a]volume={music_volume},afade=t=in:st=0:d=1,"
            f"afade=t=out:d=2[music];"
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        ),
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        video_output,
    ]

    print(f"[add_music] Mixing music into video...", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[add_music] FFmpeg error:\n{result.stderr[-1500:]}", file=sys.stderr)
        return False
    return True


def main(args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("PIXABAY_API_KEY", "")

    if args.test:
        video_input = str(BASE_DIR / "output" / "videos" / "video_with_subs.mp4")
        if not os.path.exists(video_input):
            video_input = str(BASE_DIR / "output" / "videos" / "video_no_subs.mp4")
        mood = "inspiring"
    else:
        tts_path = BASE_DIR / "output" / "tts_data.json"
        with open(tts_path, "r", encoding="utf-8") as f:
            tts_data = json.load(f)

        video_input = tts_data.get("video_path_with_subs") or tts_data.get("video_path_no_subs")
        category    = tts_data.get("script", {}).get("category", "world")
        mood_map = {
            "ai":         "electronic",
            "technology": "upbeat",
            "crypto":     "electronic",
            "business":   "corporate",
            "world":      "inspiring",
            "war":        "dramatic",
            "israel":     "tense",
            "iran":       "tense"
        }
        
        # V14.0 High Performance Overlay
        title_lower = tts_data.get("news", {}).get("title", "").lower()
        war_keywords = ["guerre", "war", "conflit", "missile", "iran", "israël", "israel", "milit"]
        if any(wk in title_lower for wk in war_keywords):
            mood = "dramatic"
        else:
            mood = mood_map.get(category, "ambient")

    if not video_input or not os.path.exists(video_input):
        print(f"[add_music] Input video not found: {video_input}", file=sys.stderr)
        sys.exit(1)

    bgm_pref = getattr(args, "bgm", "").strip()
    music_path = None

    # Support des URL externes (YouTube, etc)
    if bgm_pref.startswith("http"):
        print(f"[add_music] ⬇️ Téléchargement URL externe: {bgm_pref}", file=sys.stderr)
        try:
            dest_base = str(ASSETS_DIR / f"ext_bgm_{random.randint(1000,9999)}")
            if "youtu" in bgm_pref:
                subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3", "-o", f"{dest_base}.%(ext)s", bgm_pref], check=True)
                music_path = f"{dest_base}.mp3"
            else:
                r = requests.get(bgm_pref, timeout=30)
                if r.status_code == 200:
                    music_path = f"{dest_base}.mp3"
                    with open(music_path, "wb") as f: f.write(r.content)
        except Exception as e:
            print(f"[add_music] ❌ Erreur téléchargement: {e}. Fallback sur piste locale.", file=sys.stderr)
            bgm_pref = "" # Clear failed URL to allow local fallback logic to proceed

    # Logique de contexte IA
    if not music_path and not bgm_pref and tts_data:
        print("[add_music] 🤖 Analyse ambiance contextuelle par l'IA...", file=sys.stderr)
        script_text = tts_data.get("script", {}).get("text", "")
        if script_text:
            try:
                from engine.agents.base_agent import BaseAgent
                agent = BaseAgent()
                prompt = f"Analyse le script suivant et définis l'ambiance musicale (choisis UNIQUEMENT un mot parmi : news, chill, gaming, dramatic, tense):\n{script_text[:1000]}"
                mood_result = asyncio.run(agent.call_llm("Tu es un expert musical.", prompt)).strip().lower()
                for valid in ["news", "chill", "gaming", "dramatic", "tense"]:
                    if valid in mood_result:
                        bgm_pref = valid
                        break
                print(f"[add_music] 🎵 Ambiance IA choisie : {bgm_pref}", file=sys.stderr)
            except Exception as e:
                print(f"[add_music] ⚠ IA Error: {e}", file=sys.stderr)
                bgm_pref = mood
        else:
            bgm_pref = mood

    search_mood = bgm_pref if bgm_pref else mood
    
    # V8.6: Precise theme mapping
    theme_mapping = {
        "actualités": "news.mp3",
        "detente": "relax.mp3",
        "gaming": "gaming.mp3",
        "vlog": "vlog.mp3",
        "news": "news.mp3",
        "chill": "relax.mp3"
    }
    
    if not music_path and search_mood.lower() in theme_mapping:
        target = theme_mapping[search_mood.lower()]
        if (ASSETS_DIR / target).exists():
            music_path = str(ASSETS_DIR / target)
            print(f"[add_music] ✓ Using themed music: {target}", file=sys.stderr)

    # Contextual sub-folder fallback (assets/bgm/<categorie>)
    if not music_path and search_mood in ["news", "chill", "gaming"]:
        cat_dir = BASE_DIR / "assets" / "bgm" / search_mood
        if cat_dir.exists():
            tracks = list(cat_dir.glob("*.mp3"))
            if tracks:
                music_path = str(random.choice(tracks))
                print(f"[add_music] ✓ Picked contextual BGM from: {cat_dir.name}", file=sys.stderr)

    # Prioritize Pixabay search for ANY mood if API key is present and not themed
    if not music_path and api_key and search_mood and not search_mood.startswith("http"):
        print(f"[add_music] Attempting Pixabay search for variety: {search_mood}", file=sys.stderr)
        music_path = search_pixabay_music(search_mood)
        
    # Fallback to local only if Pixabay failed or no key
    if not music_path:
        print(f"[add_music] Falling back to local music for mood: {search_mood}", file=sys.stderr)
        music_path = get_local_music(mood=search_mood)
    
    if not music_path or args.dry_run:
        if args.dry_run:
            print("[add_music] DRY RUN: Skipping music mix.", file=sys.stderr)
        else:
            print("[add_music] Skipping music mix (no music file found)", file=sys.stderr)
        final_video = video_input
    else:
        final_video = str(OUTPUT_DIR / "video_final.mp4")
        success = mix_music(video_input, music_path, final_video, music_volume=args.music_volume)
        if not success:
            print("[add_music] Mix failed, using video without music", file=sys.stderr)
            final_video = video_input
        else:
            print(f"[add_music] ✓ Final video: {final_video}", file=sys.stderr)

    if not args.test and tts_data:
        tts_data["final_video_path"] = final_video
        with open(tts_path, "w", encoding="utf-8") as f:
            json.dump(tts_data, f, ensure_ascii=False, indent=2)

    print(final_video)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add background music to video")
    parser.add_argument("--test",     action="store_true", help="Use test data")
    parser.add_argument("--ass-only", action="store_true", help="Only generate ASS file, don't burn")
    parser.add_argument("--dry-run",  action="store_true", help="Skip burn process")
    parser.add_argument("--music-volume", type=float, help="Volume of background music (0.0 to 1.0)")
    parser.add_argument("--bgm", type=str, default="", help="Preferred mood/genre")
    main(parser.parse_args())
