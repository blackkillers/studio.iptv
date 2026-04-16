import os
import json
import sys
import argparse
from pathlib import Path

# Monkeypatch for PIL.Image.ANTIALIAS
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS if hasattr(PIL.Image, 'Resampling') else PIL.Image.LANCZOS

from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import gc

# Paths
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"

def create_text_clip(text, duration, width=1080, height=600, font_size=90, color=(255, 230, 0), bg_color=(0, 0, 0, 210), radius=30):
    """Draw text using PIL with a premium background."""
    try:
        # Use a high-quality bold font
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except:
        font = ImageFont.load_default()

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Calculate box with extra spacing for impact
    text_bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    
    padding_x, padding_y = 80, 55 # Increased padding to avoid clipping and look premium
    box_w, box_h = text_w + padding_x*2, text_h + padding_y*2
    
    # Draw shadow then box for "premium" readability
    box_x, box_y = (width - box_w) // 2, (height - box_h) // 2
    draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=radius, fill=bg_color) 
    
    # Draw text
    draw.multiline_text(((width - text_w) // 2, (height - text_h) // 2 - 10), 
                         text, font=font, fill=(*color, 255), align="center", spacing=20)
    
    # Convert to uint8 to save memory (float64 would bloat memory 8x)
    return ImageClip(np.array(img, dtype=np.uint8)).set_duration(duration)

def add_subtitles_moviepy(args):
    """Burn subtitles into video using MoviePy and PIL."""
    print("[add_subtitles_moviepy] Starting subtitle burn...", file=sys.stderr)
    
    # Load data
    with open(OUTPUT_DIR / "tts_data.json", "r", encoding='utf-8') as f:
        tts_data = json.load(f)
    
    video_input = str(OUTPUT_DIR / "videos" / "video_no_subs.mp4")
    if not os.path.exists(video_input):
        print(f"[add_subtitles_moviepy] ERROR: Video not found: {video_input}", file=sys.stderr)
        return False

    video = VideoFileClip(video_input)
    # Get duration exactly from video for sync
    vid_duration = video.duration
    
    scene_timings = tts_data.get("scene_timings", [])
    
    subtitle_overlays = []
    
    # Target height for subtitles (bottom 1/3)
    y_pos = int(video.h * 0.75) 
    
    style = getattr(args, "style", "viral").lower()
    
    # Style configs
    if style == "hugo":
        text_color = (255, 255, 255) # White
        bg_color = (255, 0, 85, 255) # Hugo Pink/Red
        radius = 10 # More rectangular
    else:
        text_color = (255, 230, 0) # Yellow
        bg_color = (0, 0, 0, 210) # Dark semi-transparent
        radius = 30

    for scene in scene_timings:
        text = scene.get("text", "")
        if not text or scene["start"] >= vid_duration:
            continue
            
        start = scene["start"]
        end = min(scene["end"], vid_duration)
        duration = end - start
        
        # Split text into lines if too long (approx 15 chars per line for readability at font 90)
        words = text.split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 < 18:
                current += (" " if current else "") + w
            else:
                lines.append(current)
                current = w
        lines.append(current)
        
        full_text = "\n".join(lines[:3]) # Allow up to 3 lines for clarity
        
        # Create a text clip
        txt_clip = create_text_clip(full_text, duration, width=video.w, color=text_color, bg_color=bg_color, radius=radius)
        # Position centered horizontally and at 75% height
        txt_clip = txt_clip.set_start(start).set_position(('center', y_pos))
        subtitle_overlays.append(txt_clip)
        
        # Hugo Mode: Additional keyword highlights if present
        keyword = scene.get("on_screen_term")
        if style == "hugo" and keyword:
            # Huge white text in the upper half
            kw_clip = create_text_clip(keyword.upper(), duration, width=video.w, font_size=140, color=(255, 255, 255), bg_color=(255, 0, 85, 230), radius=5)
            kw_clip = kw_clip.set_start(start).set_position(('center', int(video.h * 0.3)))
            subtitle_overlays.append(kw_clip)
    if args.no_subtitles:
        print("[add_subtitles_moviepy] --no-subtitles set, skipping overlays.", file=sys.stderr)
        subtitle_overlays = []
    
    # Composite
    print(f"[add_subtitles_moviepy] Compositing {len(subtitle_overlays)} overlays...", file=sys.stderr)
    gc.collect() # Pre-composite cleanup
    final_video = CompositeVideoClip([video] + subtitle_overlays)
    
    # Consistent output name for server
    output_file = str(OUTPUT_DIR / "videos" / "video_with_subs.mp4")
    print(f"[add_subtitles_moviepy] Rendering video with subs: {output_file}", file=sys.stderr)
    
    # CRITICAL: pix_fmt="yuv420p" for smartphone compatibility
    final_video.write_videofile(output_file, codec="libx264", audio_codec="aac", fps=24, ffmpeg_params=["-pix_fmt", "yuv420p"])
    
    # Cleanup
    final_video.close()
    video.close()
    for c in subtitle_overlays: c.close()
    gc.collect()
    
    print(f"[add_subtitles_moviepy] ✓ Done: {output_file}", file=sys.stderr)
    
    # Update tts_data.json so subsequent steps (music, social) know where the video is
    tts_data["video_path_with_subs"] = output_file
    with open(OUTPUT_DIR / "tts_data.json", "w", encoding='utf-8') as f:
        json.dump(tts_data, f, ensure_ascii=False, indent=2)
        
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--style", type=str, default="viral")
    parser.add_argument("--no-subtitles", action="store_true", help="Skip adding subtitles to the video")
    args = parser.parse_args()
    add_subtitles_moviepy(args)
