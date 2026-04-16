import os
import asyncio
import logging
import edge_tts
from pathlib import Path

logger = logging.getLogger("LEVIATHAN.EdgeTTS")

class EdgeTTSWrapper:
    def __init__(self, config: dict):
        self.config = config
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

    def _purify_text(self, text: str) -> str:
        """
        Convertit les balises rythmiques (SSML-like) en ponctuation standard 
        pour forcer des pauses naturelles dans edge-tts.
        """
        # ... devient une pause longue (virgule + point ou point de suspension)
        text = text.replace("...", "... ")
        # — (em dash) devient une pause moyenne (virgule ou tiret)
        text = text.replace("—", ", ")
        # Nettoyage des éventuels restes de balises SSML si présents
        import re
        text = re.sub(r'<[^>]*>', '', text)
        return text.strip()

    async def generate_audio(self, text: str, voice_id: str, lang_code: str, output_path: str) -> tuple:
        """
        Génère l'audio ET les sous-titres .srt via Edge TTS (V12.6).
        """
        clean_text = self._purify_text(text)
        srt_path = output_path.replace(".mp3", ".srt")
        # Ensure directories exist
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(srt_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Synthèse vocale Edge V12.7 (Fast-News) : {voice_id} (Rate: +10%)")
        
        try:
            # V24.8 : Robust Style (SentenceBoundary + Internal Splitter)
            communicate = edge_tts.Communicate(clean_text, voice_id, rate="+10%")
            submaker = edge_tts.SubMaker()
            
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "SentenceBoundary":
                        # SentenceBoundary is guaranteed to work in all versions
                        submaker.feed(chunk)
            
            # Post-process to get 3-word chunks from sentences
            raw_srt = submaker.get_srt()
            if not raw_srt:
                logger.warning("Edge SubMaker returned empty SRT. Falling back to dummy.")
                srt_content = "1\n00:00:00,000 --> 00:00:05,000\nProduction Le Pr\xE9sentateur\n\n"
            else:
                # Group/Split sentences into small blocks for the 'Hugo' look
                srt_content = self._group_srt_words(raw_srt, words_per_line=3)
            
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
        
        except Exception as e:
            logger.error(f"Edge TTS Failed: {e}. Switching to OpenAI TTS Failover...")
            if not self.openai_api_key:
                return None, None
            
            try:
                from openai import AsyncOpenAI
                oa_client = AsyncOpenAI(api_key=self.openai_api_key)
                # Failover Voice selection
                voice = "onyx" if "Neural" in voice_id else "alloy"
                
                response = await oa_client.audio.speech.create(
                    model="tts-1",
                    voice=voice,
                    input=clean_text
                )
                response.stream_to_file(output_path)
                
                # V24.4 : Better SRT fallback for OpenAI TTS
                # We split text into small chunks and estimate timing (approx 2 words per sec)
                words = text.split()
                srt_out = []
                for i in range(0, len(words), 5):
                    chunk = " ".join(words[i:i+5])
                    start = i * 0.5
                    end = (i+5) * 0.5
                    srt_out.append(f"{i//5+1}\n00:00:{int(start):02d},000 --> 00:00:{int(end):02d},000\n{chunk}")
                srt_content = "\n\n".join(srt_out)
                logger.info(f"OpenAI TTS Failover OK (Voice: {voice})")
            except Exception as oa_e:
                logger.error(f"OpenAI TTS Failover also failed: {oa_e}")
                return None, None

        # common save logic for SRT
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            
            # V12.12 : Sync pour l'uploader post_social.py
            import json
            tts_data_path = Path("output/tts_data.json")
            video_path = str(Path("output/videos") / f"video_{lang_code}.mp4")
            
            data = {
                "final_video_path": video_path,
                "video_path_with_subs": video_path,
                "language": lang_code,
                "script": {},
                "thumbnail_path": str(Path("output/images") / f"thumb_{lang_code}.jpg")
            }
            
            with open(tts_data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            return output_path, srt_path
        except Exception as e:
            logger.error(f"Edge TTS Exception: {e}")
            return None, None

    def _build_raw_srt_from_words(self, words_data: list) -> str:
        """Converts word data (word, start_ms, dur_ms) into raw SRT string."""
        raw_srt = ""
        for i, (word, start_ms, dur_ms) in enumerate(words_data):
            end_ms = start_ms + dur_ms
            
            def format_time(ms):
                h = int(ms // 3600000)
                m = int((ms % 3600000) // 60000)
                s = int((ms % 60000) // 1000)
                ms_rem = int(ms % 1000)
                return f"{h:02}:{m:02}:{s:02},{ms_rem:03}"
            
            raw_srt += f"{i+1}\n{format_time(start_ms)} --> {format_time(end_ms)}\n{word}\n\n"
        return raw_srt

    def _group_srt_words(self, raw_srt: str, words_per_line: int = 3) -> str:
        """Process SRT into short blocks. Handles both word-level and sentence-level inputs."""
        import re
        blocks = re.split(r'\n\n', raw_srt.strip())
        new_blocks = []
        
        all_words_timed = []
        
        for block in blocks:
            lines = block.split('\n')
            if len(lines) < 3: continue
            
            time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', lines[1])
            if not time_match: continue
            
            start_str, end_str = time_match.groups()
            text = lines[2]
            
            # Helper to convert HH:MM:SS,mmm to MS
            def ts_to_ms(ts):
                h, m, sm = ts.split(':')
                s, ms = sm.split(',')
                return int(h)*3600000 + int(m)*60000 + int(s)*1000 + int(ms)
            
            # Split sentence into words and interpolate timing
            words = text.split()
            if not words: continue
            
            start_ms = ts_to_ms(start_str)
            end_ms = ts_to_ms(end_str)
            duration_per_word = (end_ms - start_ms) / len(words)
            
            for j, w in enumerate(words):
                w_start = start_ms + j * duration_per_word
                w_end = w_start + duration_per_word
                all_words_timed.append((w, w_start, w_end))
                
        # Now re-group timed words into words_per_line
        def format_time(ms):
            h = int(ms // 3600000)
            m = int((ms % 3600000) // 60000)
            s = int((ms % 60000) // 1000)
            ms_rem = int(ms % 1000)
            return f"{h:02}:{m:02}:{s:02},{ms_rem:03}"
            
        final_blocks = []
        for i in range(0, len(all_words_timed), words_per_line):
            chunk = all_words_timed[i:i+words_per_line]
            start_ms = chunk[0][1]
            end_ms = chunk[-1][2]
            text = " ".join([c[0] for c in chunk]).upper()
            
            final_blocks.append(f"{len(final_blocks)+1}\n{format_time(start_ms)} --> {format_time(end_ms)}\n{text}")
            
        return "\n\n".join(final_blocks) + "\n\n"
