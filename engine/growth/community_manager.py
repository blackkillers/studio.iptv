# LE PR\xC9SENTATEUR V26.0 - COMMUNITY MANAGER (SEMI-AUTO)
import logging
import asyncio
from engine.agents.base_agent import BaseAgent
from utils.telegram_notifier import send_telegram_alert

logger = logging.getLogger("LEVIATHAN.CommunityManager")

class CommunityManager:
    def __init__(self, config: dict):
        self.config = config

    async def schedule_manual_poll(self, video_title: str, script_text: str, lang: str):
        """Mission 2 Pivot : G\xE9n\xE8re un sondage et l'envoie sur Telegram pour publication manuelle."""
        agent = BaseAgent()
        
        system_prompt = """
        [ROLE: COMMUNITY ENGAGEMENT EXPERT]
        Based on the video script, generate a YouTube Community Poll.
        FORMAT:
        1. Question: Provocative or interest-based (Max 65 chars).
        2. Options (3): Clear, distinct, engaging (Max 65 chars each).
        Language: Use the requested language.
        """
        
        user_prompt = f"Vid\xE9o: '{video_title}'. Script:\n{script_text[:1500]}\nG\xE9n\xE8re un sondage \xE0 3 choix."
        
        try:
            poll_text = await agent.call_llm(system_prompt, user_prompt, is_json=False)
            
            # Formatting for Telegram
            alert_msg = (
                f"\u1F4AC <b>[MISSION 2 - COMMUNITY POLL ({lang.upper()})]</b>\n"
                f"Contenu pr\xEAt pour ton onglet Communaut\xE9 YouTube\n\n"
                f"<code>{poll_text}</code>\n\n"
                f"<i>Publie-le pour optimiser le signal de l'algorithme !</i>"
            )
            
            await send_telegram_alert(alert_msg)
            logger.info(f"[{lang.upper()}] Poll suggestion sent to Telegram.")
            
        except Exception as e:
            logger.error(f"Poll generation failed: {e}")
气
