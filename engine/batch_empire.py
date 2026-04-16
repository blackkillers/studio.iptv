#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
import io
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Notification integration
try:
    from engine.pipeline_run import notify_sync
except ImportError:
    def notify_sync(m): print(f"Notify: {m}")

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent

def run_command(cmd):
    print(f"\n[batch_empire] Executing: {' '.join(cmd)}\n", flush=True)
    return subprocess.run(cmd, check=False)

def main():
    parser = argparse.ArgumentParser(description="Empire Phase 2: 15-Short Scheduled Batch")
    parser.add_argument("--category", default="technology", help="News category")
    parser.add_argument("--interval", type=int, default=30, help="Interval in minutes")
    parser.add_argument("--count", type=int, default=5, help="Number of subjects")
    parser.add_argument("--start-offset", type=int, default=30, help="Start delay in minutes")
    parser.add_argument("--article-offset", type=int, default=0, help="Index of the first article")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually generate/post")
    args = parser.parse_args()

    # 1. Fetch News to get multiple topics
    # We fetch more than args.count to have a good selection pool (offset + count + buffer)
    fetch_count = args.article_offset + args.count + 5
    news_cmd = [
        sys.executable, str(BASE_DIR / "engine" / "fetch_news.py"),
        "--category", args.category,
        "--max-items", str(fetch_count),
        "--test"
    ]
    res = subprocess.run(news_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error fetching news: {res.stderr}")
        return

    try:
        news_data = json.loads(res.stdout)
        articles = news_data.get("all_articles", [])
    except Exception as e:
        print(f"Error parsing news JSON: {e}")
        return

    if not articles:
        print("No articles found.")
        return

    # Apply article offset (skip previous batch)
    subjects = articles[args.article_offset:args.article_offset + args.count]
    languages = ["fr", "en", "ru"]
    
    # 2. Starting time (T + start_offset min)
    current_time = datetime.now(timezone.utc) + timedelta(minutes=args.start_offset)
    
    notify_sync(f"📡 <b>EMPIRE BATCH DÉMARRÉ</b>\nNombre de sujets: {args.count}\nIntervalle: {args.interval} min")

    total_runs = 0
    for i, article in enumerate(subjects):
        title = article.get("title", "")
        print(f"\nSUBJECT {i+1}/{args.count}: {title}", flush=True)
        notify_sync(f"🎬 <b>SUJET {i+1}/{args.count} :</b>\n{title}")
        
        for lang in languages:
            publish_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"  Language: {lang.upper()} | Scheduled: {publish_str}", flush=True)
            
            cmd = [
                sys.executable, str(BASE_DIR / "engine" / "pipeline_run.py"),
                "--language", lang,
                "--title", title,
                "--publish-at", publish_str,
                "--category", args.category
            ]
            
            if args.dry_run:
                print(f"  [DRY RUN] Would execute: {' '.join(cmd)}")
            else:
                run_command(cmd)
            
            # Increment interval
            current_time += timedelta(minutes=args.interval)
            total_runs += 1

    print(f"\n✅ Empire Batch Complete. {total_runs} videos handled.")

if __name__ == "__main__":
    main()
