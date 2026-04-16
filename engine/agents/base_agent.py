import os
import asyncio
import json
import logging
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from groq import AsyncGroq
from typing import Dict, Any

logger = logging.getLogger("LEVIATHAN.BaseAgent")

class BaseAgent:
    def __init__(self, model_name: str = "gemini-2.0-flash"):
        self.model_name = model_name
        self.gemini_keys = [
            os.getenv("GOOGLE_API_KEY"),
            os.getenv("GEMINI_API_KEY"),
            os.getenv("GEMINI_API_KEY_2")
        ]
        self.gemini_keys = [k for k in self.gemini_keys if k]
        self.current_gemini_key_idx = 0
        
        self.grok_api_key = os.getenv("GROK_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        
        self.openai_keys = [
            os.getenv("OPENAI_API_KEY"),
            os.getenv("OPENAI_API_KEY_2"),
            os.getenv("OPENAI_API_KEY_3")
        ]
        self.openai_keys = [k for k in self.openai_keys if k]
        
        self.grok_client = None
        if self.grok_api_key:
            self.grok_client = AsyncOpenAI(api_key=self.grok_api_key, base_url="https://api.x.ai/v1")
            
        self.groq_client = None
        if self.groq_api_key:
            self.groq_client = AsyncGroq(api_key=self.groq_api_key)
            
        self.openrouter_client = None
        if self.openrouter_api_key:
            self.openrouter_client = AsyncOpenAI(
                api_key=self.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://le-presentateur.ai", 
                    "X-Title": "Le Presentateur V20"
                }
            )
            
        # 5. Ollama (Ultimate Local Support V26.5)
        self.ollama_client = AsyncOpenAI(
            api_key="ollama", 
            base_url="http://localhost:11434/v1"
        )

    def _get_gemini_client(self):
        """Rotate Gemini keys for high availability."""
        if not self.gemini_keys: return None
        key = self.gemini_keys[self.current_gemini_key_idx]
        self.current_gemini_key_idx = (self.current_gemini_key_idx + 1) % len(self.gemini_keys)
        return genai.Client(api_key=key)

    async def call_llm(self, system_prompt: str, user_prompt: str, is_json: bool = False) -> Any:
        """Fallback-optimized multi-model LLM call."""
        
        # 1. OpenRouter OVERRIDE (V26.5 Surgical Fix) - Replacing google-genai
        if self.openrouter_client:
            try:
                # Direct route via OpenRouter to avoid Google 429
                response = await self.openrouter_client.chat.completions.create(
                    model="google/gemini-2.0-flash-001",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    response_format={"type": "json_object"} if is_json else None,
                    max_tokens=2000
                )
                logger.info("📡 [OVERRIDE] Appel LLM via OpenRouter réussi.")
                return self._parse_json(response.choices[0].message.content) if is_json else response.choices[0].message.content
            except Exception as e:
                logger.warning(f"OpenRouter Primary Override failure: {e}. Trying fallbacks...")

        # 2. OpenRouter (Multi-model Cloud)
        if self.openrouter_client:
            try:
                response = await self.openrouter_client.chat.completions.create(
                    model="google/gemini-2.0-flash-001",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    response_format={"type": "json_object"} if is_json else None,
                    max_tokens=800
                )
                return self._parse_json(response.choices[0].message.content) if is_json else response.choices[0].message.content
            except Exception as e: logger.warning(f"OpenRouter Fail: {e}")

        # 3. Groq (High Speed Fallback)
        if self.groq_client:
             try:
                response = await self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    response_format={"type": "json_object"} if is_json else None
                )
                return self._parse_json(response.choices[0].message.content) if is_json else response.choices[0].message.content
             except Exception as e:
                logger.error(f"Groq Fail: {e}")
                
        # 4. Deep Fallback OpenRouter (FREE MODEL V26.1)
        if self.openrouter_client:
            try:
                response = await self.openrouter_client.chat.completions.create(
                    model="google/gemma-2-9b-it:free",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                )
                return self._parse_json(response.choices[0].message.content) if is_json else response.choices[0].message.content
            except: pass
            
        # 5. Ollama Local (Ultimate Resilience)
        try:
            response = await self.ollama_client.chat.completions.create(
                model="llama3", # Modèle par défaut recommandé
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                max_tokens=800
            )
            logger.info("🛡️ Ollama Local utilisé avec succès.")
            return self._parse_json(response.choices[0].message.content) if is_json else response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Ollama Local unavailable: {e}")
                
        return None

    def _parse_json(self, text: str) -> Any:
        try:
             try:
                data = json.loads(text)
             except:
                clean_text = text.replace("```json", "").replace("```", "").strip()
                start = clean_text.find("{") if clean_text.find("{") != -1 else clean_text.find("[")
                end = max(clean_text.rfind("}"), clean_text.rfind("]"))
                if start != -1 and end != -1: data = json.loads(clean_text[start:end+1])
                else: raise ValueError("No JSON")
             return data
        except Exception as e:
            logger.error(f"Failed to parse LLM JSON: {e}")
            return None
