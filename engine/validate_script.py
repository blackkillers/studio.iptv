#!/usr/bin/env python3
"""
validate_script.py — "Neural Guard" V1.0
Vérifie le script vidéo avant synthèse pour éviter les doublons et erreurs.
"""

import sys
import json
import argparse
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def calculate_overlap(s1, s2):
    """Calcul simple de l'overlap de mots entre deux chaînes."""
    words1 = set(re.findall(r'\w+', s1.lower()))
    words2 = set(re.findall(r'\w+', s2.lower()))
    if not words1 or not words2: return 0
    common = words1.intersection(words2)
    return len(common) / min(len(words1), len(words2))

def validate_script(script_path):
    print(f"[Neural Guard] 👀 Analyse du script: {script_path}", file=sys.stderr)
    
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    script = data.get("script", {})
    hook = script.get("hook", "").strip()
    scenes = script.get("scenes", [])
    cta = script.get("cta", "").strip()

    errors = []
    warnings = []

    # 1. Vérification structurelle
    if not hook: errors.append("Accroche (hook) manquante.")
    if not scenes or len(scenes) < 3: errors.append(f"Nombre de scènes insuffisant ({len(scenes)}).")
    if not cta: errors.append("CTA manquant.")

    # 2. Détection de doublons (Hook vs Scène 1)
    if hook and scenes:
        first_scene = scenes[0].get("text", "")
        overlap = calculate_overlap(hook, first_scene)
        if overlap > 0.8:
            warnings.append(f"⚠️ RISQUE DE DOUBLON : Hook et Scène 1 sont identiques à {overlap*100:.0f}%.")
            # Note: La déduplication auto dans generate_tts.py gérera ça, mais on prévient.

    # 3. Vérification des répétitions internes entre scènes
    for i in range(len(scenes)-1):
        s_curr = scenes[i].get("text", "")
        s_next = scenes[i+1].get("text", "")
        overlap = calculate_overlap(s_curr, s_next)
        if overlap > 0.7:
            errors.append(f"RÉPÉTITION DÉTECTÉE entre Scène {i+1} et Scène {i+2} ({overlap*100:.0f}% similarity).")

    # 4. Vérification de la longueur (Anti-Hallucination)
    total_chars = len(hook) + sum(len(s.get("text", "")) for s in scenes) + len(cta)
    if total_chars < 150:
        errors.append(f"Script anormalement court ({total_chars} chars).")
    if total_chars > 3000:
        warnings.append(f"Script très long ({total_chars} chars), attention au rendu.")

    # Rapport final
    if warnings:
        for w in warnings: print(f"[Neural Guard] {w}", file=sys.stderr)
    
    if errors:
        print("[Neural Guard] ❌ ERREURS CRITIQUES DÉTECTÉES :", file=sys.stderr)
        for e in errors: print(f"  - {e}", file=sys.stderr)
        return False

    print("[Neural Guard] ✅ Script validé avec succès.", file=sys.stderr)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(BASE_DIR / "output" / "script_data.json"))
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"[Neural Guard] Fichier non trouvé : {args.input}", file=sys.stderr)
        sys.exit(1)
        
    success = validate_script(args.input)
    if not success:
        sys.exit(1)
    sys.exit(0)
