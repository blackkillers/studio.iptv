import logging
import json
import asyncio
from engine.agents.base_agent import BaseAgent
from typing import Dict, Any, List

logger = logging.getLogger("LEVIATHAN.EnsembleStoryteller")

class EnsembleStorytellerAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.system_prompt = """
        [ROLE: MASTER STORYTELLER - LE PRÉSENTATEUR ENSEMBLE V20]
        STYLE [HUGO]: Neutral, informative, clean, news-focused (HugoDécrypte model).
        
        STRICT SHORTS FORMAT (v24.8):
        1. SCENES: 15 to 20 scenes (Fast-paced).
        2. WORD COUNT: 140 to 160 words (STRICT: Target 58 seconds for optimal retention).
           WARNING: NEVER exceed 170 words in French, or it will exceed 60s.
        3. THE HOOK: Scene 1 MUST be a "Pattern Interrupt" under 10 words.
        4. HUGO SPECIFIC: NO clickbait. Objective titles.
        5. RHYTHMIC SYNTAX: Short, direct sentences only.
        
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

    async def call_specific_model(self, model: str, system_prompt: str, user_prompt: str) -> Any:
        """Appelle un modèle spécifique via OpenRouter."""
        if not self.openrouter_client:
            logger.error("OpenRouter client not configured.")
            return None
        
        try:
            logger.info(f"Calling specific model: {model}")
            response = await self.openrouter_client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"},
                max_tokens=800 # V24.9: Reduced to bypass OpenRouter 402/Credit limits
            )
            content = response.choices[0].message.content
            return self._parse_json(content)
        except Exception as e:
            logger.error(f"Error calling {model}: {e}")
            return None

    async def generate_ensemble_script(self, subject: str, style: str = "hugo") -> dict:
        """
        Génère 2 scripts via OpenRouter (Claude & Llama) puis laisse Gemini choisir le meilleur.
        V26.0 : Inclusion des règles de performance dynamiques.
        """
        # V26.0 : Chargement des règles de performance (Mission 3)
        from pathlib import Path
        import yaml
        rules_path = Path("config/dynamic_rules.yaml")
        current_system_prompt = self.system_prompt
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    rules = yaml.safe_load(f)
                if rules:
                    current_system_prompt += f"\n[DYNAMIC PERFORMANCE RULES - APPLY THESE FOR HOOKS]:\n{json.dumps(rules, indent=2, ensure_ascii=False)}"
                    logger.info("📈 [GROWTH] Règles dynamiques injectées dans le Storyteller.")
            except Exception as e:
                logger.warning(f"Failed to inject dynamic rules: {e}")

        logger.info(f"🚀 [ENSEMBLE] Démarrage pour : {subject}")
        
        # V26.5 : Using ultra-stable models (User has $10 balance)
        model_a = "anthropic/claude-3.5-haiku"
        model_b = "google/gemini-2.0-flash-001" # Reliable & Long
        
        user_prompt = f"Create a viral news script about: {subject}. STYLE: {style.upper()}."
        user_prompt += "\nIMPORTANT: Aim for 120-130 words. Do NOT be concise. Deliver a complete, detailed script."
        if style.lower() == "hugo":
            user_prompt += "\nINSTRUCTIONS: HugoDécrypte style (neutral, fact-based, fast-paced)."

        # 1. Génération simultanée
        logger.info(f"Generating scripts with {model_a} and {model_b}...")
        task_a = self.call_specific_model(model_a, current_system_prompt, user_prompt)
        task_b = self.call_specific_model(model_b, current_system_prompt, user_prompt)
        
        results = await asyncio.gather(task_a, task_b)
        script_a, script_b = results
        
        if not script_a and not script_b:
            logger.error("Both models failed. Fallback to default call (Gemini).")
            fallback_prompt = user_prompt + "\nSTRICT INSTRUCTION: Your script MUST contain at least 160 words and 25 individual scenes to reach the 59s duration target. This is mandatory."
            return await self.call_llm(self.system_prompt, fallback_prompt)
        
        if not script_a: return script_b
        if not script_b: return script_a

        # 2. Arbitrage par Gemini (Pick the best)
        logger.info("⚖️ [GEMINI ARBITRAGE] Sélection du meilleur script...")
        arbitrage_prompt = f"""
        You are a video production expert. Compare these two scripts for a {style} news video about '{subject}'.
        
        PICK THE ONE THAT BEST FOLLOWS THESE RULES:
        - LENGTH: Must be between 140 and 165 words (CRITICAL).
        - RHYTHM: Short sentences (max 12 words per scene).
        - CONTENT: Factual, neutral, punchy.
        
        If both are good, create a hybrid that takes the best parts of each while MAINTAINING THE LENGTH.
        STRICT: DO NOT summarize. DO NOT simplify. We need 145 words to fill 60 seconds of video.
        
        SCRIPT 1 (Claude):
        {json.dumps(script_a, indent=2, ensure_ascii=False)}
        
        SCRIPT 2 (Llama/Gemini):
        {json.dumps(script_b, indent=2, ensure_ascii=False)}
        
        OUTPUT ONLY THE FINAL SCRIPT IN JSON FORMAT.
        """
        
        try:
            final_script = await self.call_llm("You are an expert editor.", arbitrage_prompt, is_json=True)
            if final_script and isinstance(final_script, dict): return final_script
        except Exception as e:
            logger.warning(f"Arbitrage failed ({e}), returning first success.")
            
        return script_a if script_a else script_b
