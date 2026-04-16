#!/usr/bin/env python3
"""
ultra_renderer.py — Le moteur "Ultra" utilisant FFmpeg pur sans MoviePy.
Optimisé pour CloudNode : consommation RAM minimale et vitesse maximale.
"""

import sys
import json
import argparse
import subprocess
import os
import shutil
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = OUTPUT_DIR / "images"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "videos"

def get_video_duration(file_path):
    """Obtient la durée d'un fichier vidéo via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0

def ultra_renderer(args):
    print("[ultra_renderer] Initializing V8 Ultra Engine (FFmpeg Native)...", file=sys.stderr)
    
    script_path = OUTPUT_DIR / "script_data.json"
    tts_path = OUTPUT_DIR / "tts_data.json"
    
    if not tts_path.exists():
        print("[ultra_renderer] ❌ tts_data.json missing!", file=sys.stderr)
        return False

    with open(tts_path, "r", encoding="utf-8") as f:
        tts_data = json.load(f)

    # Durées par scène
    scene_timings = tts_data.get("scene_timings", [])
    if not scene_timings:
        print("[ultra_renderer] ❌ No scene timings found!", file=sys.stderr)
        return False

    voiceover_path = AUDIO_DIR / "voiceover.mp3"
    if not voiceover_path.exists():
        # Maybe absolute path in JSON?
        voiceover_path = Path(tts_data.get("audio_path", ""))
    
    H, W = 1920, 1080 # Portait 9:16
    temp_id = str(uuid.uuid4())[:8]
    temp_dir = OUTPUT_DIR / f"temp_ultra_{temp_id}"
    if temp_dir.exists(): shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # V10.2: Concatenate segments
    concat_file = temp_dir / "list.txt"
    with open(concat_file, "w") as f_list:
        for i, scene in enumerate(scene_timings):
            duration = scene["end"] - scene["start"]
            if duration <= 0: duration = 2.0 # Fallback
            
            # V10.2: SMART ASSET MAPPING
            actual_idx = scene.get("index", i)
            asset_path = scene.get("asset_override")
            
            if not asset_path:
                if actual_idx == -1: # Hook
                    base_name = "scene_00"
                elif actual_idx == -2: # CTA Narratif
                    # Use last generated scene image
                    available_images = sorted(list(ASSETS_DIR.glob("scene_*.png")))
                    base_name = available_images[-1].stem if available_images else "scene_00"
                else:
                    base_name = f"scene_{actual_idx:02d}"
                
                for ext in [".mp4", ".png", ".jpg", ".jpeg"]:
                    if (ASSETS_DIR / f"{base_name}{ext}").exists():
                        asset_path = ASSETS_DIR / f"{base_name}{ext}"
                        break
            
            # V10.2: MANDATORY STRICT IMAGE CHECK (No more silent 'black')
            # V26.5 STABLE : Fallback Visuel (No more black screens)
            if not asset_path or not Path(asset_path).exists():
                bg_dir = BASE_DIR / "assets" / "backgrounds"
                if bg_dir.exists():
                    import random
                    images = list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png")) + list(bg_dir.glob("*.jpeg"))
                    if images:
                        asset_path = random.choice(images)
                        print(f"[ultra_renderer] 🔄 Fallback image locale : {asset_path.name}", file=sys.stderr)
                    else:
                        asset_path = ASSETS_DIR / "scene_00.png" # Last resort
                else:
                    asset_path = ASSETS_DIR / "scene_00.png"

            p_asset = Path(asset_path)

            temp_output = temp_dir / f"segment_{i:03d}.mp4" 
            
            # V10.2: Check if audio slice is valid
            audio_dur = get_video_duration(voiceover_path) # Works for audio too
            has_audio = scene["start"] < audio_dur
            
            # THE MANDATORY V10.2 COMMAND (Video-Only for zero-saccade)
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", "30", "-i", str(p_asset),
                "-t", str(duration),
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p",
                "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", str(temp_output)
            ]
            
            print(f"[V10.2 CMD] Rendering Scene {i}: {' '.join(cmd)}", file=sys.stderr)
            subprocess.run(cmd, check=True, capture_output=True)
            f_list.write(f"file 'segment_{i:03d}.mp4'\n")

        # --- AJOUT OUTRO V26.5 (3s) ---
        outro_path = BASE_DIR / "assets" / "outro.png"
        if outro_path.exists():
            print("[ultra_renderer] 🎬 Adding 3s Outro segment...", file=sys.stderr)
            outro_out = temp_dir / "segment_outro.mp4"
            cmd_outro = [
                "ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", str(outro_path),
                "-t", "3", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", str(outro_out)
            ]
            subprocess.run(cmd_outro, check=True, capture_output=True)
            f_list.write("file 'segment_outro.mp4'\n")
            total_dur_with_outro = (scene_timings[-1]["end"] if scene_timings else 0) + 3
        else:
            total_dur_with_outro = scene_timings[-1]["end"] if scene_timings else 0

    # CONCATENATION OF MP4s
    final_no_branding = temp_dir / "final_no_branding.mp4"
    print("[ultra_renderer] Concatenating V10.2 segments...", file=sys.stderr)
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(final_no_branding)
    ]
    subprocess.run(cmd_concat, check=True, capture_output=True)

    # FINAL MERGE WITH BRANDING (Logo Top-Left + Subscribe CTA 5s)
    output_file = VIDEO_DIR / "video_no_subs.mp4"
    print("[ultra_renderer] Final pass: Adding branding overlays...", file=sys.stderr)
    
    logo_path = BASE_DIR / "assets" / "branding" / "logo.png"
    sub_path = BASE_DIR / "assets" / "branding" / "subscribe.png"
    
    # Get total duration for the 5s CTA logic and Progress Bar
    total_dur = scene_timings[-1]["end"] if scene_timings else 0
    sub_start = max(0, total_dur - 5.0)
    
    style = getattr(args, "style", "viral").lower()
    hugo_pink = "0xFF0055" # HugoDécrypte signature pink/red

    filters = []
    inputs = [str(final_no_branding), str(voiceover_path)]
    
    filter_complex = ""
    last_out = "[0:v]"
    
    # 1. Overlay Logo (Top-Left)
    if logo_path.exists():
        inputs.append(str(logo_path))
        # Scale to 180px width, padding 40px
        filter_complex += f"[{len(inputs)-1}:v]scale=180:-1[logo];"
        filter_complex += f"{last_out}[logo]overlay=40:40[v_logo];"
        last_out = "[v_logo]"
    
    # 2. Progress Bar (Hugo Style)
    if style == "hugo":
        # Draw a pink bar at the very bottom that grows with time
        # Formula for width: W * (t / total_dur)
        bar_h = 12
        filter_complex += (
            f"{last_out}drawbox=x=0:y=H-{bar_h}:w=W*t/{total_dur}:h={bar_h}:"
            f"color={hugo_pink}@1:t=fill[v_bar];"
        )
        last_out = "[v_bar]"

    # 3. Overlay Subscribe (Top-Right, 5s, Pulse Effect)
    if sub_path.exists():
        inputs.append(str(sub_path))
        # V8.8: Dynamic Pulse Zoom (sinusoidal) + Top-Right Positioning
        sub_idx = len(inputs) - 1
        sub_width = 550
        # Zoom formula: base_width * (1 + amplitude * sin(freq*t))
        filter_complex += (
            f"[{sub_idx}:v]scale={sub_width}:-1,"
            f"scale=w='iw*(1+0.07*sin(2*PI*t/1.5))':h=-1:eval=frame[sub_pulse];"
        )
        # Position centered in To-Right zone (x=W-w-50, y=50)
        filter_complex += f"{last_out}[sub_pulse]overlay=W-w-50:50:enable='between(t,{sub_start},{total_dur})'[v_final]"
        last_out = "[v_final]"
    else:
        # Just use last_out as is if no sub_path
        if last_out != "[0:v]":
            filter_complex = filter_complex.rstrip(";") + f";{last_out}null[v_final]"
            last_out = "[v_final]"
        else:
            last_out = "[0:v]"

    if filter_complex:
        cmd_final = ["ffmpeg", "-y"]
        for inp in inputs:
            cmd_final.extend(["-i", inp])
        
        # If no sub_path was added, last_out might be [v_logo]
        output_label = last_out.strip("[]")
        
        cmd_final.extend([
            "-filter_complex", filter_complex.rstrip(";"),
            "-map", f"[{output_label}]", 
            "-map", "1:a", 
            "-t", str(total_dur_with_outro), # Force total duration (Zero audio stutter)
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", str(output_file)
        ])
    else:
        # No assets found, just copy
        cmd_final = ["ffmpeg", "-y", "-i", str(final_no_branding), "-c", "copy", str(output_file)]

    print(f"[ultra_renderer] Executing Branding: {' '.join(cmd_final)}", file=sys.stderr)
    subprocess.run(cmd_final, check=True, capture_output=True)
    
    print(f"[ultra_renderer] ✅ Ultra Render Finished: {output_file}", file=sys.stderr)
    # Cleanup
    # shutil.rmtree(temp_dir)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", type=str, default="9:16")
    parser.add_argument("--style", type=str, default="viral", help="Visual style: viral or hugo")
    parser.add_argument("--dry-run", action="store_true", help="Does nothing but prevents crashes when called from pipeline_run.py")
    main_args = parser.parse_args()
    ultra_renderer(main_args)
