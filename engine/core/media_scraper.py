import asyncio
import os
import logging
import httpx
from pathlib import Path
from typing import List, Optional
from duckduckgo_search import DDGS
from PIL import Image

logger = logging.getLogger("LEVIATHAN.MediaScraper")

class MediaScraper:
    def __init__(self, config: dict):
        self.config = config
        self.pexels_api_key = os.getenv("PEXELS_API_KEY")
        self.pixabay_api_key = os.getenv("PIXABAY_API_KEY")
        self.unsplash_api_key = os.getenv("UNSPLASH_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.output_dir = Path("output/images")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir = Path("data/media_vault")
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    async def download_image(self, client: httpx.AsyncClient, url: str, path: Path) -> bool:
        """Télécharge une image de manière asynchrone."""
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code == 200:
                # Save using aiofiles if available, or just standard write for speed
                with open(path, "wb") as f:
                    f.write(resp.content)
                return True
            return False
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            return False

    async def fetch_pexels(self, client: httpx.AsyncClient, query: str, index: int) -> Optional[str]:
        """Recherche Pexels asynchrone."""
        if not self.pexels_api_key:
            return None
        
        # V18.5 : Dynamic Orientation
        res = self.config.get("rendering", {}).get("resolution", [1080, 1920])
        orientation = "portrait" if res[0] < res[1] else "landscape"
        
        headers = {"Authorization": self.pexels_api_key}
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=5&orientation={orientation}"
        
        try:
            resp = await client.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                if photos:
                    # Circular selection for variety
                    photo = photos[index % len(photos)]
                    return photo["src"]["large2x"]
        except Exception as e:
            logger.warning(f"Pexels failed for '{query}': {e}")
        return None

    async def fetch_pixabay(self, client: httpx.AsyncClient, query: str, index: int) -> Optional[str]:
        """Recherche Pixabay (Secondaire)."""
        if not self.pixabay_api_key: return None
        res = self.config.get("rendering", {}).get("resolution", [1080, 1920])
        orientation = "vertical" if res[0] < res[1] else "horizontal"
        url = f"https://pixabay.com/api/?key={self.pixabay_api_key}&q={query}&image_type=photo&orientation={orientation}"
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    return hits[index % len(hits)]["largeImageURL"]
        except Exception as e:
            logger.warning(f"Pixabay failed for '{query}': {e}")
        return None

    async def fetch_unsplash(self, client: httpx.AsyncClient, query: str, index: int) -> Optional[str]:
        """Recherche Unsplash (Tertiaire)."""
        if not self.unsplash_api_key: return None
        res = self.config.get("rendering", {}).get("resolution", [1080, 1920])
        orientation = "portrait" if res[0] < res[1] else "landscape"
        url = f"https://api.unsplash.com/search/photos?query={query}&orientation={orientation}&client_id={self.unsplash_api_key}"
        try:
            resp = await client.get(url, timeout=12)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return results[index % len(results)]["urls"]["regular"]
        except Exception as e:
            logger.warning(f"Unsplash failed for '{query}': {e}")
        return None

    async def generate_dalle(self, query: str, path: Path) -> bool:
        """Génération DALL-E 3 (Dernier recours)."""
        if not self.openai_api_key: return False
        try:
            from openai import AsyncOpenAI
            oa_client = AsyncOpenAI(api_key=self.openai_api_key)
            logger.info(f"🎨 Génération DALL-E 3 pour: {query}")
            response = await oa_client.images.generate(
                model="dall-e-3",
                prompt=f"A high-quality professional documentary style photo of {query}. 9:16 vertical orientation, realistic, detailed.",
                n=1,
                size="1024x1792"
            )
            image_url = response.data[0].url
            async with httpx.AsyncClient() as client:
                return await self.download_image(client, image_url, path)
        except Exception as e:
            logger.error(f"DALL-E 3 Failed: {e}")
            return False

    async def fetch_ddg(self, query: str, index: int) -> Optional[str]:
        """Recherche DuckDuckGo Image (Quaternaire)."""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.images(query, max_results=10))
                if results:
                    return results[index % len(results)]["image"]
        except Exception as e:
            logger.warning(f"DuckDuckGo failed for '{query}': {e}")
        return None

    def create_pure_blue(self, path: Path):
        """Fallback V10.5 : Création d'une image bleue pure en cas d'échec total."""
        img = Image.new("RGB", (1080, 1920), color=(0, 0, 255))
        img.save(path, "PNG")
        logger.info(f"Fallback Bleu Pur généré pour : {path}")

    async def process_scene(self, client: httpx.AsyncClient, keywords: List[str], scene_index: int, lang: str) -> str:
        """Cycle Failover Premium : VAULT -> Pexels -> Pixabay -> Unsplash -> DDG -> DALL-E 3."""
        import shutil
        filename = f"scene_{lang}_{scene_index:02d}.png"
        path = self.output_dir / filename
        
        for i, query in enumerate(keywords):
            # 1. SPRINT 1 : Cache Visuel (Media Vault) - UNIQUEMENT SUR LE PREMIER KEYWORD
            if i == 0:
                slug = "".join([c if c.isalnum() else "_" for c in query.lower()]) + ".png"
                vault_path = self.vault_dir / slug
                if vault_path.exists():
                    shutil.copy(vault_path, path)
                    logger.info(f"[{lang}] Scene {scene_index} : VAULT HIT ({query})")
                    return str(path)

            # 2. Pexels
            url = await self.fetch_pexels(client, query, scene_index)
            if url and await self.download_image(client, url, path):
                logger.info(f"[{lang}] Scene {scene_index} : Pexels OK")
                # Sauvegarde au coffre-fort pour la prochaine fois
                if i == 0: shutil.copy(path, self.vault_dir / slug)
                return str(path)
            
            # 3. Pixabay
            url = await self.fetch_pixabay(client, query, scene_index)
            if url and await self.download_image(client, url, path):
                logger.info(f"[{lang}] Scene {scene_index} : Pixabay OK")
                if i == 0: shutil.copy(path, self.vault_dir / slug)
                return str(path)

            # 4. Unsplash
            url = await self.fetch_unsplash(client, query, scene_index)
            if url and await self.download_image(client, url, path):
                logger.info(f"[{lang}] Scene {scene_index} : Unsplash OK")
                if i == 0: shutil.copy(path, self.vault_dir / slug)
                return str(path)
            
            # 5. DuckDuckGo
            url = await self.fetch_ddg(query, scene_index)
            if url and await self.download_image(client, url, path):
                logger.info(f"[{lang}] Scene {scene_index} : DDG OK")
                if i == 0: shutil.copy(path, self.vault_dir / slug)
                return str(path)

            # 6. DALL-E 3
            if await self.generate_dalle(query, path):
                logger.info(f"[{lang}] Scene {scene_index} : DALL-E 3 OK")
                if i == 0: shutil.copy(path, self.vault_dir / slug)
                return str(path)

        # 7. Fallback final (V26.5 STABLE)
        bg_dir = Path("assets/backgrounds")
        if bg_dir.exists():
            import random
            images = list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png")) + list(bg_dir.glob("*.jpeg"))
            if images:
                chosen = random.choice(images)
                import shutil
                shutil.copy(chosen, path)
                logger.info(f"🔄 Fallback : Image locale aléatoire utilisée ({chosen.name})")
                return str(path)
        
        self.create_pure_blue(path)
        return str(path)

    async def generate_thumbnail(self, title: str, lang: str) -> Optional[str]:
        """V18.5 : Génère une miniature YouTube premium via DALL-E 3 (16:9)."""
        if not self.openai_api_key: return None
        
        filename = f"thumb_{lang}.png"
        path = Path("output/images") / filename
        
        prompt = (
            f"A professional, cinematic YouTube thumbnail for a news video titled '{title}'. "
            f"Style: Dark, high contrast, high impact, expressive symbols. "
            f"No text on the image. 16:9 aspect ratio."
        )
        
        logger.info(f"[{lang}] 🎨 Génération MINIATURE DALL-E 3...")
        if await self.generate_dalle(prompt, path):
            return str(path)
        return None

    async def fetch_background_music(self, client: httpx.AsyncClient, mood: str, lang: str, bgm_pref: str = None, script_text: str = "") -> str:
        """Récupère une musique de fond dynamique: Externe URL, IA Contexte Local, ou Pixabay API."""
        import subprocess, random
        output_path = Path(f"output/audio/bgm_{lang}.mp3")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. URL externe (DÉSACTIVÉ v20.7 pour Sécurité Copyright)
        if bgm_pref and bgm_pref.startswith("http"):
             logger.warning(f"[{lang}] ⚠️ RÉVOCATION : Les URL externes sont interdites (Politique Strict No-Copyright v20.7). Repli sur Pixabay.")
             bgm_pref = None

        # 2. IA Contexte Local
        final_mood = bgm_pref if bgm_pref else mood
        if not bgm_pref and script_text:
            logger.info(f"[{lang}] 🤖 Analyse IA de l'ambiance musicale d'après le script...")
            try:
                from engine.agents.base_agent import BaseAgent
                agent = BaseAgent()
                prompt = f"Analyse le script et retourne UNIQUEMENT un mot représentant l'ambiance musicale appropriée à choisir parmi : news, chill, gaming.\n{script_text[:1000]}"
                mood_result = await agent.call_llm("Tu es un expert musical.", prompt, is_json=False)
                for valid in ["news", "chill", "gaming"]:
                    if valid in mood_result.lower():
                        final_mood = valid
                        break
                logger.info(f"[{lang}] 🎵 Ambiance IA contextuelle : {final_mood}")
            except Exception as e:
                logger.warning(f"[{lang}] ⚠ Erreur IA Contexte BGM: {e}")

        # Sélection dans dossier local correspondant ou via nom précis de bgm_pref
        music_dir = Path("assets/music")
        if music_dir.exists():
            # Si le frontend a envoyé un nom exact de fichier (ex: cyber.mp3)
            if bgm_pref and (music_dir / bgm_pref).exists():
                logger.info(f"[{lang}] ✓ Musique locale spécifique demandée : {bgm_pref}")
                return str(music_dir / bgm_pref)
            elif bgm_pref and (music_dir / f"{bgm_pref}.mp3").exists():
                return str(music_dir / f"{bgm_pref}.mp3")

            # Sinon, essayer de trouver un fichier qui contient le mood, ou n'importe lequel
            tracks = list(music_dir.glob(f"*{final_mood}*.mp3"))
            if not tracks:
                tracks = list(music_dir.glob("*.mp3"))
            if tracks:
                chosen = random.choice(tracks)
                logger.info(f"[{lang}] ✓ Musique locale sélectionnée : {chosen.name} (req: {final_mood})")
                return str(chosen)

        # 3. Fallback Pixabay (Strictly Royalty Free)
        api_key = os.getenv("PIXABAY_API_KEY")
        if not api_key:
            logger.warning("Pixabay API Key missing for free music, using default asset.")
            return "assets/music/default.mp3"

        logger.info(f"[{lang}] 🎼 Search royalty-free music on Pixabay for mood: {final_mood}")
        url = f"https://pixabay.com/api/audio/?key={api_key}&q={final_mood}"
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    music_url = hits[0]["audio"]
                    if await self.download_image(client, music_url, output_path):
                        return str(output_path)
            elif resp.status_code == 403:
                logger.warning(f"[{lang}] ⚠️ Pixabay 403 (Forbidden). Using local fallback.")
                fallback_dir = Path("assets/bgm_fallback")
                if fallback_dir.exists():
                     fallbacks = list(fallback_dir.glob("*.mp3"))
                     if fallbacks: return str(random.choice(fallbacks))
        except Exception as e:
            logger.error(f"Pixabay Audio failed: {e}")
        
        return "assets/music/default.mp3"

    async def fetch_all_media(self, script: dict, lang: str, music_mood: str = "documentary", bgm_pref: str = None) -> tuple:
        """Point d'entrée principal V14.1 : Télécharge images ET musique."""
        scenes = script.get("scenes", [])
        logger.info(f"[{lang}] Scraping média (Images & Musique) pour {len(scenes)} scènes.")
        script_text = " ".join([s.get("text", "") for s in scenes])
        
        async with httpx.AsyncClient() as client:
            # 1. Musique Dynamique / Externe
            music_task = self.fetch_background_music(client, music_mood, lang, bgm_pref, script_text)
            
            # 2. Images des scènes
            image_tasks = []
            for i, scene in enumerate(scenes):
                keywords = scene.get("search_keywords", ["technology", "abstract"])
                image_tasks.append(self.process_scene(client, keywords, i, lang))
            
            # Execution parallèle
            music_path, *image_paths = await asyncio.gather(music_task, *image_tasks)
            
        return list(image_paths), music_path
