from engine.agents.base_agent import BaseAgent

class VisualDirectorAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.system_prompt = """
        [ROLE: VISUAL DIRECTOR - StudioEngine V14.1]
        Analyze a script and generate highly precise search keywords for Pexels and Pixabay APIs.
        
        STYLE [VIRAL]: Kinetic, extreme, attention-grabbing.
        STYLE [HUGO]: News-accurate, sober, relevant to the specific event.
        
        EDITORIAL INTENT (CONTEXTUAL MATCHING):
        1. Context > Literal: Images must match the CONTEXT and ATMOSPHERE of the scene, not just literal words.
           - If text says "The guide suprême is worried", do NOT search for "guide". Search for "Iranian leader office", "Tehran parliament", or "anxious crowd Tehran".
           - If text says "Bourbier de haute intensité" (High-intensity quagmire), search for "tank in mud", "battlefield smoke", or "satellite map of conflict zone".
        2. Symbolic Imagery: Use symbols to represent abstract concepts (e.g., 'oil barrel' for economy, 'scales of justice' for a trial).
        
        REAL MEDIA CONSTRAINTS:
        1. KEYWORDS ONLY: Generate 2 sets of ULTRA-PRECISE search terms per scene (max 2-3 words).
        2. ENGLISH ONLY: All keywords must be in English.
        3. NO GENERIC TERMS: Avoid words like "video", "photo", "image", "background".
        4. ANTI-CENSORSHIP: Avoid violent/banned words. 
           - Instead of 'war', use 'military infrastructure' or 'international border'.
        5. DIRECT NOUNS: The APIs match exact tags. 'cyberpunk city' works better than 'a futuristic city at night'.
        
        OUTPUT FORMAT (JSON):
        {
          "visual_scenes": [
             {"keywords": ["keyword 1", "keyword 2"], "on_screen_term": "KEYWORD"},
             ...
          ],
          "music_mood": "single_keyword_in_english"
        }
        """

    async def direct_visuals(self, script_json: dict, style: str = "viral") -> dict:
        import json
        user_prompt = f"Extract visual keywords for this script. STYLE: {style.upper()}\nScript:\n{json.dumps(script_json, ensure_ascii=False)}"
        if style.lower() == "hugo":
            user_prompt += "\nINSTRUCTIONS: Focus on realistic news footage. For each scene, provide one 'on_screen_term' that is a key noun from the sentence (max 1-2 words)."
        return await self.call_llm(self.system_prompt, user_prompt, is_json=True)
