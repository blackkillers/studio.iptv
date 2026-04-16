import os
import json
import sys
import argparse
import shutil
import tempfile
from pathlib import Path

# Monkeypatch for PIL.Image.ANTIALIAS (removed in Pillow 10)
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS if hasattr(PIL.Image, 'Resampling') else PIL.Image.LANCZOS

from moviepy.editor import ImageClip, VideoFileClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips

# Paths
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"

def assemble_video_moviepy(args):
    """Assemble final video using MoviePy with support for multiple formats."""
    print(f"[assemble_video_moviepy] Starting assembly... Format: {getattr(args, 'format', '9:16')}", file=sys.stderr)
    
    # Format dimensions
    is_square = getattr(args, "format", "9:16") == "1:1"
    W, H = (1080, 1080) if is_square else (1080, 1920)

    # Load data
    with open(OUTPUT_DIR / "tts_data.json", "r", encoding='utf-8') as f:
        tts_data = json.load(f)
    with open(OUTPUT_DIR / "script_data.json", "r", encoding='utf-8') as f:
        script_data = json.load(f)
        
    audio_path = tts_data.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        print(f"[assemble_video_moviepy] ERROR: Audio not found: {audio_path}", file=sys.stderr)
        return False

    audio = AudioFileClip(audio_path)
    scenes = tts_data.get("scene_timings", [])
    clips = []
    
    _tmp_files = []  # Track temp copies to clean up later

    for i, scene in enumerate(scenes):
        duration = scene.get("duration") or (scene["end"] - scene["start"])
        img_path = scene.get("image_path")
        
        if img_path and img_path.lower().endswith((".mp4", ".mov")) and os.path.exists(img_path):
            try:
                # Copy to unique temp file to avoid concurrent-read corruption
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                tmp.close()
                shutil.copy2(img_path, tmp.name)
                _tmp_files.append(tmp.name)
                clip = VideoFileClip(tmp.name).set_duration(duration)
                clip = clip.resize(height=H).margin(0).on_color(size=(W, H), color=(0,0,0))
            except Exception as ve:
                print(f"[assemble_video_moviepy] ⚠ Video read error scene {i}: {ve} — using black clip", file=sys.stderr)
                from moviepy.editor import ColorClip
                clip = ColorClip(size=(W, H), color=(0,0,0), duration=duration)
        elif img_path and os.path.exists(img_path):
            try:
                clip = ImageClip(img_path).set_duration(duration)
                # Resize and crop to fill
                clip = clip.resize(height=H).set_position(('center', 'center'))
                if clip.w < W: clip = clip.resize(width=W)
                clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=W, height=H)
                # Add subtle zoom
                clip = clip.resize(lambda t: 1 + 0.04 * t/duration)
            except Exception as ie:
                print(f"[assemble_video_moviepy] ⚠ Image read error scene {i} ({img_path}): {ie} — using black clip", file=sys.stderr)
                from moviepy.editor import ColorClip
                clip = ColorClip(size=(W, H), color=(0,0,0), duration=duration)
        else:
            # Fallback V26.5 : Random background from assets/backgrounds
            bg_dir = BASE_DIR / "assets" / "backgrounds"
            try:
                import random
                if bg_dir.exists():
                    images = list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png")) + list(bg_dir.glob("*.jpeg"))
                    if images:
                        chosen = random.choice(images)
                        clip = ImageClip(str(chosen)).set_duration(duration)
                        clip = clip.resize(height=H).set_position(('center', 'center'))
                        if clip.w < W: clip = clip.resize(width=W)
                        clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=W, height=H)
                        clip = clip.resize(lambda t: 1 + 0.04 * t/duration)
                    else:
                        from moviepy.editor import ColorClip
                        clip = ColorClip(size=(W, H), color=(0,0,0), duration=duration)
                else:
                    from moviepy.editor import ColorClip
                    clip = ColorClip(size=(W, H), color=(0,0,0), duration=duration)
            except Exception as e:
                print(f"[assemble_video_moviepy] ⚠ Fallback error: {e}", file=sys.stderr)
                from moviepy.editor import ColorClip
                clip = ColorClip(size=(W, H), color=(0,0,0), duration=duration)
            
        clips.append(clip)

    # --- Add Outro Clip (3s) ---
    outro_path = BASE_DIR / "assets" / "outro.png"
    outro_duration = 0
    if outro_path.exists():
        try:
            from moviepy.editor import ImageClip
            outro_clip = ImageClip(str(outro_path)).set_duration(3)
            outro_clip = outro_clip.resize(height=H).set_position(('center', 'center'))
            if outro_clip.w < W: outro_clip = outro_clip.resize(width=W)
            outro_clip = outro_clip.crop(x_center=outro_clip.w/2, y_center=outro_clip.h/2, width=W, height=H)
            clips.append(outro_clip)
            outro_duration = 3
            print(f"[assemble_video_moviepy] Outro clip added (3s).", file=sys.stderr)
        except Exception as e:
            print(f"[assemble_video_moviepy] Outro Error: {e}", file=sys.stderr)

    final_clip = concatenate_videoclips(clips, method="compose")
    
    # We collect all overlays to compose once (prevents memory issues)
    overlays = [final_clip]
    
    # --- Add Presenter Logo (Watermark) ---
    try:
        # Priority: use the high-res custom logo if it exists in the root-relative path
        brand_path = BASE_DIR / "refonte youtube logo" / "logo youtube" / "logo presentateur tete.png"
        if not brand_path.exists():
            brand_path = BASE_DIR / "assets" / "branding" / "presenter.png"
            
        if brand_path.exists():
            print("[assemble_video_moviepy] Preparing branding...", file=sys.stderr)
            import numpy as np
            from PIL import Image
            b_img = Image.open(str(brand_path)).convert("RGBA")
            pixel_data = np.array(b_img)
            mask = (pixel_data[:, :, 0] > 220) & (pixel_data[:, :, 1] > 220) & (pixel_data[:, :, 2] > 220)
            pixel_data[mask, 3] = 0
            b_img = Image.fromarray(pixel_data)
            
            temp_brand = OUTPUT_DIR / "images" / "temp_presenter.png"
            temp_brand.parent.mkdir(parents=True, exist_ok=True)
            b_img.save(str(temp_brand))

            brand = ImageClip(str(temp_brand)).set_duration(final_clip.duration).resize(width=120)
            brand = brand.set_position((40, 40)).set_opacity(0.8)
            overlays.append(brand)
            print("[assemble_video_moviepy] Branding overlay ready.", file=sys.stderr)
    except Exception as e: 
        print(f"[assemble_video_moviepy] Branding Error: {e}", file=sys.stderr)

    # --- Add Subscribe Logo at the end ---
    try:
        # Pick logo by language / channel
        lang = getattr(args, 'language', 'fr')
        logo_candidates = [
            BASE_DIR / "assets" / "branding" / f"subscribe_{lang}.png",
            BASE_DIR / "assets" / "branding" / "subscribe.png",
        ]
        logo_path = next((p for p in logo_candidates if p.exists()), None)
        
        if logo_path:
            print(f"[assemble_video_moviepy] Preparing CTA logo: {logo_path.name}", file=sys.stderr)
            import numpy as np
            from PIL import Image
            l_img = Image.open(str(logo_path)).convert("RGBA")
            pixel_data = np.array(l_img)
            # Remove near-white backgrounds (threshold 200) — much better than 220
            r, g, b, a = pixel_data[:,:,0], pixel_data[:,:,1], pixel_data[:,:,2], pixel_data[:,:,3]
            near_white = (r > 200) & (g > 200) & (b > 200)
            pixel_data[near_white, 3] = 0
            l_img = Image.fromarray(pixel_data)
            
            temp_logo = OUTPUT_DIR / "images" / "temp_subscribe.png"
            l_img.save(str(temp_logo))

            dur = min(8, final_clip.duration)
            logo = ImageClip(str(temp_logo)).set_duration(dur).set_start(final_clip.duration - dur)
            
            import math
            base_w = int(W * 0.8)
            logo = logo.resize(width=base_w)
            
            def heartbeat(t):
                return 1.0 + 0.05 * math.sin(t * math.pi * 3)
            logo = logo.resize(heartbeat)
            
            def slide_up(t):
                y = H if t < 0 else (H - (H - int(H*0.65)) * min(1.0, t * 1.5))
                return ("center", int(y))
            logo = logo.set_position(slide_up)
            overlays.append(logo)
            print("[assemble_video_moviepy] CTA overlay ready.", file=sys.stderr)
    except Exception as e:
        print(f"[assemble_video_moviepy] CTA Logo Error: {e}", file=sys.stderr)

    # Composite ONCE
    final_comp = CompositeVideoClip(overlays)
    
    # Set audio and ensure it cuts NET before the outro (V26.5 Fix)
    audio_duration = max(0, final_clip.duration - outro_duration)
    final_comp = final_comp.set_audio(audio.set_duration(audio_duration))

    # Background music is handled by add_music.py later.
    
    try:
        output_file = str(OUTPUT_DIR / "videos" / "video_no_subs.mp4")
        print("[assemble_video_moviepy] Starting ultra-stable single-thread encoding...", file=sys.stderr)
        
        # CloudNode Compatibility: Force 1 thread to prevent kernel-level resource exhaustion
        final_comp.write_videofile(
            output_file, 
            fps=30, 
            codec="libx264", 
            audio_codec="aac", 
            ffmpeg_params=["-pix_fmt", "yuv420p", "-preset", "ultrafast"],
            threads=1, 
            bitrate="6000k", 
            logger=None,
            write_logfile=False,
            verbose=False
        )
        print("[assemble_video_moviepy] Encoding finished successfully.", file=sys.stderr)
        return True
    except Exception as e:
        import traceback
        error_msg = f"Assembly Error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        with open(OUTPUT_DIR / "assembly_error.log", "w", encoding="utf-8") as f:
            f.write(error_msg)
        raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blue-screen", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", type=str, default="9:16")
    parser.add_argument("--language", type=str, default="fr")
    args = parser.parse_args()
    assemble_video_moviepy(args)
