#!/usr/bin/env python3
"""
add_subtitles.py — Génère les sous-titres .ASS style TikTok (mots en surbrillance)
Lit tts_data.json, produit un fichier .ass et burn les sous-titres dans la vidéo
"""

import sys
import json
import argparse
import subprocess
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "subtitles"

# Style ASS pour sous-titres TikTok
ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,200,1
Style: Highlight,Arial Rounded MT Bold,72,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def seconds_to_ass(t: float) -> str:
    """Convertit des secondes en format ASS (H:MM:SS.cc)."""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int((t % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass(word_timings: list[dict], output_path: str) -> str:
    """Génère le fichier ASS avec mise en évidence mot par mot."""
    lines = [ASS_HEADER]

    # Groupe les mots en lignes de 4-5 mots max
    GROUP_SIZE = 4
    groups = []
    for i in range(0, len(word_timings), GROUP_SIZE):
        group = word_timings[i:i + GROUP_SIZE]
        if group:
            groups.append(group)

    for group in groups:
        if not group:
            continue
        group_start = group[0]["start"]
        group_end   = group[-1]["end"]
        all_words   = [w["word"] for w in group]

        # Ligne normale : tous les mots en blanc
        normal_text = " ".join(all_words)
        start_str = seconds_to_ass(group_start)
        end_str   = seconds_to_ass(group_end)
        lines.append(
            f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{normal_text}"
        )

        # Surbrillance : chaque mot en jaune/cyan au moment où il est dit
        for i, word_info in enumerate(group):
            ws = seconds_to_ass(word_info["start"])
            we = seconds_to_ass(word_info["end"])
            highlighted = []
            for j, w in enumerate(all_words):
                if j == i:
                    highlighted.append(f"{{\\c&H00FFFF&}}{w}{{\\c&HFFFFFF&}}")
                else:
                    highlighted.append(w)
            text = " ".join(highlighted)
            lines.append(f"Dialogue: 1,{ws},{we},Default,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def generate_scene_ass(scene_timings: list[dict], output_path: str) -> str:
    """
    Fallback ASS generator quand les word_timings ne sont pas disponibles (edge-tts v7+).
    Affiche le texte de chaque scène comme sous-titre pendant sa durée.
    """
    lines = [ASS_HEADER]

    for scene in scene_timings:
        text = scene.get("text", "")
        if not text:
            continue

        start_str = seconds_to_ass(scene["start"])
        end_str   = seconds_to_ass(scene["end"])

        # Coupe en lignes de ~32 chars pour lisibilité
        words = text.split()
        subtitle_lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 <= 32:
                current += ("" if not current else " ") + w
            else:
                if current:
                    subtitle_lines.append(current)
                current = w
        if current:
            subtitle_lines.append(current)

        # Rejoins avec \N (saut de ligne ASS)
        ass_text = r"\N".join(subtitle_lines[:3])
        lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def burn_subtitles(video_input: str, ass_path: str, video_output: str) -> bool:
    """Burn les sous-titres dans la vidéo avec FFmpeg."""
    # Normalise les chemins pour FFmpeg (évite les problèmes Windows)
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_input,
        "-vf", f"ass='{ass_escaped}'",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        video_output
    ]

    print(f"[add_subtitles] Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[add_subtitles] FFmpeg error:\n{result.stderr}", file=sys.stderr)
        return False
    return True


def main(args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.test:
        word_timings = [
            {"word": w, "start": i * 0.3, "end": (i + 1) * 0.3}
            for i, w in enumerate(
                "L'IA révolutionne la création de contenu vidéo en 2025 de manière spectaculaire".split()
            )
        ]
        video_input = str(BASE_DIR / "output" / "videos" / "video_no_subs.mp4")
    else:
        tts_path = BASE_DIR / "output" / "tts_data.json"
        with open(tts_path, "r", encoding="utf-8") as f:
            tts_data = json.load(f)
        word_timings = tts_data.get("word_timings", [])
        video_input  = tts_data.get("video_path_no_subs", str(BASE_DIR / "output" / "videos" / "video_no_subs.mp4"))

    ass_path = str(OUTPUT_DIR / "subtitles.ass")

    if word_timings and not args.dry_run:
        print(f"[add_subtitles] Generating ASS subtitles ({len(word_timings)} words)...", file=sys.stderr)
        generate_ass(word_timings, ass_path)
    else:
        # Fallback : sous-titres par scène (edge-tts v7+ sans word_timings ou dry-run)
        scene_timings = [] if args.test else tts_data.get("scene_timings", [])
        if scene_timings:
            print(f"[add_subtitles] Using scene-based subtitles ({len(scene_timings)} scenes)...", file=sys.stderr)
            generate_scene_ass(scene_timings, ass_path)
        else:
            print(f"[add_subtitles] No timings available, skipping subtitles.", file=sys.stderr)
            generate_ass([], ass_path)

    print(f"[add_subtitles] ASS file: {ass_path}", file=sys.stderr)

    if not args.ass_only and os.path.exists(video_input) and not args.dry_run:
        video_output = str(BASE_DIR / "output" / "videos" / "video_with_subs.mp4")
        print(f"[add_subtitles] Burning subtitles into video...", file=sys.stderr)
        success = burn_subtitles(video_input, ass_path, video_output)
        if success:
            print(f"[add_subtitles] ✓ Video with subtitles: {video_output}", file=sys.stderr)
        else:
            print(f"[add_subtitles] Failed to burn subtitles, using video without subs.", file=sys.stderr)
            video_output = video_input
    else:
        video_output = video_input
        print(f"[add_subtitles] ASS only mode or input video not found.", file=sys.stderr)

    if not args.test:
        tts_data["ass_path"] = ass_path
        tts_data["video_path_with_subs"] = video_output
        with open(tts_path, "w", encoding="utf-8") as f:
            json.dump(tts_data, f, ensure_ascii=False, indent=2)

    print(f"[add_subtitles] Done: {ass_path}", file=sys.stderr)
    print(video_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate TikTok-style subtitles")
    parser.add_argument("--test",     action="store_true", help="Use test data")
    parser.add_argument("--ass-only", action="store_true", help="Only generate ASS file, don't burn")
    parser.add_argument("--dry-run",  action="store_true", help="Skip burn process")
    main(parser.parse_args())
