#!/usr/bin/env python3
"""
assemble_video.py — Assemble les images + audio en vidéo MP4 via FFmpeg
Effet Ken Burns (zoom + pan) sur chaque image, format 9:16 (1080x1920)
"""

import sys
import json
import argparse
import subprocess
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
OUTPUT_DIR = BASE_DIR / "output" / "videos"
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920


def build_ffmpeg_command(image_paths: list[str], audio_path: str,
                          scene_timings: list[dict], output_path: str) -> list[str]:
    """
    Construit la commande FFmpeg pour créer la vidéo avec effet Ken Burns.
    Chaque image est affichée pendant la durée de sa scène.
    """
    n = len(image_paths)
    if n == 0:
        raise ValueError("No images provided")

    total_duration = scene_timings[-1]["end"] if scene_timings else 60.0

    cmd = ["ffmpeg", "-y"]

    # --- Inputs images/videos ---
    for img_path in image_paths:
        if img_path.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
            cmd += ["-i", img_path]
        else:
            cmd += ["-loop", "1", "-i", img_path]

    # --- Input audio ---
    cmd += ["-i", audio_path]

    # --- Filter complex : Ken Burns (images) or Scale (videos) + concat ---
    filter_parts = []
    for i, (img_path, scene) in enumerate(zip(image_paths, scene_timings)):
        duration = scene["end"] - scene["start"]
        duration = max(duration, 1.0)
        frames = int(duration * 25)
        
        is_video = img_path.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))

        if is_video:
            # Pour les vidéos, on scale et on crop pour remplir le ratio 9:16, puis on loop si trop court
            # Note: stream_loop n'est pas simple dans filter_complex, on utilise trim + loop filter
            filter_parts.append(
                f"[{i}:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
                f"loop=loop=-1:size={frames}:start=0,trim=duration={duration},setpts=PTS-STARTPTS[v{i}];"
            )
        else:
            # Ken Burns pour les images
            filter_parts.append(
                f"[{i}:v]scale={VIDEO_WIDTH*2}x{VIDEO_HEIGHT*2}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH*2}:{VIDEO_HEIGHT*2},"
                f"zoompan=z='min(zoom+0.001,1.1)':d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps=25,"
                f"setpts=PTS-STARTPTS[v{i}];"
            )

    # Concat toutes les scènes
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")

    filter_complex = "".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", f"{n}:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(total_duration + 0.5),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    return cmd


def main(args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.test:
        from PIL import Image
        test_images = []
        for i in range(5):
            colors = [(180, 30, 30), (30, 30, 180), (30, 180, 30), (180, 30, 180), (30, 180, 180)]
            img = Image.new("RGB", (1080, 1920), color=colors[i])
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 850, 1080, 1070], fill=(0, 0, 0, 128))
            draw.text((100, 900), f"Scène {i+1} - Test Pipeline", fill=(255, 255, 255))
            p = str(BASE_DIR / "output" / "images" / f"test_scene_{i:02d}.png")
            img.save(p)
            test_images.append(p)

        scene_timings = [
            {"index": i, "start": i * 10.0, "end": (i + 1) * 10.0, "text": f"Scène {i+1}"}
            for i in range(5)
        ]
        audio_path = str(BASE_DIR / "output" / "audio" / "voiceover.mp3")
        if not os.path.exists(audio_path):
            print("[assemble_video] No audio found, generate TTS first", file=sys.stderr)
            sys.exit(1)

        image_paths = test_images
    else:
        tts_path = BASE_DIR / "output" / "tts_data.json"
        with open(tts_path, "r", encoding="utf-8") as f:
            tts_data = json.load(f)

        image_paths   = tts_data["image_paths"]
        audio_path    = tts_data["audio_path"]
        scene_timings = tts_data["scene_timings"]

    output_path = str(OUTPUT_DIR / "video_no_subs.mp4")

    # S'assure qu'il y a autant d'images que de scènes
    n = min(len(image_paths), len(scene_timings))
    image_paths   = image_paths[:n]
    scene_timings = scene_timings[:n]

    print(f"[assemble_video] Assembling {n} scenes...", file=sys.stderr)

    if args.dry_run:
        print(f"[assemble_video] DRY RUN: Skipping FFmpeg execution.", file=sys.stderr)
        # Create an empty file just to satisfy exists() checks if needed, 
        # but skip the 'DUMMY' text which confuses FFmpeg later.
        Path(output_path).touch()
    else:
        if args.blue_screen:
            print("[assemble_video] BLACK SCREEN MODE: Forcing black background.", file=sys.stderr)
            # Override image paths with a black background image
            black_img_path = str(BASE_DIR / "output" / "images" / "black_background.png")
            from PIL import Image
            img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color=(0, 0, 0))
            img.save(black_img_path)
            image_paths = [black_img_path] * len(image_paths)

        cmd = build_ffmpeg_command(image_paths, audio_path, scene_timings, output_path)
        print(f"[assemble_video] Running FFmpeg (this may take several minutes)...", file=sys.stderr)
        
        # On ne capture pas la sortie pour voir la progression en temps réel dans GitHub Actions
        result = subprocess.run(cmd)

        if result.returncode != 0:
            print(f"[assemble_video] FFmpeg failed with return code {result.returncode}", file=sys.stderr)
            sys.exit(1)

    print(f"[assemble_video] ✓ Video: {output_path}", file=sys.stderr)

    if not (args.test or args.dry_run):
        tts_data["video_path_no_subs"] = output_path
        with open(tts_path, "w", encoding="utf-8") as f:
            json.dump(tts_data, f, ensure_ascii=False, indent=2)

    print(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble video with Ken Burns effect")
    parser.add_argument("--test", action="store_true", help="Use test data")
    parser.add_argument("--dry-run", action="store_true", help="Skip rendering")
    parser.add_argument("--blue-screen", action="store_true", help="Use solid blue background")
    main(parser.parse_args())
