#!/usr/bin/env python3
"""
generate_tts.py — Synthèse vocale via Edge-TTS (Microsoft, 100% gratuit)
Lit script_data.json, génère audio MP3 + fichier de timing pour sous-titres
"""

import sys
import json
import asyncio
import argparse
import os
import subprocess
import edge_tts
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

try:
    import replicate
except ImportError:
    replicate = None

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUTPUT_DIR = BASE_DIR / "output" / "audio"


def sanitize_text(text: str) -> str:
    """Nettoie le texte pour éviter les crashs TTS (Microsoft Azure / Edge-TTS)."""
    if not text: return ""
    # Enlever les caractères spéciaux bizarres mais garder la ponctuation V9.5
    text = re.sub(r'[^\w\s.,!?;:\-…\'"]', '', text)
    # Remplacer les points de suspension multiples par un seul
    text = re.sub(r'\.{4,}', '...', text)
    # Normaliser les espaces
    text = " ".join(text.split())
    return text

async def synthesize_edge(text: str, voice: str, output_path: str, rate: str = "-17%") -> list[dict]:
    """Synthèse via Edge-TTS (Standard)."""
    clean_text = sanitize_text(text)
    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    
    word_timings = []
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_timings.append({
                    "word":  chunk["text"],
                    "start": chunk["offset"] / 10_000_000,
                    "end":   (chunk["offset"] + chunk["duration"]) / 10_000_000,
                })
    return word_timings

async def synthesize_vibe(text: str, output_path: str) -> list[dict]:
    """Synthèse via VibeVoice (Premium - Replicate)."""
    if not replicate:
        raise ImportError("Librairie 'replicate' non installée.")
    
    api_token = os.getenv("REPLICATE_API_TOKEN")
    if not api_token:
        raise ValueError("REPLICATE_API_TOKEN manquant dans le .env")

    print(f"[generate_tts] 🚀 Appel API Replicate (microsoft/vibevoice)...", file=sys.stderr)
    
    client = replicate.Client(api_token=api_token)
    
    # On utilise le modèle microsoft/vibevoice avec la version stable
    model_version = "microsoft/vibevoice:624421f6fdd4122d0b3ff391ff3449f09db9ad4927167110a4c4b104fa37f728" 
    
    try:
        # Note: L'appel synchrone dans un thread pour ne pas bloquer l'event loop
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, lambda: client.run(
            model_version,
            input={
                "script": text,
                "scale": 1.3
            }
        ))
        
        # L'output Replicate est souvent une URL vers le fichier audio
        audio_url = output if isinstance(output, str) else output[0]
        
        print(f"[generate_tts] 🔽 Téléchargement de l'audio VibeVoice...", file=sys.stderr)
        resp = requests.get(audio_url)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
        else:
            raise Exception(f"Echec du téléchargement audio: {resp.status_code}")
            
    except Exception as e:
        print(f"[generate_tts] ❌ Erreur Replicate: {e}", file=sys.stderr)
        raise e

    # Timing fallback (VibeVoice ne donne pas encore les word boundaries par défaut via API)
    return []


def get_audio_duration(audio_path: str) -> float:
    """Mesure la durée réelle du fichier audio via ffprobe ou moviepy."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", audio_path],
            capture_output=True, text=True
        )
        info = json.loads(result.stdout)
        for stream in info.get("streams", []):
            if "duration" in stream:
                return float(stream["duration"])
    except Exception:
        pass

    try:
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(audio_path)
        dur = clip.duration
        clip.close()
        return dur
    except Exception:
        pass

    return 60.0  # fallback


async def main_async(args: argparse.Namespace) -> None:
    # Best voices per language — Multilingual Neural = most natural/human
    VOICE_MAP = {
        "fr": "fr-FR-VivienneMultilingualNeural",  # Best French — warm, natural
        "en": "en-US-EmmaMultilingualNeural",       # Best English — smooth, human
        "ru": "ru-RU-SvetlanaNeural",               # Best Russian
    }
    if args.voice:
        voice = args.voice
    else:
        voice = VOICE_MAP.get(args.language, os.getenv("TTS_VOICE", "fr-FR-VivienneMultilingualNeural"))

    if args.test or args.dry_run:
        script_data = {
            "script": {
                "hook": "L'IA va remplacer les studios vidéo en 2025 !",
                "scenes": [
                    {"text": "En 2025, l'intelligence artificielle révolutionne la création de contenu.", "image_prompt": "AI robot creating videos"},
                    {"text": "Des vidéos professionnelles peuvent être générées en quelques minutes seulement.", "image_prompt": "fast video generation"},
                    {"text": "TikTok, Instagram et YouTube voient exploser les contenus générés par IA.", "image_prompt": "social media logos"},
                    {"text": "Les créateurs humains s'adaptent en utilisant ces outils pour gagner du temps.", "image_prompt": "humans using AI"},
                    {"text": "La question n'est plus de savoir si l'IA va changer le monde du contenu, mais quand.", "image_prompt": "future of content"},
                ],
                "cta": "Suivez-nous pour plus d'actus IA !",
            }
        }
    else:
        input_path = BASE_DIR / "output" / "script_data.json"
        with open(input_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)

    script = script_data["script"]

    # Construit le texte complet avec déduplication intelligente V14.5
    hook = script.get("hook", script.get("accroche", script.get("intro", ""))).strip()
    scenes = script.get("scenes", script.get("scene", []))
    
    # --- LOGIQUE ANTI-DOUBLON ---
    if hook and scenes:
        first_scene = scenes[0].get("text", "").strip()
        # Si la scène commence par le hook (insensible à la casse/ponctuation)
        clean_hook = re.sub(r'[^\w\s]', '', hook).lower()
        clean_first = re.sub(r'[^\w\s]', '', first_scene[:len(hook)+20]).lower()
        
        if clean_hook in clean_first:
            print(f"[generate_tts] 🛡️ Doublon détecté entre Hook et Scène 1. Nettoyage...", file=sys.stderr)
            # On retire le doublon dans la scène pour ne garder que le hook pur
            import difflib
            s = difflib.SequenceMatcher(None, hook.lower(), first_scene.lower()[:len(hook)+20])
            match = s.find_longest_match(0, len(hook), 0, len(hook)+20)
            if match.size > 10:
                 # On retire la partie correspondante au début de la scène
                 scenes[0]["text"] = first_scene[match.a + match.size:].strip()
                 if scenes[0]["text"].startswith(('.', ',', '!', '?', ':')):
                     scenes[0]["text"] = scenes[0]["text"][1:].strip()

    full_text = hook + ". " if hook else ""
    
    for scene in scenes:
        text = scene.get("text", scene.get("narration", ""))
        full_text += text + " "
    
    cta = script.get("cta", script.get("outro", ""))
    full_text += cta

    print(f"[generate_tts] Voice: {voice}", file=sys.stderr)
    print(f"[generate_tts] Text length: {len(full_text)} chars", file=sys.stderr)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = str(OUTPUT_DIR / "voiceover.mp3")

    if args.dry_run:
        print("[generate_tts] DRY RUN: Generating 1s silent MP3...", file=sys.stderr)
        try:
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", 
                "-t", "1", "-q:a", "9", "-acodec", "libmp3lame", audio_path
            ], capture_output=True, check=True)
        except Exception as e:
            print(f"[generate_tts] Warning: could not generate silent MP3: {e}", file=sys.stderr)
            with open(audio_path, "wb") as f:
                f.write(b"DUMMY AUDIO")
        
        word_timings = []
        total_duration = 1.0
    if not args.dry_run:
        engine = getattr(args, "engine", "edge")
        if engine == "vibe" or voice == "vibe":
            print("[generate_tts] Using PREMIUM engine: VibeVoice", file=sys.stderr)
            word_timings = await synthesize_vibe(full_text, audio_path)
        else:
            word_timings = await synthesize_edge(full_text, voice, audio_path, rate=args.voice_rate)
            
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 100:
             print(f"[generate_tts] ERROR: TTS failed to generate audio.", file=sys.stderr)
             sys.exit(1)

    # ── Durée réelle de l'audio ──────────────────────────────────────────────
    if not args.dry_run:
        if word_timings:
            total_duration = word_timings[-1]["end"]
        else:
            total_duration = get_audio_duration(audio_path)
            print(f"[generate_tts] WordBoundary events not available, "
                  f"using audio duration: {total_duration:.2f}s", file=sys.stderr)

    # ── Calcule les timings par scène ────────────────────────────────────────
    scene_timings = []
    duration_per_char = (total_duration / len(full_text)) if len(full_text) > 0 else 0
    
    # Hook
    current_time = 0.0
    if hook:
        hook_len = len(hook) + 2
        scene_timings.append({
            "index": -1,
            "start": 0.0,
            "end": round(hook_len * duration_per_char, 3),
            "text": hook
        })
        current_time = scene_timings[-1]["end"]

    for i, s in enumerate(scenes):
        txt = s.get("text", s.get("narration", ""))
        d = (len(txt) + 1) * duration_per_char
        scene_timings.append({
            "index": i,
            "start": round(current_time, 3),
            "end": round(current_time + d, 3),
            "text": txt,
            "image_prompt": s.get("image_prompt", s.get("visuel", "")),
        })
        current_time += d

    if cta:
        cta_len = len(cta)
        scene_timings.append({
            "index": -2,
            "start": round(current_time, 3),
            "end": round(current_time + cta_len * duration_per_char, 3),
            "text": cta,
            "image_prompt": "",
        })

    output_data = {
        "audio_path": audio_path,
        "full_text": full_text,
        "word_timings": word_timings,
        "scene_timings": scene_timings,
        "total_duration": total_duration,
        "language": getattr(args, 'language', 'fr'),
        "script": script,
        "image_prompts": [s.get("image_prompt", "") for s in script["scenes"]],
        "image_paths": []
    }

    output_path_json = BASE_DIR / "output" / "tts_data.json"
    with open(output_path_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"[generate_tts] Saved to {output_path_json}", file=sys.stderr)

    if args.test or args.dry_run:
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
    else:
        print(output_path_json)


def main():
    parser = argparse.ArgumentParser(description="TTS with Edge-TTS")
    parser.add_argument("--test", action="store_true", help="Use test data")
    parser.add_argument("--dry-run", action="store_true", help="Dummy audio and test data")
    parser.add_argument("--voice", default="", help="TTS voice name")
    parser.add_argument("--voice-rate", default="-5%", help="Speech rate e.g. -5%, +10%")
    parser.add_argument("--language", default="fr", help="Language code (fr, en)")
    parser.add_argument("--engine", default="edge", choices=["edge", "vibe"], help="TTS Engine to use")
    parser.add_argument("--long", action="store_true", help="Generate longer video data")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
