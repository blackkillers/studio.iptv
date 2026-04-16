import json
import os
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
WEEKLY_FILE = DATA_DIR / "weekly_memory.json"

def log_daily_trend(topic: str, description: str = ""):
    """Saves the wining trend of the day for the Sunday recap."""
    DATA_DIR.mkdir(exist_ok=True)
    
    data = []
    if WEEKLY_FILE.exists():
        try:
            with open(WEEKLY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except: data = []
        
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }
    
    # Avoid duplicate day entries
    data = [d for d in data if d["date"] != entry["date"]]
    data.append(entry)
    
    # Keep only 14 days of history
    data = data[-14:]
    
    with open(WEEKLY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_weekly_top_topics(limit: int = 10) -> list:
    """Returns the consolidated list for the Sunday Top 10."""
    if not WEEKLY_FILE.exists(): return []
    
    with open(WEEKLY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Process or sort if needed, for now just the most recent
    return data[-limit:]
