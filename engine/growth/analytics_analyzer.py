import yaml
import logging
from pathlib import Path
from engine.agents.base_agent import BaseAgent
from engine.core.youtube_publisher import YouTubePublisher

logger = logging.getLogger("LEVIATHAN.AnalyticsAnalyzer")

class AnalyticsAnalyzer:
    def __init__(self, config: dict):
        self.config = config
        self.rules_path = Path("config/dynamic_rules.yaml")
        
    async def analyze_performance(self, lang: str):
        """V26.0 : Mission 3 - Analyse les 10 derni\xE8res vid\xE9os et ajuste les r\xE8gles de Hook."""
        publisher = YouTubePublisher(self.config)
        videos = await publisher.list_my_videos(lang, max_results=10)
        
        if not videos:
            logger.warning(f"[{lang.upper()}] Aucune vid\xE9o trouv\xE9e pour l'analyse.")
            return
            
        # Simplification : On suppose que publisher.list_my_videos r\xE9cup\xE8re aussi les stats (Views)
        # Pour ce MVP, on va simuler l'analyse des titres vs engagement
        data_summary = "\n".join([f"- Titre: {v['title']} | Id: {v['id']}" for v in videos])
        
        agent = BaseAgent()
        system_prompt = """
        [ROLE: AUDIENCE GROWTH DATA SCIENTIST - StudioEngine]
        Analyze the provided video titles and generate 3 dynamic rules for 'Hooks' (initial 5 seconds) 
        to maximize engagement. Output ONLY a YAML-compatible structure.
        """
        
        user_prompt = f"Voici les donn\xE9es des 10 derni\xE8res vid\xE9os :\n{data_summary}\nG\xE9n\xE8re 3 nouvelles r\xE8gles de Hook bas\xE9es sur ces titres en format YAML."
        
        try:
            new_rules_yaml = await agent.call_llm(system_prompt, user_prompt, is_json=False)
            # Cleanup Markdown if LLM returned it
            new_rules_yaml = new_rules_yaml.replace("```yaml", "").replace("```", "").strip()
            
            # Save to config/dynamic_rules.yaml
            with open(self.rules_path, "w", encoding="utf-8") as f:
                f.write(new_rules_yaml)
            
            logger.info(f"[{lang.upper()}] R\xE8gles dynamiques mises \xE0 jour dans {self.rules_path}")
        except Exception as e:
            logger.error(f"Analytics Analysis iteration failed: {e}")

    def load_dynamic_rules(self) -> dict:
        """Charge les r\xE8gles pour injection dans le Storyteller."""
        if self.rules_path.exists():
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
气
