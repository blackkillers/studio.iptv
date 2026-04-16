#!/usr/bin/env python3
"""
generate_images.py — Génère les images via Pexels, Pixabay ou DuckDuckGo (V11.0)
Avec fallback vers du Bleu Pur si tout échoue.
Support de la génération de miniatures (thumbnails).
"""

import sys
import json
import argparse
import time
import os
import random
from pathlib import Path
from typing import List, Optional, Any, Dict, cast
from urllib.parse import quote
import requests
import PIL.Image
from PIL import Image, ImageDraw, ImageFont
import math
import base64
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "images"

# Style cinématique par défaut ajouté à chaque prompt
STYLE_SUFFIX = (
    "cinematic vertical format, 9:16 aspect ratio, professional photography, "
    "sharp focus, dramatic lighting, news style, ultra realistic, highly detailed"
)

THUMBNAIL_STYLE_SUFFIX = (
    "cinematic horizontal 16:9 format, professional photography, sharp focus, "
    "dramatic lighting, news cover style, ultra realistic, highly detailed, vibrant colors"
)

# Prompts de fallback si l'IA ne fournit pas de prompt d'image
FALLBACK_PROMPTS = [
    "breaking news headline digital background",
    "futuristic city skyline professional photography",
    "modern business office holographic charts",
    "global network digital earth visualization",
    "audience watching social media highlights",
]

# Anchors pour forcer le contexte anglais selon la catégorie
CATEGORY_ANCHORS = {
    "israel": "israel military war conflict",
    "war": "war military conflict battlefield",
    "technology": "technology future hi-tech",
    "business": "business finance economy stock market",
    "ai": "artificial intelligence robot neural network",
    "crypto": "cryptocurrency bitcoin blockchain",
    "trending": "trending news breaking viral",
    "world": "world news international politics"
}

def is_valid_media(data: bytes, min_size: int = 10000, label: str = "media") -> bool:
    """Vérifie si les données sont un média valide (Signature + Taille > 10KB)."""
    size = len(data)
    if size < min_size:
        print(f"[V10.3 AUDIT] ❌ Small {label} detected: {size} bytes (Min: {min_size})", file=sys.stderr)
        return False
    
    # LOGO SHIELD: Reject patterns often found in small tracking pixels or branding
    if any(p in data[:200] for p in [b"Google", b"News", b"favicon"]):
        print(f"[V10.3 AUDIT] 🚫 Blocked potential error/tracking pixel for {label}", file=sys.stderr)
        return False

    is_ok = (data.startswith(b'\x89PNG\r\n\x1a\n') or 
            data.startswith(b'\xff\xd8\xff') or
            data.find(b'ftyp', 0, 20) != -1) # MP4
    
    if not is_ok:
        print(f"[V10.3 AUDIT] ❌ Invalid magic bytes for {label}", file=sys.stderr)
    return is_ok

from duckduckgo_search import DDGS

def download_ddg(query: str, output_path: str, scene_index: int = 0) -> bool:
    """Fallback via DuckDuckGo Image Search (Scraping)."""
    print(f"[V11.0 AUDIT] Scene {scene_index+1} | Source: DuckDuckGo | Keyword: \"{query}\"", file=sys.stderr)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=10))
            if results:
                # Pick one with variety
                img_url = results[scene_index % len(results)]["image"]
                resp = requests.get(img_url, timeout=15)
                if resp.status_code == 200 and is_valid_media(resp.content, label="DDG_Scene"):
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    print(f"[V11.0 AUDIT] ✓ Saved image from DDG: {output_path}", file=sys.stderr)
                    time.sleep(5)
                    return True
        return False
    except Exception as e:
        print(f"[V11.0 ERROR] DuckDuckGo failed: {e}", file=sys.stderr)
        return False

def check_sd() -> bool:
    """Vérifie si Stable Diffusion (A1111) est en ligne."""
    try:
        response = requests.get("http://127.0.0.1:7860/sdapi/v1/options", timeout=2)
        return response.status_code == 200
    except:
        return False

def download_sd(prompt: str, output_path: str, width: int = 1080, height: int = 1920, seed: int = -1) -> bool:
    """Génère une image via Stable Diffusion local (A1111 API)."""
    url = "http://127.0.0.1:7860/sdapi/v1/txt2img"
    suffix = THUMBNAIL_STYLE_SUFFIX if width > height else STYLE_SUFFIX
    payload = {
        "prompt": f"{prompt}, {suffix}",
        "steps": 20,
        "width": width,
        "height": height,
        "seed": seed,
        "cfg_scale": 7,
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            r = cast(Dict[str, Any], response.json())
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(cast(List[str], r['images'])[0]))
            return True
    except Exception as e:
        print(f"[generate_images] Stable Diffusion error: {e}", file=sys.stderr)
    return False

def download_airforce(prompt: str, output_path: str, width: int = 1080, height: int = 1920) -> bool:
    """Fallback via Airforce API."""
    suffix = THUMBNAIL_STYLE_SUFFIX if width > height else STYLE_SUFFIX
    encoded = quote(f"{prompt}, {suffix}")
    model = random.choice(["flux", "stable-diffusion-xl-lightning", "any-lora"])
    url = f"https://api.airforce/v1/image/generate?prompt={encoded}&model={model}&width={width}&height={height}"
    
    try:
        resp = requests.get(url, timeout=40)
        if resp.status_code == 200 and is_valid_media(resp.content):
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"[generate_images] ✓ Airforce ({model}): {output_path}", file=sys.stderr)
            return True
        return False
    except Exception:
        return False

# Global flag to skip Gemini refine_query_ai if quota is exhausted
SKIP_GEMINI_REFINE = False

def refine_query_ai(prompt: str, scene_index: int = 0) -> str:
    """
    Uses Gemini to extract 4-6 hyper-specific, rare English keywords for Pexels/Pixabay search.
    Adds randomization via temperature + shuffled diversity hints to prevent repetitive results.
    """
    global SKIP_GEMINI_REFINE
    if SKIP_GEMINI_REFINE:
        return ""
    try:
        if not genai:
            return ""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: return ""
        
        client = genai.Client(api_key=api_key)
        
        # Randomization anchors to force variety per scene
        DIVERSITY_HINTS = [
            "focus on people and faces",
            "focus on architecture and cityscapes",
            "focus on abstract and symbolic visuals",
            "focus on technology and screens",
            "focus on nature and environment",
            "focus on action and movement",
            "focus on close-up details and textures",
            "focus on aerial or wide-angle perspectives",
        ]
        diversity_hint = DIVERSITY_HINTS[(scene_index + random.randint(0, 3)) % len(DIVERSITY_HINTS)]
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"You are a professional stock photo researcher specializing in finding UNIQUE and SPECIFIC visuals.\n"
                f"Task: Generate 4 precise English search keywords for a stock photo query.\n"
                f"Scene context: {prompt}\n"
                f"Visual style: {diversity_hint}\n\n"
                f"STRICT RULES:\n"
                f"- NEVER use generic words like 'technology', 'news', 'business', 'people', 'modern'\n"
                f"- Use SPECIFIC, RARE, EVOCATIVE terms (e.g., 'blockchain ledger neon', 'trader gesturing monitor')\n"
                f"- Mix a visual noun + an action or emotion + a setting (e.g., 'hacker typing dark room')\n"
                f"- Return ONLY the keywords separated by spaces, no punctuation, no explanation\n"
                f"- Maximum 5 words total\n"
                f"Keywords:"
            )
        )
        res = response.text.strip().lower()
        # Clean potential markdown or prefixes
        res = res.replace("keywords:", "").replace("*", "").replace("-", " ").replace('"', "").strip()
        junk = ["stock", "photo", "image", "video", "pexels", "search", "of", "a", "the", "and"]
        words = [w for w in res.split() if w not in junk and len(w) > 2]
        return " ".join(words[:5])
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            print("[refine_query_ai] ⚠ Quota Gemini épuisé. Circuit-breaker activé.", file=sys.stderr)
            SKIP_GEMINI_REFINE = True
        else:
            print(f"[refine_query_ai] AI Refinement failed: {e}", file=sys.stderr)
        return ""


def is_content_safe(tags: List[str], topic: str) -> bool:
    """Returns False if tags contain 'chicken' related things but topic doesn't."""
    chickens = ["chicken", "poule", "hen", "rooster", "cock", "poulet", "farm", "oiseau", "bird", "gallus", "poultry", "fowl", "poussin"]
    topic_low = (topic or "").lower()
    has_chicken_request = any(c in topic_low for c in chickens)
    if has_chicken_request: return True
    
    for t in (tags or []):
        t_low = str(t).lower()
        if any(c in t_low for c in chickens):
            print(f"[is_content_safe] 🚫 Blocked potential chicken content (tag: {t_low})", file=sys.stderr)
            return False
    return True

def download_pixabay(query: str, output_path: str, width: int = 1080, height: int = 1920, is_video: bool = False, scene_index: int = 0) -> bool:
    """Télécharge depuis Pixabay (Images ou Vidéos)."""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key: return False
    
    # Use topic for chicken safety
    query_clean = query.lower()
    
    type_param = "videos" if is_video else "photo"
    base_url = "https://pixabay.com/api/videos/" if is_video else "https://pixabay.com/api/"
    # Vary page based on scene_index
    page = (scene_index // 3) + 1
    url = f"{base_url}?key={api_key}&q={quote(query)}&safesearch=true&per_page=20&page={page}"
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            hits = data.get("hits", [])
            # Pick a hit that is safe
            for hit in hits:
                tags = hit.get("tags", "").split(",")
                if not is_content_safe(tags, query): continue
                
                media_url = None
                if is_video:
                    v_res = hit.get("videos", {})
                    media_url = v_res.get("medium", {}).get("url") or v_res.get("small", {}).get("url")
                else:
                    media_url = hit.get("largeImageURL")
                
                if media_url:
                    r = requests.get(media_url, timeout=20)
                    if r.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(r.content)
                        return True
        return False
    except: return False

def download_unsplash(query: str, output_path: str, width: int = 1080, height: int = 1920, scene_index: int = 0) -> bool:
    """Télécharge depuis Unsplash."""
    api_key = os.getenv("UNSPLASH_API_KEY")
    if not api_key: return False
    url = f"https://api.unsplash.com/search/photos?query={quote(query)}&per_page=5&orientation=portrait"
    headers = {"Authorization": f"Client-ID {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            for res in results:
                tags = [t.get("title", "") for t in res.get("tags", [])]
                if not is_content_safe(tags, query): continue
                img_url = res.get("urls", {}).get("regular")
                if img_url:
                    r = requests.get(img_url, timeout=20)
                    with open(output_path, "wb") as f:
                        f.write(r.content)
                    return True
        return False
    except: return False

def download_pexels(prompt: str, output_path: str, width: int = 1080, height: int = 1920, scene_index: int = 0) -> bool:
    """Fallback via Pexels API (Images réelles)."""
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return False
    
    # Use AI to refine query if possible, otherwise fallback to basic cleaning
    ai_query = refine_query_ai(prompt, scene_index=scene_index)
    if ai_query:
        clean_query = ai_query
        print(f"[generate_images] AI Refined Query: {clean_query}", file=sys.stderr)
    else:
        # Extract keywords from English prompt, avoiding stop words
        junk = ["close-up", "shot", "cinematic", "photorealistic", "detailed", "photography", "vertical", "9:16", "4k", "style", "glowing", "neon", "high", "angle", "ultra", "realistic", "rendered", "masterpiece", "trending", "orange", "poule", "poulet", "news", "orange.fr", "actualités"]
        words = [w.lower() for w in prompt.replace(",", "").replace(".", "").replace(":", " ").split() if w.lower() not in junk and len(w) > 3]
        clean_query = " ".join(words[0:7])
    
    print(f"[generate_images] Trying Pexels for: {clean_query}", file=sys.stderr)
    headers = {"Authorization": api_key}
    orientation = "portrait" if height > width else "landscape"
    # Use scene_index to vary results
    page = (scene_index // 5) + 1
    url = f"https://api.pexels.com/v1/search?query={quote(clean_query)}&per_page=15&orientation={orientation}&page={page}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("photos"):
                photos = data["photos"]
                # Filter out chickens
                valid_photos = []
                for p in photos:
                    # Pexels doesn't give tags directly, we check alt or search for more info?
                    # We use alt text as tag proxy
                    alt = p.get("alt", "")
                    if is_content_safe([alt], clean_query):
                        valid_photos.append(p)
                
                if valid_photos:
                    p = valid_photos[scene_index % len(valid_photos)]
                    photo_url = p["src"]["large2x"] if orientation == "portrait" else p["src"]["large"]
                    img_resp = requests.get(photo_url, timeout=20)
                    if img_resp.status_code == 200 and is_valid_media(img_resp.content):
                        with open(output_path, "wb") as f:
                            f.write(img_resp.content)
                        return True
        return False
    except Exception:
        return False

def download_pexels_video(prompt: str, output_path: str, width: int = 1080, height: int = 1920) -> bool:
    """Télécharge un clip vidéo via Pexels Video API."""
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key: return False
    
    clean_query = refine_query_ai(prompt) or " ".join(prompt.split()[0:4])
    print(f"[generate_images] Trying Pexels Video for: {clean_query}", file=sys.stderr)
    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={quote(clean_query)}&per_page=10&orientation=portrait"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            vids = resp.json().get("videos", [])
            for v in vids:
                if not is_content_safe([v.get("url", "")], clean_query): continue
                
                files = v.get("video_files", [])
                best = next((f for f in files if f.get("width") == 720 or f.get("height") == 1280), files[0] if files else None)
                if best and best.get("link"):
                    v_url = best["link"]
                    v_resp = requests.get(v_url, timeout=30)
                    if v_resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(v_resp.content)
                        print(f"[generate_images] ✓ Pexels Video: {output_path}", file=sys.stderr)
                        return True
        return False
    except Exception as e:
        print(f"[generate_images] ⚠ Pexels Video error: {e}", file=sys.stderr)
        return False

# Global flag to skip Google services if they fail due to quota/payment
SKIP_GOOGLE_IMAGEN = False

def download_google_image(prompt: str, output_path: str, width: int = 1080, height: int = 1920) -> bool:
    """Generate image using Google Imagen 3/4 via Gemini API."""
    global SKIP_GOOGLE_IMAGEN
    if SKIP_GOOGLE_IMAGEN:
        return False
        
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False
    
    if genai is None or types is None:
        return False
        
    print(f"[generate_images] Trying Google Imagen for: {prompt}", file=sys.stderr)
    try:
        g_client = cast(Any, genai).Client(api_key=api_key)
        g_types = cast(Any, types)
        
        # Try different model versions to avoid 404
        model_versions = ['imagen-3.0-generate-001', 'imagen-3', 'imagen-2']
        
        for model_id in model_versions:
            try:
                response = g_client.models.generate_images(
                    model=model_id,
                    prompt=prompt,
                    config=g_types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="9:16" if height > width else "16:9",
                        output_mime_type="image/png"
                    )
                )
                if response.generated_images:
                    image_bytes = response.generated_images[0].image_bytes
                    with open(output_path, "wb") as f:
                        f.write(image_bytes)
                    print(f"[generate_images] ✓ Google Imagen ({model_id}): {output_path}", file=sys.stderr)
                    return True
            except Exception as e:
                err = str(e).lower()
                if "404" in err or "not found" in err:
                    continue # Try next model
                if "quota" in err or "429" in err or "exhausted" in err:
                    print("[generate_images] ⚠ Gemini Quota Exceeded. Switching off Google Imagen.", file=sys.stderr)
                    SKIP_GOOGLE_IMAGEN = True
                    return False
                raise e # Other error
        return False
    except Exception as e:
        print(f"[generate_images] ⚠ Google Imagen error: {e}", file=sys.stderr)
        return False

def download_google_video(prompt: str, output_path: str) -> bool:
    """Generate short video clip using Google Veo via Gemini API."""
    global SKIP_GOOGLE_IMAGEN
    if SKIP_GOOGLE_IMAGEN:
        return False
        
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False
        
    print(f"[generate_images] Trying Google Veo for: {prompt}", file=sys.stderr)
    if genai is None or types is None:
        print("[generate_images] Google GenAI or types is not installed. Skipping.", file=sys.stderr)
        return False

    try:
        g_client = cast(Any, genai).Client(api_key=api_key)
        g_types = cast(Any, types)
        # Veo generation usually takes time and might be async, but SDK wraps it
        operation = g_client.models.generate_videos(
            model='veo-2.0-generate-001', # Using available Veo
            prompt=prompt,
            config=g_types.GenerateVideosConfig(
                duration_seconds=5,
                aspect_ratio="9:16"
            )
        )
        # Wait for operation if necessary (SDK might handle it)
        if operation.result:
            video_bytes = operation.result.video_bytes
            with open(output_path, "wb") as f:
                f.write(video_bytes)
            print(f"[generate_images] ✓ Google Veo: {output_path}", file=sys.stderr)
            return True
        return False
    except Exception as e:
        error_msg = str(e)
        # Fallback to simple print if Veo isn't fully ready in this SDK version
        print(f"[generate_images] ⚠ Google Veo error: {error_msg}", file=sys.stderr)
        if "paid plan" in error_msg.lower() or "400" in error_msg:
            SKIP_GOOGLE_IMAGEN = True
        return False

def download_pixabay_video(prompt: str, output_path: str) -> bool:
    """Fallback via Pixabay Video API."""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return False
    
    # Simplify prompt for search
    v_split = prompt.split()
    v_words = []
    for i in range(min(len(v_split), 5)):
        v_words.append(v_split[i])
    simple_prompt = " ".join(v_words)
    print(f"[generate_images] Trying Pixabay Video for: {simple_prompt}", file=sys.stderr)
    url = f"https://pixabay.com/api/videos/?key={api_key}&q={quote(simple_prompt)}&per_page=3"
    
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("hits"):
                # On prend la version MP4 la plus appropriée
                videos = cast(Dict[str, Any], data["hits"][0]["videos"])
                # Préfère medium ou small pour la rapidité
                v_url = cast(Dict[str, Any], videos.get("medium", {})).get("url") or cast(Dict[str, Any], videos.get("small", {})).get("url")
                if v_url:
                    v_resp = requests.get(v_url, timeout=30)
                    if v_resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(v_resp.content)
                        print(f"[generate_images] ✓ Pixabay Video: {output_path}", file=sys.stderr)
                        return True
        return False
    except Exception as e:
        print(f"[generate_images] ⚠ Pixabay Video error: {e}", file=sys.stderr)
        return False

def create_placeholder_image(output_path: str, scene_index: int, text: str = "", width: int = 1080, height: int = 1920, force_black: bool = False) -> bool:
    """Crée une image placeholder (Dégradé si Branding, BLEU PUR si échec V10.5)."""
    try:
        if force_black:
            color = (0, 0, 0)
        else:
            # V10.5: MANDATORY PURE BLUE if AI fails (to distinguish from black screen bug)
            color = (0, 0, 255) 
            
        img = Image.new("RGB", (width, height), color=color)
        img.save(output_path, "PNG")
        print(f"[V10.5 AUDIT] ✓ PURE BLUE Fallback saved: {output_path}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[V10.5 ERROR] Failed to save fallback: {e}", file=sys.stderr)
        return False

def get_image(prompt: str, output_path: str, width: int = 1080, height: int = 1920, seed: int = -1, scene_index: int = 0, scene_text: str = "", use_video: bool = False, title: str = "", category: str = "") -> bool:
    """V11.0: Real Media Cascade (Pexels -> Pixabay -> DDG -> Blue)."""
    
    # Clean query: prompt is now search_keywords from script
    search_query = prompt.replace('"', '').replace("'", "")
    
    # 1. Pexels (High Quality Stock)
    if download_pexels(search_query, output_path, width, height, scene_index=scene_index):
        return True
    
    # 2. Pixabay (Secondary Stock)
    if download_pixabay(search_query, output_path, width, height, is_video=False, scene_index=scene_index):
        return True

    # 3. DuckDuckGo (Unlimited Web Search)
    if download_ddg(search_query, output_path, scene_index=scene_index):
        return True
        
    # 4. Final Security: Pure Blue (V10.5)
    return create_placeholder_image(output_path, scene_index, scene_text, width, height, force_black=False)

def main(args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    input_path = BASE_DIR / "output" / "tts_data.json"
    if args.test or args.dry_run or not os.path.exists(input_path):
        scene_timings = [{"index": i, "search_keywords": FALLBACK_PROMPTS[i], "text": f"Test {i}"} for i in range(5)]
        tts_data = {"scene_timings": scene_timings, "metadata": {"title": "Test AI News"}}
        script_scenes = []
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            tts_data = cast(Dict[str, Any], json.load(f))
        scene_timings = cast(List[Dict[str, Any]], tts_data["scene_timings"])
        script_scenes = cast(List[Dict[str, Any]], tts_data.get("script", {}).get("scenes", []))

    selected_images = []
    if args.selected_images:
        # Split by comma and clean up
        paths = [p.strip() for p in args.selected_images.split(",") if p.strip()]
        for p in paths:
            # If it's a relative path starting with /output, make it absolute
            if p.startswith("/output"):
                p = str(BASE_DIR / p.lstrip("/"))
            if os.path.exists(p):
                selected_images.append(p)
    
    image_paths = []
    seed_base = int(time.time()) % 999999
    # Prioritise le titre spécifique du script sinon fallback
    if isinstance(tts_data, dict):
        title = tts_data.get("metadata", {}).get("title") or tts_data.get("script", {}).get("title") or "AI News Today"
    else:
        title = "AI News Today"

    for i, scene in enumerate(scene_timings):
        # Type narrowing for linter
        if not isinstance(scene, dict):
            scene = {}
            
        # V11.0: Support both image_prompt and search_keywords
        p1 = scene.get("search_keywords") or scene.get("image_prompt")
        p2 = ""
        if i < len(script_scenes):
            s_scene = script_scenes[i]
            if isinstance(s_scene, dict):
                p2 = s_scene.get("search_keywords") or s_scene.get("image_prompt", "")
        
        prompt = p1 or p2 or FALLBACK_PROMPTS[i % len(FALLBACK_PROMPTS)]
        
        scene_text = scene.get("text", "")
        
        # Determine extension based on selected image if any
        ext = ".png"
        src_path = None
        if selected_images:
            src_path = selected_images[i % len(selected_images)]
            ext = os.path.splitext(src_path)[1].lower() or ".png"
            
        out_path = str(OUTPUT_DIR / f"scene_{i:02d}{ext}")
        
        print(f"[generate_images] Scene {i+1}/{len(scene_timings)}: {title}...", file=sys.stderr)
        if args.dry_run:
            create_placeholder_image(out_path, i, scene_text, force_black=True)
        else:
            downloaded_native = False
            
            # Fetch article images
            article_images = []
            try:
                with open(BASE_DIR / "output" / "script_data.json", "r", encoding="utf-8") as f:
                    article_images = json.load(f).get("news", {}).get("article_images", [])
            except Exception:
                pass

            # Check if this scene should use an article image
            if i < len(article_images) and not selected_images:
                try:
                    r = requests.get(article_images[i], timeout=15)
                    if r.status_code == 200 and is_valid_media(r.content):
                        with open(out_path, "wb") as f_img:
                            f_img.write(r.content)
                        print(f"[generate_images] Using Article Image for scene {i}: {article_images[i]}", file=sys.stderr)
                        downloaded_native = True
                except Exception as e:
                    print(f"[generate_images] Error fetching article image {article_images[i]}: {e}", file=sys.stderr)

            if not downloaded_native:
                # Enriched prompt for AI and Stock
                enriched_prompt = prompt
                # Cast for linter
                c_title = cast(str, title)
                c_prompt = cast(str, prompt or "")
                if c_title and c_title.lower() not in c_prompt.lower():
                    enriched_prompt = f"{c_title}, {c_prompt}"
                
                # Use selected image if available, else generate
                if selected_images:
                    # src_path was already determined above
                    import shutil
                    try:
                        shutil.copy(src_path, out_path)
                        print(f"[generate_images] Using selected media: {src_path} -> {out_path}", file=sys.stderr)
                    except Exception as e:
                        print(f"[generate_images] Error copying selected image: {e}", file=sys.stderr)
                        get_image(enriched_prompt, out_path, seed=seed_base + i, scene_index=i, scene_text=scene_text, use_video=False, title=c_title, category=args.category)
                else:
                    get_image(enriched_prompt, out_path, seed=seed_base + i, scene_index=i, scene_text=scene_text, use_video=False, title=c_title, category=args.category)
                
                # Update the scene object so validate_assets.py sees the relevance
                scene["image_prompt"] = enriched_prompt
        
        # CRITICAL: Save path in scene object for assembly script
        cast(Dict[str, Any], scene)["image_path"] = out_path
        image_paths.append(out_path)

    thumbnail_path = str(OUTPUT_DIR / "thumbnail.png")
    print(f"[generate_images] Generating Thumbnail for: {title}...", file=sys.stderr)
    
    if args.dry_run:
        create_placeholder_image(thumbnail_path, 99, title, width=1280, height=720)
    else:
        get_image(f"Viral news thumbnail about {title}, catchy visual, no text", thumbnail_path, width=1280, height=720, seed=seed_base)

    tts_data["image_paths"] = image_paths
    tts_data["thumbnail_path"] = thumbnail_path
    
    if not (args.test or args.dry_run):
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(tts_data, f, ensure_ascii=False, indent=2)
    
    print(json.dumps({"image_paths": image_paths, "thumbnail_path": thumbnail_path}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate images with various backends")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--category", default="", help="News category for anchoring search")
    parser.add_argument("--long", action="store_true", help="Use video clips if possible for long videos")
    parser.add_argument("--use-video", action="store_true", help="Force use of video clips")
    parser.add_argument("--selected-images", default="", help="Comma separated list of pre-selected image paths")
    main(parser.parse_args())
