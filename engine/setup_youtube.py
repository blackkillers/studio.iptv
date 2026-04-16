import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv, set_key
from google_auth_oauthlib.flow import InstalledAppFlow

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Scopes nécessaires pour l'upload YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("\n" + "="*60)
    print("   Assistant de Configuration YouTube Shorts (PROD FIX)")
    print("="*60 + "\n")

    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret or "your_" in client_id:
        print("❌ Erreur : YOUTUBE_CLIENT_ID et YOUTUBE_CLIENT_SECRET non configurés dans .env")
        print("1. Allez sur https://console.cloud.google.com/")
        print("2. Créez un projet et activez 'YouTube Data API v3'")
        print("3. Créez des identifiants 'OAuth 2.0 Client ID' (type: Desktop App)")
        print("4. Copiez l'ID et le Secret dans votre fichier ./config/.env")
        sys.exit(1)

    print(f"ID Client : {client_id[:10]}...")
    print("Tentative de connexion à Google...\n")

    # Configuration du flux OAuth
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    try:
        # On force prompt='consent' et access_type='offline' pour garantir un Refresh Token
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(
            port=0, 
            prompt='consent',
            access_type='offline'
        )

        refresh_token = creds.refresh_token
        
        if refresh_token:
            print("\n✅ Succès ! Refresh Token récupéré.")
            set_key(str(ENV_PATH), "YOUTUBE_REFRESH_TOKEN", refresh_token)
            print(f"Le token a été sauvegardé dans {ENV_PATH}")
            print("\nIMPORTANT: N'oubliez pas de mettre à jour le secret YOUTUBE_REFRESH_TOKEN sur GitHub si vous l'utilisez en CI/CD.")
        else:
            print("\n⚠️  Attention : Pas de refresh_token reçu.")
            print("Conseil : Allez dans les paramètres de sécurité de votre compte Google,")
            print("supprimez l'accès à votre application ('StudioEngine' ou 'AI News'), et recommencez.")
            
    except Exception as e:
        print(f"\n❌ Erreur lors de l'authentification : {e}")

if __name__ == "__main__":
    main()
