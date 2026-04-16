import argparse
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

# Scopes pour FULL ACCESS (Gestion + Analytics)
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube.readonly'
]

def main():
    parser = argparse.ArgumentParser(description="Générateur de Token YouTube - Full Access")
    parser.add_argument("--lang", required=True, choices=["fr", "en", "ru"], help="Langue de la chaîne")
    args = parser.parse_args()

    # Définition des chemins
    base_dir = Path(__file__).resolve().parent.parent
    client_secret_path = base_dir / "config" / "client_secret.json"
    token_output_path = base_dir / "config" / f"token_{args.lang}.json"

    if not client_secret_path.exists():
        print(f"ERREUR : Fichier {client_secret_path} manquant !")
        return

    print(f"--- 🔑 AUTHENTIFICATION YouTube [{args.lang.upper()}] ---")
    print("Une fenêtre de navigateur va s'ouvrir. Connectez-vous au compte de la chaîne.")
    print("N'oubliez pas de TOUT cocher (Gérer vidéos, voir stats etc.).")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)

    # Sauvegarde du token JSON
    with open(token_output_path, "w") as token:
        token.write(creds.to_json())

    print(f"✅ SUCCÈS : Token sauvegardé dans {token_output_path}")
    print("Relancez l'empire StudioEngine pour activer le Full Access !")

if __name__ == "__main__":
    main()
