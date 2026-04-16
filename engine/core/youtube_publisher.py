import asyncio
import os
import logging
from pathlib import Path
from typing import Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("LEVIATHAN.YouTubePublisher")

class YouTubePublisher:
    def __init__(self, config: dict):
        self.config = config
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.scopes = [
            'https://www.googleapis.com/auth/youtube.upload',
            'https://www.googleapis.com/auth/youtube.force-ssl',
            'https://www.googleapis.com/auth/youtube.readonly'
        ]

    def get_credentials(self, lang: str):
        """Loads or refreshes credentials for a specific channel (FR, EN, RU)."""
        token_path = self.base_dir / "config" / f"token_{lang}.json"
        
        # 1. Tenter de charger depuis le fichier local
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)
            if creds and creds.expired and creds.refresh_token:
                logger.info(f"[{lang.upper()}] Refreshing YouTube token from file...")
                creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            return creds

        # 2. Fallback pour CloudNode (Variables d'environnement)
        lang_upper = lang.upper()
        # On cherche d'abord les IDs spécifiques à la langue, sinon les globaux
        client_id = os.getenv(f"YT_CLIENT_ID_{lang_upper}") or os.getenv("YT_CLIENT_ID")
        client_secret = os.getenv(f"YT_CLIENT_SECRET_{lang_upper}") or os.getenv("YT_CLIENT_SECRET")
        refresh_token = os.getenv(f"YT_REFRESH_TOKEN_{lang_upper}")

        if refresh_token and client_id and client_secret:
            logger.info(f"[{lang.upper()}] Constructing credentials from CloudNode ENV...")
            return Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=self.scopes
            )

        logger.error(f"[{lang.upper()}] YouTube token not found (no file and no ENV).")
        return None

    async def upload_video(self, video_path: str, title: str, description: str, lang: str) -> Optional[str]:
        """Uploads a video to YouTube and returns the short URL."""
        from utils.telegram_notifier import send_telegram_alert
        
        logger.info(f"[{lang.upper()}] Starting real YouTube upload: {video_path}")
        await send_telegram_alert(f"🚀 <b>[YOUTUBE {lang.upper()}]</b> Démarrage de l'upload...\n🎬 <i>{title}</i>")
        
        creds = self.get_credentials(lang)
        if not creds:
            await send_telegram_alert(f"❌ <b>[YOUTUBE {lang.upper()}]</b> Échec d'authentification (Token manquant).")
            return None

        try:
            youtube = build('youtube', 'v3', credentials=creds)
            
            body = {
                'snippet': {
                    'title': title[:100], # Max 100 chars
                    'description': description[:4000],
                    'tags': ['LePresentateur', 'AIVideo', lang.upper()],
                    'categoryId': '22' # People & Blogs
                },
                'status': {
                    'privacyStatus': 'public', # User requested public by default
                    'selfDeclaredMadeForKids': False
                }
            }

            media = MediaFileUpload(
                video_path,
                chunksize=-1,
                resumable=True
            )

            request = youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )

            response = None
            loop = asyncio.get_event_loop()
            while response is None:
                status, response = await loop.run_in_executor(None, request.next_chunk)
                if status:
                    logger.info(f"[{lang.upper()}] Upload Progress: {int(status.progress() * 100)}%")

            video_id = response.get('id')
            video_url = f"https://youtu.be/{video_id}"
            logger.info(f"[{lang.upper()}] Upload success! URL: {video_url}")
            
            # V26.0 : MISSION 1 - Automated First Comment
                # Note: API V3 doesn't support Pinning, but we post it as the first interaction
            try:
                await self.add_comment(video_id, title, lang)
            except Exception as comm_err:
                logger.warning(f"[{lang.upper()}] Comment Auto-Post failed: {comm_err}")
                
            await send_telegram_alert(f"✅ <b>[YOUTUBE {lang.upper()}]</b> Publication réussie !\n🔗 <a href='{video_url}'>{video_url}</a>")
            return video_url

        except Exception as e:
            logger.error(f"[{lang.upper()}] YouTube upload failed: {e}")
            await send_telegram_alert(f"🚨 <b>[YOUTUBE {lang.upper()}]</b> Erreur d'upload : <code>{str(e)}</code>")
            return None

    async def add_comment(self, video_id: str, video_title: str, lang: str):
        """V26.0 : Mission 1 - Poste un commentaire engageant via IA."""
        creds = self.get_credentials(lang)
        if not creds: return
        
        from engine.growth.growth_agent import GrowthAgent
        agent = GrowthAgent()
        comment_text = await agent.generate_growth_comment(video_title, lang)
        
        try:
            youtube = build('youtube', 'v3', credentials=creds)
            request = youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text
                            }
                        }
                    }
                }
            )
            request.execute()
            logger.info(f"[{lang.upper()}] Pinned Comment payload posted on {video_id}")
        except Exception as e:
            logger.error(f"[{lang.upper()}] Failed to post comment: {e}")

    async def delete_video(self, video_id_or_url: str, lang: str) -> bool:
        """Deletes a video from the YouTube channel."""
        video_id = video_id_or_url.split("/")[-1].split("=")[-1]
        
        creds = self.get_credentials(lang)
        if not creds: return False
        
        try:
            youtube = build('youtube', 'v3', credentials=creds)
            request = youtube.videos().delete(id=video_id)
            request.execute()
            logger.info(f"[{lang.upper()}] Video {video_id} deleted successfully.")
            return True
        except Exception as e:
            logger.error(f"[{lang.upper()}] Failed to delete video {video_id}: {e}")
            return False

    async def list_my_videos(self, lang: str, max_results: int = 5):
        """Lists the most recent videos from the channel."""
        creds = self.get_credentials(lang)
        if not creds: return []
        
        try:
            youtube = build('youtube', 'v3', credentials=creds)
            request = youtube.search().list(
                part="snippet",
                forMine=True,
                type="video",
                order="date",
                maxResults=max_results
            )
            response = request.execute()
            videos = []
            for item in response.get("items", []):
                videos.append({
                    "id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "description": item["snippet"]["description"]
                })
            return videos
        except Exception as e:
            logger.error(f"[{lang.upper()}] Failed to list videos: {e}")
            return []

    async def update_video_metadata(self, video_id: str, title: str, description: str, lang: str):
        """Updates the title and description of an existing video."""
        creds = self.get_credentials(lang)
        if not creds: return False
        
        try:
            youtube = build('youtube', 'v3', credentials=creds)
            
            # First get existing tags, etc.
            get_req = youtube.videos().list(part="snippet,status", id=video_id)
            get_resp = get_req.execute()
            if not get_resp.get("items"): return False
            
            video = get_resp["items"][0]
            snippet = video["snippet"]
            snippet["title"] = title[:100]
            snippet["description"] = description[:4000]
            
            update_req = youtube.videos().update(
                part="snippet",
                body={
                    "id": video_id,
                    "snippet": snippet
                }
            )
            update_req.execute()
            logger.info(f"[{lang.upper()}] Metadata updated for {video_id}")
            return True
        except Exception as e:
            logger.error(f"[{lang.upper()}] Failed to update metadata for {video_id}: {e}")
            return False
