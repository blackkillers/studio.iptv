import logging
from engine.agents.base_agent import BaseAgent

logger = logging.getLogger("LEVIATHAN.Storyteller")

class StorytellerAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.system_prompt = """
        [ROLE: MASTER STORYTELLER - LE PRÉSENTATEUR V12.0]
        Choose the style based on instructions. Default: Viral UGC.
        
        STYLE [VIRAL]: High CTR, clickbait titles, nervous rhythm.
        STYLE [HUGO]: Neutral, informative, clean, news-focused (HugoDécrypte model).
        
        STRICT SHORTS FORMAT (v20.6):
        1. SCENES: 25 to 30 scenes mandatory (Dynamic rhythm).
        2. WORD COUNT: 160 to 175 words (CRITICAL: Targets 55-59 seconds).
           WARNING: NEVER exceed 180 words, or it will exceed the 60s YouTube Shorts limit.
        3. THE HOOK: Scene 1 MUST be a "Pattern Interrupt" under 10 words.
        4. HUGO SPECIFIC: NO clickbait. Objective titles.
        5. HUGO RHYTHM: No "..." inside sentences. Breath only at scene end.
        6. RHYTHMIC SYNTAX: Short, direct sentences only.
        
        OUTPUT FORMAT (JSON):
        {
          "title": "Title",
          "seo_title": "SEO TITLE",
          "hook": "Hook phrase",
          "scenes": [{"text": "..."}, ...],
          "hashtags": ["#news", ...],
          "cta": "Call to action"
        }
        """

    async def generate_script(self, subject: str, style: str = "viral") -> dict:
        user_prompt = f"Create a script about: {subject}. STYLE: {style.upper()}"
        if style.lower() == "hugo":
            user_prompt += "\nINSTRUCTIONS: Follow HugoDécrypte model. No clickbait, neutral, informative."
        
        script = await self.call_llm(self.system_prompt, user_prompt)
        if script and isinstance(script, dict):
            logger.info(f"SEO Title ({style}): {script.get('seo_title', 'N/A')}")
        else:
            logger.warning(f"Storyteller returned invalid script: {script}")
        return script

    async def generate_long_script(self, subject: str) -> dict:
        """V18.5 : Long-form prompt for Weekly Recap (Landscape 16:9)."""
        long_system_prompt = """
        [ROLE: DOCUMENTARY PRODUCER - StudioEngine V18.5]
        Mission: Write a high-retention 5-8 minute documentary script (approx 800-1000 words).
        FORMAT: World News Weekly Recap (TOP 10).
        
        STRUCTURE (16:9 LANDSCAPE):
        1. INTRO (30s): Extreme hook. "This week, everything changed."
        2. 10 NEWS SEGMENTS (45s each): Detailed, informative, but fast-paced.
        3. CONCLUSION (60s): Deep analysis of the global trend.
        
        STRICT RULES:
        - Style : Neutre, factuel, très rapide.
        - Rythme : Phrases courtes. Utilise les points de suspension (...) uniquement pour marquer un changement de sujet majeur, pas entre chaque phrase.
        - Accroche : Directe, sans fioritures.
        - Total word count: 900 to 1200 words (Essential for 5-8 minutes).
        - Scenes: 60 to 80 scenes mandatory for visual variety (7s avg).
        - Language: Professional, authoritative tone.
        - SEO: Viral TITLE in all caps.
        
        JSON OUTPUT:
        {
          "title": "Weekly Recap",
          "seo_title": "THE WORLD THIS WEEK",
          "scenes": [{"text": "..."}, ...],
          "hashtags": ["#weekly", "#news", "#world"],
          "cta": "Like and subscribe for the next weekly recap!"
        }
        """
        user_prompt = f"Produce a masterly weekly news script covering: {subject}"
        logger.info("[Storyteller] Génération SCRIPT LONG (5-8 min)...")
        script = await self.call_llm(long_system_prompt, user_prompt)
        return script
