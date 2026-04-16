#!/usr/bin/env python3
"""
generate_script.py — Génère un script vidéo ~60s via Groq API (llama-3.3-70b)
Si pas de clé Groq, utilise un template local intelligent.
Lit news_data.json, écrit script_data.json
"""

import sys
import json
import argparse
import os
import re
import random
from pathlib import Path
from dotenv import load_dotenv
import threading # For timeout or parallel safety if needed
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback for older Python versions
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_system_prompt(theme: str = "actualités", language: str = "fr") -> str:
    """Génère un prompt système V9.5 (Dynamic Storyteller Engine)."""
    lang_name = "français" if language == "fr" else "anglais" if language == "en" else "russe" if language == "ru" else language

    # DIRECTIVES ABSOLUES V9.5
    v95_directives = """
    [DIRECTIVE ABSOLUE : StudioEngine V9.5 - MOTEUR STORYTELLER DYNAMIQUE]
    Ta mission : Écrire un script de 12 scènes maximum. Tu es un rédacteur en chef expert en viralité.

    RÈGLES UNIVERSELLES :
    1. ZÉRO "VOCABULAIRE IA" : Bannis strictement : "crucial", "paysage", "fascinant", "toutefois", "en conclusion", "plongeons dans...".
    2. SYNTAXE HUMAINE ET VARIÉE : Utilise des conjonctions (Et, Mais, Sauf que) de manière PARCIMONIEUSE, maximum 2 fois dans tout le script. Alterne avec des affirmations directes, des questions, et des phrases nominales. Phrases de 4 à 8 mots.
    3. INGÉNIERIE DU RYTHME : Utilise "..." pour des pauses de 500ms (suspense ou comique). Utilise "—" pour les incises.
    4. RECHERCHE MÉDIAS RÉELS (V11.0) : Tu DOIS fournir des `search_keywords` au lieu de prompts descriptifs.
       - Règle : 3-4 mots-clés simples en ANGLAIS, factuels et inoffensifs. 
       - Interdit : Mots violents (war, missile, explosion).
       - Exemple : "tehran street", "industrial satellite", "concrete tunnel", "usa flag".
    """

    if theme == "dramatic":
        v95_directives += """
        [MODE DRAMATIQUE ACTIVÉ]
        - Ton : Urgent, grave, sensationnel.
        - Style : Utilise des mots d'impact (Urgent, Alerte, Historique).
        - Accroche : Doit donner l'impression que le monde vient de changer.
        """

    base = f"Tu es le cerveau derrière StudioEngine. Tu crées des Shorts en {lang_name} qui dominent les algorithmes par leur impact émotionnel et leur urgence. " \
           f"IMPORTANT: Toute ta réponse doit être en {lang_name}. "
    
    return f"{base}\n{v95_directives}\n" \
           f"ÉTAPE 2 : EXÉCUTION\n" \
           f"Tu réponds UNIQUEMENT en JSON valide avec 'title', 'hook', 'scenes' (tableau d'objets avec 'text' et 'search_keywords'), et 'cta'."

def get_user_prompt(title: str, body: str, duration_desc: str, scene_count: int, language: str = "fr") -> str:
    """Génère le prompt utilisateur dans la langue cible."""
    
    labels = {
        "fr": {
            "instruction": f"Crée un script viral {duration_desc} capable de générer 1M de vues.",
            "hook": "Accroche 'Stop-scroll' choc (max 8 mots, curiosité maximale)",
            "text": "Narration rapide (max 15 mots par scène, impact maximum)",
            "cta": "CTA viral (ex: Abonne-toi pour ne rien rater !)",
            "title_label": "Titre clic-bait efficace"
        },
        "en": {
            "instruction": f"Create a viral {duration_desc} script designed to hit 1M views.",
            "hook": "Stop-scroll shock hook (max 8 words, extreme curiosity)",
            "text": "Fast-paced narration (max 15 words per scene, high impact)",
            "cta": "Viral CTA (e.g., Subscribe for more fire content!)",
            "title_label": "High-CTR clickbait title"
        },
        "ru": {
            "instruction": f"Создайте вирусный сценарий {duration_desc}, способный набрать 1 миллион просмотров.",
            "hook": "Шокирующий хук (максимум 8 слов, максимальное любопытство)",
            "text": "Быстрое повествование (макс. 15 слов на сцену, макс. эффект)",
            "cta": "Вирусный призыв (например, Подпишись, чтобы не пропустить!)",
            "title_label": "Привлекательный кликбейт-заголовок"
        }
    }
    
    L = labels.get(language, labels["fr"])
    
    return f"""Article du jour :
Titre : {title}
Résumé : {body}

{L['instruction']}

Réponds en JSON avec exactement cette structure :
{{
  "hook": "{L['hook']}",
  "scenes": [
    {{
      "text": "Narration détaillée (entre 15 et 25 mots par scène. IMPORTANT : Utilise uniquement des guillemets simples ' pour les citations internes !)",
      "search_keywords": "3-4 simple English keywords for stock photo search. Example: 'military satellite', 'iran desert'."
    }}
  ],
  "cta": "{L['cta']}",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
  "title": "{L['title_label']}"
}}

Génère exactement {scene_count} scenes. Pas de guillemets doubles imbriqués dans les chaînes JSON !"""



def generate_script_ollama(news_data: dict, args: argparse.Namespace) -> dict:
    """Génère le script via Ollama local API (llama3, etc)."""
    ollama_url = "http://localhost:11434/api/generate"
    model = os.getenv("OLLAMA_MODEL", "llama3")
    
    scene_count = 12
    duration_desc = "de 55 secondes environ"
    
    prompt = get_user_prompt(
        title=news_data["title"],
        body=news_data["body"][:12000],
        duration_desc=duration_desc,
        scene_count=scene_count,
        language=getattr(args, 'language', 'fr')
    )
    
    sys_prompt = get_system_prompt(getattr(args, 'theme', 'actualités'), getattr(args, 'language', 'fr'))
    
    payload = {
        "model": model,
        "prompt": f"{sys_prompt}\n\n{prompt}",
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(ollama_url, json=payload, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        raw = res_json.get("response", "")
        script = json.loads(raw)
        return script
    except Exception as e:
        print(f"[generate_script] Ollama error: {e}", file=sys.stderr)
        return None

def check_ollama() -> bool:
    """Vérifie si Ollama est en ligne."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

def generate_script_groq(news_data: dict, args: argparse.Namespace) -> dict:
    """Génère le script via Groq API (LLM)."""
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Force 12 scenes for V9.6
    scene_count = 12
    duration_desc = "de 55 secondes environ"

    prompt = get_user_prompt(
        title=news_data["title"],
        body=news_data["body"][:12000],
        duration_desc=duration_desc,
        scene_count=scene_count,
        language=getattr(args, 'language', 'fr')
    )

    sys_prompt = get_system_prompt(getattr(args, 'theme', 'actualités'), getattr(args, 'language', 'fr'))
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    script = json.loads(raw)

    # Post-parsing cleanup: remove double quotes inside texts if any
    if "scenes" in script:
        for scene in script["scenes"]:
            if "text" in scene:
                scene["text"] = scene["text"].replace('"', "'")
    
    assert "hook" in script and "scenes" in script, "Script JSON invalide"
    assert len(script["scenes"]) >= 3, "Pas assez de scènes"

    return script


def normalize_script(script: dict) -> dict:
    """Ensure the script dict has the required keys: hook, scenes, title, hashtags."""
    if not isinstance(script, dict):
        return {"hook": "", "scenes": [], "title": "Sans titre", "hashtags": []}
        
    # Normalize 'scenes' key
    for alt in ["scene", "scènes", "scène", "list_scenes", "content", "scenes_list"]:
        if alt in script and "scenes" not in script:
            script["scenes"] = script[alt]
            break
            
    if "scenes" not in script or not isinstance(script["scenes"], list):
        script["scenes"] = []
        
    # Normalize 'hook' key
    for alt in ["accroche", "intro", "hook_text", "introduction", "hook_phrase"]:
        if alt in script and "hook" not in script:
            script["hook"] = str(script[alt])
            break
            
    if "hook" not in script:
        script["hook"] = ""
            
    # Normalize 'title' key
    for alt in ["titre", "titre_reel", "video_title", "headline"]:
        if alt in script and "title" not in script:
            script["title"] = str(script[alt])
            break
            
    if "title" not in script:
        script["title"] = "ACTU DU JOUR"
            
    # Normalize 'hashtags' key
    for alt in ["tags", "mots_clés", "keywords", "hash_tags"]:
        if alt in script and "hashtags" not in script:
            script["hashtags"] = script[alt]
            break
            
    if "hashtags" not in script or not isinstance(script["hashtags"], list):
        script["hashtags"] = ["#news", "#actu"]
            
    # Ensure nested keys are present in scenes
    for scene in script["scenes"]:
        if not isinstance(scene, dict): continue
        if "narration" in scene and "text" not in scene:
            scene["text"] = scene["narration"]
        if "vidéo" in scene and "text" not in scene:
             scene["text"] = scene["vidéo"]
             
        if "visuel" in scene and "image_prompt" not in scene:
            scene["image_prompt"] = scene["visuel"]
        if "search_keywords" in scene and "image_prompt" not in scene:
            scene["image_prompt"] = scene["search_keywords"]
        
        # Default empty strings to prevent downstream crashes
        if "text" not in scene: scene["text"] = ""
        if "image_prompt" not in scene: scene["image_prompt"] = ""
            
    return script

def generate_script_gemini(news_data: dict, args: argparse.Namespace, custom_prompt: str = "") -> dict:
    """Génère le script via Google Gemini Pro API."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[generate_script] google-genai not installed", file=sys.stderr)
        raise ImportError("google-genai not installed")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    model_id = 'gemini-2.0-flash'


    scene_count = 12
    duration_desc = "de 55 secondes environ"

    if custom_prompt:
        prompt = f"{custom_prompt}\n\nContexte de l'article :\n{news_data['title']}\n{news_data['body'][:8000]}"
    else:
        prompt = get_user_prompt(
            title=news_data["title"],
            body=news_data["body"][:12000],
            duration_desc=duration_desc,
            scene_count=scene_count,
            language=getattr(args, 'language', 'fr')
        )

    sys_prompt = get_system_prompt(getattr(args, 'theme', 'actualités'), getattr(args, 'language', 'fr'))

    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=f"{sys_prompt}\n\n{prompt}",
        config=types.GenerateContentConfig(
            candidate_count=1,
            max_output_tokens=2000,
            temperature=0.7,
            response_mime_type="application/json",
        )
    )

    try:
        # Nettoyage sommaire si le JSON est dans des backticks
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        script = json.loads(text)
    except Exception as e:
        print(f"[generate_script] Gemini JSON parsing error: {e}", file=sys.stderr)
        raise e

    return script


def generate_script_local(news_data: dict, args: argparse.Namespace = None) -> dict:
    """
    Fallback local : génère un script basique à partir du titre et du corps.
    Aucune API requise — produit un script fonctionnel pour le pipeline.
    """
    is_long = getattr(args, 'long', False)
    target_scenes = 50 if is_long else 20
    title = news_data.get("title", "Actualité du jour")
    body  = news_data.get("body", news_data.get("summary", ""))
    category = news_data.get("category", "world")

    # Nettoie le titre (enlève le nom du journal après " - ")
    clean_title = re.split(r'\s*[-–—|]\s*(?:Le Monde|Franceinfo|BFM|TF1|BFMTV|France\s?\d|20 Minutes|L\'Express|Libération|Les Échos)', title)[0].strip()
    if len(clean_title) < 10:
        clean_title = title

    # Coupe le corps en phrases
    sentences = re.split(r'(?<=[.!?])\s+', body)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:10]

    # Hook : version courte du titre
    hook = clean_title[:80]
    if len(hook) > 60:
        hook = hook[:60].rsplit(" ", 1)[0] + "..."

    # Génère les scènes à partir du contenu
    scenes = []
    scene_count = min(target_scenes, max(3, len(sentences)))

    # Image prompts par catégorie
    img_styles = {
        "world":      ["war correspondent reporting", "political summit meeting", "world map with highlights", "UN assembly hall", "international newspaper headlines"],
        "technology": ["futuristic tech lab", "programmer coding on screens", "microchip close-up", "silicon valley aerial", "users with smartphones"],
        "business":   ["stock market display board", "corporate meeting boardroom", "financial charts analysis", "business newspaper front page", "city financial district"],
        "ai":         ["neural network visualization", "AI robot humanoid face", "data center server room", "holographic display interface", "machine learning algorithm visualization"],
        "crypto":     ["bitcoin gold coin close-up", "cryptocurrency trading dashboard", "blockchain network diagram", "mining farm hardware", "digital wallet on phone"],
        "trending":   ["trending social media feeds", "viral content spreading", "crowd watching big screen", "breaking news studio", "smartphone notification alerts"],
    }
    prompts = img_styles.get(category, img_styles["world"])

    # Distribue les phrases dans les scènes
    for i in range(scene_count):
        if i < len(sentences):
            text = sentences[i]
        elif i == 0:
            text = f"Voici ce qu'il faut retenir de l'actualité : {clean_title}."
        else:
            text = f"Une affaire à suivre de très près dans les prochains jours."

        # Limite à ~2 phrases par scène
        if len(text) > 160:
            text = text[:160].rsplit(" ", 1)[0] + "."

        scenes.append({
            "text": text,
            "image_prompt": f"{prompts[i % len(prompts)]}, cinematic lighting, photorealistic, vertical 9:16, 4K news style",
        })

    # Pad to target scenes if needed
    while len(scenes) < target_scenes:
        scenes.append({
            "text": "Restez informés, suivez-nous pour plus d'actualités chaque jour !",
            "image_prompt": f"social media news application interface, modern smartphone, cinematic 9:16",
        })

    hashtags_map = {
        "world":     ["#breaking", "#news", "#world", "#viral", "#foryou"],
        "technology":["#tech", "#innovation", "#ai", "#future", "#scitech"],
        "business":  ["#money", "#business", "#success", "#finance", "#wealth"],
        "ai":        ["#ai", "#automation", "#future", "#technology", "#chatgpt"],
        "crypto":    ["#crypto", "#bitcoin", "#eth", "#trading", "#bitcoinnews"],
        "trending":  ["#viral", "#trending", "#foryou", "#shortsvideo", "#fyp"],
    }

    return {
        "hook": hook,
        "scenes": scenes[:target_scenes],
        "cta": "Suivez-nous pour l'actu quotidienne ! 📲",
        "hashtags": hashtags_map.get(category, ["#news", "#actu", "#fr", "#viral", "#info"]),
        "title": clean_title[:100],
    }


def main(args: argparse.Namespace) -> None:
    input_path = BASE_DIR / "output" / "news_data.json"
    if args.test or args.dry_run or not input_path.exists():
        news_data = {
            "title": "Test : L'IA révolutionne la création de contenu en 2025",
            "body": "En 2025, les outils d'intelligence artificielle permettent aux créateurs de produire "
                    "des vidéos professionnelles en quelques minutes. Des studios entiers sont remplacés "
                    "par des pipelines automatisés. TikTok, Instagram et YouTube voient une explosion "
                    "du contenu généré par IA.",
            "category": "ai",
        }
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            news_data = json.load(f)

    groq_key = os.getenv("GROQ_API_KEY", "")
    has_groq = groq_key and groq_key != "your_groq_api_key_here" and len(groq_key) > 10
    
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY_1") or os.getenv("GOOGLE_API_KEY")
    has_gemini = gemini_key and len(gemini_key) > 10
    
    script = None

    if has_gemini:
       # Update environment variable so the gemini library finds it if needed
       os.environ["GEMINI_API_KEY"] = gemini_key

    if (has_gemini or args.custom_prompt) and not args.dry_run:
        print(f"[generate_script] Using Gemini Pro API...", file=sys.stderr)
        try:
            script = generate_script_gemini(news_data, args, custom_prompt=args.custom_prompt)
            if not script or not script.get("scenes") or len(script["scenes"]) < 2:
                print("[generate_script] Gemini returned incomplete script, falling back...", file=sys.stderr)
                script = None
        except Exception as e:
            print(f"[generate_script] Gemini error: {e}, falling back...", file=sys.stderr)
            script = None

    if script is None and has_groq and not args.dry_run:
        # V14.0: AUTO-DRAMA DETECTION
        current_theme = args.theme
        title_lower = news_data.get("title", "").lower()
        if any(wk in title_lower for wk in ["guerre", "war", "iran", "israel", "conflit"]):
            current_theme = "dramatic"
            
        print(f"[generate_script] Using Groq API (LLM) with theme: {current_theme}...", file=sys.stderr)
        try:
            # Overriding theme temporarily for prompt generation
            temp_args = argparse.Namespace(**vars(args))
            temp_args.theme = current_theme
            script = generate_script_groq(news_data, temp_args)
        except Exception as e:
            print(f"[generate_script] Groq error: {e}, falling back...", file=sys.stderr)
            script = None

    if script is None and check_ollama() and not args.dry_run:
        print("[generate_script] Using local Ollama...", file=sys.stderr)
        script = generate_script_ollama(news_data, args)

    if script is None:
        print("[generate_script] Using local smart template...", file=sys.stderr)
        script = generate_script_local(news_data, args)
    
    if script is not None:
        script = normalize_script(script)

    output = {
        "news": news_data,
        "script": script,
    }

    output_path = BASE_DIR / "output" / "script_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[generate_script] Saved to {output_path}", file=sys.stderr)
    
    if args.test or args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate video script via Groq or local template")
    parser.add_argument("--test", action="store_true", help="Use test data")
    parser.add_argument("--dry-run", action="store_true", help="Use local template and test data")
    parser.add_argument("--custom-prompt", default="", help="Custom prompt for Gemini")
    parser.add_argument("--category", default="", help="News category")
    parser.add_argument("--long", action="store_true", help="Generate 3-5 minute video script")
    parser.add_argument("--theme", default="actualités", help="Theme/Tone of the video (amical, professionnel, etc.)")
    parser.add_argument("--language", default="fr", help="Target language (fr, en)")
    main(parser.parse_args())
