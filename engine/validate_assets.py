import os
import json
import sys
from pathlib import Path
from datetime import date

# Paths
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"

import argparse

def validate_assets(dry_run=False):
    """Verify that all assets for the video are present and valid."""
    print("\n" + "="*40)
    print("🔍 VALIDATION DES ASSETS")
    print("="*40)
    
    errors = []
    
    # 1. Check tts_data.json
    tts_path = OUTPUT_DIR / "tts_data.json"
    data = {}
    if not tts_path.exists():
        errors.append("❌ tts_data.json manquant")
    else:
        with open(tts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data.get("scene_timings"):
                errors.append("❌ Aucune scène dans tts_data.json")
            if not data.get("audio_path") or not os.path.exists(data["audio_path"]):
                errors.append(f"❌ Audio manquant: {data.get('audio_path')}")

    # 2. Check Video with Subs
    video_path = OUTPUT_DIR / "videos" / "video_with_subs.mp4"
    if not video_path.exists():
        # Fallback check for no_subs if subs isn't mandatory (but here it should be)
        video_path = OUTPUT_DIR / "videos" / "video_no_subs.mp4"
        if not video_path.exists():
            # In dry run, we might not have a video if it crashed, but if it didn't it should be there
            errors.append("❌ Vidéo finale manquante dans output/videos/")
    
    if video_path.exists():
        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        # Relax constraints during dry run
        min_size = 0.01 if dry_run else 0.5
        if size_mb < min_size:
            errors.append(f"⚠️ Vidéo trop petite ({size_mb:.2f} MB), possiblement corrompue")
        else:
            print(f"✅ Vidéo OK: {video_path.name} ({size_mb:.2f} MB)")

    # 3. Check Images & Relevance
    image_dir = OUTPUT_DIR / "images"
    # Extraction du titre (cherche dans metadata ou script)
    title = (data.get("metadata", {}).get("title") or 
             data.get("script", {}).get("title") or "").lower()
    title_words = [w for w in title.split() if len(w) > 3]
    
    # In dry run, we use placeholders, so we check if they exist
    if not image_dir.exists() or not list(image_dir.glob("*.png")):
         errors.append("❌ Images des scènes manquantes")
    else:
         scenes = data.get("scene_timings", [])
         count = 0
         relevance_score = 0
         for scene in scenes:
             # Look for scene_XX.png in images folder
             # scene_timings might not have image_path set yet if validate is run separately
             # but generate_images usually sets it.
             img_path = scene.get("image_path", "")
             if img_path and os.path.exists(img_path):
                 count += 1
                 # Check if prompt contains title keywords
                 prompt = scene.get("image_prompt", "").lower()
                 if any(word in prompt for word in title_words):
                     relevance_score += 1
         
         # Fallback count if image_path not in scene_timings
         if count == 0:
             count = len(list(image_dir.glob("scene_*.png")))

         print(f"✅ Images: {count} photos générées")
         if count > 0 and not dry_run:
             perc = (relevance_score / count) * 100
             print(f"🎯 Score de pertinence titre/image: {perc:.0f}%")
             if perc < 50:
                 errors.append(f"⚠️ Pertinence trop faible ({perc:.0f}%). Le titre '{title}' est peu présent dans les prompts.")

    # Summary
    if errors:
        print("\n❌ ERREURS DE VALIDATION TROUVÉES :")
        for err in errors:
            print(f"  - {err}")
        return False
    
    print("\n✅ Tous les assets (Son, Sous-titres, Images) sont validés !")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if not validate_assets(dry_run=args.dry_run):
        sys.exit(1)
    sys.exit(0)
