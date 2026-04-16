# -*- coding: utf-8 -*-
import asyncio
import subprocess
import time
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
import redis

# Setup Path & Logger
ROOT_DIR = Path(__file__).resolve().parent.parent

# Switching logic V24
PLATFORM = "cloud" if os.environ.get("CloudNode_SERVICE_ID") or os.path.exists("/app") else "local"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6373/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

logger = logging.getLogger("STUDIO.PerpetualEmpire")
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] PerpetualEmpire: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

async def run_production_cycle():
    """Exécute un cycle complet si le nœud est actif."""
    
    # Check if this instance is the Master
    active_mode = r.get("studio:active_mode") or "cloud"
    if active_mode != PLATFORM:
        logger.info(f"[SHADOW] Nœud {PLATFORM.upper()} en veille. Mode actif : {active_mode.upper()}")
        return

    logger.info(f"[EMPIRE] --- STARTING PRODUCTION CYCLE on {PLATFORM.upper()} ---")
    
    cmd = [
        sys.executable, str(ROOT_DIR / "main.py"),
        "--subject", "AUTO",
        "--langs", "fr,en,ru",
        "--format", "short",
        "--style", "viral",
        "--mode", "titan" # Cloud Titan stability
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        while True:
            line = await process.stdout.readline()
            if not line: break
            logger.info(f"  [LOG] {line.decode('utf-8', errors='ignore').strip()}")
            
        await process.wait()
        logger.info(f"[EMPIRE] Cycle de production terminé avec code : {process.returncode}")
        
    except Exception as e:
        logger.error(f"[EMPIRE] Erreur critique lors du cycle : {e}")

async def main():
    """Main loop for perpetual production."""
    # Production schedule: Every 8 hours (3x per day)
    INTERVAL = 28800 
    
    logger.info(f"[EMPIRE] --- LE PRESENTATEUR LOOP V24.0 STARTING ---")
    logger.info(f"Platerforme : {PLATFORM.upper()} | Intervalle : {INTERVAL}s")
    
    while True:
        await run_production_cycle()
        
        # Log countdown
        next_run = datetime.fromtimestamp(time.time() + INTERVAL).strftime('%H:%M:%S')
        logger.info(f"[EMPIRE] En attente de la prochaine ronde à : {next_run}")
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Boucle Empire arrêtée.")
