import os
import sys
import json
import requests
import webbrowser
import time
import hashlib
import base64
import secrets
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Configuration TikTok
REDIRECT_URI = "https://www.google.com/"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "user.info.basic,video.upload,video.publish"

def generate_pkce():
    code_verifier = secrets.token_urlsafe(64)
    sha256 = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').replace('=', '')
    return code_verifier, code_challenge

def main():
    print("\n" + "="*60)
    print("   Assistant de Configuration TikTok (Mode Manuel)")
    print("="*60 + "\n")

    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")

    if not client_key or not client_secret or "your_" in client_key:
        print("❌ Erreur : TIKTOK_CLIENT_KEY et TIKTOK_CLIENT_SECRET manquants dans .env")
        print("Vérifiez votre fichier C:\\StudioAutomation\\.env")
        sys.exit(1)

    # 1. Générer PKCE et ouvrir le navigateur
    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    
    url = (f"{AUTH_URL}?client_key={client_key}&scope={SCOPES}"
           f"&response_type=code&redirect_uri={REDIRECT_URI}&state={state}"
           f"&code_challenge={code_challenge}&code_challenge_method=S256")
    
    print("Étape 1 : Modification de la Redirect URI sur TikTok")
    print("-" * 45)
    print(f"👉 Allez dans Login Kit sur le portail TikTok.")
    print(f"👉 Supprimez le localhost et ajoutez : {REDIRECT_URI}")
    print("👉 IMPORTANT : Cliquez sur 'Add' puis sur le bouton rouge 'Apply changes'.\n")
    
    input("Appuyez sur Entrée quand c'est fait pour ouvrir la page d'autorisation...")
    
    print("\nÉtape 2 : Autorisation")
    print("-" * 45)
    webbrowser.open(url)
    
    print("\nUne fois que vous avez cliqué sur 'Autoriser', la page va charger Google.")
    print("COPIEZ l'adresse complète (URL) qui s'affiche dans votre navigateur.")
    
    full_url = input("\nCollez l'URL ici : ").strip()
    
    if not full_url:
        print("❌ Aucune URL fournie.")
        return

    # Extraire le code de l'URL
    try:
        query = urlparse(full_url).query
        params = parse_qs(query)
        auth_code = params.get('code', [None])[0]
    except Exception:
        auth_code = None
        
    if not auth_code:
        print("❌ Code introuvable. Avez-vous bien copié toute l'URL ?")
        return

    print(f"\nÉtape 3 : Échange du code contre les jetons...")

    # 3. Échange
    resp = requests.post(TOKEN_URL, data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": auth_code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    data = resp.json()
    
    if "access_token" in data:
        access_token = data["access_token"]
        refresh_token = data.get("refresh_token")
        
        print("\n✅ SUCCÈS ! Les tokens ont été récupérés.")
        set_key(str(ENV_PATH), "TIKTOK_ACCESS_TOKEN", access_token)
        if refresh_token:
            set_key(str(ENV_PATH), "TIKTOK_REFRESH_TOKEN", refresh_token)
            print(f"Sauvegardé dans {ENV_PATH}")
        
        print("\n" + "="*60)
        print("🚀 ACTION FINALE :")
        print("Copiez la valeur ci-dessous dans votre Secret GitHub TIKTOK_ACCESS_TOKEN :")
        print("-" * 60)
        print(f"\n{access_token}\n")
        print("="*60)
    else:
        print(f"\n❌ Erreur TikTok : {data.get('error_description', data.get('message', 'Inconnue'))}")
        print(f"Détails : {data}")

if __name__ == "__main__":
    main()
