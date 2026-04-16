#!/usr/bin/env python3
"""
post_social.py — Poste la vidéo sur TikTok, Instagram Reels, et Facebook Reels
Lit tts_data.json pour récupérer le chemin vidéo, titre, hashtags et miniature.
"""

import sys
import json
import argparse
import os
import time
import requests
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# YouTube imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    HAS_YOUTUBE = True
except ImportError:
    HAS_YOUTUBE = False

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def post_instagram_reel(video_path: str, caption: str,
                          account_id: str, access_token: str) -> dict:
    """
    Poste un Reel sur Instagram via Meta Graph API.
    """
    BASE = "https://graph.facebook.com/v19.0"

    print(f"[post_social] Uploading to Instagram account {account_id}...", file=sys.stderr)

    # 1. Créer un container de media
    # NOTE: Pour les Reels, on utilise le endpoint /media
    with open(video_path, "rb") as vf:
        upload_resp = requests.post(
            f"{BASE}/{account_id}/media",
            data={
                "media_type": "REELS",
                "caption": caption,
                "access_token": access_token,
            },
            files={"video": vf},
            timeout=120,
        )

    if upload_resp.status_code != 200:
        print(f"[post_social] IG Init Error: {upload_resp.text}", file=sys.stderr)
        return {"error": f"Instagram upload failed: {upload_resp.text}"}

    container_id = upload_resp.json().get("id")
    print(f"[post_social] IG container created: {container_id}", file=sys.stderr)

    # 2. Attendre le processing (max 3 min)
    for i in range(18):
        time.sleep(10)
        status_resp = requests.get(
            f"{BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        status = status_resp.json().get("status_code", "")
        print(f"[post_social] IG status ({i+1}): {status}", file=sys.stderr)
        if status == "FINISHED":
            break
        if status == "ERROR":
            return {"error": f"Instagram processing error: {status_resp.text}"}

    # 3. Publier
    pub_resp = requests.post(
        f"{BASE}/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    return pub_resp.json()


def post_facebook_reel(video_path: str, caption: str,
                        page_id: str, access_token: str) -> dict:
    """
    Poste un Reel sur Facebook via Meta Graph API.
    """
    BASE = "https://graph.facebook.com/v19.0"

    print(f"[post_social] Uploading to Facebook Page {page_id}...", file=sys.stderr)

    with open(video_path, "rb") as vf:
        resp = requests.post(
            f"{BASE}/{page_id}/videos",
            data={
                "description": caption,
                "published":   "true",
                "access_token": access_token,
            },
            files={"source": vf},
            timeout=120,
        )

    return resp.json()


def post_tiktok(video_path: str, caption: str, access_token: str) -> dict:
    """
    Poste une vidéo sur TikTok via Content Posting API.
    Utilise SELF_ONLY pour le mode Sandbox.
    """
    BASE = "https://open.tiktokapis.com/v2"

    print(f"[post_social] Initializing TikTok upload (Privacy: SELF_ONLY)...", file=sys.stderr)

    # 1. Initialiser l'upload
    init_resp = requests.post(
        f"{BASE}/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "post_info": {
                "title": caption[:150],
                "privacy_level": os.getenv("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"), 
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": os.path.getsize(video_path),
                "chunk_size": os.path.getsize(video_path),
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )

    if init_resp.status_code != 200:
        print(f"[post_social] TikTok Init Error: {init_resp.text}", file=sys.stderr)
        return {"error": f"TikTok init failed: {init_resp.text}"}

    data = init_resp.json().get("data", {})
    upload_url   = data.get("upload_url")
    publish_id   = data.get("publish_id")

    if not upload_url:
        return {"error": f"No upload_url from TikTok: {init_resp.text}"}

    # 2. Upload du fichier
    file_size = os.path.getsize(video_path)
    print(f"[post_social] Uploading file to TikTok ({file_size} bytes)...", file=sys.stderr)
    with open(video_path, "rb") as vf:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
                "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
            },
            data=vf,
            timeout=120,
        )

    print(f"[post_social] TikTok upload status: {upload_resp.status_code}", file=sys.stderr)
    return {"publish_id": publish_id, "upload_status": upload_resp.status_code}


def post_youtube_shorts(video_path: str, title: str, description: str,
                        tags: list[str], client_id: str, client_secret: str,
                        refresh_token: str, thumbnail_path: str = None, 
                        publish_at: str = None) -> dict:
    """
    Poste un Short sur YouTube via YouTube Data API v3.
    """
    if not HAS_YOUTUBE:
        return {"error": "YouTube dependencies (google-api-python-client) not installed"}

    print(f"[post_social] Uploading to YouTube Shorts: {title}", file=sys.stderr)

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )

        # Refresh token if needed
        if not creds.valid:
            creds.refresh(Request())

        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "22"  # People & Blogs
            },
            "status": {
                "privacyStatus": "private" if publish_at else "public",
                "selfDeclaredMadeForKids": False
            }
        }
        
        if publish_at:
            # YouTube API expects ISO 8601 (e.g. 2024-03-31T12:00:00Z)
            body["status"]["publishAt"] = publish_at
            print(f"[post_social] Scheduling video for: {publish_at}", file=sys.stderr)

        insert_request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
        )

        response = insert_request.execute()
        video_id = response.get('id')
        print(f"[post_social] YouTube upload success: {video_id}", file=sys.stderr)

        # Update thumbnail if provided
        if video_id and thumbnail_path and os.path.exists(thumbnail_path):
            try:
                print(f"[post_social] Setting YouTube thumbnail...", file=sys.stderr)
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
            except Exception as te:
                print(f"[post_social] YouTube Thumbnail minor error: {te}", file=sys.stderr)

        return response

    except Exception as e:
        print(f"[post_social] YouTube error: {e}", file=sys.stderr)
        return {"error": str(e)}


def build_caption(script: dict, category: str) -> str:
    """Construit la description/caption de la vidéo."""
    title    = script.get("title", "Actualité du jour")
    hook     = script.get("hook", "")
    hashtags = " ".join(script.get("hashtags", ["#news", "#actu", "#fr", "#viral", "#shortsvideo"]))
    caption  = f"{title}\n\n{hook}\n\n{hashtags}\n\n📱 Suivez-nous pour l'actualité chaque jour !"
    return caption[:2200]  # Limite Instagram


def cleanup_output():
    """Supprime les fichiers temporaires pour économiser l'espace disque."""
    print("[post_social] Cleaning up temporary media assets...", file=sys.stderr)
    folders = ["images", "audio"]
    for folder in folders:
        path = BASE_DIR / "output" / folder
        if path.exists():
            import shutil
            try:
                # On garde le dossier mais on vide le contenu
                for item in path.iterdir():
                    if item.is_file(): item.unlink()
                    elif item.is_dir(): shutil.rmtree(item)
                print(f"[post_social] ✓ Emptyied {folder}", file=sys.stderr)
            except Exception as e:
                print(f"[post_social] ⚠️ Cleanup error ({folder}): {e}", file=sys.stderr)
    
    # Supprimer aussi les vidéos intermédiaires
    try:
        vid_dir = BASE_DIR / "output" / "videos"
        if vid_dir.exists():
            for v in vid_dir.glob("video_no_subs.mp4"):
                v.unlink()
            print("[post_social] ✓ Removed intermediate videos", file=sys.stderr)
    except: pass


def main(args: argparse.Namespace) -> None:
    tts_path = BASE_DIR / "output" / "tts_data.json"

    if args.test or not os.path.exists(tts_path):
        print("[post_social] DRY RUN — No actual posting", file=sys.stderr)
        print(json.dumps({"status": "dry_run", "message": "Would post video here"}))
        return

    with open(tts_path, "r", encoding="utf-8") as f:
        tts_data = json.load(f)

    video_path = tts_data.get("final_video_path") or tts_data.get("video_path_with_subs")
    thumbnail_path = tts_data.get("thumbnail_path")
    
    if not video_path or not os.path.exists(video_path):
        print(f"[post_social] Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    script   = tts_data.get("script", {})
    category = tts_data.get("news", {}).get("category", "world")
    caption  = build_caption(script, category)

    results = {}
    
    # Parse requested platforms
    target_platforms = []
    if args.platforms:
        target_platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
    
    should_post = lambda p: not target_platforms or p.lower() in target_platforms

    if dry_run:
        print(f"[post_social] DRY RUN mode — video: {video_path}", file=sys.stderr)
        print(f"[post_social] Caption preview:\n{caption[:200]}", file=sys.stderr)
        results = {"dry_run": True, "video_path": video_path, "thumbnail": thumbnail_path, "caption": caption}
    else:
        meta_token     = os.getenv("META_ACCESS_TOKEN")
        ig_account     = os.getenv("INSTAGRAM_ACCOUNT_ID")
        fb_page        = os.getenv("FACEBOOK_PAGE_ID")
        tiktok_token   = os.getenv("TIKTOK_ACCESS_TOKEN")
        yt_client_id   = os.getenv("YOUTUBE_CLIENT_ID")
        yt_client_sec  = os.getenv("YOUTUBE_CLIENT_SECRET")
        yt_refresh     = os.getenv("YOUTUBE_REFRESH_TOKEN")

        if meta_token and ig_account and should_post("instagram"):
            r = post_instagram_reel(video_path, caption, ig_account, meta_token)
            results["instagram"] = r
            print(f"[post_social] Instagram: {r}", file=sys.stderr)

        if meta_token and fb_page:
            r = post_facebook_reel(video_path, caption, fb_page, meta_token)
            results["facebook"] = r
            print(f"[post_social] Facebook: {r}", file=sys.stderr)

        tiktok_token   = os.getenv("TIKTOK_ACCESS_TOKEN")
        tiktok_json    = BASE_DIR / "token_tiktok.json"
        if tiktok_json.exists():
            try:
                with open(tiktok_json, "r") as tf:
                    tk_data = json.load(tf)
                    tiktok_token = tk_data.get("access_token") or tiktok_token
            except: pass

        if tiktok_token and should_post("tiktok"):
            r = post_tiktok(video_path, caption, tiktok_token)
            results["tiktok"] = r
            print(f"[post_social] TikTok: {r}", file=sys.stderr)

        # YouTube Posting with Multi-Channel support
        lang = tts_data.get("language", "fr")
        token_path = BASE_DIR / "config" / f"token_{lang}.json"
        
        if token_path.exists() and should_post("youtube"):
             print(f"[post_social] Using specific token for language {lang}: {token_path.name}", file=sys.stderr)
             try:
                 from google.oauth2.credentials import Credentials
                 from google.auth.transport.requests import Request
                 creds = Credentials.from_authorized_user_file(str(token_path))
                 if not creds.valid and creds.refresh_token:
                     creds.refresh(Request())
                 
                 yt_title = script.get("title", "News Short")
                 yt_tags  = script.get("hashtags", ["#news", "#shorts"])
                 
                 publish_at = getattr(args, "publish_at", None)
                 
                 # On réutilise post_youtube_shorts mais avec les creds du JSON
                 r = post_youtube_shorts(video_path, yt_title, caption, yt_tags,
                                         creds.client_id, creds.client_secret, creds.refresh_token,
                                         thumbnail_path=thumbnail_path, publish_at=publish_at)
                 results["youtube"] = r
                 print(f"[post_social] YouTube ({lang}): {r}", file=sys.stderr)
             except Exception as ye:
                 print(f"[post_social] YouTube Token Error ({lang}): {ye}", file=sys.stderr)
                 results["youtube"] = {"error": str(ye)}
        elif yt_client_id and yt_client_sec and yt_refresh and should_post("youtube"):
            yt_title = script.get("title", "News Short")
            yt_tags  = script.get("hashtags", ["#news", "#shorts"])
            publish_at = getattr(args, "publish_at", None)
            r = post_youtube_shorts(video_path, yt_title, caption, yt_tags,
                                    yt_client_id, yt_client_sec, yt_refresh,
                                    thumbnail_path=thumbnail_path, publish_at=publish_at)
            results["youtube"] = r
            print(f"[post_social] YouTube (Default): {r}", file=sys.stderr)

    # Sauvegarde du rapport de posting
    report_path = BASE_DIR / "output" / f"posting_report_{date.today()}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[post_social] Report saved: {report_path}", file=sys.stderr)
    
    # OPTIMIZATION: Nettoyage disque après succès (CloudNode Storage)
    if not dry_run:
        cleanup_output()
        
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post video to social networks")
    parser.add_argument("--test", action="store_true", help="Dry run, no actual posting")
    parser.add_argument("--platforms", default="", help="Comma-separated list of platforms to post to")
    parser.add_argument("--publish-at", default=None, help="ISO 8601 timestamp for scheduled publish")
    main(parser.parse_args())
