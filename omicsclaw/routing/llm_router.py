"""LLM-based query routing for orchestrators."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

from omicsclaw.common.runtime_env import load_project_dotenv
from omicsclaw.core.provider_registry import resolve_provider

load_project_dotenv(Path(__file__).resolve().parent.parent.parent, override=False)

logger = logging.getLogger(__name__)


def _resolve_llm_config() -> Tuple[str, str, str]:
    """Resolve (api_key, base_url, model) for LLM routing calls.

    Returns:
        (api_key, base_url, model) tuple.
    """
    base_url, model, api_key = resolve_provider(
        provider=os.getenv("LLM_PROVIDER", ""),
        base_url=os.getenv("LLM_BASE_URL", ""),
        model=os.getenv("OMICSCLAW_MODEL") or os.getenv("LLM_MODEL", ""),
        api_key=os.getenv("LLM_API_KEY", ""),
    )
    return api_key, (base_url or "https://api.openai.com/v1"), (model or "gpt-5-mini")


def route_with_llm(query: str, skills: Dict[str, str], domain: str) -> Tuple[Optional[str], float]:
    """Route query using LLM API.

    Supports all providers configured in omicsclaw.core.provider_registry:
    deepseek, openai, anthropic, gemini, nvidia, siliconflow, openrouter,
    volcengine, dashscope, zhipu, ollama, custom

    Args:
        query: User's natural language query
        skills: Dict of {skill_name: description}
        domain: Omics domain (spatial, singlecell, etc.)

    Returns:
        (skill_name, confidence) tuple
    """
    api_key, base_url, model = _resolve_llm_config()
    if not api_key:
        logger.warning("No API key found for LLM routing. Check provider config or set LLM_API_KEY.")
        return None, 0.0

    # Build skill list for prompt
    skill_list = "\n".join([f"- {name}: {desc}" for name, desc in skills.items()])
    
    prompt = f"""You are an expert in {domain} omics analysis. Given a user query, select the MOST appropriate skill and provide a confidence score.

Available skills:
{skill_list}

User query: "{query}"

Respond with ONLY a JSON object in this exact format:
{{"skill": "skill-name", "confidence": 0.95}}

The confidence should be between 0.0 and 1.0, where:
- 1.0 = perfect match, no ambiguity
- 0.8-0.9 = strong match, clear intent
- 0.6-0.7 = reasonable match, some ambiguity
- 0.5 or below = weak match, uncertain"""
    
    try:
        import requests
        url = f"{base_url.rstrip('/')}/chat/completions"
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"API error {response.status_code}: {response.text}")
            return None, 0.0

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        try:
            parsed = json.loads(content)
            skill = parsed.get("skill", "").strip()
            confidence = float(parsed.get("confidence", 0.0))
        except (json.JSONDecodeError, ValueError, KeyError):
            # Fallback: treat as plain skill name
            skill = content
            confidence = 0.8

        # Validate skill exists
        if skill in skills:
            return skill, min(max(confidence, 0.0), 1.0)  # Clamp to [0, 1]
        else:
            logger.warning(f"LLM returned invalid skill: {skill}")
            return None, 0.0
    except Exception as e:
        logger.error(f"LLM routing failed: {e}")
        return None, 0.0
