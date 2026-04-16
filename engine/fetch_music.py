import os
import sys
import requests
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
MUSIC_DIR = BASE_DIR / "assets" / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# Royalty-free music URLs (Direct MP3 links)
# Using some reliable high-quality free sources
MUSIC_MAP = {
    "epic.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "tech.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "cyber.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "default.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3"
}

def fetch_music():
    print("[fetch_music] Checking background music assets...", file=sys.stderr)
    for filename, url in MUSIC_MAP.items():
        dest = MUSIC_DIR / filename
        if not dest.exists() or dest.stat().st_size < 1000:
            print(f"[fetch_music] Downloading {filename} from {url}...", file=sys.stderr)
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                if resp.status_code == 200:
                    with open(dest, "wb") as f:
                        f.write(resp.content)
                    print(f"[fetch_music] ✓ Saved {filename}", file=sys.stderr)
                else:
                    print(f"[fetch_music] ❌ Failed to download {filename} (Status {resp.status_code})", file=sys.stderr)
            except Exception as e:
                print(f"[fetch_music] ❌ Error downloading {filename}: {e}", file=sys.stderr)
        else:
            print(f"[fetch_music] - {filename} already exists.", file=sys.stderr)

if __name__ == "__main__":
    fetch_music()
