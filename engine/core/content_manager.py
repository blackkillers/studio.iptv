import logging
import asyncio
from typing import Dict, Any
from engine.agents.storyteller import StorytellerAgent
from engine.agents.ensemble_storyteller import EnsembleStorytellerAgent
from engine.agents.localizer import LocalizerAgent
from engine.agents.visual_director import VisualDirectorAgent
from engine.agents.reviewer import ReviewerAgent

logger = logging.getLogger("LEVIATHAN.ContentManager")

class ContentManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.storyteller = StorytellerAgent()
        self.ensemble_storyteller = EnsembleStorytellerAgent()
        self.localizer = LocalizerAgent()
        self.visual_director = VisualDirectorAgent()
        self.reviewer = ReviewerAgent()
        self.extra_instr = ""

    async def generate_workflow(self, subject: str, target_lang: str, style: str = "viral") -> dict:
        """
        Gère la chaîne agentique : Storyteller (EN) -> Localizer -> Visual Director.
        Inclut une validation de qualité avec Retry (V12.1).
        """
        # V18.5 : Check if long-form is requested from config
        rendering_conf = self.config.get("rendering", {})
        is_long = rendering_conf.get("resolution") == [1920, 1080]
        mode_str = "LONG-FORM (5-8 min)" if is_long else "SHORT (60s)"
        logger.info(f"Démarrage du workflow {mode_str} pour '{subject}' (Lang: {target_lang})")

        MAX_RETRIES = 3
        final_script = None

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"Tentative de génération {attempt}/{MAX_RETRIES}...")
            
            # 1. Storytelling (EN)
            try:
                if is_long:
                     # V24.4 : Pass extra instructions separately to avoid narrating them
                     en_script = await self.storyteller.generate_long_script(subject + " " + self.extra_instr)
                else:
                     # V20 : Ensemble Mode (2 OpenRouter models + Gemini picker)
                     en_script = await self.ensemble_storyteller.generate_ensemble_script(subject + " " + self.extra_instr, style=style)
            except Exception as e:
                logger.error(f"Storyteller Crash: {e}")
                en_script = None
            
            if not en_script:
                logger.warning(f"Tentative {attempt} : Storyteller a échoué.")
                continue
            
            # 2. Localization
            try:
                if target_lang.lower() != "en":
                    current_script = await self.localizer.localize(en_script, target_lang)
                else:
                    current_script = en_script
            except Exception as e:
                logger.error(f"Localizer Crash: {e}")
                current_script = None
            
            if not current_script:
                logger.warning(f"Tentative {attempt} : Localizer a échoué.")
                continue

            # 3. Validation HARD de la durée (V20.5)
            word_count = sum(len(s.get("text", "").split()) for s in current_script.get("scenes", []))
            min_words = 800 if is_long else 120
            
            if word_count < min_words:
                logger.warning(f"🚫 TROP COURT (Tentative {attempt}) : {word_count} mots < {min_words}. Regénération...")
                self.extra_instr = f" (IMPORTANT : Fais un script de {min_words}+ mots, c'est impératif !)"
                continue

            # 4. Validation et Revue de Qualité (V20.5)
            review = await self.reviewer.review_script(current_script, is_long=is_long, style=style)
            
            if review.get("decision") == "APPROVED":
                final_script = current_script
                logger.info(f"✅ APPROVED : Qualit\xE9 du script valid\xE9e par ReviewerAgent ({review.get('reason')}).")
                break
            else:
                logger.warning(f"🚫 REJECTED (Tentative {attempt}) : {review.get('reason')}. Reg\xE9n\xE9ration...")
                # On peut optionnellement injecter les corrections au prochain tour
                continue

        # V18.6 : Blackout Protection (Total Fail-Safe)
        if not final_script:
            logger.critical("🚨 TOTAL LLM BLACKOUT : Utilisation du Template de Secours V18.6.")
            final_script = {
                "title": f"Mise \xE0 jour : {subject}",
                "seo_title": f"URGENT: {subject.upper()}",
                "scenes": [
                    {"text": f"Voici les derni\xE8res informations concernant {subject}."},
                    {"text": "La situation \xE9volue rapidement \xE0 l'\xE9chelle internationale."},
                    {"text": "Nos \xE9quipes suivent de pr\xE8s les r\xE9percussions mondiales."},
                    {"text": "Les analystes s'accordent sur l'importance de cet \xE9v\xE9nement."},
                    {"text": "Nous analysons actuellement les cons\xE9quences \xE0 long terme."},
                    {"text": "Restez connect\xE9 pour plus de d\xE9tails dans les prochaines heures."},
                    {"text": "La g\xE9opolitique mondiale est en pleine mutation aujourd'hui."},
                    {"text": "Chaque d\xE9tail compte dans cette affaire complexe et tendue."},
                    {"text": "Nous restons mobilis\xE9s pour vous informer en temps r\xE9el."},
                    {"text": "Les march\xE9s r\xE9agissent d\xE9j\xE0 aux annonces r\xE9centes du jour."},
                    {"text": "La stabilit\xE9 r\xE9gionale pourrait \xEAtre impact\xE9e par ce dossier."},
                    {"text": "Suivez le flux d'informations continu pour ne rien rater."},
                    {"text": "Le Pr\xE9sentateur d\xE9crypte pour vous les enjeux cach\xE9s du pouvoir."},
                    {"text": "L'information ne s'arr\xEAte jamais, et nous non plus."},
                    {"text": "Partagez cette mise \xE0 jour avec vos proches d\xE8s maintenant."},
                    {"text": "Votre soutien nous permet de continuer ce travail d'analyse."},
                    {"text": "Nous arrivons bient\xF4t au terme de ce r\xE9sum\xE9 express."},
                    {"text": "N'oubliez pas d'activer la cloche pour les notifications."},
                    {"text": "Merci de nous avoir suivis sur Le Pr\xE9sentateur."},
                    {"text": "Nous serons de retour d\xE8s qu'un nouveau d\xE9veloppement survient."},
                    {"text": "Le monde change, gardez une longueur d'avance avec nous."},
                    {"text": "Dites-nous ce que vous en pensez dans l'espace commentaires."},
                    {"text": "Votre avis est pr\xE9cieux pour notre communaut\xE9 d'info."},
                    {"text": "C'est la fin de ce point presse international sp\xE9cial."},
                    {"text": "Continuez de vous informer sur les sources officielles."},
                    {"text": "La r\xE9alit\xE9 d\xE9passe souvent la fiction dans ces dossiers."},
                    {"text": "Prenez soin de vous et restez \xE0 l'aff\xFBt du prochain Short."},
                    {"text": "Abonnez-vous pour la suite de nos d\xE9cryptages exclusifs."}
                ],
                "hashtags": ["#news", "#global", "#studioengine"],
                "cta": "Abonnez-vous pour la suite."
            }

        # 4. AGENT 3 : Visual Direction
        logger.info(f"Agent Visual Director ({style}) : Extraction des mots-clés...")
        visuals = await self.visual_director.direct_visuals(final_script, style=style)
        
        if not visuals:
             logger.warning("Échec Visual Director : Utilisation de mots-clés par défaut.")
             visuals = {"visual_scenes": [], "music_mood": "documentary"}
             
        for i, scene in enumerate(final_script.get("scenes", [])):
            v_scenes = visuals.get("visual_scenes", [])
            if i < len(v_scenes):
                scene["search_keywords"] = v_scenes[i].get("keywords", [])
                scene["on_screen_term"] = v_scenes[i].get("on_screen_term", "")
            else:
                scene["search_keywords"] = ["news", "abstract"]
                scene["on_screen_term"] = ""

        return final_script

    def _validate_script(self, script: dict) -> bool:
        """Vérifie si le script est exploitable (V12.1)."""
        if not script or "scenes" not in script:
            return False
        if len(script["scenes"]) < 3:
            return False
        return True
