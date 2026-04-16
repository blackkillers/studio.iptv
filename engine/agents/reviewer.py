import logging
import json
from engine.agents.base_agent import BaseAgent

logger = logging.getLogger("LEVIATHAN.Reviewer")

class ReviewerAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.system_prompt = """
        [ROLE: CHIEF EDITOR - StudioEngine V20.5]
        Mission: Review the script and metadata for VIRALITY and DURATION.
        
        CRITERIA:
        1. DURATION: 
           - For SHORTS: Must be ~130-160 words. Too short (<115) or too long (>175) is REJECTED.
           - For LONG: Must be >800 words.
        2. TONE: 
           - [HUGO]: Must be neutral and fact-based. No excessive "!!!" or hype words.
           - [VIRAL]: Must be high-retention.
        3. METADATA: 
           - SEO Title must be in CAPS and include keywords.
           - Hashtags must be relevant.
        4. COHERENCE:
           - Proper scene transitions.
        
        OUTPUT FORMAT (JSON):
        {
          "decision": "APPROVED" or "REJECTED",
          "reason": "Detailed reason",
          "corrections": ["correction 1", ...]
        }
        """

    async def review_script(self, script: dict, is_long: bool = False, style: str = "hugo") -> dict:
        """Reviews a generated script."""
        word_count = sum(len(s.get("text", "").split()) for s in script.get("scenes", []))
        logger.info(f"Reviewing script: {word_count} words (is_long={is_long}, style={style})")
        
        user_prompt = f"""
        Review the following script for a {style} video.
        Type: {'Long-form' if is_long else 'Short-form'}.
        Word Count: {word_count}.
        
        SCRIPT:
        {json.dumps(script, indent=2, ensure_ascii=False)}
        """
        
        review = await self.call_llm(self.system_prompt, user_prompt, is_json=True)
        return review
