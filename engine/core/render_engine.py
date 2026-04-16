import asyncio
import os
import logging
import subprocess
from pathlib import Path
from typing import List
from PIL import Image, ImageOps # Added for pre-FFmpeg crop

logger = logging.getLogger("LEVIATHAN.RenderEngine")

class RenderEngine:
    def __init__(self, config: dict):
        self.config = config
        self.temp_dir = Path("output/temp_ultra")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.rendering_config = config.get("rendering", {})
        # V24.3 : Semaphores to prevent OOM on CloudNode (limit FFmpeg concurrency)
        self.segment_semaphore = asyncio.Semaphore(2)

    def _normalize_media(self, image_path: str, target_size=(1080, 1920)):
        """Force conversion et redimensionnement exact via Pillow."""
        try:
            with Image.open(image_path) as img:
                # Force conversion to RGB
                img = img.convert("RGB")
                # Redimensionnement et crop centré exact
                img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)
                img.save(image_path, "PNG")
                logger.debug(f"[Pillow] Image normalisée ({target_size}) : {image_path}")
        except Exception as e:
            logger.error(f"[Pillow] Erreur sur {image_path}: {e}")

    async def run_ffmpeg(self, args: List[str]):
        """Exécute une commande FFmpeg de manière asynchrone."""
        logger.info(f"FFmpeg CMD: {' '.join(args)}")
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"FFmpeg Error: {stderr.decode()}")
            raise RuntimeError(f"FFmpeg failed with return code {process.returncode}")

    async def render_segment(self, image_path: str, duration: float, output: str):
        """Rendu d'un segment individuel avec SPRINT 2 (Ken Burns Zoompan)."""
        res = self.rendering_config.get("resolution", [1080, 1920])
        # V24.10 : Lent et subtil zoom avant (1.0 à 1.15)
        # fps=25 par défaut
        fps = 25
        num_frames = int(duration * fps)
        
        # Le filtre zoompan a besoin d'une résolution de sortie fixée
        vf = (
            f"zoompan=z='min(zoom+0.0006,1.15)':d={num_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={res[0]}x{res[1]},"
            f"setsar=1:1,format=yuv420p"
        )
        
        args = [
            "-y", "-loop", "1", "-t", str(duration), "-i", image_path,
            "-vf", vf,
            "-r", str(fps), # Force constant fps for concatenation
            "-c:v", "libx264", "-threads", "2", "-tune", "stillimage", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", output
        ]
        async with self.segment_semaphore:
            await self.run_ffmpeg(args)

    async def get_audio_duration_mutagen(self, audio_path: str) -> float:
        """Récupère la durée précise de l'audio via Mutagen."""
        from mutagen.mp3 import MP3
        try:
            audio = MP3(audio_path)
            return audio.info.length
        except Exception as e:
            logger.warning(f"Mutagen fail: {e}")
            return 5.0

    async def assemble_video(self, script: dict, image_paths: List[str], audio_path: str, srt_path: str, music_path: str, output_path: str, lang: str, style: str = "viral"):
        """V26.6 : Master Render Engine - ULTRA STABLE Revision."""
        logger.info(f"[{lang}] 🔴 RENDER REVOLUTION : Sync, Centering & Variety Fix.")
        
        # 1. Normalisation & Math
        res = self.rendering_config.get("resolution", [1080, 1920])
        total_duration = await self.get_audio_duration_mutagen(audio_path)
        num_scenes = len(script["scenes"])
        avg_duration = total_duration / num_scenes if num_scenes > 0 else 5.0
        
        # 2. Visuels de secours (Variety Fix - Bug 4)
        bg_dir = Path("assets/backgrounds")
        available_bgs = []
        if bg_dir.exists():
            available_bgs = [str(f) for f in (list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png")))]
            import random
            random.shuffle(available_bgs)

        safe_image_paths = []
        for i, img in enumerate(image_paths):
            # Si image vide, manquante, ou identique à la première (monotonie), on force la diversité
            if not img or not Path(img).exists() or (i > 0 and img == image_paths[0]):
                if available_bgs: safe_image_paths.append(available_bgs[i % len(available_bgs)])
                else: safe_image_paths.append(img)
            else:
                safe_image_paths.append(img)
        
        # Normalisation Pillow
        for img_path in safe_image_paths:
            if Path(img_path).exists():
                self._normalize_media(img_path, target_size=(res[0], res[1]))

        # 3. Rendu des Segments
        segments = []
        tasks = []
        for i, img in enumerate(safe_image_paths):
            seg_path = self.temp_dir / f"seg_{lang}_{i:03d}.mp4"
            tasks.append(self.render_segment(img, avg_duration, str(seg_path)))
            segments.append(seg_path)
            
        # 4. Outro (Bug 5)
        outro_path = Path("assets/outro.png")
        if outro_path.exists():
            outro_seg = self.temp_dir / f"seg_{lang}_outro.mp4"
            tasks.append(self.render_segment(str(outro_path), 3.0, str(outro_seg)))
            segments.append(outro_seg)
            total_duration_with_outro = total_duration + 3.0
        else:
            total_duration_with_outro = total_duration

        await asyncio.gather(*tasks)

        # 5. Concaténation Vidéo (Thread-Safe)
        concat_list = self.temp_dir / f"list_{lang}.txt"
        with open(concat_list, "w") as f:
            for seg in segments: f.write(f"file '{seg.absolute()}'\n")
        
        raw_output = self.temp_dir / f"raw_{lang}.mp4"
        await self.run_ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(raw_output)])
        
        # 6. Master Filtergraph (Bug 1, 2, 3)
        # SRT Safety
        import shutil
        temp_srt = Path("master_render.srt")
        shutil.copy(srt_path, temp_srt)
        srt_rel = "master_render.srt"
        
        # Style Subtitles (Bug 2)
        font_size = int(res[0] * 0.07)
        hugo_yellow = "&H00FFFF"
        # Alignment 10 = Middle Center. MarginV=0 for perfect centering.
        sub_style = f"Fontname=Arial,Bold=1,Fontsize={font_size},PrimaryColour={hugo_yellow},OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=10,MarginV=0"
        
        # Audio Mix (Bug 1 Sync Fix)
        # On force le départ à 0 et la resynchronisation des PTS
        audio_filter = f"[1:a]adelay=0|0[voice]; [2:a]volume=0.25[bgm]; [voice][bgm]amix=inputs=2:duration=first:dropout_transition=0,aresample=async=1[aout]"
        
        # Vidéo Graph
        v_graph = f"[0:v]setpts=PTS-STARTPTS,subtitles='{srt_rel}':force_style='{sub_style}'[vsubs]"
        
        # Logo (Bug 3)
        logo_path = Path("assets/branding/logo.png")
        if logo_path.exists():
            v_graph += f"; [3:v]scale=150:-1[logo];[vsubs][logo]overlay=W-w-60:60[vout]"
            map_v = "[vout]"
        else:
            map_v = "[vsubs]"
            
        final_args = [
            "-y", "-i", str(raw_output),               # 0
            "-i", audio_path,                         # 1
            "-i", music_path                          # 2
        ]
        if logo_path.exists(): final_args.extend(["-i", str(logo_path)]) # 3
        
        final_args.extend([
            "-filter_complex", f"{v_graph}; {audio_filter}",
            "-map", map_v, "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "44100",
            "-t", str(total_duration_with_outro), # Outro inclu
            "-async", "1", "-vsync", "1",          # Force Sync
            str(output_path)
        ])
        
        await self.run_ffmpeg(final_args)
        return str(output_path)
