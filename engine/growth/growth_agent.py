from engine.agents.base_agent import BaseAgent
import logging

logger = logging.getLogger("LEVIATHAN.GrowthAgent")

class GrowthAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.system_prompt = """
        [ROLE: GROWTH & MONETIZATION MASTER - LE PR\xC9SENTATEUR V26.0]
        Your goal is to generate a highly engaging, provocative, or value-adding first comment for a YouTube video.
        The comment MUST include a Call to Action (CTA) for an affiliate link.

        RULES:
        1. PERSUASIVE & ENGAGING: Use hook techniques (questions, bold statements).
        2. AFFILIATE PLACEHOLDER: Always include the exact text "[LIEN_AFFILIATION]" in a natural context.
        3. MULTILINGUAL: Output ONLY the comment in the requested language.
        4. NO HASHTAGS: The video already has them.
        5. CONTEXTUAL: Mention a specific detail or theme related to the title.
        """

    async def generate_growth_comment(self, video_title: str, lang: str) -> str:
        """G\xE9n\xE8re le commentaire de mon\xE9tisation auto."""
        user_prompt = f"G\xE9n\xE8re un premier commentaire fix\xE9 pour la vid\xE9o : '{video_title}'. Langue: {lang.upper()}."
        try:
            comment = await self.call_llm(self.system_prompt, user_prompt, is_json=False)
            if not comment:
                return f"Que penses-tu de ce sujet ? Partage ton avis ! \u1F4AC\n\u27A1\uFE0F D\xE9couvre notre recommandation : [LIEN_AFFILIATION]"
            return comment.strip().strip('"')
        except Exception as e:
            logger.error(f"Growth Comment generation failed: {e}")
            return f"Partage ton avis en commentaire ! \u1F4AC\n\u27A1\uFE0F Plus d'infos ici : [LIEN_AFFILIATION]"
气
