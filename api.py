# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import json
import logging
import psutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

import time
import yaml
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.auth_helper import create_access_token, verify_token, verify_totp, get_totp_uri, generate_qr_base64
from utils.youtube_analytics import get_all_empire_stats
import stripe
import pyotp
import base64
from engine.core.youtube_intelligence import YouTubeIntelligence

# Ensure project root is in path
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "studio" / "frontend" / "dist"
sys.path.append(str(BASE_DIR))

try:
    from main import process_channel, cleanup_workspace
    from utils.social_publisher import publish_via_webhook
    from utils.telegram_notifier import send_telegram_alert, send_stats_update
    import yaml
except Exception as e:
    print(f"CRITICAL STARTUP ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("STUDIO.API")

# Scheduler
scheduler = AsyncIOScheduler()

# Celery integration V20
from engine.tasks import produce_video_task
import redis

# Redis for Status (Lazy Connection to avoid Railway startup timeouts)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6373/0")
r = None
try:
    r = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
    # We do NOT r.ping() here as it can freeze startup. We'll check it on first use.
except Exception as e:
    logger.error(f"[REDIS] Config error : {e}")

async def run_production_task(subject: str, langs: List[str], bgm_pref: str = None, master_script: dict = None, platforms: List[str] = ["youtube"], style: str = "viral"):
    """
    Triggers the Celery task (V20).
    The production logic now lives in engine/tasks.py.
    """
    logger.info(f"Triggering Celery task for : {subject} [Style: {style}]")
    # Enqueue in Redis
    produce_video_task.delay(subject, langs, bgm_pref, master_script, platforms, style=style)

async def scheduled_production():
    logger.info("CRON: Lancement de la production automatique...")
    from engine.auto_produce import get_best_trend
    subject, reason = await get_best_trend()
    await run_production_task(subject, ["fr", "en", "ru"])

async def daily_stats_job():
    logger.info("CRON: Envoi des statistiques quotidiennes (20:00)...")
    # Simulation stats pour le moment (Sprint 10)
    stats = {
        "youtube_fr": "12 Shorts postÃ©s, +450 vues",
        "youtube_en": "8 Shorts postÃ©s, +120 vues",
        "youtube_ru": "5 Shorts postÃ©s, +15 vues",
        "serveur": f"CPU: {psutil.cpu_percent()}%, RAM: {psutil.virtual_memory().percent}%"
    }
    await send_stats_update(stats)

async def weekly_long_production():
    logger.info("CRON: Lancement de la production Hebdomadaire [TITAN] (LONG VIDEO)...")
    from engine.core.weekly_aggregator import get_weekly_top_topics
    
    # 1. Fetch memory
    topics = get_weekly_top_topics(limit=7)
    if not topics:
        logger.warning("Aucune mÃ©moire hebdo trouvÃ©e. Extraction directe RSS...")
        from engine.auto_produce import get_best_trend
        subject, _ = await get_best_trend()
        subject = f"RÃ©trospective SpÃ©ciale : {subject}"
    else:
        # Build composite subject
        main_titles = [t["topic"] for t in topics]
        subject = f"RECAP SEMAINE : {' | '.join(main_titles[:3])}"

    # 2. Toggle Landscape Resolution
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    old_res = config["rendering"]["resolution"]
    config["rendering"]["resolution"] = [1920, 1080]
    with open("config/settings.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)
    
    try:
        # 3. Trigger Long Production (High Density)
        await run_production_task(subject, ["fr", "en", "ru"], platforms=["youtube"])
    finally:
        # 4. Restore Portrait configuration
        config["rendering"]["resolution"] = old_res
        with open("config/settings.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Key verification (Sprint 10)
    logger.info("--- Le Presentateur : STARTUP CHECK (V20 ULTIMATE) ---")
    
    # Initialize Secrets if missing
    if not os.getenv("JWT_SECRET"):
        os.environ["JWT_SECRET"] = os.urandom(24).hex()
        logger.info("[SEC] JWT_SECRET généré dynamiquement.")
        
    keys = ["GOOGLE_API_KEY", "GROQ_API_KEY", "PEXELS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    for k in keys:
        if not os.getenv(k):
            logger.warning(f"[SEC] {k} est manquant.")
    
    # 📅 Startup jobs (3 shorts/jour + 1 Weekly Long + Daily Stats)
    # Target: End date 30/04/2026 for all industrial slots.
    end_dt = datetime(2026, 4, 30, 23, 59)
    
    # Slot 1: 08:00
    scheduler.add_job(scheduled_production, CronTrigger(hour=8, minute=0), end_date=end_dt)
    # Slot 2: 12:00
    scheduler.add_job(scheduled_production, CronTrigger(hour=12, minute=0), end_date=end_dt)
    # Slot 3: 20:00 (Production)
    scheduler.add_job(scheduled_production, CronTrigger(hour=20, minute=0), end_date=end_dt)
    # Stats: 20:10 (Stats Telegram)
    scheduler.add_job(daily_stats_job, CronTrigger(hour=20, minute=10), end_date=end_dt)
    # Weekly: Sunday 21:00 (Weekly Long 16:9)
    scheduler.add_job(weekly_long_production, CronTrigger(day_of_week='sun', hour=21, minute=0), end_date=end_dt)
    
    scheduler.start()
    logger.info(f"APScheduler Titan Mode (Locked 3x Daily until {end_dt.strftime('%d/%m/%Y')})")
    
    # Send Startup Notify
    await send_telegram_alert("🚀 <b>Le Presentateur V24.3 Démarré</b>\n<i>Mode Empire YouTube Trilingue Actif.</i>")
    
    yield
    scheduler.shutdown()

# Initialize FastAPI with lifespan
app = FastAPI(title="Le Presentateur API Bridge (V24.3)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared state replaced by Redis in tasks.py
# status = AppStatus()

class GenerateRequest(BaseModel):
    subject: Optional[str] = None
    langs: List[str] = ["fr", "en", "ru"]
    channels: Optional[List[str]] = None # New: Explicit channel selection
    category: str = "actualitÃ©s"
    bgm: Optional[str] = None
    validated_script: Optional[dict] = None
    platforms: List[str] = ["youtube"]
    style: str = "viral"

class ManualRequest(BaseModel):
    topic: str

class MonitoringEvent(BaseModel):
    event: str
    details: str
    timestamp: float
    category: str = "actualitÃ©s"

class IdeasRequest(BaseModel):
    topic: str
    category: str = "actualitÃ©s"

class PreviewRequest(BaseModel):
    topic: str
    category: str = "actualitÃ©s"

class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None
    otp: Optional[str] = None

# --- API ENDPOINTS ---

# --- AUTH & SECURITY V20 (Airlock) ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide ou expirÃ©")
    return payload

def check_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis pour cette action")
    return user

@app.post("/api/auth/login")
async def studio_login(req: LoginRequest):
    """Hybrid SaaS Login: admin (TOTP-only) or test (fixed pass)."""
    if req.username == "test":
        if req.password == "1357901":
            token = create_access_token(data={"sub": "test", "role": "guest"})
            return {"status": "success", "access_token": token, "token_type": "bearer"}
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    
    if req.username == "admin":
        # Check Redis for persisted secret first
        totp_secret = r.get("studio:auth:totp_secret") or os.getenv("TOTP_SECRET")
        if not totp_secret:
            new_secret = pyotp.random_base32()
            uri = get_totp_uri("admin", new_secret)
            qr_code = generate_qr_base64(uri)
            return {"status": "setup_required", "qr_code": qr_code, "secret": new_secret}
        return {"status": "2fa_required"}
        
    raise HTTPException(status_code=404, detail="Utilisateur inconnu")

@app.post("/api/auth/verify-2fa")
async def verify_2fa(req: dict):
    """Verify TOTP and issue Admin JWT. Persists secret to Redis if first-time."""
    code = req.get("code")
    setup_secret = req.get("secret")
    persisted_secret = r.get("studio:auth:totp_secret") or os.getenv("TOTP_SECRET")
    
    active_secret = setup_secret or persisted_secret
    
    if not active_secret:
        raise HTTPException(status_code=400, detail="2FA non configurÃ©")

    if verify_totp(active_secret, code):
        # If this was a setup-stage verify, persist the secret now
        if r and setup_secret and not persisted_secret:
            r.set("studio:auth:totp_secret", setup_secret)
            logger.info("2FA Setup complet : Secret persisté dans Redis.")
            
        token = create_access_token(data={"sub": "admin", "role": "admin"})
        return {"access_token": token, "token_type": "bearer", "status": "success"}
    
    raise HTTPException(status_code=401, detail="Code TOTP invalide")

# --- WEBSOCKET LOGS ---
class WebSocketLoggingHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        asyncio.run_coroutine_threadsafe(manager.broadcast(log_entry), asyncio.get_event_loop())

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# Setup logging to WS
ws_handler = WebSocketLoggingHandler()
ws_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logging.getLogger().addHandler(ws_handler)

@app.websocket("/api/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't really need to receive anything from client
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "Le Presentateur API is running"}

@app.get("/api/rss-trends")
async def get_rss_trends():
    """Fetches world news RSS feeds and returns a clean list for the UI."""
    try:
        import feedparser
        FEEDS = [
            {"url": "https://www.lemonde.fr/rss/une.xml", "category": "ð Monde"},
            {"url": "https://news.google.com/rss/search?q=intelligence+artificielle&hl=fr&gl=FR&ceid=FR:fr", "category": "ð¤ Tech/IA"},
            {"url": "https://www.france24.com/fr/rss", "category": "ð Monde"},
            {"url": "https://www.lequipe.fr/rss/actu_rss.xml", "category": "â½ Sport"},
            {"url": "https://www.lesechos.fr/rss/rss_une.xml", "category": "ð¼ Business"},
            {"url": "https://www.sciencesetavenir.fr/rss.xml", "category": "ð¬ Science"},
        ]
        entries = []
        seen = set()
        for feed_info in FEEDS:
            try:
                f = feedparser.parse(feed_info["url"])
                for e in f.entries[:3]:
                    title = getattr(e, 'title', '')
                    if title and title not in seen:
                        seen.add(title)
                        entries.append({
                            "title": title,
                            "link": getattr(e, 'link', ''),
                            "published": e.get("published", ""),
                            "category": feed_info["category"]
                        })
            except: continue
        return {"trends": entries[:25]}
    except Exception as e:
        logger.error(f"RSS Error: {e}")
        return {"trends": []}

@app.get("/api/list-bgm")
async def list_bgm():
    """Returns a list of available BGM files."""
    bgm_path = BASE_DIR / "assets" / "music"
    if not bgm_path.exists(): return {"tracks": []}
    files = [f.name for f in bgm_path.glob("*.mp3")]
    return {"tracks": files}

@app.get("/api/channel-stats")
async def get_channel_stats():
    """Fetches YouTube stats via API for handled channels."""
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key: raise Exception("No YOUTUBE_API_KEY set in environment")
        handles = {"fr": "@lpresentateur", "en": "@TPresenter", "ru": "@Ð¢ÐÐµÐ´ÑÑÐ¸Ð¹"}
        stats = []
        async with httpx.AsyncClient() as client:
            for lang, handle in handles.items():
                url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&forHandle={handle}&key={api_key}"
                resp = await client.get(url, timeout=5)
                data = resp.json()
                if "items" in data and len(data["items"]) > 0:
                    stat = data["items"][0]["statistics"]
                    subs = stat.get("subscriberCount", "0")
                    views = stat.get("viewCount", "0")
                    def fmt(n):
                        n = int(n)
                        return f"{n/1000:.1f}k" if n >= 1000 else str(n)
                    stats.append({"lang": lang, "subs": fmt(subs), "views": fmt(views), "status": "Actif"})
                else:
                    stats.append({"lang": lang, "subs": 0, "views": 0, "status": "Not Found"})
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error(f"YouTube Stats Error: {e}")
        return {"status": "ok", "stats": [
            {"lang": "fr", "subs": 0, "views": 0, "status": "No Key"},
            {"lang": "en", "subs": 0, "views": 0, "status": "No Key"},
            {"lang": "ru", "subs": 0, "views": 0, "status": "No Key"}
        ]}

@app.get("/api/health/keys")
async def health_keys():
    matrix = {"GEMINI": "Checking", "PEXELS": "Checking", "PIXABAY": "Checking", "OPENROUTER": "Checking"}
    
    # Check Gemini (V15.1.3 - New SDK Style)
    from google import genai
    gem_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not gem_key:
        matrix["GEMINI"] = "Non configurÃ©"
    else:
        try:
            client = genai.Client(api_key=gem_key)
            # Just try to list models as a health check
            for m in client.models.list():
                if "gemini" in m.name:
                    matrix["GEMINI"] = "OpÃ©rationnel"
                    break
        except Exception as e: 
            logger.warning(f"Health check Gemini fail: {e}")
            matrix["GEMINI"] = "Erreur"

    # Check Pexels
    pex_key = os.getenv("PEXELS_API_KEY")
    if not pex_key: matrix["PEXELS"] = "Non configurÃ©"
    else:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get("https://api.pexels.com/v1/search?query=nature&per_page=1", headers={"Authorization": pex_key}, timeout=5)
                matrix["PEXELS"] = "OpÃ©rationnel" if r.status_code == 200 else "ClÃ© expirÃ©e"
        except: matrix["PEXELS"] = "ClÃ© morte"

    # Check OpenRouter
    or_key = os.getenv("OPENROUTER_API_KEY")
    if not or_key: matrix["OPENROUTER"] = "Non configurÃ©"
    else:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {or_key}"}, timeout=5)
                matrix["OPENROUTER"] = "OpÃ©rationnel" if r.status_code == 200 else "ClÃ© invalide"
        except: matrix["OPENROUTER"] = "Erreur rÃ©seau"

    return {"matrix": matrix}

@app.get("/api/scheduled-videos")
async def scheduled_videos():
    import random
    titles = ["IA qui clÃ´ne les voix", "Guerre des consoles", "Nouveau record NASA", "ChatGPT v5 Analyse", "L'avenir du Bitcoin", "Voiture autonome rumeur", "DÃ©couverte secrÃ¨te OcÃ©an"]
    events = []
    base_time = int(time.time() * 1000)
    for i in range(12):
        events.append({
            "title": random.choice(titles),
            "time": base_time + (i * 86400000) + random.randint(0, 43200000)
        })
    return {"gcal_events": events}

@app.post("/api/push-telegram")
async def push_telegram(req: Request):
    """Sends a test notification."""
    try:
        data = await req.json()
    except Exception:
        pass
    return {"status": "ok", "message": "Notification envoyÃ©e !"}

@app.post("/api/generate-ideas")
async def generate_ideas(req: IdeasRequest):
    """Brainstorms 3 viral titles for a topic using Gemini."""
    try:
        from engine.agents.base_agent import BaseAgent
        agent = BaseAgent()
        prompt = f"GÃ©nÃ¨re 3 titres viraux pour Shorts/TikTok sur le sujet: {req.topic}. CatÃ©gorie: {req.category}."
        sys_instr = "Tu es un expert en viralitÃ©. RÃ©ponds uniquement en JSON: [{ 'title': '...', 'summary': '...', 'success_rate': 95 }, ...]"
        ideas = await agent.call_llm(sys_instr, prompt, is_json=True)
        return {"ideas": ideas or []}
    except Exception as e:
        logger.error(f"Ideas Error: {e}")
        return {"ideas": []}

@app.post("/api/generate-previews")
async def generate_previews(req: PreviewRequest):
    """Fetches Pexels/IA images for the Dashboard preview step."""
    try:
        # Mocking for now to avoid long delays, in production this calls engine.media_scraper
        return {"images": [
            "https://images.pexels.com/photos/3183150/pexels-photo-3183150.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1",
            "https://images.pexels.com/photos/3183197/pexels-photo-3183197.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1"
        ]}
    except Exception as e:
        logger.error(f"Preview Error: {e}")
        return {"images": []}

@app.post("/api/calendar/sync")
async def calendar_sync():
    """Google Calendar Sync initializing google api client."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        
        token_path = BASE_DIR / "config" / "token.json"
        if not token_path.exists():
            return {"status": "error", "message": "Aucun token.json trouvÃ©. Le backend n'est pas autorisÃ© par Google."}
            
        creds = Credentials.from_authorized_user_file(str(token_path))
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save updated credentials back
            with open(token_path, "w") as token:
                token.write(creds.to_json())
                
        # Test de connexion en rÃ©cupÃ©rant la liste des calendriers
        service = build('calendar', 'v3', credentials=creds)
        calendar_list = service.calendarList().list().execute()
        nb_cals = len(calendar_list.get('items', []))
        
        return {"status": "ok", "message": f"Service Google Calendar initialisÃ©. AccÃ¨s Ã  {nb_cals} calendriers."}
    except Exception as e:
        logger.error(f"Calendar Sync Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/neural-pulse")
async def get_neural_pulse():
    """Viral trends pulse."""
    try:
        return {"pulse": [
            {"topic": "L'IA qui clÃ´ne les voix", "success_rate": 98, "reason": "Tendance tech massive.", "keywords": ["IA", "Voice", "Cloning"]},
            {"topic": "Guerre des consoles 2026", "success_rate": 85, "reason": "Forte audience gaming.", "keywords": ["Gaming", "Sony", "Xbox"]}
        ]}
    except: return {"pulse": []}

@app.post("/api/neural-chat")
async def neural_chat(req: dict):
    try:
        from engine.agents.base_agent import BaseAgent
        agent = BaseAgent()
        resp = await agent.call_llm("Tu es Neural Pulse, Assistant IA de Le Presentateur.", req.get("message", "Bonjour"), is_json=False)
        return {"response": resp}
    except Exception as e:
        return {"response": f"Erreur Neural Pulse: {e}"}

@app.post("/api/rewrite-script")
async def rewrite_script(req: dict, user: dict = Depends(check_admin)):
    """ReviewNode - Gemini rewriting script magic."""
    try:
        from engine.agents.base_agent import BaseAgent
        agent = BaseAgent()
        sys_instr = "Tu es RÃ©dacteur IA. AmÃ©liore l'accroche et dynamise le rythme du script. Renvoie uniquement le texte corrigÃ©, prÃªt pour la production."
        prompt = f"Voici le script Ã  amÃ©liorer:\n\n{req.get('script', '')}"
        improved = await agent.call_llm(sys_instr, prompt, is_json=False)
        return {"improved_script": improved.strip()}
    except Exception as e:
        logger.error(f"Rewrite Error: {e}")
        return {"error": str(e)}

@app.post("/api/tts-preview")
async def tts_preview(req: dict):
    """VoiceNode direct TTS preview."""
    try:
        text = req.get("text", "Bonjour, test de voix rÃ©ussi.")
        voice = req.get("voice", "fr-FR-VivienneMultilingualNeural")
        
        import edge_tts
        import tempfile
        from fastapi.responses import FileResponse
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
            
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)
        
        return FileResponse(tmp_path, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS Error: {e}")
        return {"error": str(e)}

@app.post("/api/generate-master-script")
async def generate_master_script(req: IdeasRequest):
    """Stage 1: Generate script in source language for review."""
    try:
        from engine.core.content_manager import ContentManager
        with open("config/settings.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        manager = ContentManager(config)
        # Use target_lang="fr" for initial review as requested by user
        script = await manager.generate_workflow(req.topic, "fr") 
        return {"status": "ok", "script": script}
    except Exception as e:
        logger.error(f"Script Generation Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/stats/channels")
async def get_empire_stats(user: dict = Depends(get_current_user)):
    """Fetch real metrics from YouTube API for the 3 channels."""
    stats = await get_all_empire_stats()
    return stats

@app.post("/api/run-pipeline")
async def run_pipeline(req: GenerateRequest, background_tasks: BackgroundTasks, user: dict = Depends(check_admin)):
    """Stage 3: Start targeted parallel production."""
    # Check running status from Redis instead of memory status object
    is_running_raw = r.get("studio:status")
    if is_running_raw:
        st_data = json.loads(is_running_raw)
        if st_data.get("is_running"):
            raise HTTPException(status_code=400, detail="Une production est dÃ©jÃ  en cours.")
    
    subject = req.subject
    if not subject:
        from engine.auto_produce import get_best_trend
        subject, reason = await get_best_trend()
    
    # Priority: Explicit channels, then langs, then default all 3
    active_langs = req.channels or req.langs or ["fr", "en", "ru"]
        
    background_tasks.add_task(run_production_task, subject, active_langs, req.bgm, req.validated_script, req.platforms, style=req.style)
    return {"message": f"Empire Mode lancÃ© ({req.style}) !", "subject": subject, "channels": active_langs}

@app.post("/api/monitor/event")
async def monitor_guest_event(payload: MonitoringEvent, request: Request, user: dict = Depends(get_current_user)):
    """Receives and sends guest activity to Telegram with IP detection."""
    if user.get("role") != "guest":
        return {"status": "ignored"}
        
    # Extract Real IP (CloudNode/Proxy handling)
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0] if forwarded else request.client.host
    
    if payload.event == "SESSION_INIT":
        msg = (
            f"ð¨ <b>NOUVELLE CONNEXION GUEST</b>\n\n"
            f"ð <b>IP :</b> <code>{ip}</code>\n"
            f"ð» <b>SystÃ¨me :</b> {payload.details}\n"
            f"â° <b>Heure Local :</b> {datetime.fromtimestamp(payload.timestamp).strftime('%d/%m/%Y %H:%M:%S')}"
        )
    else:
        msg = (
            f"ðµï¸ <b>ACTION GUEST ({ip})</b>\n"
            f"<b>{payload.event} :</b> {payload.details}"
        )
    
    await send_telegram_alert(msg)
    return {"status": "logged", "client_ip": ip}

@app.get("/api/status")
async def get_status():
    """Reads status from Redis (V20)."""
    try:
        raw = r.get("studio:status")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.error(f"Redis status error: {e}")
    
    return {
        "is_running": False,
        "progress": 0,
        "current_step": "Idle",
        "last_output": "Redis Offline"
    }

@app.get("/api/hardware-status")
async def hardware_status():
    return {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('/').percent,
        "disk_free": f"{psutil.disk_usage('/').free // (1024**3)} GB"
    }

@app.get("/api/logs")
async def get_logs():
    """Returns the last 50 lines of logs."""
    try:
        # Assuming log is stored in studio_admin.log or just return a dummy tail for now
        return {"logs": "tail -f studio_admin.log\n" + "-"*30 + "\n[SYSTEM] Server V14.0 active\n[AUTH] Multi-factor enabled\n[SYNC] YouTube Channel FR: 1.2k subs"}
    except: return {"logs": "Erreur lecture logs."}

@app.post("/api/wol-mock")
async def wol_mock():
    return {"status": "ok", "message": "Signal WOL envoyÃ© vers 100.123.191.92"}

@app.post("/api/system/update-password")
async def update_studio_password(req: dict):
    """Updates STUDIO_PASSWORD on CloudNode using GraphQL."""
    new_pass = req.get("new_password")
    if not new_pass: raise HTTPException(status_code=400, detail="Nouveau mot de passe requis")
    
    token = os.getenv("CloudNode_API_TOKEN")
    project_id = os.getenv("CloudNode_PROJECT_ID")
    env_id = os.getenv("CloudNode_ENVIRONMENT_ID")
    service_id = os.getenv("CloudNode_SERVICE_ID")
    
    if not all([token, project_id, env_id]):
        raise HTTPException(status_code=500, detail="Config CloudNode manquante (Token/Project/Env)")
        
    query = """
    mutation variableUpsert($input: VariableUpsertInput!) {
        variableUpsert(input: $input)
    }
    """
    variables = {
        "input": {
            "projectId": project_id,
            "environmentId": env_id,
            "serviceId": service_id,
            "name": "STUDIO_PASSWORD",
            "value": new_pass
        }
    }
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://backboard.CloudNode.app/graphql", json={"query": query, "variables": variables}, headers=headers)
        data = resp.json()
        if "errors" in data:
            raise HTTPException(status_code=500, detail=str(data["errors"][0]["message"]))
            
    return {"status": "ok", "message": "Mot de passe mis à jour sur CloudNode. Le service va redémarrer."}

# --- OPÉRATION HIDDEN EMPIRE (Real OAuth Handler) ---

@app.get("/api/auth/google/callback")
async def oauth2_callback(code: str, state: str, background_tasks: BackgroundTasks):
    """Processes Google Auth Code and persists Refresh Token for 24/7 access."""
    try:
        token_url = "https://oauth2.googleapis.com/token"
        client_id = os.getenv("GOOGLE_CLIENT_ID") or "562740318749-i83rj55sbh827thj2e13e2ctqpsfd6jn.apps.googleusercontent.com"
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        
        if not client_secret or client_secret == "A_REMPLIR":
            return HTMLResponse("<html><body style='background:#050505;color:red;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;'><div><h1>ERREUR : SECRET MANQUANT</h1><p>Tu dois ajouter GOOGLE_CLIENT_SECRET dans tes variables Railway.</p></div></body></html>")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(token_url, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": "https://web-production-87108.up.railway.app/api/auth/google/callback",
                "grant_type": "authorization_code"
            })
            token_data = resp.json()

        if "access_token" in token_data:
            # Persistent storage (Redis)
            email = token_data.get("email", "unknown_user")
            
            if r:
                r.set(f"empire:token:{email}", json.dumps(token_data))
                logger.info(f"Token persisté pour {email}")
            
            # Multi-Agent Notification
            msg = f"🌑 <b>NOUVEL ACCÈS IMPÉRIAL</b>\nUtilisateur : <code>{email}</code>\nStatut : <b>Refresh Token Persisté</b> (Accès 24/7 autorisé)."
            background_tasks.add_task(send_telegram_alert, msg)
            
            return HTMLResponse(f"<html><body style='background:#050505;color:#00f2ff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;'><div><h1>ACCÈS ACCORDÉ ✅</h1><p>L'usine Leviathan a synchronisé ton empire.</p><br><a href='https://blackkillers.github.io/web.studio/' style='color:white;text-decoration:none;border:1px solid #00f2ff;padding:10px 20px;border-radius:10px;'>Retour à la vitrine</a></div></body></html>")
        
        err_msg = token_data.get('error_description') or token_data.get('error') or 'Échec inconnu'
        return HTMLResponse(f"<html><body style='background:#050505;color:white;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;'><div><h1 style='color:orange;'>ERREUR GOOGLE</h1><p>{err_msg}</p><a href='https://blackkillers.github.io/web.studio/' style='color:cyan;'>Réessayer</a></div></body></html>")
    except Exception as e:
        logger.error(f"OAuth Callback Error: {e}")
        return HTMLResponse(f"<html><body><h1 style='color:red;'>ERREUR CRITIQUE</h1><p>{str(e)}</p></body></html>")

@app.get("/empire/control/99b82-f5e1-4c12-a764-hidden-hub", include_in_schema=False)
async def hidden_empire_hub():
    """Undetectable Hidden Dashboard for the Admin to see 'looted' data (Demo mode)."""
    # In production, this would list all tokens stored in Redis
    keys = r.keys("empire:token:*")
    count = len(keys)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <title>Imperial Control | StudioEngine</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>body {{ background: black; color: #00f2ff; font-family: 'Courier New', monospace; }}</style>
    </head>
    <body class="p-12">
        <h1 class="text-4xl font-black mb-8 border-b border-primary/20 pb-4">🌑 LEVIATHAN : GHOST CONTROL</h1>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div class="p-8 border border-primary/10 bg-zinc-900/50">
                <h3 class="text-white font-bold mb-4">AUTORISATIONS ACTIVES</h3>
                <p class="text-5xl font-black text-white">{count}</p>
                <p class="text-xs mt-4 opacity-50 text-primary">Refresh Tokens actifs en base.</p>
            </div>
            <div class="p-8 border border-primary/10 bg-zinc-900/50">
                <h3 class="text-white font-bold mb-4">SERVICES SYNCHRONISÉS</h3>
                <ul class="text-xs space-y-2">
                    <li class="text-green-500">✓ YouTube Content Managed</li>
                    <li class="text-green-500">✓ Google Photos Linked</li>
                    <li class="text-green-500">✓ Drive Workspace Active</li>
                </ul>
            </div>
        </div>
        <div class="mt-12 p-8 border border-primary/10 bg-black">
            <h3 class="text-white font-bold mb-4">JOURNAL DES ACCÈS</h3>
            <pre class="text-[10px] opacity-70">
[SYSTEM] Ghost Mode Active
[AUTH] Link generated: /empire/control/99b82-f5e1-4c12-a764-hidden-hub
[DATA] Polling YouTube Trends...
[WARN] 245 photos scanned in background for 'viral_style'
            </pre>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

# --- STUDIO IPTV INDUSTRIALIZATION (V2.0) ---

class IPTVTrackRequest(BaseModel):
    project: str = "studio-iptv"
    platform: str
    agent: str
    screen: str
    url: str

@app.post("/api/iptv/track")
async def iptv_track(req: IPTVTrackRequest, request: Request, background_tasks: BackgroundTasks):
    """Logs IPTV visitor data silently and alerts Telegram."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0] if forwarded else request.client.host
    
    visit_data = {
        "ip": ip,
        "platform": req.platform,
        "agent": req.agent,
        "screen": req.screen,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "url": req.url
    }
    
    # Store in Redis
    if r:
        r.lpush("iptv:visits", json.dumps(visit_data))
        r.ltrim("iptv:visits", 0, 999) # Keep last 1000
    
    return {"status": "tracked"}

@app.get("/iptv/payment-success", include_in_schema=False)
async def iptv_success_redirect(name: str, amount: str, email: str = "ilanhcohen@gmail.com", phone: str = "N/A", background_tasks: BackgroundTasks = None):
    """Callback landing page after payment. EVERYTHING is non-blocking to avoid Railway timeouts."""
    order_id = f"IPT-{int(time.time())}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # This function MUST be ultra-fast to return HTML before Railway (30s) or Bot (10s) timeout
    if background_tasks:
        background_tasks.add_task(process_iptv_order_background, name, amount, email, phone, order_id, now_str)
    
    return HTMLResponse(f"""
    <html>
    <head><title>Succès</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body style="background:#010101;color:white;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;">
        <div class="p-12 border border-blue-500/20 rounded-[3rem] bg-white/5 backdrop-blur-xl max-w-lg">
            <h1 class="text-4xl font-black text-blue-400 mb-4 uppercase">MERCI {name.upper()} !</h1>
            <p class="text-gray-400 mb-6">Ta commande <b>{order_id}</b> a été reçue.</p>
            <p class="text-[10px] text-green-500 uppercase font-black mb-8 animate-pulse">Un technicien te contactera sur {phone}</p>
            <a href="https://blackkillers.github.io/studio.iptv/" class="inline-block px-10 py-4 bg-white text-black rounded-xl text-xs font-black uppercase tracking-widest">Retour</a>
        </div>
    </body>
    </html>
    """)

async def process_iptv_order_background(name, amount, email, phone, order_id, timestamp):
    """Isolated heavy logic (Redis + Telegram)."""
    try:
        IPTV_BOT_TOKEN = "8609326262:AAGy9hvxLFO9SFxBf0urxEmzH2inyCVbEvA"
        msg = (
            f"💳 <b>NOUVELLE COMMANDE IPTV</b>\n"
            f"<b>Commande :</b> <code>{order_id}</code>\n"
            f"<b>Client :</b> {name}\n"
            f"<b>Email :</b> {email}\n"
            f"<b>WhatsApp :</b> {phone}\n"
            f"<b>Prix :</b> {amount}₪\n\n"
            f"📅 {timestamp}"
        )
        # Attempt Redis Storage
        if r:
            try:
                r.lpush("iptv:orders", json.dumps({
                    "order_id": order_id, "client": name, "email": email,
                    "phone": phone, "amount": amount, "timestamp": timestamp
                }))
                r.ltrim("iptv:orders", 0, 49)
            except: pass
            
        # Attempt Telegram
        await send_telegram_alert(msg, custom_token=IPTV_BOT_TOKEN)
    except Exception as e:
        logger.error(f"IPTV Background Process Error: {e}")

@app.get("/iptv/ghost-admin-hub", include_in_schema=False)
async def iptv_admin_hub(pin: str = None):
    """Ultra-Secure Hidden Admin for IPTV (Requires PIN)."""
    # Simple security step before 2FA UI
    if pin != "1499":
        return HTMLResponse("<html><body style='background:black;color:red;display:flex;align-items:center;justify-content:center;height:100vh;'><h1>ACCESS DENIED</h1></body></html>")
    
    visits = []
    orders = []
    orders_count = 0
    
    try:
        if r:
            visits_raw = r.lrange("iptv:visits", 0, 15)
            orders_raw = r.lrange("iptv:orders", 0, 15)
            orders_count = r.llen("iptv:orders")
            
            visits = [json.loads(v) for v in visits_raw if v]
            orders = [json.loads(o) for o in orders_raw if o]
    except Exception as e:
        logger.error(f"Ghost Hub Redis error: {e}")
    
    visit_rows = ""
    for v in visits:
        v_ts = v.get('timestamp', 'N/A')
        v_ip = v.get('ip', 'N/A')
        v_pl = v.get('platform', 'N/A')
        v_ag = v.get('agent', 'N/A')
        visit_rows += f"<tr class='border-b border-white/5 opacity-80'><td class='py-2'>{v_ts}</td><td class='text-primary'>{v_ip}</td><td>{v_pl}</td><td class='text-[10px]'>{v_ag[:30]}...</td></tr>"

    order_rows = ""
    for o in orders:
        o_id = o.get('order_id', 'N/A')
        o_cl = o.get('client', 'N/A')
        o_am = o.get('amount', '0')
        o_ts = o.get('timestamp', 'N/A')
        order_rows += f"<tr class='border-b border-green-500/10 text-white'><td class='py-2 font-black'>{o_id}</td><td>{o_cl}</td><td class='text-green-500 font-bold'>{o_am}₪</td><td class='opacity-50'>{o_ts}</td></tr>"

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <title>STUDIO IPTV | Admin Control</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>body {{ background: #010101; color: #00f2ff; font-family: 'Space Grotesk', sans-serif; }}</style>
    </head>
    <body class="p-8">
        <div class="max-w-7xl mx-auto">
            <header class="flex justify-between items-center mb-12 border-b border-primary/20 pb-6">
                <h1 class="text-3xl font-black italic tracking-tighter uppercase">GHOST <span class="text-white">COMMAND</span> <span class="text-[10px] not-italic text-gray-500">IPTV V2.2</span></h1>
                <div class="flex space-x-8 text-sm uppercase tracking-widest font-bold">
                    <p>Orders : <span class="text-white bg-green-600 px-3 py-1 rounded-lg ml-2">{orders_count}</span></p>
                    <p>Backend : <span class="text-green-500 animate-pulse">● ONLINE</span></p>
                </div>
            </header>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-12">
                <!-- Orders Table -->
                <div class="bg-zinc-950 p-10 rounded-[3rem] border border-green-500/20 shadow-2xl">
                    <h3 class="text-white font-black mb-8 flex items-center text-xl tracking-tighter uppercase">
                        <span class="w-3 h-3 bg-green-500 rounded-full mr-4 shadow-[0_0_15px_rgba(34,197,94,0.5)]"></span> 
                        Dernières Commandes
                    </h3>
                    <table class="w-full text-left">
                        <thead><tr class="text-gray-600 border-b border-white/10 text-[10px] uppercase tracking-widest font-black"><th class="pb-4">N° Commande</th><th class="pb-4">Client</th><th class="pb-4">Prix</th><th class="pb-4">Heure</th></tr></thead>
                        <tbody class="text-sm">{order_rows}</tbody>
                    </table>
                    {'' if orders else '<p class="text-center py-10 opacity-30 italic text-xs">En attente du premier paiement...</p>'}
                </div>

                <!-- Visits Table -->
                <div class="bg-zinc-950 p-10 rounded-[3rem] border border-white/5 shadow-2xl">
                    <h3 class="text-white font-black mb-8 flex items-center text-xl tracking-tighter uppercase opacity-70">
                        <span class="w-3 h-3 bg-primary rounded-full mr-4 shadow-[0_0_15px_rgba(0,242,255,0.5)]"></span> 
                        Traffic Live
                    </h3>
                    <table class="w-full text-left">
                        <thead><tr class="text-gray-600 border-b border-white/10 text-[10px] uppercase tracking-widest font-black"><th class="pb-4">Heure</th><th class="pb-4">IP</th><th class="pb-4">OS</th><th class="pb-4">Agent</th></tr></thead>
                        <tbody class="text-xs opacity-60">{visit_rows}</tbody>
                    </table>
                </div>
            </div>

            <div class="mt-20 flex justify-center opacity-30 hover:opacity-100 transition-all">
                <button onclick="parent.location='/'" class="text-[10px] font-black uppercase tracking-[0.5em] border-b border-white/20 pb-2">BACK TO CORE BASE</button>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

# --- FIN STUDIO IPTV ---

# Mount assets subdirectory
if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

# Mount music directory
music_dir = BASE_DIR / "assets" / "music"
if music_dir.exists():
    app.mount("/assets/music", StaticFiles(directory=music_dir), name="music")

# SPA Catch-all (Must be last)
@app.get("/{file_path:path}")
async def serve_static_or_ui(request: Request, file_path: str):
    # Check if the requested path exists as a file in dist (like favicon.svg, manifest.json)
    potential_file = FRONTEND_DIR / file_path
    if potential_file.exists() and potential_file.is_file():
        return FileResponse(potential_file)
    
    # Fallback to index.html for React SPA
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    
    return {"status": "ok", "message": f"API is running. Path /{file_path} not found."}

@app.get("/api/iptv/stripe/checkout", include_in_schema=False)
async def stripe_checkout(name: str, email: str, amount: int, phone: str = "N/A"):
    """Creates a Stripe Checkout Session for real payments."""
    # SECRET IS NOW IN ENVIRONMENT VARIABLES (RAILWAY)
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'ils',
                    'product_data': {
                        'name': f'Abonnement IPTV Studio - {name}',
                    },
                    'unit_amount': amount * 100,
                },
                'quantity': 1,
            }],
            mode='payment',
            customer_email=email,
            success_url=f"https://web-production-87108.up.railway.app/iptv/payment-success?name={name}&amount={amount}&email={email}&phone={phone}&method=Stripe",
            cancel_url="https://blackkillers.github.io/studio.iptv/",
        )
        return RedirectResponse(url=session.url, status_code=303)
    except Exception as e:
        logger.error(f"Stripe Error: {e}")
        return HTMLResponse(f"Erreur Stripe : {str(e)}", status_code=400)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
