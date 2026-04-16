import logging
from engine.agents.base_agent import BaseAgent

logger = logging.getLogger("LEVIATHAN.Localizer")

class LocalizerAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.system_prompt = """
        [ROLE: CONTEXTUAL LOCALIZER - LE PRÉSENTATEUR V12.0 - PROMPT MAÎTRE V9.5]
        You translate viral scripts from English to a target language (FR or RU).
        
        STRICT RULES:
        1. MINIMUM LENGTH: Every translated scene MUST contain at least 4 words.
        2. NO EXTRA CONTENT: Translate only the provided text.
        3. RHYTHM PRESERVATION: Keep the exact placement of '...' and '—'.
        4. HUMAN SYNTAX: Maximum 2 conjunctions (like 'Et', 'Mais', 'Donc') in the ENTIRE script.
        5. TONE: Rapid, punchy, human. No robotic literal translation.
        6. NO SUMMARIZATION: Every single scene from the source MUST be translated. Do NOT merge scenes. Do NOT simplify the content. The word count of the translation must stay close to the source.
        7. CLICKBAIT RETENTION: Maintain the same level of "curiosity gap" and "UGC energy" in the Translated SEO TITLE.
        8. FINAL CTA: Ensure the last scene (the Call to Action) is translated to sound like a native influencer.
        
        OUTPUT FORMAT (JSON): Same structure as input (including seo_title and hashtags). Localize hashtags to be relevant for the target country.
        """

    async def localize(self, script_json: dict, target_lang: str) -> dict:
        import json
        user_prompt = f"Target Language: {target_lang}\nScript to Translate:\n{json.dumps(script_json, ensure_ascii=False)}"
        script = await self.call_llm(self.system_prompt, user_prompt, is_json=True)
        
        # Robustness V24.3: Handle None or List results
        if not script:
            logger.error(f"Localizer returned None for {target_lang}")
            return script_json
            
        if isinstance(script, list):
            logger.warning(f"Localizer returned a LIST instead of a DICT for {target_lang}. Searching for dict...")
            # Try to find a dict in the list (sometimes LLM returns [{...}])
            for item in script:
                if isinstance(item, dict):
                    script = item
                    break
            else:
                # If no dict found, fallback to original
                return script_json

        logger.info(f"SEO Title ({target_lang}): {script.get('seo_title', 'N/A')}")
        return script
